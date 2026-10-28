from types import SimpleNamespace

from content_radar.collectors import reddit as reddit_module
from content_radar.collectors.energy_sources import clean_official_title
from content_radar.collectors.news import NewsCollector, clean_title
from content_radar.collectors.reddit import RedditCollector
from content_radar.config.sources import NewsFeed


def test_clean_title_removes_google_news_outlet_suffix():
    assert clean_title("ANEEL aprova edital - Valor Econômico", "Valor Econômico") == "ANEEL aprova edital"
    assert clean_title("Título - com hífen", None) == "Título - com hífen"


def test_clean_official_title_strips_navigation_noise_and_drops_page_names():
    assert clean_official_title("- Empresa de Pesquisa Energética (EPE)") is None
    assert clean_official_title("Operador Nacional do Sistema Elétrico") is None
    assert (
        clean_official_title("MME publica cronograma de leilões de transmissão — Ministério de Minas e Energia")
        == "MME publica cronograma de leilões de transmissão"
    )
    assert (
        clean_official_title("Notícias PDE projeta avanço da demanda de energia")
        == "PDE projeta avanço da demanda de energia"
    )


def test_news_collector_filters_general_feeds_by_sector_keywords(monkeypatch):
    entries = [
        SimpleNamespace(title="Mega-Sena acumula; g1 transmite ao vivo", link="https://g1.globo.com/a",
                        summary="transmissão ao vivo", published="Tue, 27 Oct 2026 10:00:00 GMT"),
        SimpleNamespace(title="Conta de luz terá bandeira amarela", link="https://g1.globo.com/b",
                        summary="", published="Tue, 27 Oct 2026 10:00:00 GMT"),
    ]
    monkeypatch.setattr("content_radar.collectors.news.fetch_feed", lambda url: SimpleNamespace(entries=entries))

    general = NewsCollector([NewsFeed("G1", "https://g1/rss", general=True)], ["conta de luz", "linha de transmissão"])
    specialized = NewsCollector([NewsFeed("MegaWhat", "https://mw/rss")], ["conta de luz"])

    assert [signal.title for signal in general.collect()] == ["Conta de luz terá bandeira amarela"]
    assert len(specialized.collect()) == 2
    assert general.collect()[0].metadata["outlet"] == "G1"


class FakeResponse:
    def __init__(self, status_code=200, text="", json_data=None, headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self._json_data = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise reddit_module.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self._responses = list(responses)
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        return self._responses.pop(0)


def test_reddit_collector_retries_after_rate_limit_and_falls_back_to_json(monkeypatch):
    monkeypatch.setattr(reddit_module.time, "sleep", lambda seconds: None)
    session = FakeSession([
        FakeResponse(status_code=429, headers={"Retry-After": "2"}),
        FakeResponse(text="<html>blocked</html>"),
        FakeResponse(json_data={"data": {"children": [{"data": {
            "title": "Grid storage record", "permalink": "/r/energy/comments/1/x", "selftext": "body",
            "score": 120, "num_comments": 30, "created_utc": 1793000000,
        }}]}}),
    ])

    signals = RedditCollector(["energy"], [], session=session).collect()

    assert len(signals) == 1
    assert str(signals[0].url) == "https://www.reddit.com/r/energy/comments/1/x"
    assert signals[0].metadata["score"] == 120
    assert signals[0].metadata["outlet"] == "Reddit r/energy"
    assert "/r/energy/top/.json?t=week" in session.urls[-1]
