from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any
from urllib.parse import urlencode

import feedparser
import requests

from content_radar.collectors.base import Collector
from content_radar.collectors.news import parse_published_at
from content_radar.config.settings import settings
from content_radar.config.sources import RedditSearch, load_source_config
from content_radar.models import Signal

logger = logging.getLogger(__name__)


# O Reddit devolve 429 para requisicoes anonimas em sequencia rapida.
REQUEST_INTERVAL_SECONDS = 3.0
MAX_RATE_LIMIT_WAIT_SECONDS = 30.0


class RedditRateLimitError(RuntimeError):
    def __init__(self, url: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(f"Reddit rate limit: {url}")
        self.retry_after_seconds = retry_after_seconds


class RedditCollector(Collector):
    """Top da semana de subreddits + buscas restritas a um subreddit. RSS primeiro, JSON como fallback."""

    name = "reddit"

    def __init__(
        self,
        subreddits: list[str] | None = None,
        searches: list[RedditSearch] | None = None,
        session: requests.Session | None = None,
        request_interval: float = REQUEST_INTERVAL_SECONDS,
    ) -> None:
        source_config = load_source_config()
        self._request_interval = request_interval
        self._subreddits = subreddits if subreddits is not None else source_config.reddit_subreddits
        self._searches = searches if searches is not None else source_config.reddit_searches
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "User-Agent": settings.reddit_user_agent,
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
            }
        )

    def collect(self) -> list[Signal]:
        targets: list[tuple[str, str, dict[str, str]]] = [
            (subreddit, f"r/{subreddit}/top", {"t": "week"}) for subreddit in self._subreddits
        ]
        targets += [
            (
                search.subreddit,
                f"r/{search.subreddit}/search",
                {"q": search.query, "restrict_sr": "1", "t": "week", "sort": "top"},
            )
            for search in self._searches
        ]

        signals: list[Signal] = []
        for index, (subreddit, path, params) in enumerate(targets):
            if index:
                time.sleep(self._request_interval)
            posts = self._fetch_with_retry(path, params)
            for post in posts:
                signal = self._post_to_signal(subreddit, post)
                if signal is not None:
                    signals.append(signal)
            logger.info("Reddit %s: %s posts", path, len(posts))
        return signals

    def _fetch_with_retry(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        attempts = max(settings.collector_retry_attempts, 1)
        for attempt in range(1, attempts + 1):
            try:
                posts = self._fetch_rss(path, params)
                return posts or self._fetch_json(path, params)
            except RedditRateLimitError as exc:
                wait = min(exc.retry_after_seconds or 10.0 * attempt, MAX_RATE_LIMIT_WAIT_SECONDS)
                logger.info("Reddit rate limit em %s (tentativa %s); aguardando %.0fs", path, attempt, wait)
                if attempt < attempts:
                    time.sleep(wait)
            except (requests.RequestException, RuntimeError, ValueError, JSONDecodeError) as exc:
                logger.warning("Reddit %s falhou (tentativa %s): %s", path, attempt, exc)
                if attempt < attempts:
                    time.sleep(settings.collector_retry_delay_seconds * attempt)
        return []

    def _get(self, url: str) -> requests.Response:
        response = self._session.get(url, timeout=settings.collector_timeout_seconds)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "")
            raise RedditRateLimitError(url, float(retry_after) if retry_after.isdigit() else None)
        response.raise_for_status()
        return response

    def _fetch_rss(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = self._get(f"https://www.reddit.com/{path}/.rss?{urlencode(params)}")
        feed = feedparser.parse(response.text)
        return [
            {
                "title": getattr(entry, "title", ""),
                "url": getattr(entry, "link", ""),
                "selftext": getattr(entry, "summary", ""),
                "published_at": parse_published_at(entry),
            }
            for entry in getattr(feed, "entries", [])
        ]

    def _fetch_json(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = self._get(f"https://www.reddit.com/{path}/.json?{urlencode(params)}")
        try:
            payload = response.json()
        except (ValueError, JSONDecodeError) as error:
            raise RuntimeError(f"JSON invalido do Reddit em {path}: {error}") from error

        children = payload.get("data", {}).get("children", []) if isinstance(payload, dict) else []
        posts: list[dict[str, Any]] = []
        for child in children:
            data = child.get("data", {}) if isinstance(child, dict) else {}
            permalink = str(data.get("permalink", ""))
            created_utc = data.get("created_utc")
            posts.append(
                {
                    "title": str(data.get("title", "")),
                    "url": f"https://www.reddit.com{permalink}" if permalink else str(data.get("url", "")),
                    "selftext": str(data.get("selftext", "")),
                    "score": data.get("score"),
                    "num_comments": data.get("num_comments"),
                    "published_at": (
                        datetime.fromtimestamp(created_utc, tz=timezone.utc) if created_utc else None
                    ),
                }
            )
        return posts

    def _post_to_signal(self, subreddit: str, post: dict[str, Any]) -> Signal | None:
        title = str(post.get("title", "")).strip()
        url_value = str(post.get("url", "")).strip()
        if not title or not url_value:
            return None

        return Signal(
            source="reddit",
            title=title,
            content=str(post.get("selftext", "")).strip(),
            url=url_value,
            published_at=post.get("published_at") or datetime.now(timezone.utc),
            metadata={
                "outlet": f"Reddit r/{subreddit}",
                "subreddit": subreddit,
                "score": post.get("score"),
                "num_comments": post.get("num_comments"),
            },
        )
