import os

# Antes de qualquer import do projeto: os testes nunca leem o .env com as credenciais reais.
os.environ["ENERGY_RADAR_ENV_FILE"] = ""

from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402

from content_radar.models import Signal  # noqa: E402

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def make_signal(title: str, *, source: str = "news", url: str | None = None, content: str = "", days_ago: float = 1,
                **metadata) -> Signal:
    slug = abs(hash((title, source, url))) % 10**8
    return Signal(
        source=source,
        title=title,
        content=content,
        url=url or f"https://example.com/{source}/{slug}",
        published_at=NOW - timedelta(days=days_ago),
        metadata={"outlet": metadata.pop("outlet", "Exemplo"), **metadata},
    )


@pytest.fixture
def now() -> datetime:
    return NOW
