from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus

import pandas as pd
from pytrends.request import TrendReq

from content_radar.collectors.base import Collector
from content_radar.config.settings import settings
from content_radar.config.sources import load_source_config
from content_radar.models import Signal
from content_radar.utils.retry import retry_call

logger = logging.getLogger(__name__)

TIMEFRAME = "today 3-m"
# Limite do Google Trends por requisicao.
BATCH_SIZE = 5


class TrendsCollector(Collector):
    """Interesse da ultima semana comparado a media dos ultimos 3 meses, no Brasil."""

    name = "trends"

    def __init__(self, keywords: list[str] | None = None, client: TrendReq | None = None) -> None:
        self._keywords = keywords if keywords is not None else load_source_config().trend_keywords
        self._client = client

    def collect(self) -> list[Signal]:
        if not self._keywords:
            return []

        if self._client is None:
            self._client = TrendReq(hl="pt-BR", tz=180)

        signals: list[Signal] = []
        collected_at = datetime.now(timezone.utc)

        for start in range(0, len(self._keywords), BATCH_SIZE):
            batch = self._keywords[start : start + BATCH_SIZE]
            try:
                frame = retry_call(
                    lambda: self._fetch_interest_frame(batch),
                    attempts=settings.collector_retry_attempts,
                    delay_seconds=settings.collector_retry_delay_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Google Trends falhou para %s: %s", batch, exc)
                continue

            for keyword in batch:
                signal = self._keyword_to_signal(keyword, frame, collected_at)
                if signal is not None:
                    signals.append(signal)

        return signals

    def _fetch_interest_frame(self, keywords: list[str]) -> pd.DataFrame:
        self._client.build_payload(keywords, cat=0, timeframe=TIMEFRAME, geo="BR", gprop="")
        frame = self._client.interest_over_time()
        if frame.empty:
            raise RuntimeError("Google Trends returned no data")
        if "isPartial" in frame.columns:
            frame = frame.drop(columns=["isPartial"])
        return frame

    def _keyword_to_signal(self, keyword: str, frame: pd.DataFrame, collected_at: datetime) -> Signal | None:
        if keyword not in frame.columns:
            return None
        series = frame[keyword].dropna()
        if len(series) < 2:
            return None

        last_week = float(series.iloc[-7:].mean()) if len(series) > 14 else float(series.iloc[-1])
        baseline = float(series.mean())
        growth = self.calculate_growth(baseline, last_week)

        return Signal(
            source="trends",
            title=keyword,
            content=(
                f"Busca por '{keyword}' no Brasil: interesse medio da ultima semana {last_week:.0f}/100, "
                f"variacao de {growth:+.0f}% sobre a media de 3 meses."
            ),
            # O fragmento com a data torna a URL unica por semana (o dedup entre semanas e por URL).
            url=(
                f"https://trends.google.com/trends/explore?geo=BR&date=today%203-m&q={quote_plus(keyword)}"
                f"#{collected_at:%Y-%m-%d}"
            ),
            published_at=collected_at,
            metadata={
                "outlet": "Google Trends",
                "keyword": keyword,
                "growth": round(growth, 1),
                "interest_last_week": round(last_week, 1),
                "baseline_interest": round(baseline, 1),
                "timeframe": TIMEFRAME,
            },
        )

    @staticmethod
    def calculate_growth(baseline: float, current: float) -> float:
        if baseline <= 0:
            return 0.0
        return ((current - baseline) / baseline) * 100.0
