from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup


def goal_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["💘 Знакомства", "🔥 Оценка внешности"]], resize_keyboard=True, one_time_keyboard=True)


def pref_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["Парней", "Девушек", "Всех"]], resize_keyboard=True, one_time_keyboard=True)


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["👀 Смотреть анкеты", "📊 Мой профиль"], ["🔥 Кто меня лайкнул", "⚙️ Настройки"]],
        resize_keyboard=True,
    )


def rate_keyboard(candidate_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👍 Нравится", callback_data=f"rate:{candidate_id}:like")],
            [InlineKeyboardButton("😐 Норм", callback_data=f"rate:{candidate_id}:neutral")],
            [InlineKeyboardButton("👎 Не мой тип", callback_data=f"rate:{candidate_id}:dislike")],
        ]
    )


def match_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    profile_url = f"tg://user?id={telegram_id}"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💬 Открыть профиль", url=profile_url)],
            [InlineKeyboardButton("❌ Закрыть", callback_data="match:close")],
        ]
    )
