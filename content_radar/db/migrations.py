from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_migrations(database_url: str | None = None) -> None:
    """Aplica as migracoes pendentes (cria as tabelas na primeira execucao; depois e no-op).
    Roda no inicio do main.py para nao depender do comando de start do Railway."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.attributes["configure_logger"] = False
    if database_url:
        config.attributes["database_url"] = database_url
    logger.info("Aplicando migracoes do banco")
    command.upgrade(config, "head")
