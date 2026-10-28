from __future__ import annotations

from content_radar.config.sources import Category, SourceConfig, load_source_config
from content_radar.models import Signal
from content_radar.utils.text import KeywordMatcher

# Termos de categoria a partir dos quais a relevancia satura em 1.0.
_RELEVANCE_SATURATION = 4


class SignalClassifier:
    """Classificacao deterministica por palavras-chave: categoria principal + relevancia 0..1.
    Sinais sem nenhum termo do setor sao descartados (exceto Trends e fontes oficiais,
    que ja sao do setor por construcao)."""

    def __init__(self, config: SourceConfig | None = None) -> None:
        config = config or load_source_config()
        self._sector_matcher = KeywordMatcher(config.sector_keywords)
        self._categories: list[tuple[Category, KeywordMatcher]] = [
            (category, KeywordMatcher(category.keywords)) for category in config.categories
        ]

    def classify(self, signals: list[Signal]) -> list[Signal]:
        classified: list[Signal] = []
        for signal in signals:
            result = self.classify_one(signal)
            if result is not None:
                classified.append(result)
        return classified

    def classify_one(self, signal: Signal) -> Signal | None:
        text = f"{signal.title} {signal.title} {signal.content}"  # titulo pesa em dobro
        in_sector = signal.source in {"official", "trends"} or self._sector_matcher.any_match(text)
        if not in_sector:
            return None

        best_key: str | None = None
        best_hits: list[str] = []
        all_hits: dict[str, list[str]] = {}
        for category, matcher in self._categories:
            hits = matcher.matches(text)
            if hits:
                all_hits[category.key] = hits
            if len(hits) > len(best_hits):
                best_key, best_hits = category.key, hits

        total_hits = sum(len(hits) for hits in all_hits.values())
        relevance = min(1.0, 0.25 + total_hits / _RELEVANCE_SATURATION * 0.75)
        if signal.source == "official":
            relevance = max(relevance, 0.8)

        return signal.model_copy(
            update={
                "category": best_key or "geral",
                "relevance": round(relevance, 3),
                "metadata": {**signal.metadata, "category_hits": all_hits},
            }
        )
