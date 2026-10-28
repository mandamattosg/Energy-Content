from types import SimpleNamespace

import pytest
from google.genai import errors

from content_radar.llm import gemini
from content_radar.llm.gemini import GeminiProvider, LLMQuotaError


class FakeModels:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


def _provider(monkeypatch, outcomes):
    monkeypatch.setattr(gemini.time, "sleep", lambda seconds: None)
    provider = GeminiProvider(api_key="key", model_name="model-a")
    fake = FakeModels(outcomes)
    provider._client = SimpleNamespace(models=fake)
    return provider, fake


def _api_error(code, message=None):
    return errors.APIError(code, {"error": {"message": message or f"HTTP {code}"}})


def test_retries_on_503_then_succeeds(monkeypatch):
    provider, fake = _provider(monkeypatch, [_api_error(503), '{"headline": "ok"}'])
    data, raw = provider.generate_json("prompt")
    assert data == {"headline": "ok"}
    assert fake.calls == ["model-a", "model-a"]


def test_falls_back_to_next_model_on_404(monkeypatch):
    provider, fake = _provider(monkeypatch, [_api_error(404), '{"a": 1}'])
    provider.generate_json("prompt")
    assert fake.calls == ["model-a", "gemini-flash-latest"]
    assert provider.model_name == "gemini-flash-latest"


def test_quota_error_is_not_retried(monkeypatch):
    provider, fake = _provider(monkeypatch, [_api_error(429)])
    with pytest.raises(LLMQuotaError):
        provider.generate_json("prompt")
    assert fake.calls == ["model-a"]


def test_gives_up_after_all_models_unavailable(monkeypatch):
    provider, fake = _provider(monkeypatch, [_api_error(504)] * 9)
    with pytest.raises(errors.APIError):
        provider.generate_json("prompt")
    assert fake.calls == ["model-a"] * 3 + ["gemini-flash-latest"] * 3 + ["gemini-flash-lite-latest"] * 3


def test_sends_low_thinking_level_and_drops_it_when_model_rejects(monkeypatch):
    provider, fake = _provider(monkeypatch, [_api_error(400, "thinking_level is not supported"), '{"a": 1}'])
    configs = []
    original = fake.generate_content

    def capture(model, contents, config):
        configs.append(config.thinking_config)
        return original(model, contents, config)

    fake.generate_content = capture
    provider.generate_json("prompt")

    assert configs[0].thinking_level.value == "LOW"
    assert configs[1] is None
