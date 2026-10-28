"""Entrypoint do cron semanal (Railway): roda o pipeline uma vez e sai com 0 (ok) ou 1 (falha)."""

import argparse
import logging
import sys

import truststore

# Usa os certificados do sistema operacional (evita erro de SSL no Google Trends com antivirus/proxy no Windows).
truststore.inject_into_ssl()

from content_radar.collectors import default_collectors
from content_radar.db.session import SessionLocal
from content_radar.llm.gemini import GeminiProvider
from content_radar.llm.weekly_summary import WeeklySummaryGenerator
from content_radar.outputs.telegram import TelegramOutput
from content_radar.pipeline import PipelineOptions, WeeklyPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Energy Radar - resumo semanal do setor eletrico")
    parser.add_argument("--dry-run", action="store_true", help="gera o resumo e imprime, sem enviar nem gravar")
    parser.add_argument("--skip-llm", action="store_true", help="so coleta, classifica e mostra o ranking")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    pipeline = WeeklyPipeline(
        session_factory=SessionLocal,
        collectors=default_collectors(),
        generator=None if args.skip_llm else WeeklySummaryGenerator(GeminiProvider()),
        output=TelegramOutput(),
    )
    return pipeline.run(PipelineOptions(dry_run=args.dry_run, skip_llm=args.skip_llm))


if __name__ == "__main__":
    sys.exit(main())
