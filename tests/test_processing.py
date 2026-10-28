from content_radar.config.sources import Category, SourceConfig
from content_radar.processing.classification import SignalClassifier
from content_radar.processing.deduplication import deduplicate, filter_recent
from content_radar.processing.ranking import SignalRanker
from content_radar.utils.hashing import build_signal_hash
from content_radar.utils.text import KeywordMatcher
from tests.conftest import make_signal


def test_keyword_matcher_ignores_accents_and_requires_whole_word_for_short_terms():
    matcher = KeywordMatcher(["ons", "elétric"])
    assert matcher.matches("Operador ONS anuncia corte") == ["ons"]
    assert matcher.matches("Considerações sobre o mercado") == []
    assert matcher.matches("Setor ELETRICO em alta") == ["elétric"]


def test_filter_recent_drops_old_signals(now):
    signals = [make_signal("nova", days_ago=2), make_signal("velha", days_ago=10)]
    assert [signal.title for signal in filter_recent(signals, 7, now=now)] == ["nova"]


def test_deduplicate_removes_exact_and_known_and_groups_near_duplicates():
    official = make_signal("ANEEL aprova edital do leilão de armazenamento de energia", source="official",
                           outlet="ANEEL")
    copy = make_signal("ANEEL aprova edital de leilão de armazenamento de energia", outlet="Valor Econômico")
    same_url = make_signal("Outro título", url=str(official.url))
    already_sent = make_signal("Notícia da semana passada")
    other = make_signal("ONS registra recorde de geração eólica")

    result = deduplicate(
        [copy, same_url, official, already_sent, other],
        known_hashes={build_signal_hash(already_sent)},
    )

    titles = [signal.title for signal in result]
    assert titles == [official.title, other.title]
    assert result[0].metadata["duplicates_count"] == 1
    assert result[0].metadata["also_reported_by"] == ["Valor Econômico"]


def test_deduplicate_skips_known_urls():
    signal = make_signal("Leilão de transmissão")
    assert deduplicate([signal], known_urls={str(signal.url)}) == []


def _config() -> SourceConfig:
    return SourceConfig(
        sector_keywords=["energia", "elétric", "aneel"],
        categories=[
            Category("regulacao", "Regulação", ["aneel", "consulta pública"]),
            Category("ia", "IA & digitalização", ["inteligência artificial", "data center"]),
        ],
    )


def test_classifier_assigns_category_and_drops_off_topic():
    classifier = SignalClassifier(_config())
    on_topic = make_signal("ANEEL abre consulta pública sobre energia")
    ai = make_signal("Data center pressiona demanda de energia", content="inteligência artificial")
    off_topic = make_signal("Bolsa fecha em alta com bancos")

    result = classifier.classify([on_topic, ai, off_topic])

    assert [(signal.title, signal.category) for signal in result] == [
        (on_topic.title, "regulacao"),
        (ai.title, "ia"),
    ]
    assert all(0 < signal.relevance <= 1 for signal in result)


def test_classifier_keeps_official_and_trends_without_sector_terms():
    classifier = SignalClassifier(_config())
    result = classifier.classify([make_signal("Nota à imprensa", source="official")])
    assert result[0].relevance >= 0.8


def test_ranker_prefers_official_and_respects_source_limits(now):
    ranker = SignalRanker(
        source_weights={"official": 3.0, "news": 2.0, "reddit": 0.5},
        source_limits={"official": 5, "news": 1, "reddit": 5},
        max_total=10,
        lookback_days=7,
    )
    signals = [
        make_signal("notícia 1", days_ago=1).model_copy(update={"relevance": 0.5}),
        make_signal("notícia 2", days_ago=1).model_copy(update={"relevance": 0.4}),
        make_signal("oficial", source="official", days_ago=3).model_copy(update={"relevance": 0.8}),
        make_signal("reddit", source="reddit", days_ago=1, score=500).model_copy(update={"relevance": 0.3}),
    ]

    ranked = ranker.rank(signals, now=now)

    assert [signal.title for signal in ranked] == ["oficial", "notícia 1", "reddit"]
    assert ranked[0].score > ranked[1].score
