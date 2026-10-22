from collections.abc import Sequence
from difflib import SequenceMatcher

from app.database.models import CheckModel, EvidenceModel, SourceModel
from app.domain.schemas import Evidence, Source
from app.domain.verdict import Verdict

DETAILS_PAGE_SIZE = 3


def format_claim_report(
    claim_text: str,
    verdict: Verdict,
    evidence: Sequence[Evidence],
    sources: Sequence[Source],
) -> str:
    usable_evidence = [item for item in evidence if item.usable]
    lines = [
        "📋 Результат проверки",
        "",
        _compact_text(claim_text, 500),
        "",
        f"{_verdict_icon(verdict.status.value)} {verdict_label(verdict.status.value)}",
        "",
        _compact_text(verdict.short_reason, 700),
        "",
        f"Надёжность вывода: {confidence_label(verdict.confidence, usable_evidence)}",
    ]
    lines.extend(
        [
            "",
            "Важно: это информационная проверка, а не диагноз и не медицинская рекомендация.",
        ]
    )
    return "\n".join(lines)[:3900]


def format_saved_check(check: CheckModel) -> list[str]:
    messages: list[str] = []
    for claim in sorted(check.claims, key=lambda item: item.claim_order):
        verdict = claim.verdict
        if verdict is None:
            messages.append(f"📋 Результат проверки\n\n{claim.text}\n\n🟡 ДАННЫХ НЕДОСТАТОЧНО")
            continue
        lines = [
            "📋 Сохранённый результат проверки",
            "",
            _compact_text(claim.text, 500),
            "",
            f"{_verdict_icon(verdict.status)} {verdict_label(verdict.status)}",
            "",
            _compact_text(verdict.short_reason, 700),
            "",
            f"Надёжность вывода: {confidence_label(verdict.confidence, claim.evidence)}",
        ]
        lines.extend(
            [
                "",
                "Важно: это информационная проверка, а не диагноз и не медицинская рекомендация.",
            ]
        )
        messages.append("\n".join(lines))
    return messages or ["В сохранённой проверке нет утверждений."]


def format_saved_evidence(check: CheckModel) -> str:
    lines = ["📚 Все доказательства", ""]
    for claim in sorted(check.claims, key=lambda item: item.claim_order):
        lines.extend([f"Утверждение: {claim.text}", ""])
        usable = _unique_model_evidence([item for item in claim.evidence if item.usable])
        if not usable:
            lines.append("Доступных доказательств нет.")
        for item in usable:
            lines.extend(
                _format_evidence_lines(
                    item.relation,
                    item.directness,
                    item.evidence_summary or item.evidence_text,
                )
            )
            if item.scope != "CLAIM_SPECIFIC":
                lines.append(
                    "  Ограничение: источник рассматривает более общий или иной аспект темы."
                )
            for limitation in (item.limitations or [])[:2]:
                lines.append(f"  Ограничение: {limitation}")
        lines.append("")
    return "\n".join(lines).strip() or "📚 Доказательства не найдены."


def format_saved_details(check: CheckModel) -> str:
    pages: list[str] = []
    page = 0
    while True:
        text, has_next = format_saved_details_page(check, page)
        pages.append(text)
        if not has_next:
            return "\n\n".join(pages)
        page += 1


def format_saved_details_page(check: CheckModel, page: int) -> tuple[str, bool]:
    lines = ["📚 Доказательства и источники", ""]
    cards: list[tuple[tuple[int, int, int, int], str]] = []
    unavailable: list[SourceModel] = []
    for claim in sorted(check.claims, key=lambda item: item.claim_order):
        sources = {source.id: source for source in claim.sources}
        evidence = sorted(
            _unique_model_evidence(claim.evidence),
            key=_evidence_sort_key,
        )
        for item in evidence:
            cards.append(
                (
                    _evidence_sort_key(item),
                    _format_detail_card(claim.text, item, sources.get(item.source_id)),
                )
            )
        unavailable.extend(
            [
                source
                for source in _unique_model_sources(claim.sources)
                if source.content_status != "CONTENT_EXTRACTED"
            ]
        )
    start = max(page, 0) * DETAILS_PAGE_SIZE
    cards.sort(key=lambda item: item[0])
    page_cards = cards[start : start + DETAILS_PAGE_SIZE]
    has_next = start + DETAILS_PAGE_SIZE < len(cards)
    if not page_cards:
        lines.append("Доказательства не найдены.")
    else:
        lines.append(f"Страница {page + 1}")
        lines.append("")
        for _, card in page_cards:
            lines.extend([card, ""])
    if not has_next and unavailable:
        lines.extend(["Найденные, но не изученные источники:"])
        for source in _unique_model_sources(unavailable):
            title = source.title or "Название не указано"
            url = source.url or "URL не указан"
            lines.append(f"• {title}: {url}")
            lines.append(f"  Статус: {_source_status_label(source.content_status)}.")
        lines.append("")
    return "\n".join(lines).strip() or "📚 Доказательства и источники не найдены.", has_next


def _format_detail_card(
    claim_text: str, evidence: EvidenceModel, source: SourceModel | None
) -> str:
    lines = [f"Утверждение: {_compact_text(claim_text, 260)}", _evidence_group_label(evidence)]
    lines.append(f"Связь: {directness_label(evidence.directness)}.")
    summary = evidence.evidence_summary or evidence.evidence_text
    lines.append(f"Суть: {_compact_text(summary, 420)}")
    lines.append(f"Сила фрагмента: {_strength_label(evidence.evidence_strength)}.")
    if not evidence.usable:
        lines.append("Статус: не используется в итоговом verdict.")
    if source is None:
        lines.append("Источник: данные об источнике недоступны.")
    else:
        title = source.title or "Название не указано"
        url = source.url or "URL не указан"
        lines.append(f"Источник: {title}")
        lines.append(f"Домен: {source.domain or 'домен не указан'}")
        lines.append(f"Тип: {_source_type_label(source.source_type)}")
        lines.append(f"Авторитетность: {_authority_label(source.authority_level)}")
        lines.append(f"Качество источника: {_relevance_label(source.quality_score)}")
        lines.append(f"Соответствие теме: {_relevance_label(source.relevance_score)}")
        lines.append(f"Статус: {_source_status_label(source.content_status)}")
        lines.append(f"Ссылка: {url}")
    limitations = list(evidence.limitations or [])
    if evidence.scope != "CLAIM_SPECIFIC":
        limitations.append("Источник рассматривает более общий или иной аспект темы.")
    merged = _merge_limitations(limitations)
    if merged:
        lines.append(f"Ограничение: {merged}")
    return "\n".join(lines)


def format_saved_sources(check: CheckModel) -> str:
    lines = ["🔗 Все источники", ""]
    seen: set[str] = set()
    for claim in sorted(check.claims, key=lambda item: item.claim_order):
        for source in _unique_model_sources(claim.sources):
            if source.url in seen:
                continue
            seen.add(source.url)
            status = source.content_status
            if status in {
                "NOT_FETCHED",
                "CAPTCHA",
                "EMPTY",
                "ERROR",
                "BLOCKED",
                "UNSUPPORTED",
            }:
                explanation = "содержимое недоступно для анализа"
            else:
                explanation = f"соответствие: {_relevance_label(source.relevance_score)}"
            lines.append(f"• {source.title}: {source.url}\n  {explanation}")
    return "\n".join(lines).strip() or "🔗 Источники не найдены."


def _unique_evidence(items: Sequence[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, str]] = set()
    result: list[Evidence] = []
    for item in items:
        key = (item.source_id, item.evidence_text.strip())
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _unique_sources(items: Sequence[Source]) -> list[Source]:
    seen: set[str] = set()
    result: list[Source] = []
    for item in items:
        key = str(item.url)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _unique_model_evidence(items: Sequence[EvidenceModel]) -> list[EvidenceModel]:
    seen: set[tuple[object, object]] = set()
    result: list[EvidenceModel] = []
    for item in items:
        key = (getattr(item, "source_id", None), getattr(item, "evidence_text", None))
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _unique_model_sources(items: Sequence[SourceModel]) -> list[SourceModel]:
    seen: set[str] = set()
    result: list[SourceModel] = []
    for item in items:
        key = str(getattr(item, "url", ""))
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _evidence_sort_key(item: EvidenceModel) -> tuple[int, int, int, int]:
    directness = getattr(item, "directness", "")
    relation = getattr(item, "relation", "")
    relation_rank = {
        "SUPPORTS": 0,
        "CONTRADICTS": 1,
        "NEUTRAL": 2,
    }.get(str(relation), 3)
    directness_rank = {
        "DIRECT": 0,
        "INDIRECT": 1,
        "BACKGROUND": 2,
        "NOT_RELEVANT": 3,
    }.get(str(directness), 4)
    usable_rank = 0 if getattr(item, "usable", False) else 1
    strength_rank = {
        "STRONG": 0,
        "MODERATE": 1,
        "WEAK": 2,
        "UNKNOWN": 3,
    }.get(str(getattr(item, "evidence_strength", "UNKNOWN")), 3)
    return (relation_rank, directness_rank, usable_rank, strength_rank)


def _relevance_label(score: float | None) -> str:
    if score is None:
        return "не определено"
    if score >= 0.75:
        return "высокое"
    if score >= 0.5:
        return "умеренное"
    return "ограниченное"


def _evidence_group_label(evidence: EvidenceModel) -> str:
    if evidence.directness == "BACKGROUND":
        return "ℹ️ Фоновая информация"
    if evidence.directness == "NOT_RELEVANT":
        return "⚪ Не относится напрямую"
    return {
        "SUPPORTS": "✅ Поддерживает утверждение",
        "CONTRADICTS": "⚠️ Противоречит утверждению",
        "NEUTRAL": "ℹ️ Нейтральный контекст",
    }.get(evidence.relation, "ℹ️ Связь не определена")


def _strength_label(value: str) -> str:
    return {
        "STRONG": "высокая",
        "MODERATE": "умеренная",
        "WEAK": "низкая",
        "UNKNOWN": "не определена",
    }.get(value, "не определена")


def _source_type_label(value: str) -> str:
    return {
        "OFFICIAL": "официальный источник",
        "GUIDELINE": "рекомендации/руководство",
        "SYSTEMATIC_REVIEW": "систематический обзор",
        "META_ANALYSIS": "метаанализ",
        "PEER_REVIEWED_STUDY": "рецензируемое исследование",
        "MEDICAL_PUBLICATION": "медицинская публикация",
        "NEWS": "новостной материал",
        "BLOG": "блог/вторичный материал",
        "COMMERCIAL": "коммерческий материал",
        "SOCIAL": "социальные сети",
        "UNKNOWN": "тип не указан",
    }.get(value, "тип не указан")


def _authority_label(value: str) -> str:
    return {
        "HIGH": "высокая",
        "MEDIUM": "средняя",
        "LOW": "низкая",
        "UNKNOWN": "не определена",
    }.get(value, "не определена")


def _source_status_label(value: str) -> str:
    return {
        "CONTENT_EXTRACTED": "текст извлечён и проанализирован",
        "FETCHED": "страница загружена, но текст ещё не извлечён",
        "NOT_FETCHED": "страница не загружена",
        "CAPTCHA": "доступ заблокирован проверкой CAPTCHA",
        "EMPTY": "текст не извлечён",
        "BLOCKED": "доступ заблокирован",
        "UNSUPPORTED": "формат не поддержан",
        "ERROR": "произошла ошибка извлечения",
    }.get(value, "обработка не завершена")


def _merge_limitations(values: Sequence[str]) -> str:
    unique: list[str] = []
    for value in values:
        normalized = " ".join(value.split())
        if not normalized:
            continue
        if any(
            normalized.casefold() == existing.casefold()
            or SequenceMatcher(None, normalized.casefold(), existing.casefold()).ratio() >= 0.92
            for existing in unique
        ):
            continue
        unique.append(_compact_text(normalized, 260))
        if len(unique) == 2:
            break
    return "; ".join(unique)


def verdict_label(value: str) -> str:
    return {
        "CONFIRMED": "ПОДТВЕРЖДАЕТСЯ",
        "PARTIALLY_CONFIRMED": "ЧАСТИЧНО ПОДТВЕРЖДАЕТСЯ",
        "NOT_SUPPORTED": "НЕ ПОДТВЕРЖДАЕТСЯ",
        "CONTRADICTED": "НЕ ПОДТВЕРЖДАЕТСЯ",
        "INSUFFICIENT_EVIDENCE": "ДАННЫХ НЕДОСТАТОЧНО",
        "CONFLICTING_EVIDENCE": "ДАННЫЕ ПРОТИВОРЕЧИВЫ",
    }.get(value, value)


def _verdict_icon(value: str) -> str:
    return {
        "CONFIRMED": "🟢",
        "PARTIALLY_CONFIRMED": "🟡",
        "NOT_SUPPORTED": "🔴",
        "CONTRADICTED": "🔴",
        "INSUFFICIENT_EVIDENCE": "🟡",
        "CONFLICTING_EVIDENCE": "🟠",
    }.get(value, "ℹ️")


def confidence_label(confidence: float, evidence: Sequence[object]) -> str:
    """Show a cautious qualitative signal, not an uncalibrated probability."""
    if not evidence or confidence < 0.6:
        return "ограниченное"
    has_direct_evidence = any(
        getattr(getattr(item, "directness", None), "value", getattr(item, "directness", None))
        == "DIRECT"
        for item in evidence
    )
    if confidence >= 0.8 and has_direct_evidence:
        return "высокое"
    return "умеренное"


def relation_label(value: str) -> str:
    return {
        "SUPPORTS": "Поддерживает утверждение",
        "CONTRADICTS": "Противоречит утверждению",
        "NEUTRAL": "Нейтральный контекст",
    }.get(value, value)


def directness_label(value: str) -> str:
    return {
        "DIRECT": "Прямо относится к утверждению",
        "INDIRECT": "Косвенно поддерживает вывод",
        "BACKGROUND": "Фоновая информация, не доказательство",
        "NOT_RELEVANT": "Не относится напрямую к утверждению",
    }.get(value, value)


def _format_evidence_lines(relation: str, directness: str, summary: str) -> list[str]:
    return [
        f"• {relation_label(relation)}",
        f"  Связь: {directness_label(directness)}.",
        f"  Суть: {summary}",
    ]


def _compact_text(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else f"{value[: limit - 1]}…"
