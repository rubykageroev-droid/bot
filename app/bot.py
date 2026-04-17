from __future__ import annotations

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.config import Settings
from app.db import Database
from app.keyboards import goal_keyboard, match_keyboard, menu_keyboard, pref_keyboard, rate_keyboard

CHOOSE_GOAL, PHOTO, AGE, BIO, PREF = range(5)


class DatingBot:
    def __init__(self, settings: Settings) -> None:
        self.db = Database(settings.db_path)
        self.app = Application.builder().token(settings.bot_token).build()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        registration = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                CHOOSE_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.choose_goal)],
                PHOTO: [MessageHandler(filters.PHOTO, self.get_photo)],
                AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_age)],
                BIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_bio)],
                PREF: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_pref)],
            },
            fallbacks=[CommandHandler("start", self.start)],
        )
        self.app.add_handler(registration)

        self.app.add_handler(MessageHandler(filters.Regex("^👀 Смотреть анкеты$"), self.show_next_profile))
        self.app.add_handler(MessageHandler(filters.Regex("^📊 Мой профиль$"), self.my_profile))
        self.app.add_handler(MessageHandler(filters.Regex("^🔥 Кто меня лайкнул$"), self.who_liked))
        self.app.add_handler(MessageHandler(filters.Regex("^⚙️ Настройки$"), self.settings_menu))
        self.app.add_handler(CallbackQueryHandler(self.rate_callback, pattern=r"^rate:"))
        self.app.add_handler(CallbackQueryHandler(self.close_match, pattern=r"^match:close$"))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user = update.effective_user
        if not user:
            return ConversationHandler.END
        self.db.upsert_user(user.id)
        await update.effective_message.reply_text("Привет 👋\nЗачем ты здесь?", reply_markup=goal_keyboard())
        return CHOOSE_GOAL

    async def choose_goal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        choice = update.message.text.strip()
        goal_map = {"💘 Знакомства": "dating", "🔥 Оценка внешности": "rating"}
        if choice not in goal_map:
            await update.message.reply_text("Выбери цель кнопкой ниже 👇", reply_markup=goal_keyboard())
            return CHOOSE_GOAL

        self.db.upsert_user(update.effective_user.id, goal=goal_map[choice])
        await update.message.reply_text("Отправь своё фото 📸", reply_markup=ReplyKeyboardRemove())
        return PHOTO

    async def get_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        photo_id = update.message.photo[-1].file_id
        self.db.upsert_user(update.effective_user.id, photo_id=photo_id)
        await update.message.reply_text("Сколько тебе лет?")
        return AGE

    async def get_age(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text.strip()
        if not text.isdigit() or not 18 <= int(text) <= 99:
            await update.message.reply_text("Введи возраст числом от 18 до 99.")
            return AGE

        self.db.upsert_user(update.effective_user.id, age=int(text))
        await update.message.reply_text("Напиши коротко о себе (или отправь '-')")
        return BIO

    async def get_bio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        bio = update.message.text.strip()
        if bio == "-":
            bio = ""
        self.db.upsert_user(update.effective_user.id, bio=bio)
        await update.message.reply_text("Кого хочешь видеть?", reply_markup=pref_keyboard())
        return PREF

    async def get_pref(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        pref = update.message.text.strip()
        if pref not in {"Парней", "Девушек", "Всех"}:
            await update.message.reply_text("Выбери вариант кнопкой 👇", reply_markup=pref_keyboard())
            return PREF

        self.db.upsert_user(update.effective_user.id, gender_pref=pref)
        await update.message.reply_text("Анкета создана ✅", reply_markup=menu_keyboard())
        return ConversationHandler.END

    async def show_next_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        tg_id = update.effective_user.id
        if not self.db.has_complete_profile(tg_id):
            await update.message.reply_text("Сначала заверши анкету через /start")
            return

        viewer = self.db.get_user_by_telegram(tg_id)
        if self.db.daily_actions_count(viewer["id"]) >= 20:
            await update.message.reply_text("Лимит достигнут 😢")
            return

        candidate = self.db.pick_candidate(tg_id)
        if not candidate:
            await update.message.reply_text("Пока анкеты закончились, загляни позже ✨")
            return

        self.db.mark_view(viewer["id"], candidate["id"])
        caption = f"Возраст: {candidate['age']}\n\n{candidate['bio'] or 'Без описания'}"
        await update.message.reply_photo(photo=candidate["photo_id"], caption=caption, reply_markup=rate_keyboard(candidate["id"]))

    async def rate_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        _, candidate_id, reaction = query.data.split(":")
        candidate_id = int(candidate_id)

        from_user = self.db.get_user_by_telegram(update.effective_user.id)
        if self.db.daily_actions_count(from_user["id"]) >= 20:
            await query.message.reply_text("Лимит достигнут 😢")
            return

        matched = self.db.save_reaction(from_user["id"], candidate_id, reaction)
        if matched:
            candidate = self.db.get_user_by_id(candidate_id)
            await query.message.reply_text(
                "🔥 Взаимная симпатия!",
                reply_markup=match_keyboard(candidate["telegram_id"]),
            )

        await query.edit_message_reply_markup(reply_markup=None)

    async def my_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = self.db.get_user_by_telegram(update.effective_user.id)
        if not user or not user["photo_id"]:
            await update.message.reply_text("Анкета не заполнена. Нажми /start")
            return

        stats = self.db.profile_stats(user["id"])
        total_votes = stats["likes"] + stats["dislikes"]
        like_percent = int((stats["likes"] / total_votes) * 100) if total_votes else 0

        caption = (
            f"Возраст: {user['age']}\n"
            f"О себе: {user['bio'] or '—'}\n\n"
            f"👍 % лайков: {like_percent}%\n"
            f"👀 Показов: {stats['views']}\n"
            f"❤️ Лайков: {stats['likes']}\n"
            f"⭐ Рейтинг: {user['rating']}"
        )
        await update.message.reply_photo(user["photo_id"], caption=caption, reply_markup=menu_keyboard())

    async def who_liked(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = self.db.get_user_by_telegram(update.effective_user.id)
        if not user:
            await update.message.reply_text("Анкета не заполнена. Нажми /start")
            return

        count = self.db.count_likes_to_user(user["id"])
        await update.message.reply_text(f"Тебя лайкнули {count} человек 👀\nПрофили скрыты.")

    async def settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "⚙️ Настройки:\n"
            "• Изменить анкету — /start\n"
            "• Сменить цель — /start\n"
            "• Кого показывать — /start"
        )

    async def close_match(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=None)

    def run(self) -> None:
        self.app.run_polling()
