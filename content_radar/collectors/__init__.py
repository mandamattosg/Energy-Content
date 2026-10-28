from content_radar.collectors.energy_sources import EnergySourcesCollector
from content_radar.collectors.google_trends import TrendsCollector
from content_radar.collectors.news import NewsCollector
from content_radar.collectors.reddit import RedditCollector

__all__ = ["EnergySourcesCollector", "NewsCollector", "RedditCollector", "TrendsCollector"]


def default_collectors():
    return [EnergySourcesCollector(), NewsCollector(), RedditCollector(), TrendsCollector()]
