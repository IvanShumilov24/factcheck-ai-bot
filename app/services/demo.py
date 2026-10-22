"""Deterministic demo response that does not depend on external services."""

from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards import followup_actions_keyboard

DEMO_REPORT = """🧪 Демонстрационный результат

Утверждение:
Антибиотики лечат вирусную простуду.

❌ НЕ ПОДТВЕРЖДАЕТСЯ

Антибиотики действуют на бактерии, а не на вирусы. При обычной вирусной простуде
они не лечат причину заболевания и не должны приниматься без назначения врача.

Надёжность вывода: высокая

📚 Доказательство:
Медицинские рекомендации разделяют бактериальные и вирусные инфекции; антибиотики
неэффективны против вирусов.

🔗 Источник:
WHO — Antimicrobial resistance
https://www.who.int/news-room/fact-sheets/detail/antimicrobial-resistance

Важно: это демонстрационный пример. Бот не ставит диагноз и не заменяет консультацию врача."""


def demo_report() -> str:
    """Return the stable demo text and build only local follow-up controls."""
    return DEMO_REPORT


def demo_keyboard() -> InlineKeyboardMarkup:
    return followup_actions_keyboard()
