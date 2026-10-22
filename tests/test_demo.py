from app.services.demo import demo_keyboard, demo_report


def test_demo_is_deterministic_and_self_contained() -> None:
    report = demo_report()

    assert report == demo_report()
    assert "Демонстрационный результат" in report
    assert "НЕ ПОДТВЕРЖДАЕТСЯ" in report
    assert "антибиотики" in report.casefold()
    assert "Бот не ставит диагноз" in report


def test_demo_keyboard_contains_only_local_actions() -> None:
    callbacks = [
        button.callback_data
        for row in demo_keyboard().inline_keyboard
        for button in row
    ]

    assert callbacks == ["check", "about"]
