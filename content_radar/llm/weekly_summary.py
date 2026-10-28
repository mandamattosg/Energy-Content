from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from content_radar.config.settings import settings
from content_radar.config.sources import load_source_config
from content_radar.llm.gemini import LLMProvider
from content_radar.models import Signal
from content_radar.utils.text import normalize_text, truncate_text

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompts" / "weekly_summary.md"
PROMPT_VERSION = "weekly_summary_v2"
_SOURCE_ORDER = {"official": 0, "news": 1, "trends": 2, "reddit": 3}


class SourceRef(BaseModel):
    outlet: str
    url: str


class SummaryItem(BaseModel):
    title: str
    why_it_matters: str = ""
    signal_ids: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)


class RankedItem(SummaryItem):
    rank: int = 0
    category: str = "geral"
    importance: int = 3

    @field_validator("importance", mode="before")
    @classmethod
    def clamp_importance(cls, value: Any) -> int:
        try:
            return max(1, min(5, round(float(value))))
        except (TypeError, ValueError):
            return 3


class WeeklySummary(BaseModel):
    headline: str = ""
    ranking: list[RankedItem] = Field(default_factory=list)
    ai_in_energy: list[SummaryItem] = Field(default_factory=list)
    trends: list[str] = Field(default_factory=list)
    watchlist_next_week: list[str] = Field(default_factory=list)


@dataclass
class SummaryResult:
    summary: WeeklySummary
    raw_response: str
    model: str
    prompt_version: str = PROMPT_VERSION


def build_payload(signals: list[Signal]) -> tuple[list[dict[str, Any]], dict[str, Signal]]:
    """Atribui ids curtos (s1, s2...) aos sinais. O LLM so referencia ids; URLs saem do nosso lado."""
    payload: list[dict[str, Any]] = []
    id_map: dict[str, Signal] = {}
    for index, signal in enumerate(signals, start=1):
        signal_id = f"s{index}"
        id_map[signal_id] = signal
        item: dict[str, Any] = {
            "id": signal_id,
            "source": signal.source,
            "outlet": signal.metadata.get("outlet"),
            "category": signal.category,
            "title": normalize_text(signal.title),
            "content": truncate_text(normalize_text(signal.content), settings.analysis_max_content_length),
            "published_at": signal.published_at.date().isoformat(),
        }
        if signal.metadata.get("also_reported_by"):
            item["also_reported_by"] = signal.metadata["also_reported_by"]
        if signal.source == "trends":
            item["growth_pct"] = signal.metadata.get("growth")
        payload.append(item)
    return payload, id_map


def resolve_sources(summary: WeeklySummary, id_map: dict[str, Signal]) -> WeeklySummary:
    """Liga cada item aos sinais citados. Ids desconhecidos sao descartados: item sem
    correspondencia direta fica sem fonte, nunca com link inventado."""

    def resolve(item: SummaryItem) -> None:
        valid_ids: list[str] = []
        sources: list[tuple[int, SourceRef]] = []
        seen_outlets: set[str] = set()
        for signal_id in item.signal_ids:
            signal = id_map.get(signal_id.strip())
            if signal is None:
                continue
            valid_ids.append(signal_id.strip())
            outlet = signal.metadata.get("outlet") or signal.source
            if outlet in seen_outlets:
                continue
            seen_outlets.add(outlet)
            sources.append((_SOURCE_ORDER.get(signal.source, 9), SourceRef(outlet=outlet, url=str(signal.url))))
        item.signal_ids = valid_ids
        # Orgao oficial primeiro; dentro do mesmo tipo, mantem a ordem do LLM (sort estavel).
        item.sources = [source for _, source in sorted(sources, key=lambda pair: pair[0])]

    for item in summary.ranking:
        resolve(item)
    for item in summary.ai_in_energy:
        resolve(item)

    summary.ranking.sort(key=lambda item: item.rank or 999)
    for position, item in enumerate(summary.ranking, start=1):
        item.rank = position
    return summary


def build_prompt(payload: list[dict[str, Any]], period_start: datetime, period_end: datetime) -> str:
    categories = ", ".join(category.key for category in load_source_config().categories)
    template = PROMPT_PATH.read_text(encoding="utf-8")
    instructions = template.format(
        period_start=period_start.strftime("%d/%m/%Y"),
        period_end=period_end.strftime("%d/%m/%Y"),
        categories=categories,
    )
    return f"{instructions}\n\nSinais:\n{json.dumps(payload, ensure_ascii=False, indent=1)}"


class WeeklySummaryGenerator:
    def __init__(self, provider: LLMProvider, attempts: int = 2) -> None:
        self._provider = provider
        self._attempts = attempts

    def generate(self, signals: list[Signal], period_start: datetime, period_end: datetime) -> SummaryResult:
        payload, id_map = build_payload(signals)
        prompt = build_prompt(payload, period_start, period_end)

        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            raw_text = ""
            try:
                data, raw_text = self._provider.generate_json(prompt)
                summary = WeeklySummary.model_validate(data)
            except (JSONDecodeError, ValidationError) as exc:
                logger.warning("Resposta invalida do LLM (tentativa %s): %s", attempt, exc)
                last_error = exc
                continue

            return SummaryResult(
                summary=resolve_sources(summary, id_map),
                raw_response=raw_text,
                model=self._provider.model_name,
            )

        raise RuntimeError(f"LLM returned invalid JSON after {self._attempts} attempts") from last_error
