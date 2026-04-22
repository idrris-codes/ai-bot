import asyncio
import logging
import os
import sqlite3
import time
from contextlib import suppress

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from openai import AsyncOpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini")
DB_PATH = "telegram_ai_bot.db"
MAX_HISTORY_MESSAGES = 16
MAX_TELEGRAM_MESSAGE = 4000
REQUEST_TIMEOUT = 120
AD_FREQUENCY = 6

logging.basicConfig(level=logging.INFO)

TEXTS = {
    "ru": {
        "welcome": "Привет, {name}.\n\nЯ AI-бот. Пиши вопрос прямо в чат.\n\nНиже только нужные функции.",
        "menu": "Главное меню",
        "thinking": "Думаю…",
        "error": "⚠️ Сейчас ИИ временно не ответил. Попробуй ещё раз чуть позже.",
        "empty_history": "История пока пустая.",
        "export_ready": "Готово. Отправляю чат.",
        "choose_style": "Выбери стиль общения:",
        "style_changed": "Стиль общения обновлён ✅",
        "ask_custom_style": "Отправь свой стиль одним сообщением.\n\nПример:\nОтвечай жёстко, кратко и только по сути.",
        "custom_style_saved": "Кастомный стиль сохранён ✅",
        "btn_style": "🎭 Стиль общения",
        "btn_export": "📤 Экспорт чата",
        "btn_back": "⬅️ Назад",
        "btn_precise": "🎯 Точный",
        "btn_short": "✂️ Короткий",
        "btn_teacher": "📘 Понятный",
        "btn_custom": "✍️ Свой стиль",
        "style_precise": "Точный",
        "style_short": "Короткий",
        "style_teacher": "Понятный",
        "style_custom": "Свой стиль",
        "promo_title": "💻 Нужен Telegram-бот или сайт?",
        "promo_text": "Разрабатываю Telegram-ботов и сайты под задачи бизнеса: автоматизация, заявки, AI-функции, лендинги и простые веб-решения.\n\nЕсли нужен проект — пиши разработчику: @idris_codes",
    },
    "en": {
        "welcome": "Hi, {name}.\n\nI am an AI bot. Just send your question.\n\nOnly the needed functions are below.",
        "menu": "Main menu",
        "thinking": "Thinking…",
        "error": "⚠️ AI did not respond right now. Please try again a bit later.",
        "empty_history": "History is empty.",
        "export_ready": "Done. Sending the chat.",
        "choose_style": "Choose communication style:",
        "style_changed": "Communication style updated ✅",
        "ask_custom_style": "Send your custom style in one message.\n\nExample:\nAnswer sharply, briefly, and only to the point.",
        "custom_style_saved": "Custom style saved ✅",
        "btn_style": "🎭 Style",
        "btn_export": "📤 Export chat",
        "btn_back": "⬅️ Back",
        "btn_precise": "🎯 Precise",
        "btn_short": "✂️ Short",
        "btn_teacher": "📘 Clear",
        "btn_custom": "✍️ Custom",
        "style_precise": "Precise",
        "style_short": "Short",
        "style_teacher": "Clear",
        "style_custom": "Custom",
        "promo_title": "💻 Need a Telegram bot or website?",
        "promo_text": "I build Telegram bots and websites for business needs: automation, leads, AI features, landing pages, and simple web solutions.\n\nFor a project, contact the developer: @idris_codes",
    },
}

STYLE_PROMPTS = {
    "precise": {
        "ru": "Отвечай максимально точно и по делу. Без воды. Без приветствий. Без лишних комментариев. Если можно ответить в 1–4 предложениях — отвечай именно так.",
        "en": "Answer as precisely and directly as possible. No fluff. No greetings. No unnecessary commentary. If the answer can fit in 1–4 sentences, do that.",
    },
    "short": {
        "ru": "Отвечай очень кратко. Только суть. Без лишних слов и объяснений.",
        "en": "Answer very briefly. Only the essence. No unnecessary words or explanations.",
    },
    "teacher": {
        "ru": "Отвечай понятно и кратко. Объясняй просто, но без воды. Сначала дай короткий ответ, потом при необходимости одно краткое пояснение.",
        "en": "Answer clearly and briefly. Explain simply without fluff. Give a short answer first, then one brief clarification if needed.",
    },
}

router = Router()


class Database:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.setup()

    def setup(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                language TEXT DEFAULT 'ru',
                style_key TEXT DEFAULT 'precise',
                custom_style TEXT DEFAULT '',
                awaiting_custom_style INTEGER DEFAULT 0,
                reply_count INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        self.conn.commit()

    def upsert_user(self, user_id: int, username: str, full_name: str):
        now = int(time.time())
        cur = self.conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        exists = cur.fetchone()
        if exists:
            cur.execute(
                "UPDATE users SET username=?, full_name=?, updated_at=? WHERE user_id=?",
                (username, full_name, now, user_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO users (
                    user_id, username, full_name, language, style_key,
                    custom_style, awaiting_custom_style, reply_count, created_at, updated_at
                ) VALUES (?, ?, ?, 'ru', 'precise', '', 0, 0, ?, ?)
                """,
                (user_id, username, full_name, now, now),
            )
        self.conn.commit()

    def get_user(self, user_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if row is None:
            self.upsert_user(user_id, "", "")
            cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
            row = cur.fetchone()
        return dict(row)

    def update_user_field(self, user_id: int, field: str, value):
        cur = self.conn.cursor()
        cur.execute(f"UPDATE users SET {field}=?, updated_at=? WHERE user_id=?", (value, int(time.time()), user_id))
        self.conn.commit()

    def increment_reply_count(self, user_id: int):
        cur = self.conn.cursor()
        cur.execute("UPDATE users SET reply_count = reply_count + 1, updated_at=? WHERE user_id=?", (int(time.time()), user_id))
        self.conn.commit()

    def add_message(self, user_id: int, role: str, content: str):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, int(time.time())),
        )
        self.conn.commit()

    def get_recent_messages(self, user_id: int, limit: int = MAX_HISTORY_MESSAGES):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = cur.fetchall()
        rows = list(reversed(rows))
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def export_history_text(self, user_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT role, content, created_at FROM messages WHERE user_id=? ORDER BY id ASC", (user_id,))
        rows = cur.fetchall()
        if not rows:
            return ""
        parts = []
        for row in rows:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["created_at"]))
            parts.append(f"[{ts}] {row['role'].upper()}\n{row['content']}\n")
        return "\n".join(parts)


db = Database(DB_PATH)

client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)


def t(lang: str, key: str, **kwargs):
    text = TEXTS.get(lang, TEXTS["ru"]).get(key, key)
    return text.format(**kwargs)


def safe_name(message: Message):
    if message.from_user:
        return (message.from_user.full_name or message.from_user.first_name or "friend").strip()
    return "friend"


def get_lang(user_id: int):
    return db.get_user(user_id).get("language", "ru")


def main_menu(user_id: int):
    lang = get_lang(user_id)
    buttons = [
        [InlineKeyboardButton(text=t(lang, "btn_style"), callback_data="settings:style")],
        [InlineKeyboardButton(text=t(lang, "btn_export"), callback_data="history:export")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def style_menu(user_id: int):
    lang = get_lang(user_id)
    buttons = [
        [InlineKeyboardButton(text=t(lang, "btn_precise"), callback_data="style:precise")],
        [InlineKeyboardButton(text=t(lang, "btn_short"), callback_data="style:short")],
        [InlineKeyboardButton(text=t(lang, "btn_teacher"), callback_data="style:teacher")],
        [InlineKeyboardButton(text=t(lang, "btn_custom"), callback_data="style:custom")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def promo_text(lang: str):
    return f"{t(lang, 'promo_title')}\n\n{t(lang, 'promo_text')}"


async def send_long_message(message: Message, text: str, reply_markup=None):
    chunks = []
    while text:
        if len(text) <= MAX_TELEGRAM_MESSAGE:
            chunks.append(text)
            break
        cut = text[:MAX_TELEGRAM_MESSAGE]
        last_newline = cut.rfind("\n")
        if last_newline > 1000:
            chunks.append(text[:last_newline])
            text = text[last_newline:].lstrip()
        else:
            chunks.append(cut)
            text = text[MAX_TELEGRAM_MESSAGE:]
    first = True
    for chunk in chunks:
        if first:
            await message.answer(chunk, reply_markup=reply_markup)
            first = False
        else:
            await message.answer(chunk)


def build_system_prompt(user: dict):
    lang = user["language"]
    base = [
        "You are an AI assistant inside Telegram.",
        "Always answer directly.",
        "Do not add greetings unless the user explicitly asks for them.",
        "Do not add unnecessary comments.",
        "Do not use filler phrases.",
        "Prefer short, exact answers.",
        "If the user asks for code, provide working code.",
        "If the user asks a simple question, answer in the shortest correct form.",
        "Follow the user's language.",
    ]
    if user["style_key"] == "custom" and user["custom_style"].strip():
        base.append(user["custom_style"].strip())
    else:
        base.append(STYLE_PROMPTS[user["style_key"]][lang])
    return "\n".join(base)


async def ask_ai(user: dict, user_text: str):
    history = db.get_recent_messages(user["user_id"], MAX_HISTORY_MESSAGES)
    messages = [{"role": "system", "content": build_system_prompt(user)}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.2,
        extra_headers={
            "HTTP-Referer": "https://railway.app",
            "X-Title": "Telegram AI Bot",
        },
        timeout=REQUEST_TIMEOUT,
    )
    text = response.choices[0].message.content or ""
    return text.strip()


@router.message(CommandStart())
async def start_handler(message: Message):
    if not message.from_user:
        return
    db.upsert_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or "",
    )
    user = db.get_user(message.from_user.id)
    welcome = f"{t(user['language'], 'welcome', name=safe_name(message))}\n\n{promo_text(user['language'])}"
    await message.answer(welcome, reply_markup=main_menu(message.from_user.id))


@router.callback_query(F.data == "back:menu")
async def back_menu_handler(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(t(user["language"], "menu"), reply_markup=main_menu(callback.from_user.id))
    await callback.answer()


@router.callback_query(F.data == "settings:style")
async def settings_style_handler(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(t(user["language"], "choose_style"), reply_markup=style_menu(callback.from_user.id))
    await callback.answer()


@router.callback_query(F.data == "history:export")
async def export_history_callback(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user = db.get_user(callback.from_user.id)
    data = db.export_history_text(callback.from_user.id)
    if not data:
        await callback.message.answer(t(user["language"], "empty_history"), reply_markup=main_menu(callback.from_user.id))
        await callback.answer()
        return
    payload = BufferedInputFile(data.encode("utf-8"), filename=f"chat_history_{callback.from_user.id}.txt")
    caption = f"{t(user['language'], 'export_ready')}\n\n{promo_text(user['language'])}"
    await callback.message.answer_document(payload, caption=caption)
    await callback.answer()


@router.callback_query(F.data.startswith("style:"))
async def style_change_handler(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    style = callback.data.split(":", 1)[1]
    if style == "custom":
        db.update_user_field(callback.from_user.id, "style_key", "custom")
        db.update_user_field(callback.from_user.id, "awaiting_custom_style", 1)
        user = db.get_user(callback.from_user.id)
        await callback.message.edit_text(t(user["language"], "ask_custom_style"), reply_markup=main_menu(callback.from_user.id))
        await callback.answer()
        return
    db.update_user_field(callback.from_user.id, "style_key", style)
    db.update_user_field(callback.from_user.id, "awaiting_custom_style", 0)
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(t(user["language"], "style_changed"), reply_markup=main_menu(callback.from_user.id))
    await callback.answer()


@router.message(F.text)
async def text_handler(message: Message, bot: Bot):
    if not message.from_user or not message.text:
        return
    db.upsert_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or "",
    )
    user = db.get_user(message.from_user.id)

    if user["awaiting_custom_style"]:
        db.update_user_field(message.from_user.id, "custom_style", message.text.strip())
        db.update_user_field(message.from_user.id, "style_key", "custom")
        db.update_user_field(message.from_user.id, "awaiting_custom_style", 0)
        user = db.get_user(message.from_user.id)
        await message.answer(t(user["language"], "custom_style_saved"), reply_markup=main_menu(message.from_user.id))
        return

    db.add_message(message.from_user.id, "user", message.text.strip())

    thinking_msg = await message.answer(t(user["language"], "thinking"))
    try:
        with suppress(Exception):
            await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        answer = await ask_ai(user, message.text.strip())
        if not answer:
            raise RuntimeError("empty ai response")
        db.add_message(message.from_user.id, "assistant", answer)
        db.increment_reply_count(message.from_user.id)
        user = db.get_user(message.from_user.id)
        if user["reply_count"] % AD_FREQUENCY == 0:
            answer = f"{answer}\n\n{promo_text(user['language'])}"
        with suppress(Exception):
            await thinking_msg.delete()
        await send_long_message(message, answer, reply_markup=main_menu(message.from_user.id))
    except Exception as e:
        logging.exception("AI response error: %s", e)
        with suppress(Exception):
            await thinking_msg.edit_text(t(user["language"], "error"), reply_markup=main_menu(message.from_user.id))


async def main():
    if not BOT_TOKEN or not OPENAI_API_KEY:
        raise RuntimeError("BOT_TOKEN or OPENAI_API_KEY is missing in environment variables.")
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
