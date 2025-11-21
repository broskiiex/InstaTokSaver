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

TIKTOK_API = "https://api.sssapi.net/tiktok?url={url}"  # TikTok рабочий
URL_RE = re.compile(r'https?://\S+')

def get_user(user_id):
    cur.execute("INSERT OR IGNORE INTO users (user_id, free_used, pro) VALUES (?,0,0)", (user_id,))
    conn.commit()
    cur.execute("SELECT free_used, pro FROM users WHERE user_id = ?", (user_id,))
    return cur.fetchone()

def increment_used(user_id):
    cur.execute("UPDATE users SET free_used = free_used + 1 WHERE user_id = ?", (user_id,))
    conn.commit()


# -----------------------
#   INSTAGRAM FIXED API
# -----------------------
def download_instagram(url: str):
    api_url = "https://saveinsta.io/core/ajax.php"

    payload = {
        "url": url,
        "action": "post"
    }

    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.post(api_url, data=payload, headers=headers)
    html = r.text

    if "download" not in html:
        return None

    # вытащим первый mp4
    links = re.findall(r'href="(.*?)"', html)
    for link in links:
        if link.endswith(".mp4"):
            return link

    return None


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("TikTok", "Instagram", "PRO", "Баланс")
    text = (f"Привет! Я {SERVICE_NAME} — скачиваю видео из TikTok и Instagram без водяных знаков.\n"
            f"Бесплатно: {FREE_LIMIT} скачиваний в день.\n"
            "Просто отправьте ссылку на видео.")
    await message.reply(text, reply_markup=keyboard)


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
        # -------------- TIKTOK --------------
        if "tiktok.com" in url:
            api_url = TIKTOK_API.format(url=url)
            resp = requests.get(api_url, timeout=30).json()
            video_url = resp.get("video_no_watermark") or resp.get("video")

        # -------------- INSTAGRAM --------------
        elif "instagram.com" in url:
            video_url = download_instagram(url)

        else:
            await message.reply("Ссылка не распознана.")
            return

        if not video_url:
            await message.reply("Не удалось получить видео. Ссылка может быть приватной.")
            return

        video_resp = requests.get(video_url)
        bio = io.BytesIO(video_resp.content)
        bio.seek(0)
        increment_used(message.from_user.id)

        await message.answer_video(InputFile(bio, filename="video.mp4"))

    except Exception as e:
        await message.reply(f"Ошибка: {e}")


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
