from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

from content_radar.config.settings import settings
from content_radar.config.sources import load_source_config
from content_radar.models import Signal


class SignalRanker:
    """Score heuristico usado so para escolher o que vai para o LLM.
    A ordem final do ranking da semana e decidida pelo LLM."""

    def __init__(
        self,
        *,
        source_weights: dict[str, float] | None = None,
        source_limits: dict[str, int] | None = None,
        max_total: int | None = None,
        lookback_days: int | None = None,
    ) -> None:
        self._weights = source_weights or load_source_config().source_weights
        self._limits = source_limits or {
            "official": settings.analysis_max_official_signals,
            "news": settings.analysis_max_news_signals,
            "reddit": settings.analysis_max_reddit_signals,
            "trends": settings.analysis_max_trends_signals,
        }
        self._max_total = max_total or settings.analysis_max_total_signals
        self._lookback_days = lookback_days or settings.lookback_days

    def score(self, signal: Signal, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        metadata = signal.metadata

        source_weight = self._weights.get(signal.source, 1.0)
        relevance = signal.relevance * 3.0

        age_days = max(0.0, (now - signal.published_at).total_seconds() / 86400)
        recency = max(0.0, 1.0 - age_days / self._lookback_days)

        # Mesma noticia em varios veiculos = assunto quente.
        coverage = math.log1p(metadata.get("duplicates_count", 0)) * 1.5

        engagement = 0.0
        if signal.source == "reddit":
            engagement = math.log1p(max(0, metadata.get("score") or 0)) / 3
        elif signal.source == "trends":
            engagement = max(0.0, (metadata.get("growth") or 0.0) / 50)

        return round(source_weight + relevance + recency + coverage + min(engagement, 2.0), 3)

    def rank(self, signals: list[Signal], now: datetime | None = None) -> list[Signal]:
        scored = sorted(
            (signal.model_copy(update={"score": self.score(signal, now)}) for signal in signals),
            key=lambda signal: signal.score,
            reverse=True,
        )

        per_source: dict[str, int] = defaultdict(int)
        selected: list[Signal] = []
        for signal in scored:
            limit = self._limits.get(signal.source, self._max_total)
            if per_source[signal.source] >= limit:
                continue
            per_source[signal.source] += 1
            selected.append(signal)
            if len(selected) >= self._max_total:
                break
        return selected
