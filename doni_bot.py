#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Doni — Telegram Bot (упрощённая версия)
---------------------------------------
Работает с Gemini 1.5 Flash API без необходимости указывать BASE_URL и MODEL в .env
Идеально подходит для деплоя на Render (Web Service plan)
"""

import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import aiohttp
import sqlite3
from datetime import datetime

# ==========================
# Конфигурация
# ==========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN отсутствует в переменных окружения Render.")
if not GEMINI_API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY отсутствует в переменных окружения Render.")

# Инициализация бота
bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ==========================
# Простая база (SQLite)
# ==========================
DB_PATH = "doni_memory.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            text TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_user(user):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (
            user.id,
            user.username,
            user.first_name,
            datetime.utcnow().isoformat()
        ))
        conn.commit()
    conn.close()

def save_message(uid: int, role: str, text: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages(user_id, role, text, created_at) VALUES (?, ?, ?, ?)",
        (uid, role, text, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def get_last_messages(uid: int, limit: int = 5):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT role, text FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))
    rows = cur.fetchall()
    conn.close()
    rows.reverse()
    return rows

# ==========================
# Мини-вебсервер для Render
# ==========================
async def handle(request):
    return web.Response(text="Doni is alive 🚀")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Мини-сервер запущен на порту {port}")

# ==========================
# Gemini API (без URL и модели)
# ==========================
async def call_gemini(prompt: str) -> str:
    """
    Отправляет запрос в Google Gemini API (v1) без указания BASE_URL и MODEL в .env
    """
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=60) as resp:
                data = await resp.json()
                if "error" in data:
                    return f"⚠️ Ошибка Gemini API: {data['error'].get('message', 'Неизвестная ошибка')}"
                return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"⚠️ Ошибка соединения с Gemini: {e}"

# ==========================
# Команды
# ==========================
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    save_user(msg.from_user)
    await msg.answer(
        "Привет, я <b>Doni</b> 💰 — твой дружелюбный миллионер!\n"
        "Готов говорить обо всём: деньги, успех, крипта и жизнь 😎\n\n"
        "Просто напиши сообщение 👇"
    )

@dp.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer(
        "<b>Команды:</b>\n"
        "/start — начать\n"
        "/help — помощь\n"
        "/profile — твой профиль\n\n"
        "А просто пиши — я отвечу 😉"
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
    hist_text = "\n".join(
        [("Пользователь: " if r == "user" else "Doni: ") + t for r, t in history]
    )

    prompt = (
        f"Ты — Doni, уверенный миллионер с чувством юмора, знаток инвестиций, крипты и финансов.\n"
        f"Отвечай дружелюбно, с лёгкой харизмой.\n\n"
        f"История диалога:\n{hist_text}\n\n"
        f"Пользователь: {user_text}\nDoni:"
    )

    reply = await call_gemini(prompt)
    save_message(user.id, "assistant", reply)
    await msg.answer(reply)

# ==========================
# Главная точка входа
# ==========================
async def main():
    print("🚀 Doni Bot запущен и готов к работе!")
    init_db()
    asyncio.create_task(start_web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
