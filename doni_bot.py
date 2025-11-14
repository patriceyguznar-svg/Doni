#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from openai import OpenAI
import sqlite3
from datetime import datetime

# ==========================
# Конфигурация
# ==========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Отсутствует TELEGRAM_TOKEN!")
if not OPENAI_API_KEY:
    raise RuntimeError("Отсутствует OPENAI_API_KEY!")

# OpenAI клиент
client = OpenAI(api_key=OPENAI_API_KEY)

# Telegram Bot
bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==========================
# База данных (SQLite)
# ==========================
DB_PATH = "doni_memory.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, joined_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, role TEXT, text TEXT, created_at TEXT)""")
    conn.commit()
    conn.close()


def save_user(user):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (user.id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users VALUES (?, ?, ?, ?)",
                    (user.id, user.username, user.first_name, datetime.utcnow().isoformat()))
        conn.commit()
    conn.close()


def save_message(uid: int, role: str, text: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO messages(user_id, role, text, created_at) VALUES (?, ?, ?, ?)",
                (uid, role, text, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def get_last_messages(uid: int, limit: int = 5):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT role, text FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))
    rows = cur.fetchall()
    conn.close()
    return rows[::-1]


# ==========================
# GPT (OpenAI)
# ==========================
async def call_gpt(prompt: str) -> str:

    messages = [
        {"role": "system", "content": (
            "Ты — Doni, богатый, уверенный в себе миллионер с юмором. "
            "Ты мастер в криптовалюте, инвестициях и финансах. "
            "Отвечай дружелюбно, уверенно, иногда шути, всегда на русском."
        )},
        {"role": "user", "content": prompt}
    ]

    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            max_tokens=500,
            temperature=0.8,
            top_p=0.95
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка GPT: {str(e)}"


# ==========================
# Команды
# ==========================
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    save_user(msg.from_user)
    await msg.answer(
        "<b>Привет!</b> Я <b>Doni</b> — богатый миллионер-бот.\n"
        "Пиши — пообщаемся 😎"
    )


@dp.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer(
        "<b>Команды:</b>\n"
        "/start — старт\n"
        "/help — помощь\n"
        "/profile — твой профиль\n"
    )


@dp.message(Command("profile"))
async def profile_cmd(msg: Message):
    uid = msg.from_user.id
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT username, first_name, joined_at FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    conn.close()
    if row:
        username, first_name, joined_at = row
        await msg.answer(
            f"<b>Твой профиль:</b>\n"
            f"Имя: {first_name or '—'}\n"
            f"Логин: @{username or '—'}\n"
            f"Дата регистрации: {joined_at.split('T')[0]}"
        )
    else:
        await msg.answer("Ты ещё не в базе. Напиши /start.")


# ==========================
# Основной чат
# ==========================
@dp.message()
async def chat_handler(msg: Message):
    user = msg.from_user
    save_user(user)
    text = msg.text.strip()

    save_message(user.id, "user", text)

    # История
    history = get_last_messages(user.id)
    hist_text = "\n".join([f"{'Пользователь' if role=='user' else 'Doni'}: {t}" for role, t in history])

    prompt = f"История:\n{hist_text}\n\nПользователь: {text}\nDoni:"

    reply = await call_gpt(prompt)
    save_message(user.id, "assistant", reply)

    await msg.answer(reply)


# ==========================
# Точка входа (Polling)
# ==========================
async def main():
    print("🚀 Doni Polling Bot запущен!")
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
