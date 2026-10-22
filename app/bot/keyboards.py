from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Проверить информацию", callback_data="check")],
            [InlineKeyboardButton(text="🕘 История проверок", callback_data="history:page:0")],
            [InlineKeyboardButton(text="📚 Как проверять самому", callback_data="education")],
            [InlineKeyboardButton(text="ℹ️ О проекте", callback_data="about")],
        ]
    )


def education_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"education:{page - 1}")
        )
    if page + 1 < total:
        navigation.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"education:{page + 1}")
        )
    rows = [navigation] if navigation else []
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="about")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_keyboard(page: int, has_previous: bool, has_next: bool) -> InlineKeyboardMarkup:
    navigation: list[InlineKeyboardButton] = []
    if has_previous:
        navigation.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"history:page:{page - 1}")
        )
    if has_next:
        navigation.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"history:page:{page + 1}")
        )
    rows = [navigation] if navigation else []
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="about")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_item_keyboard(check_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"Открыть проверку №{check_id}", callback_data=f"history:view:{check_id}"
            )
        ]
        for check_id in check_ids
    ]
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="about")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def result_actions_keyboard(check_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📚 Доказательства и источники",
                    callback_data=f"history:details:{check_id}",
                ),
            ],
            [
                InlineKeyboardButton(text="🔍 Проверить ещё", callback_data="check"),
                InlineKeyboardButton(text="🏠 В меню", callback_data="about"),
            ],
        ]
    )


def followup_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Проверить ещё", callback_data="check"),
                InlineKeyboardButton(text="🏠 В меню", callback_data="about"),
            ]
        ]
    )


def details_keyboard(
    check_id: int, page: int, has_previous: bool, has_next: bool
) -> InlineKeyboardMarkup:
    navigation: list[InlineKeyboardButton] = []
    if has_previous:
        navigation.append(
            InlineKeyboardButton(
                text="◀️ Назад", callback_data=f"history:details:{check_id}:{page - 1}"
            )
        )
    if has_next:
        navigation.append(
            InlineKeyboardButton(
                text="Вперёд ▶️", callback_data=f"history:details:{check_id}:{page + 1}"
            )
        )
    rows = [navigation] if navigation else []
    rows.append(
        [
            InlineKeyboardButton(
                text="◀️ Назад к результату", callback_data=f"history:result:{check_id}"
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="🔍 Проверить ещё", callback_data="check"),
            InlineKeyboardButton(text="🏠 В меню", callback_data="about"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
