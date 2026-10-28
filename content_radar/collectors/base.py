from abc import ABC, abstractmethod

from content_radar.models import Signal


class Collector(ABC):
    name: str = "collector"

    @abstractmethod
    def collect(self) -> list[Signal]:
        raise NotImplementedError
