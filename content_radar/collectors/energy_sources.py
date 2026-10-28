from __future__ import annotations

import logging
import re

from content_radar.collectors.base import Collector
from content_radar.collectors.news import entry_outlet, entry_to_signal, fetch_feed
from content_radar.config.sources import OfficialFeed, load_source_config
from content_radar.models import Signal
from content_radar.utils.text import fold_text

logger = logging.getLogger(__name__)

# Restos de navegacao dos sites oficiais que o Google News traz no titulo.
_NOISE_PREFIX = re.compile(r"^(?:[-–—]\s*|not[ií]cias\s+|co\s*[-–—]?\s+)", re.IGNORECASE)
_NOISE_SUFFIX = re.compile(r"\s+[-–—]\s+(?:minist[ée]rio de minas e energia|gov\.br|ccee|ons|epe|aneel)$", re.IGNORECASE)
_PARENTHESES = re.compile(r"\([^)]*\)")
# Paginas institucionais que o Google News indexa como se fossem noticias.
_PAGE_NAMES = {
    "agencia nacional de energia eletrica",
    "operador nacional do sistema eletrico",
    "empresa de pesquisa energetica",
    "camara de comercializacao de energia eletrica",
    "ministerio de minas e energia",
}
_MIN_TITLE_WORDS = 4


def clean_official_title(title: str) -> str | None:
    cleaned = _NOISE_SUFFIX.sub("", _NOISE_PREFIX.sub("", title.strip())).strip()
    if fold_text(_PARENTHESES.sub("", cleaned)).strip(" -–—") in _PAGE_NAMES:
        return None
    if len(cleaned.split()) < _MIN_TITLE_WORDS:
        return None
    return cleaned


class EnergySourcesCollector(Collector):
    """ANEEL / ONS / EPE / CCEE / MME. A fonte exibida e sempre o orgao, nao o "GOV.BR" do Google News."""

    name = "official"

    def __init__(self, feeds: list[OfficialFeed] | None = None) -> None:
        self._feeds = feeds if feeds is not None else load_source_config().official_feeds

    def collect(self) -> list[Signal]:
        signals: list[Signal] = []

        for feed_config in self._feeds:
            feed = fetch_feed(feed_config.url)
            if feed is None:
                continue

            kept = 0
            for entry in getattr(feed, "entries", []):
                signal = entry_to_signal(
                    entry,
                    source="official",
                    outlet=feed_config.agency,
                    metadata={
                        "agency": feed_config.agency,
                        "feed_url": feed_config.url,
                        "original_outlet": entry_outlet(entry),
                    },
                )
                if signal is None:
                    continue
                title = clean_official_title(signal.title)
                if title is None:
                    continue
                signals.append(signal.model_copy(update={"title": title}))
                kept += 1
            logger.info("Fonte oficial %s: %s itens", feed_config.agency, kept)

        return signals
