from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from content_radar.db.models import SignalRecord, WeeklyRun
from content_radar.models import Signal
from content_radar.utils.hashing import build_signal_hash, canonical_url


class SignalRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def known_keys(self, signals: Iterable[Signal]) -> tuple[set[str], set[str]]:
        """URLs e hashes ja gravados (de qualquer semana) entre os sinais informados."""
        signals = list(signals)
        urls = {canonical_url(str(signal.url)) for signal in signals}
        hashes = {build_signal_hash(signal) for signal in signals}
        if not signals:
            return set(), set()

        known_urls = set(self._db.scalars(select(SignalRecord.url).where(SignalRecord.url.in_(urls))))
        known_hashes = set(
            self._db.scalars(select(SignalRecord.content_hash).where(SignalRecord.content_hash.in_(hashes)))
        )
        return known_urls, known_hashes

    def add_signals(self, signals: Iterable[Signal]) -> dict[str, SignalRecord]:
        """Grava os sinais e devolve os registros indexados pela URL canonica."""
        records: dict[str, SignalRecord] = {}
        for signal in signals:
            url = canonical_url(str(signal.url))
            record = SignalRecord(
                source=signal.source,
                category=signal.category,
                title=signal.title,
                content=signal.content,
                url=url,
                content_hash=build_signal_hash(signal),
                published_at=signal.published_at,
                relevance=signal.relevance,
                score=signal.score,
                signal_metadata=signal.metadata,
            )
            self._db.add(record)
            records[url] = record
        self._db.flush()
        return records

    def mark_sent(self, record_ids: Iterable[int], run_id: int) -> None:
        ids = list(record_ids)
        if ids:
            self._db.execute(update(SignalRecord).where(SignalRecord.id.in_(ids)).values(sent_in_run_id=run_id))

    def purge_older_than(self, days: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = self._db.execute(delete(SignalRecord).where(SignalRecord.created_at < cutoff))
        return result.rowcount or 0

    def create_run(self, **fields) -> WeeklyRun:
        run = WeeklyRun(**fields)
        self._db.add(run)
        self._db.flush()
        return run
