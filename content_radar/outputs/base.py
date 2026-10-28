from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from content_radar.llm.weekly_summary import WeeklySummary


@dataclass
class DeliveryContext:
    period_start: datetime
    period_end: datetime
    source_counts: dict[str, int] = field(default_factory=dict)


class Output(ABC):
    name: str = "output"

    @abstractmethod
    def render(self, summary: WeeklySummary, context: DeliveryContext) -> list[str]:
        """Mensagens prontas para envio (usado tambem no --dry-run)."""
        raise NotImplementedError

    @abstractmethod
    def send(self, summary: WeeklySummary, context: DeliveryContext) -> dict[str, Any]:
        raise NotImplementedError
