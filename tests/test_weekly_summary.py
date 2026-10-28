from datetime import timedelta

import pytest

from content_radar.llm.gemini import parse_json_response
from content_radar.llm.weekly_summary import WeeklySummaryGenerator, build_payload
from tests.conftest import make_signal


class FakeProvider:
    model_name = "fake-model"

    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response, "raw"


def _signals():
    return [
        make_signal("ANEEL aprova edital", source="official", outlet="ANEEL", url="https://gov.br/aneel/1"),
        make_signal("Valor repercute edital", outlet="Valor Econômico", url="https://valor.globo.com/1"),
        make_signal("IA em subestações", outlet="MegaWhat", url="https://megawhat.energy/ia"),
    ]


def test_build_payload_assigns_short_ids_and_hides_urls():
    payload, id_map = build_payload(_signals())
    assert [item["id"] for item in payload] == ["s1", "s2", "s3"]
    assert "url" not in payload[0]
    assert str(id_map["s2"].url) == "https://valor.globo.com/1"


def test_generate_resolves_sources_and_orders_ranking(now):
    provider = FakeProvider([
        {
            "headline": "Semana de leilões",
            "ranking": [
                {"rank": 2, "title": "Sem fonte", "importance": 9, "why_it_matters": "x", "signal_ids": ["s99"]},
                {"rank": 1, "title": "Edital aprovado", "importance": 5, "signal_ids": ["s2", "s1", "s1"]},
            ],
            "ai_in_energy": [{"title": "IA", "signal_ids": ["s3"]}],
        }
    ])

    result = WeeklySummaryGenerator(provider).generate(_signals(), now - timedelta(days=7), now)
    ranking = result.summary.ranking

    assert [item.title for item in ranking] == ["Edital aprovado", "Sem fonte"]
    assert [item.rank for item in ranking] == [1, 2]
    assert [(source.outlet, source.url) for source in ranking[0].sources] == [
        ("ANEEL", "https://gov.br/aneel/1"),
        ("Valor Econômico", "https://valor.globo.com/1"),
    ]
    # id inventado pelo LLM: item fica sem fonte, nunca com link inventado
    assert ranking[1].sources == [] and ranking[1].signal_ids == []
    assert ranking[1].importance == 5
    assert result.summary.ai_in_energy[0].sources[0].outlet == "MegaWhat"
    assert result.model == "fake-model"


def test_generate_retries_once_on_invalid_payload(now):
    provider = FakeProvider([{"ranking": "not a list"}, {"headline": "ok"}])
    result = WeeklySummaryGenerator(provider).generate(_signals(), now - timedelta(days=7), now)
    assert result.summary.headline == "ok"
    assert len(provider.prompts) == 2


def test_generate_gives_up_after_attempts(now):
    provider = FakeProvider([{"ranking": 1}, {"ranking": 2}])
    with pytest.raises(RuntimeError):
        WeeklySummaryGenerator(provider).generate(_signals(), now - timedelta(days=7), now)


def test_parse_json_response_strips_code_fence():
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}
