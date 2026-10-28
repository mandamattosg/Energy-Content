from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass(frozen=True)
class NewsFeed:
    name: str
    url: str
    general: bool = False


@dataclass(frozen=True)
class OfficialFeed:
    agency: str
    url: str


@dataclass(frozen=True)
class RedditSearch:
    subreddit: str
    query: str


DEFAULT_CATEGORY_EMOJI = "📰"


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    keywords: list[str]
    emoji: str = DEFAULT_CATEGORY_EMOJI


@dataclass(frozen=True)
class SourceConfig:
    news_feeds: list[NewsFeed] = field(default_factory=list)
    official_feeds: list[OfficialFeed] = field(default_factory=list)
    reddit_subreddits: list[str] = field(default_factory=list)
    reddit_searches: list[RedditSearch] = field(default_factory=list)
    trend_keywords: list[str] = field(default_factory=list)
    sector_keywords: list[str] = field(default_factory=list)
    categories: list[Category] = field(default_factory=list)
    source_weights: dict[str, float] = field(default_factory=dict)

    def category_label(self, key: str | None) -> str:
        for category in self.categories:
            if category.key == key:
                return category.label
        return "Geral"

    def category_emoji(self, key: str | None) -> str:
        for category in self.categories:
            if category.key == key:
                return category.emoji
        return DEFAULT_CATEGORY_EMOJI


DEFAULT_PATH = Path(__file__).with_name("sources.yaml")


@lru_cache(maxsize=4)
def load_source_config(path: Path = DEFAULT_PATH) -> SourceConfig:
    with path.open("r", encoding="utf-8") as file_handle:
        raw = yaml.safe_load(file_handle) or {}

    reddit = raw.get("reddit", {}) or {}
    return SourceConfig(
        news_feeds=[NewsFeed(**item) for item in raw.get("news_feeds", [])],
        official_feeds=[OfficialFeed(**item) for item in raw.get("official_feeds", [])],
        reddit_subreddits=list(reddit.get("subreddits", [])),
        reddit_searches=[RedditSearch(**item) for item in reddit.get("searches", [])],
        trend_keywords=list(raw.get("trend_keywords", [])),
        sector_keywords=list(raw.get("sector_keywords", [])),
        categories=[
            Category(
                key=key,
                label=value["label"],
                keywords=list(value.get("keywords", [])),
                emoji=value.get("emoji", DEFAULT_CATEGORY_EMOJI),
            )
            for key, value in (raw.get("categories", {}) or {}).items()
        ],
        source_weights={key: float(value) for key, value in (raw.get("source_weights", {}) or {}).items()},
    )
