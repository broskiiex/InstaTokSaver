import os
import re
import requests
import sqlite3
import io
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InputFile

load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise SystemExit("TOKEN не найден в .env")

SERVICE_NAME = "InstaTok Saver"

DB_PATH = "data.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, free_used INTEGER DEFAULT 0, pro INTEGER DEFAULT 0)")
conn.commit()

FREE_LIMIT = 5

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# РАБОЧИЕ API
TIKTOK_API = "https://www.tikwm.com/api/?url={url}"
INSTAGRAM_API = "https://api.sssapi.net/instagram?url={url}"


URL_RE = re.compile(r'https?://\S+')

def get_user(user_id):
    cur.execute("INSERT OR IGNORE INTO users (user_id, free_used, pro) VALUES (?,0,0)", (user_id,))
    conn.commit()
    cur.execute("SELECT free_used, pro FROM users WHERE user_id = ?", (user_id,))
    return cur.fetchone()

def increment_used(user_id):
    cur.execute("UPDATE users SET free_used = free_used + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("TikTok", "Instagram", "PRO", "Баланс")
    text = (f"Привет! Я {SERVICE_NAME} — скачиваю видео из TikTok и Instagram без водяных знаков.\n"
            f"Бесплатно: {FREE_LIMIT} скачиваний в день.\n"
            "Просто отправьте ссылку на видео.")
    await message.reply(text, reply_markup=keyboard)

@dp.message_handler(commands=['balance'])
async def cmd_balance(message: types.Message):
    free_used, pro = get_user(message.from_user.id)
    await message.reply(f"Использовано бесплатных скачиваний: {free_used}/{FREE_LIMIT}. PRO: {'Да' if pro else 'Нет'}")

@dp.message_handler(commands=['buy'])
async def cmd_buy(message: types.Message):
    await message.reply("Чтобы отключить лимит — купите PRO. Связь: @your_support_here (замените на ваш контакт).")

@dp.message_handler()
async def handle_message(message: types.Message):
    text = message.text or ""
    urls = URL_RE.findall(text)
    if not urls:
        await message.reply("Пожалуйста, отправьте ссылку на TikTok или Instagram.")
        return

    url = urls[0]
    free_used, pro = get_user(message.from_user.id)
    if not pro and free_used >= FREE_LIMIT:
        await message.reply("Вы исчерпали бесплатный лимит. Купите PRO (/buy) или попробуйте позже.")
        return

    await message.reply("Обрабатываю ссылку, подождите...")

    try:
        # TikTok
        if "tiktok.com" in url or "vt.tiktok.com" in url:
            api_url = TIKTOK_API.format(url=url)
            data = requests.get(api_url, timeout=30).json()

            if not data.get("data"):
                await message.reply("Не удалось получить видео. Попробуйте другую ссылку.")
                return

            video_url = data["data"]["play"]  # без водяного знака

        # Instagram
        elif "instagram.com" in url or "instagr.am" in url:
            api_url = INSTAGRAM_API.format(url=url)
            data = requests.get(api_url, timeout=30).json()

            if "data" not in data or "medias" not in data["data"]:
                await message.reply("Не удалось получить видео. Попробуйте другую ссылку.")
                return

            video_url = data["data"]["medias"][0]["url"]

        else:
            await message.reply("Ссылка не распознана как TikTok или Instagram.")
            return

        # Скачивание видео
        file = requests.get(video_url, timeout=60).content
        bio = io.BytesIO(file)
        bio.seek(0)
        increment_used(message.from_user.id)

        await message.answer_video(InputFile(bio, "video.mp4"))

    except Exception as e:
        await message.reply(f"Ошибка при скачивании: {e}")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
