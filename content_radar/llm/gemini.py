from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from content_radar.config.settings import settings

logger = logging.getLogger(__name__)

# Fallback quando o modelo configurado falha. "*-latest" acompanha o Flash mais novo; o lite e mais rapido.
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]
REQUEST_TIMEOUT_MS = 180_000
# 503 ("high demand") costuma passar em alguns segundos/minutos.
ATTEMPTS_PER_MODEL = 3
RETRY_DELAY_SECONDS = 20.0


class LLMQuotaError(RuntimeError):
    pass


class LLMProvider(ABC):
    model_name: str

    @abstractmethod
    def generate_json(self, prompt: str) -> tuple[dict[str, Any], str]:
        """Devolve (json parseado, texto bruto)."""
        raise NotImplementedError


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        self._api_key = api_key or settings.gemini_api_key
        preferred = (model_name or settings.gemini_model_name or "").strip()
        self._candidates = list(dict.fromkeys(model for model in [preferred, *FALLBACK_MODELS] if model))
        self.model_name = self._candidates[0]
        # Raciocinio longo e o que mais pesa no tempo de resposta (e causa 504); resumo nao precisa de muito.
        self._thinking_level = settings.gemini_thinking_level.strip()
        # Sem timeout o SDK espera indefinidamente e o cron fica pendurado.
        self._client = (
            genai.Client(api_key=self._api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
            if self._api_key
            else None
        )

    def generate_json(self, prompt: str) -> tuple[dict[str, Any], str]:
        if self._client is None:
            raise ValueError("GEMINI_API_KEY is required")

        last_error: Exception | None = None
        for model_name in self._candidates:
            use_thinking_level = bool(self._thinking_level)
            for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
                started = time.monotonic()
                try:
                    logger.info("Chamando Gemini (%s, tentativa %s)", model_name, attempt)
                    response = self._client.models.generate_content(
                        model=model_name, contents=prompt, config=self._config(use_thinking_level)
                    )
                    self.model_name = model_name
                    text = response.text or ""
                    logger.info("Gemini respondeu em %.0fs", time.monotonic() - started)
                    return parse_json_response(text), text
                except errors.APIError as exc:
                    last_error = exc
                    elapsed = time.monotonic() - started
                    if exc.code == 429:
                        raise LLMQuotaError(str(exc)) from exc
                    if exc.code == 404:
                        logger.warning("Modelo %s nao existe mais, tentando o proximo", model_name)
                        break
                    if exc.code == 400 and use_thinking_level and "thinking" in str(exc).lower():
                        # Modelos anteriores ao Gemini 3 nao aceitam thinking_level.
                        logger.warning("Modelo %s nao aceita thinking_level; repetindo sem", model_name)
                        use_thinking_level = False
                        continue
                    if exc.code < 500:
                        raise
                    logger.warning("Gemini %s instavel (%s) apos %.0fs", model_name, exc.code, elapsed)
                except httpx.TimeoutException as exc:
                    last_error = exc
                    logger.warning("Gemini %s excedeu o timeout", model_name)
                if attempt < ATTEMPTS_PER_MODEL:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)

        raise last_error or RuntimeError("Gemini call failed")

    def _config(self, use_thinking_level: bool) -> types.GenerateContentConfig:
        thinking = (
            types.ThinkingConfig(thinking_level=types.ThinkingLevel(self._thinking_level.upper()))
            if use_thinking_level
            else None
        )
        return types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.3, thinking_config=thinking
        )


def parse_json_response(response_text: str) -> dict[str, Any]:
    cleaned = response_text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    return json.loads(cleaned)
