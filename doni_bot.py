#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Doni — Telegram Bot
-------------------
Полностью готовый код для Render (Web Service).
Исправлено под gemini-2.5-flash (ноябрь 2025).
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
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")  # Актуальная модель (2025)

if not TELEGRAM_TOKEN:
    raise RuntimeError("Отсутствует TELEGRAM_TOKEN!")
if not GEMINI_API_KEY:
    raise RuntimeError("Отсутствует GEMINI_API_KEY!")

# Bot
bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==========================
# База данных
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
    return rows[::-1]  # reverse

# ==========================
# Веб-сервер для Render
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
# Gemini API — ИСПРАВЛЕНО ПОД 2.5 FLASH
# ==========================
async def call_gemini(prompt: str) -> str:
    url = f"{GEMINI_BASE_URL}/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 8192,  # Максимум для 2.5 Flash
            "temperature": 0.8,       # Юмор Doni
            "topP": 0.95              # Разнообразие
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=60) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    print(f"Gemini ошибка {resp.status}: {error}")
                    return f"Ошибка: {resp.status} ({error[:100]}...)"
                
                data = await resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    return candidates[0]["content"]["parts"][0]["text"]
                return "Пустой ответ от Gemini"
                
    except Exception as e:
        print(f"Исключение: {e}")
        return f"Ошибка: {str(e)[:100]}"

# ==========================
# Команды
# ==========================
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    save_user(msg.from_user)
    await msg.answer(
        "<b>Привет!</b> Я <b>Doni</b> — твой миллионер с чувством юмора!\n"
        "Пиши что угодно — отвечу с огоньком"
    )

@dp.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer(
        "<b>Команды:</b>\n"
        "/start — начать\n"
        "/help — помощь\n"
        "/profile — твой профиль"
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
        username, name, date = row
        await msg.answer(
            f"<b>Профиль:</b>\n"
            f"Имя: {name}\n"
            f"Логин: @{username or '—'}\n"
            f"С нами с: {date.split('T')[0]}"
        )
    else:
        await msg.answer("Напиши /start")

# ==========================
# Основной чат
# ==========================
@dp.message()
async def chat_handler(msg: Message):
    user = msg.from_user
    save_user(user)
    text = msg.text.strip()
    save_message(user.id, "user", text)

    history = get_last_messages(user.id)
    hist = "\n".join([f"{'Ты' if r == 'user' else 'Doni'}: {t}" for r, t in history])

    prompt = (
        f"Ты — Doni, миллионер с юмором, эксперт по крипте и инвестициям.\n"
        f"Отвечай легко, уверенно, с шутками.\n"
        f"История:\n{hist}\n\n"
        f"Пользователь: {text}\nDoni:"
    )

    reply = await call_gemini(prompt)
    save_message(user.id, "assistant", reply)
    await msg.answer(reply)

# ==========================
# Запуск
# ==========================
async def main():
    print("Doni Bot запущен")
    init_db()
    asyncio.create_task(start_web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
