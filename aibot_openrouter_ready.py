
import asyncio
import logging
import os
import sqlite3
import time
from contextlib import suppress

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from openai import AsyncOpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini")
DB_PATH = "telegram_ai_bot.db"
MAX_HISTORY_MESSAGES = 20
MAX_TELEGRAM_MESSAGE = 4000
REQUEST_TIMEOUT = 120

logging.basicConfig(level=logging.INFO)

TEXTS = {
    "ru": {
        "welcome": "Привет, {name} 👋\n\nЯ AI-бот в Telegram.\n\nЯ умею:\n• отвечать как ChatGPT\n• помнить переписку\n• менять стиль ответов\n• экспортировать историю\n• очищать память\n\nВыбери действие ниже или просто напиши сообщение.",
        "menu": "Главное меню",
        "chat_enabled": "Режим чата с ИИ включён ✅\nТеперь просто пиши сообщения.",
        "chat_disabled": "Режим чата с ИИ выключен ⛔",
        "history_cleared": "История диалога очищена 🧹",
        "style_changed": "Стиль ответа обновлён ✅",
        "lang_changed": "Язык обновлён ✅",
        "thinking": "Думаю…",
        "error": "⚠️ Сейчас ИИ временно не ответил. Попробуй ещё раз чуть позже.",
        "empty_history": "История пока пустая.",
        "export_ready": "Готово. Отправляю историю диалога 📄",
        "ask_custom_style": "Отправь мне свой кастомный стиль одним сообщением.\n\nНапример:\nОтвечай кратко, как профессиональный разработчик, с примерами.",
        "custom_style_saved": "Кастомный стиль сохранён ✅",
        "help": "Команды:\n/start — запуск\n/menu — меню\n/new — очистить историю\n/export — экспорт истории\n/help — помощь",
        "choose_language": "Выбери язык:",
        "choose_style": "Выбери стиль ответа:",
        "status": "⚙️ Текущие настройки\n\nЯзык: {lang}\nМодель: {model}\nСтиль: {style}\nAI-режим: {enabled}\nСообщений в памяти: {count}",
        "enabled_yes": "включён",
        "enabled_no": "выключен",
        "style_balanced": "Сбалансированный",
        "style_precise": "Точный",
        "style_friendly": "Дружелюбный",
        "style_short": "Краткий",
        "style_custom": "Кастомный",
        "lang_ru": "Русский",
        "lang_en": "English",
        "btn_chat_on": "🟢 AI вкл",
        "btn_chat_off": "⛔ AI выкл",
        "btn_clear": "🧹 Очистить",
        "btn_export": "📄 Экспорт",
        "btn_style": "🎭 Стиль",
        "btn_lang": "🌐 Язык",
        "btn_status": "⚙️ Статус",
        "btn_back": "⬅️ Назад",
        "btn_balanced": "⚖️ Сбалансированный",
        "btn_precise": "🎯 Точный",
        "btn_friendly": "😊 Дружелюбный",
        "btn_short": "✂️ Краткий",
        "btn_custom": "✍️ Кастомный",
    },
    "en": {
        "welcome": "Hi, {name} 👋\n\nI am an AI bot in Telegram.\n\nI can:\n• answer like ChatGPT\n• remember conversation\n• change response style\n• export history\n• clear memory\n\nChoose an action below or just send a message.",
        "menu": "Main menu",
        "chat_enabled": "AI chat mode enabled ✅\nNow just send messages.",
        "chat_disabled": "AI chat mode disabled ⛔",
        "history_cleared": "Conversation history cleared 🧹",
        "style_changed": "Response style updated ✅",
        "lang_changed": "Language updated ✅",
        "thinking": "Thinking…",
        "error": "⚠️ AI did not respond right now. Please try again a bit later.",
        "empty_history": "History is empty.",
        "export_ready": "Done. Sending chat history 📄",
        "ask_custom_style": "Send your custom style in one message.\n\nExample:\nAnswer briefly like a professional developer with examples.",
        "custom_style_saved": "Custom style saved ✅",
        "help": "Commands:\n/start — launch\n/menu — menu\n/new — clear history\n/export — export history\n/help — help",
        "choose_language": "Choose language:",
        "choose_style": "Choose response style:",
        "status": "⚙️ Current settings\n\nLanguage: {lang}\nModel: {model}\nStyle: {style}\nAI mode: {enabled}\nMessages in memory: {count}",
        "enabled_yes": "enabled",
        "enabled_no": "disabled",
        "style_balanced": "Balanced",
        "style_precise": "Precise",
        "style_friendly": "Friendly",
        "style_short": "Short",
        "style_custom": "Custom",
        "lang_ru": "Русский",
        "lang_en": "English",
        "btn_chat_on": "🟢 AI on",
        "btn_chat_off": "⛔ AI off",
        "btn_clear": "🧹 Clear",
        "btn_export": "📄 Export",
        "btn_style": "🎭 Style",
        "btn_lang": "🌐 Language",
        "btn_status": "⚙️ Status",
        "btn_back": "⬅️ Back",
        "btn_balanced": "⚖️ Balanced",
        "btn_precise": "🎯 Precise",
        "btn_friendly": "😊 Friendly",
        "btn_short": "✂️ Short",
        "btn_custom": "✍️ Custom",
    },
}

STYLE_PROMPTS = {
    "balanced": {
        "ru": "Отвечай полезно, ясно и по делу. Будь естественным и структурным. Не растягивай ответ без причины.",
        "en": "Answer helpfully, clearly, and directly. Be natural and structured. Do not be verbose without reason.",
    },
    "precise": {
        "ru": "Отвечай максимально точно, строго и профессионально. Убирай воду. Давай чёткие шаги и конкретику.",
        "en": "Answer as precisely and professionally as possible. Avoid fluff. Give clear steps and specifics.",
    },
    "friendly": {
        "ru": "Отвечай дружелюбно, тепло и понятно. Объясняй простыми словами, но сохраняй пользу.",
        "en": "Answer in a friendly, warm, and clear way. Explain simply while staying useful.",
    },
    "short": {
        "ru": "Отвечай кратко, но полезно. Только главное. Без лишних вступлений.",
        "en": "Answer briefly but usefully. Only the essentials.",
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
            '''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                language TEXT DEFAULT 'ru',
                style_key TEXT DEFAULT 'balanced',
                custom_style TEXT DEFAULT '',
                chat_enabled INTEGER DEFAULT 1,
                awaiting_custom_style INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            '''
        )
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            '''
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
                '''
                INSERT INTO users (
                    user_id, username, full_name, language, style_key,
                    custom_style, chat_enabled, awaiting_custom_style, created_at, updated_at
                ) VALUES (?, ?, ?, 'ru', 'balanced', '', 1, 0, ?, ?)
                ''',
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

    def clear_history(self, user_id: int):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
        self.conn.commit()

    def history_count(self, user_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM messages WHERE user_id=?", (user_id,))
        return cur.fetchone()["c"]

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
    user = db.get_user(user_id)
    lang = user["language"]
    buttons = [
        [
            InlineKeyboardButton(text=t(lang, "btn_chat_on"), callback_data="chat:on"),
            InlineKeyboardButton(text=t(lang, "btn_chat_off"), callback_data="chat:off"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_clear"), callback_data="history:clear"),
            InlineKeyboardButton(text=t(lang, "btn_export"), callback_data="history:export"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_style"), callback_data="settings:style"),
            InlineKeyboardButton(text=t(lang, "btn_lang"), callback_data="settings:lang"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_status"), callback_data="settings:status"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def lang_menu(user_id: int):
    lang = get_lang(user_id)
    buttons = [
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="lang:en")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def style_menu(user_id: int):
    lang = get_lang(user_id)
    buttons = [
        [InlineKeyboardButton(text=t(lang, "btn_balanced"), callback_data="style:balanced")],
        [InlineKeyboardButton(text=t(lang, "btn_precise"), callback_data="style:precise")],
        [InlineKeyboardButton(text=t(lang, "btn_friendly"), callback_data="style:friendly")],
        [InlineKeyboardButton(text=t(lang, "btn_short"), callback_data="style:short")],
        [InlineKeyboardButton(text=t(lang, "btn_custom"), callback_data="style:custom")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def style_label(user: dict):
    lang = user["language"]
    key = user["style_key"]
    if key == "custom":
        return t(lang, "style_custom")
    return t(lang, f"style_{key}")

def lang_label(user: dict):
    return t(user["language"], f"lang_{user['language']}")

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
        "You are a high-quality AI assistant inside Telegram.",
        "Be accurate, useful, and well-structured.",
        "Adapt to the user's language automatically.",
        "When the user writes in Russian, answer in Russian unless asked otherwise.",
        "When the user writes in English, answer in English unless asked otherwise.",
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
        temperature=0.7,
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
    await message.answer(
        t(user["language"], "welcome", name=safe_name(message)),
        reply_markup=main_menu(message.from_user.id),
    )

@router.message(Command("menu"))
async def menu_handler(message: Message):
    if not message.from_user:
        return
    db.upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    user = db.get_user(message.from_user.id)
    await message.answer(t(user["language"], "menu"), reply_markup=main_menu(message.from_user.id))

@router.message(Command("help"))
async def help_handler(message: Message):
    if not message.from_user:
        return
    user = db.get_user(message.from_user.id)
    await message.answer(t(user["language"], "help"), reply_markup=main_menu(message.from_user.id))

@router.message(Command("new"))
async def new_handler(message: Message):
    if not message.from_user:
        return
    db.clear_history(message.from_user.id)
    user = db.get_user(message.from_user.id)
    await message.answer(t(user["language"], "history_cleared"), reply_markup=main_menu(message.from_user.id))

@router.message(Command("export"))
async def export_handler(message: Message):
    if not message.from_user:
        return
    user = db.get_user(message.from_user.id)
    data = db.export_history_text(message.from_user.id)
    if not data:
        await message.answer(t(user["language"], "empty_history"), reply_markup=main_menu(message.from_user.id))
        return
    payload = BufferedInputFile(data.encode("utf-8"), filename=f"chat_history_{message.from_user.id}.txt")
    await message.answer(t(user["language"], "export_ready"))
    await message.answer_document(payload, caption="history.txt")

@router.callback_query(F.data == "back:menu")
async def back_menu_handler(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(t(user["language"], "menu"), reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data.startswith("chat:"))
async def chat_toggle_handler(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    mode = callback.data.split(":", 1)[1]
    db.update_user_field(callback.from_user.id, "chat_enabled", 1 if mode == "on" else 0)
    user = db.get_user(callback.from_user.id)
    text = t(user["language"], "chat_enabled" if mode == "on" else "chat_disabled")
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data == "history:clear")
async def clear_history_callback(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    db.clear_history(callback.from_user.id)
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(t(user["language"], "history_cleared"), reply_markup=main_menu(callback.from_user.id))
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
    await callback.message.answer(t(user["language"], "export_ready"))
    await callback.message.answer_document(payload, caption="history.txt")
    await callback.answer()

@router.callback_query(F.data == "settings:lang")
async def settings_lang_handler(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(t(user["language"], "choose_language"), reply_markup=lang_menu(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data == "settings:style")
async def settings_style_handler(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(t(user["language"], "choose_style"), reply_markup=style_menu(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data == "settings:status")
async def settings_status_handler(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user = db.get_user(callback.from_user.id)
    text = t(
        user["language"],
        "status",
        lang=lang_label(user),
        model=OPENAI_MODEL,
        style=style_label(user),
        enabled=t(user["language"], "enabled_yes" if user["chat_enabled"] else "enabled_no"),
        count=db.history_count(callback.from_user.id),
    )
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data.startswith("lang:"))
async def lang_change_handler(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    new_lang = callback.data.split(":", 1)[1]
    db.update_user_field(callback.from_user.id, "language", new_lang)
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(t(user["language"], "lang_changed"), reply_markup=main_menu(callback.from_user.id))
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

    if not user["chat_enabled"]:
        await message.answer(t(user["language"], "chat_disabled"), reply_markup=main_menu(message.from_user.id))
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
        with suppress(Exception):
            await thinking_msg.delete()
        await send_long_message(message, answer, reply_markup=main_menu(message.from_user.id))
    except Exception as e:
        logging.exception("AI response error: %s", e)
        with suppress(Exception):
            await thinking_msg.edit_text(t(user["language"], "error"), reply_markup=main_menu(message.from_user.id))

@router.message()
async def fallback_handler(message: Message):
    if not message.from_user:
        return
    user = db.get_user(message.from_user.id)
    await message.answer(t(user["language"], "menu"), reply_markup=main_menu(message.from_user.id))

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
