from app.bot.keyboards import education_keyboard
from app.services.education import LESSONS, lesson_page


def test_education_contains_five_lessons() -> None:
    assert len(LESSONS) == 5
    assert all(lesson.title and lesson.body for lesson in LESSONS)


def test_education_page_is_bounded() -> None:
    assert lesson_page(-1) == lesson_page(0)
    assert lesson_page(99) == lesson_page(4)


def test_education_keyboard_paginates() -> None:
    first = [
        button.callback_data for row in education_keyboard(0, 5).inline_keyboard for button in row
    ]
    last = [
        button.callback_data for row in education_keyboard(4, 5).inline_keyboard for button in row
    ]

    assert first == ["education:1", "about"]
    assert last == ["education:3", "about"]
