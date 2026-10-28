from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from content_radar.collectors.base import Collector
from content_radar.db.models import Base, SignalRecord, WeeklyRun
from content_radar.llm.weekly_summary import WeeklySummaryGenerator
from content_radar.outputs.telegram import TelegramOutput
from content_radar.pipeline import PipelineOptions, WeeklyPipeline
from tests.conftest import make_signal
from tests.test_weekly_summary import FakeProvider


class StaticCollector(Collector):
    name = "static"

    def __init__(self, signals):
        self._signals = signals

    def collect(self):
        return list(self._signals)


class BrokenCollector(Collector):
    name = "broken"

    def collect(self):
        raise RuntimeError("boom")


class RecordingOutput(TelegramOutput):
    def __init__(self, fail=False):
        super().__init__(token="t", chat_id="c")
        self.sent = []
        self._fail = fail

    def send(self, summary, context):
        if self._fail:
            raise RuntimeError("telegram down")
        self.sent.append(self.render(summary, context))
        return {"ok": True}


def _session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _signals():
    return [
        make_signal("ANEEL aprova reajuste de tarifa de energia", source="official", outlet="ANEEL",
                    url="https://gov.br/aneel/reajuste"),
        make_signal("Mercado livre de energia cresce", outlet="Canal Energia", url="https://canalenergia.com.br/1"),
        make_signal("Bolsa fecha em alta", outlet="G1", url="https://g1.globo.com/bolsa"),
        make_signal("Notícia antiga do setor elétrico", days_ago=20, url="https://example.com/antiga"),
    ]


def _llm_response():
    return {"headline": "Semana", "ranking": [{"rank": 1, "title": "Reajuste", "signal_ids": ["s1"]}]}


def _pipeline(factory, output, responses):
    return WeeklyPipeline(
        session_factory=factory,
        collectors=[BrokenCollector(), StaticCollector(_signals())],
        generator=WeeklySummaryGenerator(FakeProvider(responses)),
        output=output,
    )


def test_pipeline_sends_persists_and_does_not_resend_next_week(now):
    factory = _session_factory()
    output = RecordingOutput()

    assert _pipeline(factory, output, [_llm_response()]).run(now=now) == 0
    assert len(output.sent) == 1
    assert 'href="https://gov.br/aneel/reajuste"' in output.sent[0][0]

    with factory() as db:
        assert db.scalar(select(func.count(SignalRecord.id))) == 2  # fora do setor e antiga ficaram de fora
        run = db.scalars(select(WeeklyRun)).one()
        assert run.delivery_status == "delivered"
        assert db.scalar(select(func.count(SignalRecord.id)).where(SignalRecord.sent_in_run_id == run.id)) == 2

    # Mesmos sinais na semana seguinte: nada novo, nada enviado.
    second_output = RecordingOutput()
    assert _pipeline(factory, second_output, [_llm_response()]).run(now=now) == 0
    assert second_output.sent == []


def test_pipeline_failure_keeps_signals_for_next_run(now):
    factory = _session_factory()

    assert _pipeline(factory, RecordingOutput(fail=True), [_llm_response()]).run(now=now) == 1
    with factory() as db:
        assert db.scalar(select(func.count(SignalRecord.id))) == 0
        assert db.scalars(select(WeeklyRun.delivery_status)).one() == "failed"

    retry_output = RecordingOutput()
    assert _pipeline(factory, retry_output, [_llm_response()]).run(now=now) == 0
    assert len(retry_output.sent) == 1


def test_dry_run_does_not_persist(now, capsys):
    factory = _session_factory()
    output = RecordingOutput()

    assert _pipeline(factory, output, [_llm_response()]).run(PipelineOptions(dry_run=True), now=now) == 0
    assert output.sent == []
    assert "Radar do Setor Elétrico" in capsys.readouterr().out
    with factory() as db:
        assert db.scalar(select(func.count(SignalRecord.id))) == 0
