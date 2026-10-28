from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, sessionmaker

from content_radar.collectors.base import Collector
from content_radar.config.settings import settings
from content_radar.db.repository import SignalRepository
from content_radar.llm.weekly_summary import WeeklySummaryGenerator
from content_radar.models import Signal
from content_radar.outputs.base import DeliveryContext, Output
from content_radar.processing.classification import SignalClassifier
from content_radar.processing.deduplication import deduplicate, filter_recent
from content_radar.processing.ranking import SignalRanker
from content_radar.utils.hashing import canonical_url

logger = logging.getLogger("content_radar.pipeline")


def _memory_note() -> str:
    """Pico de memoria do processo (so Linux/Railway), para diagnosticar mortes por falta de memoria."""
    try:
        import resource
    except ImportError:
        return ""
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    return f" (pico de memoria {peak_mb:.0f} MB)"


@dataclass
class PipelineOptions:
    dry_run: bool = False
    skip_llm: bool = False


class WeeklyPipeline:
    """coleta -> janela de 7 dias -> classificacao -> dedup (inclusive contra o banco) -> ranking
    -> LLM -> envio -> persistencia. Tudo numa transacao: se o envio falhar nada e gravado
    como visto, e os mesmos sinais voltam na proxima execucao."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        collectors: list[Collector],
        generator: WeeklySummaryGenerator | None,
        output: Output | None,
        classifier: SignalClassifier | None = None,
        ranker: SignalRanker | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._collectors = collectors
        self._generator = generator
        self._output = output
        self._classifier = classifier or SignalClassifier()
        self._ranker = ranker or SignalRanker()

    def run(self, options: PipelineOptions | None = None, now: datetime | None = None) -> int:
        options = options or PipelineOptions()
        period_end = now or datetime.now(timezone.utc)
        period_start = period_end - timedelta(days=settings.lookback_days)

        collected = self._collect()
        recent = filter_recent(collected, settings.lookback_days, now=period_end)
        classified = self._classifier.classify(recent)
        logger.info("Coletados=%s  na janela=%s  do setor=%s", len(collected), len(recent), len(classified))

        with self._session_factory() as db:
            repo = SignalRepository(db)
            try:
                known_urls, known_hashes = repo.known_keys(classified)
                unique = deduplicate(
                    classified,
                    known_urls=known_urls,
                    known_hashes=known_hashes,
                    similarity_threshold=settings.near_duplicate_threshold,
                )
                ranked = self._ranker.rank(unique, now=period_end)
                source_counts = dict(Counter(signal.source for signal in unique))
                logger.info("Ineditos=%s %s  enviados ao LLM=%s", len(unique), source_counts, len(ranked))

                if not ranked:
                    logger.warning("Nenhum sinal novo nesta semana; nada a enviar")
                    return 0

                if options.skip_llm or self._generator is None:
                    self._print_ranked(ranked)
                    db.rollback()
                    return 0

                logger.info("Gerando resumo com o LLM")
                result = self._generator.generate(ranked, period_start, period_end)
                context = DeliveryContext(period_start, period_end, source_counts)

                if options.dry_run or self._output is None:
                    for message in self._output.render(result.summary, context) if self._output else []:
                        print(message, end="\n\n" + "-" * 60 + "\n\n")
                    db.rollback()
                    return 0

                records = repo.add_signals(unique)
                run = repo.create_run(
                    period_start=period_start,
                    period_end=period_end,
                    model=result.model,
                    prompt_version=result.prompt_version,
                    signals_count=len(ranked),
                    source_counts=source_counts,
                    raw_response=result.raw_response,
                    summary=result.summary.model_dump(mode="json"),
                )

                logger.info("Enviando para %s", self._output.name)
                delivery = self._output.send(result.summary, context)
                logger.info("Entrega: %s", delivery)
                run.delivery_status = "delivered"
                run.delivered_at = datetime.now(timezone.utc)

                sent_ids = [records[canonical_url(str(signal.url))].id for signal in ranked]
                repo.mark_sent(sent_ids, run.id)
                purged = repo.purge_older_than(settings.data_retention_days)
                db.commit()
                logger.info("Run %s concluido; %s sinais antigos removidos", run.id, purged)
                return 0
            except Exception:
                db.rollback()
                logger.exception("Pipeline falhou")
                self._record_failure(period_start, period_end)
                return 1

    def _collect(self) -> list[Signal]:
        signals: list[Signal] = []
        for collector in self._collectors:
            logger.info("Iniciando coletor %s", collector.name)
            try:
                collected = collector.collect()
            except Exception:  # noqa: BLE001 - um coletor quebrado nao derruba os outros
                logger.exception("Coletor %s falhou", collector.name)
                continue
            logger.info("Coletor %s: %s sinais%s", collector.name, len(collected), _memory_note())
            signals.extend(collected)
        return signals

    def _record_failure(self, period_start: datetime, period_end: datetime) -> None:
        try:
            with self._session_factory() as db:
                SignalRepository(db).create_run(
                    period_start=period_start, period_end=period_end, delivery_status="failed"
                )
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Nao foi possivel registrar a falha no banco")

    @staticmethod
    def _print_ranked(signals: list[Signal]) -> None:
        for position, signal in enumerate(signals, start=1):
            outlet = signal.metadata.get("outlet", signal.source)
            print(f"{position:>2}. [{signal.score:5.2f}] {signal.category:<16} {outlet}: {signal.title}")
