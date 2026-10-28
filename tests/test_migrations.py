import logging

from sqlalchemy import create_engine, inspect

from content_radar.db.migrations import run_migrations


def test_run_migrations_creates_tables_is_idempotent_and_keeps_app_logging(tmp_path, caplog):
    url = f"sqlite:///{(tmp_path / 'radar.db').as_posix()}"
    app_logger = logging.getLogger("content_radar.pipeline")

    run_migrations(url)
    run_migrations(url)  # segunda vez nao faz nada

    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"signals", "weekly_runs", "alembic_version"} <= tables
    # O fileConfig do alembic.ini nao pode desligar os loggers do projeto.
    assert not app_logger.disabled
    with caplog.at_level(logging.INFO):
        app_logger.info("ainda logando")
    assert "ainda logando" in caplog.text
