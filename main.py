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
RAPIDGRAB_KEY = os.getenv("RAPIDGRAB_KEY")

if not TOKEN:
    raise SystemExit("❌ TOKEN не найден в .env")
if not RAPIDGRAB_KEY:
    raise SystemExit("❌ RAPIDGRAB_KEY не найден в .env")

SERVICE_NAME = "InstaTok Saver"

DB_PATH = "data.db"

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    free_used INTEGER DEFAULT 0,
    pro INTEGER DEFAULT 0
)
""")
conn.commit()

FREE_LIMIT = 5

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

TIKTOK_API = "https://api.sssapi.net/tiktok?url={url}"
URL_RE = re.compile(r'https?://\S+')


# ============================
#    ФУНКЦИИ БАЗЫ
# ============================

def get_user(user_id):
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    cur.execute("SELECT free_used, pro FROM users WHERE user_id = ?", (user_id,))
    return cur.fetchone()

def increment_used(user_id):
    cur.execute("UPDATE users SET free_used = free_used + 1 WHERE user_id = ?", (user_id,))
    conn.commit()


# ============================
#    КОМАНДЫ СТАРТ
# ============================

@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("TikTok", "Instagram", "PRO", "Баланс")
    text = (
        f"Привет! Я {SERVICE_NAME} — скачиваю видео из TikTok и Instagram.\n"
        f"Бесплатно: {FREE_LIMIT} скачиваний.\n"
        f"Просто пришли ссылку ❤️"
    )
    await message.reply(text, reply_markup=keyboard)


@dp.message_handler(commands=['balance'])
async def cmd_balance(message: types.Message):
    free_used, pro = get_user(message.from_user.id)
    await message.reply(f"Бесплатных использовано: {free_used}/{FREE_LIMIT}. PRO: {'Да' if pro else 'Нет'}")


@dp.message_handler(commands=['buy'])
async def cmd_buy(message: types.Message):
    await message.reply("Для покупки PRO — напиши @your_support_here")


# ============================
#      ОСНОВНОЙ ОБРАБОТЧИК
# ============================

@dp.message_handler()
async def handle_message(message: types.Message):
    text = message.text or ""
    urls = URL_RE.findall(text)

    if not urls:
        await message.reply("Отправьте ссылку на TikTok или Instagram.")
        return

    url = urls[0]

    # Лимиты
    free_used, pro = get_user(message.from_user.id)
    if not pro and free_used >= FREE_LIMIT:
        await message.reply("Вы исчерпали бесплатный лимит. Купите PRO.")
        return

    await message.reply("Обрабатываю ссылку...")

    try:

        # -------- TikTok --------
        if "tiktok.com" in url:
            resp = requests.get(TIKTOK_API.format(url=url), timeout=20).json()
            video_url = (
                resp.get("video_no_watermark")
                or resp.get("no_watermark")
                or resp.get("video")
            )

        # -------- Instagram через RAPIDGRAB --------
        elif "instagram.com" in url:
            api_url = f"https://api.rapidgrab.net/instagram?apikey={RAPIDGRAB_KEY}&url={url}"
            resp = requests.get(api_url, timeout=25).json()

            if resp.get("status") != "success":
                await message.reply("Ошибка при скачивании Instagram видео.")
                return

            video_url = resp["data"]["video"]

        else:
            await message.reply("Это не TikTok и не Instagram ссылка.")
            return

        # Если ссылки нет
        if not video_url:
            await message.reply("Не удалось получить прямой URL видео.")
            return

        # Скачиваем файл
        video_resp = requests.get(video_url, timeout=60)
        bio = io.BytesIO(video_resp.content)
        bio.seek(0)

        # Увеличиваем счётчик
        increment_used(message.from_user.id)

        # Отправляем файл
        await message.answer_video(
            video=InputFile(bio, filename="video.mp4"),
            caption="🎉 Готово!"
        )

    except Exception as e:
        await message.reply(f"Ошибка: {e}")


# ============================
#      ЗАПУСК
# ============================

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
