from datetime import timedelta

from content_radar.llm.weekly_summary import RankedItem, SourceRef, SummaryItem, WeeklySummary
from content_radar.outputs.base import DeliveryContext
from content_radar.outputs.telegram import TelegramOutput, pack_blocks


def test_render_shows_ranking_with_sources_and_escapes_html(now):
    summary = WeeklySummary(
        headline="Semana <agitada>",
        ranking=[
            RankedItem(rank=1, title="Edital", category="regulacao", importance=5, why_it_matters="Afeta tudo",
                       sources=[SourceRef(outlet="ANEEL", url="https://gov.br/aneel?a=1&b=2")]),
            RankedItem(rank=2, title="Sem fonte", category="xyz", importance=2),
        ],
        ai_in_energy=[SummaryItem(title="IA", why_it_matters="Data centers")],
        watchlist_next_week=["Leilão dia 05/11"],
    )
    context = DeliveryContext(now - timedelta(days=7), now, {"news": 40, "official": 5})

    text = "\n".join(TelegramOutput(token="t", chat_id="c").render(summary, context))

    assert "semana 21/10 a 28/10" in text
    assert "Analisados: 40 notícias · 5 oficiais" in text
    assert "Semana &lt;agitada&gt;" in text
    assert "<b>1.</b> ⚖️ [Regulação] <b>Edital</b>\nResumo: Afeta tudo" in text
    assert 'Fonte: <a href="https://gov.br/aneel?a=1&amp;b=2">ANEEL</a>' in text
    assert "<b>2.</b> 📰 [Geral] <b>Sem fonte</b>" in text
    assert "🤖 <b>IA</b>\nResumo: Data centers" in text
    assert "★" not in text and "Por que importa" not in text
    assert text.index("Edital") < text.index("Sem fonte")
    assert "👀 <b>Para acompanhar</b>" in text


def test_render_caps_sources_per_item(now):
    sources = [SourceRef(outlet=f"Veículo {index}", url=f"https://example.com/{index}") for index in range(6)]
    summary = WeeklySummary(ranking=[RankedItem(rank=1, title="Fato", importance=4, sources=sources)])
    context = DeliveryContext(now - timedelta(days=7), now)

    text = "\n".join(TelegramOutput(token="t", chat_id="c").render(summary, context))

    assert "Veículo 2</a> e mais 3" in text
    assert "Veículo 3" not in text


def test_send_errors_never_include_the_token(monkeypatch):
    import pytest
    import requests

    def fail(url, **kwargs):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(requests, "post", fail)
    with pytest.raises(RuntimeError) as error:
        TelegramOutput(token="123:SECRET", chat_id="c")._send_message("oi")
    assert "SECRET" not in str(error.value)
    assert error.value.__cause__ is None


def test_pack_blocks_splits_without_breaking_blocks():
    blocks = ["a" * 30, "b" * 30, "c" * 30]
    assert pack_blocks(blocks, max_length=65) == ["a" * 30 + "\n\n" + "b" * 30, "c" * 30]


def test_pack_blocks_truncates_oversized_block_on_line_boundary():
    block = "título\n" + '<a href="https://x">link</a>\n' * 10
    [message] = pack_blocks([block], max_length=80)
    assert message.endswith("\n…")
    assert message.count("<a ") == message.count("</a>")
