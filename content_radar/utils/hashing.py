from __future__ import annotations

import hashlib

from content_radar.models import Signal
from content_radar.utils.text import fold_text


def build_signal_hash(signal: Signal) -> str:
    # Sem a data: a mesma noticia republicada em outro dia continua sendo duplicata.
    canonical_parts = [
        signal.source.lower().strip(),
        fold_text(signal.title),
        fold_text(signal.content),
    ]
    canonical_value = "|".join(canonical_parts)
    return hashlib.sha256(canonical_value.encode("utf-8")).hexdigest()


def canonical_url(url: str) -> str:
    # Sem lower(): ids de artigo do Google News diferenciam maiusculas.
    return url.strip().rstrip("/")
