from __future__ import annotations

import html
import logging
from typing import Any

import requests

from content_radar.config.settings import settings
from content_radar.config.sources import load_source_config
from content_radar.llm.weekly_summary import SummaryItem, WeeklySummary
from content_radar.outputs.base import DeliveryContext, Output

logger = logging.getLogger(__name__)

# Limite do Telegram e 4096; folga para entidades HTML.
MAX_MESSAGE_LENGTH = 3900
# Links do Google News sao longos; mais que isso estoura o bloco. A lista completa fica no banco.
MAX_SOURCES_PER_ITEM = 3

SOURCE_LABELS = {"news": "notícias", "official": "oficiais", "reddit": "Reddit", "trends": "Trends"}


def _escape(value: str) -> str:
    return html.escape(value, quote=False)


def _format_sources(item: SummaryItem) -> str | None:
    if not item.sources:
        return None
    shown = item.sources[:MAX_SOURCES_PER_ITEM]
    links = [f'<a href="{html.escape(source.url)}">{_escape(source.outlet)}</a>' for source in shown]
    text = "Fonte: " + " · ".join(links)
    hidden = len(item.sources) - len(shown)
    if hidden:
        text += f" e mais {hidden}"
    return text


def _format_item(title_line: str, item: SummaryItem) -> str:
    lines = [title_line]
    if item.why_it_matters:
        lines.append(f"Resumo: {_escape(item.why_it_matters)}")
    sources = _format_sources(item)
    if sources:
        lines.append(sources)
    return "\n".join(lines)


class TelegramOutput(Output):
    name = "telegram"

    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self._token = token or settings.telegram_token
        self._chat_id = chat_id or settings.telegram_chat_id

    def render(self, summary: WeeklySummary, context: DeliveryContext) -> list[str]:
        return pack_blocks(self._build_blocks(summary, context))

    def send(self, summary: WeeklySummary, context: DeliveryContext) -> dict[str, Any]:
        if not self._token or not self._chat_id:
            raise ValueError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID are required")

        messages = self.render(summary, context)
        for message in messages:
            self._send_message(message)
        return {"ok": True, "sent_messages": len(messages)}

    def _send_message(self, text: str) -> None:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={
                    "chat_id": str(self._chat_id).strip(),
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            # A mensagem do requests inclui a URL, que contem o token: nunca deixar chegar ao log.
            raise RuntimeError(f"Telegram request failed: {str(exc).replace(self._token, '<TOKEN>')}") from None
        if not response.ok:
            raise RuntimeError(f"Telegram sendMessage failed ({response.status_code}): {response.text[:300]}")

    def _build_blocks(self, summary: WeeklySummary, context: DeliveryContext) -> list[str]:
        config = load_source_config()
        period = f"{context.period_start:%d/%m} a {context.period_end:%d/%m}"
        counts = " · ".join(
            f"{count} {SOURCE_LABELS.get(source, source)}" for source, count in context.source_counts.items() if count
        )

        header = [f"⚡ <b>Radar do Setor Elétrico</b> — semana {period}"]
        if counts:
            header.append(f"Analisados: {counts}")
        if summary.headline:
            header += ["", f"📌 {_escape(summary.headline)}"]
        blocks = ["\n".join(header)]

        if summary.ranking:
            blocks.append("🏆 <b>Ranking da semana</b>")
            for item in summary.ranking:
                title = (
                    f"<b>{item.rank}.</b> {config.category_emoji(item.category)} "
                    f"[{_escape(config.category_label(item.category))}] <b>{_escape(item.title)}</b>"
                )
                blocks.append(_format_item(title, item))
        else:
            blocks.append("Nenhuma notícia relevante identificada nesta semana.")

        if summary.ai_in_energy:
            blocks.append("🤖 <b>IA no setor elétrico</b>")
            ai_emoji = config.category_emoji("ia")
            for item in summary.ai_in_energy:
                blocks.append(_format_item(f"{ai_emoji} <b>{_escape(item.title)}</b>", item))

        if summary.trends:
            blocks.append("\n".join(["📈 <b>Google Trends</b>", *(f"• {_escape(text)}" for text in summary.trends)]))

        if summary.watchlist_next_week:
            blocks.append(
                "\n".join(["👀 <b>Para acompanhar</b>", *(f"• {_escape(text)}" for text in summary.watchlist_next_week)])
            )

        return blocks


def pack_blocks(blocks: list[str], max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Junta blocos em mensagens de ate max_length sem quebrar um bloco no meio."""
    messages: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > max_length:
            # Cortar no meio de uma tag quebraria o parse HTML do Telegram: corta por linha.
            block = _truncate_by_lines(block, max_length)
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= max_length:
            current = candidate
            continue
        messages.append(current)
        current = block
    if current:
        messages.append(current)
    return messages


def _truncate_by_lines(block: str, max_length: int) -> str:
    kept: list[str] = []
    size = 0
    for line in block.split("\n"):
        if size + len(line) + 2 > max_length:
            break
        kept.append(line)
        size += len(line) + 1
    return "\n".join(kept) + "\n…"
