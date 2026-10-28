from __future__ import annotations

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from content_radar.models import Signal
from content_radar.utils.hashing import build_signal_hash, canonical_url
from content_radar.utils.text import fold_text

# Ordem de preferencia de qual copia manter quando a mesma noticia aparece em varias fontes.
_SOURCE_PRIORITY = {"official": 3, "news": 2, "reddit": 1, "trends": 0}


def filter_recent(signals: list[Signal], days: int, now: datetime | None = None) -> list[Signal]:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    return [signal for signal in signals if signal.published_at >= cutoff]


def deduplicate(
    signals: list[Signal],
    *,
    known_urls: set[str] | None = None,
    known_hashes: set[str] | None = None,
    similarity_threshold: float = 0.85,
) -> list[Signal]:
    """Remove duplicatas exatas (URL/hash/titulo), itens ja vistos em semanas anteriores e
    agrupa titulos quase iguais. O sinal mantido recebe metadata.duplicates_count e
    metadata.also_reported_by (veiculos que deram a mesma noticia)."""
    known_urls = known_urls or set()
    known_hashes = known_hashes or set()

    ordered = sorted(
        signals,
        key=lambda signal: (_SOURCE_PRIORITY.get(signal.source, 0), len(signal.content)),
        reverse=True,
    )

    kept: list[Signal] = []
    kept_titles: list[str] = []
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()

    for signal in ordered:
        url = canonical_url(str(signal.url))
        signal_hash = build_signal_hash(signal)
        if url in known_urls or signal_hash in known_hashes:
            continue
        if url in seen_urls or signal_hash in seen_hashes:
            continue

        title = fold_text(signal.title)
        match_index = _find_similar(title, kept_titles, similarity_threshold) if signal.source != "trends" else None
        if match_index is not None:
            _register_duplicate(kept[match_index], signal)
            continue

        seen_urls.add(url)
        seen_hashes.add(signal_hash)
        kept_titles.append(title)
        kept.append(signal.model_copy(update={"metadata": {**signal.metadata, "duplicates_count": 0}}))

    return kept


def _find_similar(title: str, titles: list[str], threshold: float) -> int | None:
    for index, existing in enumerate(titles):
        if title == existing:
            return index
        matcher = SequenceMatcher(None, title, existing)
        if matcher.quick_ratio() >= threshold and matcher.ratio() >= threshold:
            return index
    return None


def _register_duplicate(kept: Signal, duplicate: Signal) -> None:
    kept.metadata["duplicates_count"] = kept.metadata.get("duplicates_count", 0) + 1
    outlet = duplicate.metadata.get("outlet")
    also = kept.metadata.setdefault("also_reported_by", [])
    if outlet and outlet != kept.metadata.get("outlet") and outlet not in also:
        also.append(outlet)
