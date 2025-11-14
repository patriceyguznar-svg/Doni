#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Doni — Telegram Bot на OpenAI GPT
-------------------
Полностью готовый код для Render (Web Service).
Использует GPT-4o-mini (2025).
"""

import os
import asyncio
import signal
import sys
from aiohttp import web
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

# Bot
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
# Веб-сервер для Render (keep-alive)
# ==========================
async def handle(request):
    return web.Response(text="Doni is alive")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")

# ==========================
# OpenAI GPT API
# ==========================
async def call_gpt(prompt: str) -> str:
    history = get_last_messages(0)  # Пока без user_id
    messages = [
        {"role": "system", "content": (
            "Ты — Doni, дружелюбный миллионер с чувством юмора и знаниями в крипте, банкинге и инвестициях. "
            "Отвечай легко, уверенно, иногда с шутками. Используй русский язык."
        )}
    ]
    for role, text in history[-4:]:
        messages.append({"role": "user" if role == "user" else "assistant", "content": text})
    messages.append({"role": "user", "content": prompt})

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
        print(f"GPT ошибка: {e}")
        return f"Ошибка GPT: {str(e)[:100]}"

# ==========================
# Обработчики команд
# ==========================
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    save_user(msg.from_user)
    await msg.answer(
        "<b>Привет!</b> Я <b>Doni</b> — твой миллионер с чувством юмора!\n"
        "Могу болтать, давать советы по крипте и инвестициям, шутить.\n\n"
        "Просто напиши сообщение!"
    )

@dp.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer(
        "<b>Команды:</b>\n"
        "/start — начать\n"
        "/help — список команд\n"
        "/profile — информация о тебе\n"
        "Пиши текст — отвечу через GPT!"
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
            f"Имя: {first_name or 'Без имени'}\n"
            f"Логин: @{username or '—'}\n"
            f"Дата регистрации: {joined_at.split('T')[0]}"
        )
    else:
        await msg.answer("Ты ещё не зарегистрирован. Напиши /start.")

# ==========================
# Основной чат
# ==========================
@dp.message()
async def chat_handler(msg: Message):
    user = msg.from_user
    save_user(user)
    user_text = msg.text.strip()
    save_message(user.id, "user", user_text)

    history = get_last_messages(user.id)
    hist_text = "\n".join([f"{'Пользователь: ' if r == 'user' else 'Doni: '}{t}" for r, t in history])
    prompt = f"История диалога:\n{hist_text}\n\nПользователь: {user_text}\nDoni:"

    reply = await call_gpt(prompt)
    save_message(user.id, "assistant", reply)
    await msg.answer(reply)

# ==========================
# Graceful Shutdown
# ==========================
async def shutdown():
    print("Остановка бота...")
    await bot.session.close()
    print("Бот остановлен.")
    sys.exit(0)

# ==========================
# Главная точка входа
# ==========================
async def main():
    print("Doni Bot на GPT запущен!")
    init_db()
    asyncio.create_task(start_web_server())

    # Graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Polling остановлен: {e}")
        await shutdown()

if __name__ == "__main__":
    asyncio.run(main())
