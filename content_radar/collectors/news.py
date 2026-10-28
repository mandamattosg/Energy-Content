from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser

from content_radar.collectors.base import Collector
from content_radar.config.settings import settings
from content_radar.config.sources import NewsFeed, load_source_config
from content_radar.models import Signal
from content_radar.utils.retry import retry_call
from content_radar.utils.text import KeywordMatcher

logger = logging.getLogger(__name__)


def parse_feed(feed_url: str) -> Any:
    feed = feedparser.parse(feed_url, agent=settings.reddit_user_agent)
    bozo_exception = getattr(feed, "bozo_exception", None)
    if getattr(feed, "bozo", False) and bozo_exception is not None and not getattr(feed, "entries", None):
        raise RuntimeError(f"Failed to parse RSS feed {feed_url}: {bozo_exception}")
    return feed


def fetch_feed(feed_url: str) -> Any | None:
    try:
        return retry_call(
            lambda: parse_feed(feed_url),
            attempts=settings.collector_retry_attempts,
            delay_seconds=settings.collector_retry_delay_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Feed ignorado %s: %s", feed_url, exc)
        return None


def entry_outlet(entry: Any) -> str | None:
    """Veiculo original do item (o Google News informa em <source>)."""
    source = getattr(entry, "source", None)
    if source is None:
        return None
    title = source.get("title") if isinstance(source, dict) else getattr(source, "title", None)
    if not title:
        return None
    return str(title).strip() or None


def clean_title(title: str, outlet: str | None) -> str:
    # Google News termina os titulos com " - Veiculo".
    title = title.strip()
    if outlet and title.endswith(f" - {outlet}"):
        return title[: -len(outlet) - 3].strip()
    return title


def parse_published_at(entry: Any) -> datetime:
    for field_name in ("published", "updated"):
        raw_value = getattr(entry, field_name, None)
        if raw_value:
            try:
                return parsedate_to_datetime(raw_value).astimezone(timezone.utc)
            except (TypeError, ValueError, AttributeError):
                pass

    for field_name in ("published_parsed", "updated_parsed"):
        parsed_value = getattr(entry, field_name, None)
        if parsed_value:
            return datetime(*parsed_value[:6], tzinfo=timezone.utc)

    return datetime.now(timezone.utc)


def entry_to_signal(entry: Any, *, source: str, outlet: str, metadata: dict[str, Any]) -> Signal | None:
    title = clean_title(getattr(entry, "title", "") or "", entry_outlet(entry))
    link = (getattr(entry, "link", "") or "").strip()
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    if not title or not link:
        return None

    return Signal(
        source=source,
        title=title,
        content=summary,
        url=link,
        published_at=parse_published_at(entry),
        metadata={"outlet": outlet, **metadata},
    )


class NewsCollector(Collector):
    name = "news"

    def __init__(self, feeds: list[NewsFeed] | None = None, sector_keywords: list[str] | None = None) -> None:
        source_config = load_source_config()
        self._feeds = feeds if feeds is not None else source_config.news_feeds
        self._sector_matcher = KeywordMatcher(
            sector_keywords if sector_keywords is not None else source_config.sector_keywords
        )

    def collect(self) -> list[Signal]:
        signals: list[Signal] = []

        for feed_config in self._feeds:
            feed = fetch_feed(feed_config.url)
            if feed is None:
                continue

            kept = 0
            for entry in getattr(feed, "entries", []):
                outlet = entry_outlet(entry) or feed_config.name
                signal = entry_to_signal(
                    entry,
                    source="news",
                    outlet=outlet,
                    metadata={"feed_name": feed_config.name, "feed_url": feed_config.url},
                )
                if signal is None:
                    continue
                # Portais generalistas trazem de tudo: so fica o que menciona o setor.
                if feed_config.general and not self._sector_matcher.any_match(f"{signal.title} {signal.content}"):
                    continue
                signals.append(signal)
                kept += 1
            logger.info("Feed %s: %s itens", feed_config.name, kept)

        return signals
