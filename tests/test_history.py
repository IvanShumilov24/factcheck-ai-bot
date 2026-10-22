from datetime import UTC, datetime

from app.bot.keyboards import history_keyboard
from app.database.models import (
    CheckModel,
    ClaimModel,
    EvidenceModel,
    SourceModel,
    VerdictModel,
)
from app.domain.enums import EvidenceDirectness, EvidenceRelation, EvidenceScope
from app.domain.schemas import Evidence
from app.domain.verdict import Verdict
from app.services.history import (
    format_history_datetime,
    parse_details_callback,
    parse_history_callback,
)
from app.services.report import (
    format_claim_report,
    format_saved_check,
    format_saved_details,
    format_saved_details_page,
    format_saved_evidence,
    format_saved_sources,
)


def test_history_callback_is_short_and_strictly_validated() -> None:
    assert parse_history_callback("history:page:2") == ("page", 2)
    assert parse_history_callback("history:view:42") == ("view", 42)
    assert parse_history_callback("history:details:42") == ("details", 42)
    assert parse_history_callback("history:result:42") == ("result", 42)
    assert parse_history_callback("history:view:42:extra") is None
    assert parse_history_callback("history:view:-1") is None
    assert parse_history_callback("history:view:SELECT") is None


def test_history_keyboard_contains_only_navigation_and_menu() -> None:
    keyboard = history_keyboard(page=1, has_previous=True, has_next=True)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert labels == ["◀️ Назад", "Вперёд ▶️", "🏠 В меню"]
    assert all("Открыть проверку" not in label for label in labels)


def test_history_datetime_handles_aware_and_naive_values() -> None:
    aware = format_history_datetime(datetime(2026, 10, 15, 19, 30, tzinfo=UTC))
    naive = format_history_datetime(datetime(2026, 10, 15, 19, 30))
    assert aware == naive
    assert aware.startswith("15.10.2026 ")
    assert aware.endswith(":30")


def test_saved_report_contains_special_characters_and_verdict() -> None:
    check = CheckModel(id=42)
    claim = ClaimModel(id=7, claim_order=0, text="Проверить <мнение> & детали")
    claim.verdict = VerdictModel(
        status="INSUFFICIENT_EVIDENCE",
        confidence=0.2,
        short_reason="Недостаточно данных.",
        detailed_reason="Источников недостаточно.",
    )
    check.claims = [claim]
    report = format_saved_check(check)[0]
    assert "Проверить <мнение> & детали" in report
    assert "ДАННЫХ НЕДОСТАТОЧНО" in report


def test_live_report_does_not_expose_uncalibrated_percentage() -> None:
    verdict = Verdict(
        claim_id="claim-1",
        status="CONTRADICTED",
        confidence=0.9,
        short_reason="Есть прямое опровержение.",
        detailed_reason="Основание ограничено доступными источниками.",
    )
    evidence = Evidence(
        claim_id="claim-1",
        source_id="source-1",
        source_url="https://example.com/source",
        source_title="Источник",
        evidence_text="Текст доказательства",
        evidence_summary="Краткое доказательство",
        relation=EvidenceRelation.CONTRADICTS,
        directness=EvidenceDirectness.DIRECT,
        scope=EvidenceScope.CLAIM_SPECIFIC,
    )
    report = format_claim_report("Проверяемое утверждение", verdict, [evidence], [])
    assert "90%" not in report
    assert "Надёжность вывода: высокое" in report
    assert "Доказательства:" not in report
    assert "Источники:" not in report


def test_compact_report_does_not_repeat_verdict_explanation() -> None:
    verdict = Verdict(
        claim_id="claim-1",
        status="CONFIRMED",
        confidence=0.9,
        short_reason="Утверждение подтверждается.",
        detailed_reason="Утверждение подтверждается. Техническая детализация.",
    )
    report = format_claim_report("Текст утверждения", verdict, [], [])
    assert report.count("Утверждение подтверждается.") == 1
    assert "Техническая детализация" not in report


def test_report_hides_internal_scope_names() -> None:
    verdict = Verdict(
        claim_id="claim-1",
        status="PARTIALLY_CONFIRMED",
        confidence=0.4,
        short_reason="Подтверждена только часть утверждения.",
        detailed_reason="",
        supported_summary="Косвенно поддерживается польза физической активности.",
        unresolved_summary="Не установлен дополнительный эффект открытого воздуха.",
    )
    report = format_claim_report("Прогулки полезны", verdict, [], [])
    assert "ОБЩАЯ ПОПУЛЯЦИЯ" not in report
    assert "ОБ АЛКОГОЛЕ В ЦЕЛОМ" not in report
    assert "Краткий вывод:" not in report


def test_all_saved_evidence_and_sources_are_available_without_external_calls() -> None:
    check = CheckModel(id=7)
    claim = ClaimModel(id=8, claim_order=0, text="Проверяемый текст")
    first_source = SourceModel(
        id=1,
        title="Первый источник",
        url="https://example.com/one",
        content_status="CONTENT_EXTRACTED",
        relevance_score=0.9,
    )
    second_source = SourceModel(
        id=2,
        title="Второй источник",
        url="https://example.com/two",
        content_status="EMPTY",
        relevance_score=0.2,
    )
    claim.sources = [first_source, second_source]
    claim.evidence = [
        EvidenceModel(
            source_id=1,
            evidence_text="Первое доказательство",
            evidence_summary="Первое краткое доказательство",
            relation="SUPPORTS",
            directness="DIRECT",
            scope="CLAIM_SPECIFIC",
            usable=True,
        ),
        EvidenceModel(
            source_id=2,
            evidence_text="Второе доказательство",
            evidence_summary="Второе краткое доказательство",
            relation="SUPPORTS",
            directness="INDIRECT",
            scope="GENERAL_POPULATION",
            usable=True,
        ),
    ]
    check.claims = [claim]
    evidence_report = format_saved_evidence(check)
    source_report = format_saved_sources(check)
    assert "Первое краткое доказательство" in evidence_report
    assert "Второе краткое доказательство" in evidence_report
    assert "Прямо относится к утверждению" in evidence_report
    assert "Косвенно поддерживает вывод" in evidence_report
    assert "Первый источник" in source_report and "Второй источник" in source_report
    assert "содержимое недоступно для анализа" in source_report


def test_saved_details_pair_each_evidence_with_its_source() -> None:
    check = CheckModel(id=7)
    claim = ClaimModel(id=8, claim_order=0, text="Проверяемый текст")
    source = SourceModel(
        id=1,
        title="Источник о проверяемой теме",
        url="https://example.com/source",
        content_status="CONTENT_EXTRACTED",
    )
    claim.sources = [source]
    claim.evidence = [
        EvidenceModel(
            source_id=1,
            evidence_text="Фрагмент",
            evidence_summary="Краткое доказательство",
            relation="SUPPORTS",
            directness="INDIRECT",
            scope="GENERAL_POPULATION",
            usable=True,
        )
    ]
    check.claims = [claim]
    report = format_saved_details(check)
    assert "Краткое доказательство" in report
    assert "Источник о проверяемой теме" in report
    assert "https://example.com/source" in report


def test_details_separate_source_quality_from_evidence_strength() -> None:
    check = CheckModel(id=8)
    claim = ClaimModel(id=9, claim_order=0, text="Проверяемое утверждение")
    official = SourceModel(
        id=1,
        title="Официальные рекомендации",
        url="https://who.int/guideline",
        domain="who.int",
        source_type="OFFICIAL",
        authority_level="HIGH",
        relevance_score=0.9,
        content_status="CONTENT_EXTRACTED",
    )
    secondary = SourceModel(
        id=2,
        title="Вторичный материал",
        url="https://example.com/blog",
        domain="example.com",
        source_type="BLOG",
        authority_level="LOW",
        relevance_score=0.3,
        content_status="CONTENT_EXTRACTED",
    )
    claim.sources = [official, secondary]
    claim.evidence = [
        EvidenceModel(
            source_id=1,
            evidence_text="Официальный фрагмент",
            evidence_summary="Прямой вывод из рекомендаций",
            relation="SUPPORTS",
            evidence_strength="STRONG",
            directness="DIRECT",
            scope="CLAIM_SPECIFIC",
            usable=True,
        ),
        EvidenceModel(
            source_id=2,
            evidence_text="Вторичный фрагмент",
            evidence_summary="Косвенное наблюдение",
            relation="SUPPORTS",
            evidence_strength="WEAK",
            directness="INDIRECT",
            scope="GENERAL_POPULATION",
            usable=True,
        ),
    ]
    check.claims = [claim]

    report = format_saved_details(check)

    assert "Тип: официальный источник" in report
    assert "Авторитетность: высокая" in report
    assert "Тип: блог/вторичный материал" in report
    assert "Авторитетность: низкая" in report
    assert "Сила фрагмента: высокая" in report
    assert "Сила фрагмента: низкая" in report


def test_details_merge_repeated_limitations() -> None:
    check = CheckModel(id=10)
    claim = ClaimModel(id=11, claim_order=0, text="Утверждение")
    source = SourceModel(id=1, title="Источник", url="https://example.com")
    claim.sources = [source]
    claim.evidence = [
        EvidenceModel(
            source_id=1,
            evidence_text="Текст",
            evidence_summary="Кратко",
            relation="SUPPORTS",
            evidence_strength="MODERATE",
            directness="DIRECT",
            scope="CLAIM_SPECIFIC",
            usable=True,
            limitations=[
                "Вывод основан на коротком фрагменте.",
                "Вывод основан на коротком фрагменте",
                "Выборка ограничена взрослыми участниками.",
            ],
        )
    ]
    check.claims = [claim]

    report = format_saved_details(check)

    assert report.count("Вывод основан на коротком фрагменте") == 1
    assert "Выборка ограничена взрослыми участниками." in report


def test_details_group_useful_evidence_before_background() -> None:
    check = CheckModel(id=12)
    claim = ClaimModel(id=13, claim_order=0, text="Утверждение")
    source = SourceModel(id=1, title="Источник", url="https://example.com")
    claim.sources = [source]
    claim.evidence = [
        EvidenceModel(
            source_id=1,
            evidence_text="Фон",
            evidence_summary="Фоновая информация",
            relation="NEUTRAL",
            evidence_strength="UNKNOWN",
            directness="BACKGROUND",
            scope="GENERAL_POPULATION",
            usable=True,
        ),
        EvidenceModel(
            source_id=1,
            evidence_text="Прямой вывод",
            evidence_summary="Полезное доказательство",
            relation="SUPPORTS",
            evidence_strength="STRONG",
            directness="DIRECT",
            scope="CLAIM_SPECIFIC",
            usable=True,
        ),
    ]
    check.claims = [claim]

    report = format_saved_details(check)

    assert report.index("Полезное доказательство") < report.index("Фоновая информация")


def test_details_paginate_and_keep_unavailable_sources_on_last_page() -> None:
    check = CheckModel(id=14)
    claim = ClaimModel(id=15, claim_order=0, text="Утверждение")
    source = SourceModel(id=1, title="Изученный источник", url="https://example.com")
    unavailable = SourceModel(
        id=2,
        title="Недоступная страница",
        url="https://example.com/captcha",
        content_status="CAPTCHA",
    )
    claim.sources = [source, unavailable]
    claim.evidence = [
        EvidenceModel(
            source_id=1,
            evidence_text=f"Текст {index}",
            evidence_summary=f"Карточка {index}",
            relation="SUPPORTS",
            evidence_strength="MODERATE",
            directness="DIRECT",
            scope="CLAIM_SPECIFIC",
            usable=True,
        )
        for index in range(1, 5)
    ]
    check.claims = [claim]

    first, has_next = format_saved_details_page(check, 0)
    last, last_has_next = format_saved_details_page(check, 1)

    assert has_next is True
    assert last_has_next is False
    assert "Карточка 1" in first and "Карточка 4" not in first
    assert "Карточка 4" in last
    assert "Недоступная страница" in last
    assert "доступ заблокирован проверкой CAPTCHA" in last
    assert last.count("Суть:") == 1
    assert len(first) <= 3900
    assert len(last) <= 3900


def test_details_callback_supports_legacy_and_paginated_buttons() -> None:
    assert parse_details_callback("history:details:42") == (42, 0)
    assert parse_details_callback("history:details:42:3") == (42, 3)
    assert parse_details_callback("history:details:-1:3") is None
    assert parse_details_callback("history:details:42:3:4") is None
