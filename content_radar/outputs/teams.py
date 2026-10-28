"""Fase 2: envio para um canal do Microsoft Teams.

Caminho previsto: no canal, "..." > Workflows > "Post to a channel when a webhook request is received".
O Workflow gera uma URL (TEAMS_WEBHOOK_URL) que recebe um POST com um Adaptive Card.
"""

from __future__ import annotations

from typing import Any

from content_radar.llm.weekly_summary import WeeklySummary
from content_radar.outputs.base import DeliveryContext, Output


class TeamsOutput(Output):
    name = "teams"

    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook_url = webhook_url

    def render(self, summary: WeeklySummary, context: DeliveryContext) -> list[str]:
        raise NotImplementedError("Teams output is planned for phase 2")

    def send(self, summary: WeeklySummary, context: DeliveryContext) -> dict[str, Any]:
        raise NotImplementedError("Teams output is planned for phase 2")
