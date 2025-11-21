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
cur.execute(
    "CREATE TABLE IF NOT EXISTS users ("
    "user_id INTEGER PRIMARY KEY, "
    "free_used INTEGER DEFAULT 0, "
    "pro INTEGER DEFAULT 0)"
)
conn.commit()

FREE_LIMIT = 5

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# TikTok — через sssapi (как было)
TIKTOK_API = "https://api.sssapi.net/tiktok?url={url}"

# Регулярка для поиска любой ссылки
URL_RE = re.compile(r'https?://\S+')


def get_user(user_id: int):
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, free_used, pro) "
        "VALUES (?, 0, 0)",
        (user_id,),
    )
    conn.commit()
    cur.execute(
        "SELECT free_used, pro FROM users WHERE user_id = ?",
        (user_id,),
    )
    return cur.fetchone()


def increment_used(user_id: int):
    cur.execute(
        "UPDATE users SET free_used = free_used + 1 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()


def get_instagram_video_url(post_url: str) -> str | None:
    """
    Пытаемся вытащить прямую ссылку на видео из страницы Instagram.
    Работает с публичными Reels/постами, если Инста не требует логин.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    resp = requests.get(post_url, headers=headers, timeout=25)
    if resp.status_code != 200:
        return None

    html = resp.text

    # Ищем "video_url":"https:\/\/....mp4"
    m = re.search(r'"video_url":"([^"]+)"', html)
    if not m:
        return None

    raw = m.group(1)
    # В HTML слеши экранированы, нужно вернуть нормальный URL
    video_url = raw.encode("utf-8").decode("unicode_escape")
    return video_url


@dp.message_handler(commands=["start", "help"])
async def send_welcome(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("TikTok", "Instagram", "PRO", "Баланс")
    text = (
        f"Привет! Я {SERVICE_NAME} — скачиваю видео из TikTok и Instagram "
        f"без водяных знаков (где возможно).\n"
        f"Бесплатно: {FREE_LIMIT} скачиваний в день.\n"
        "Просто отправь ссылку на видео."
    )
    await message.reply(text, reply_markup=keyboard)


@dp.message_handler(commands=["balance"])
async def cmd_balance(message: types.Message):
    free_used, pro = get_user(message.from_user.id)
    await message.reply(
        f"Использовано бесплатных скачиваний: {free_used}/{FREE_LIMIT}. "
        f"PRO: {'Да' if pro else 'Нет'}"
    )


@dp.message_handler(commands=["buy"])
async def cmd_buy(message: types.Message):
    await message.reply(
        "Чтобы отключить лимит — купите PRO. "
        "Связь: @your_support_here (замени на свой контакт)."
    )


@dp.message_handler()
async def handle_message(message: types.Message):
    text = message.text or ""
    urls = URL_RE.findall(text)
    if not urls:
        await message.reply("Пожалуйста, отправь ссылку на TikTok или Instagram.")
        return

    url = urls[0]

    free_used, pro = get_user(message.from_user.id)
    if not pro and free_used >= FREE_LIMIT:
        await message.reply(
            "Ты исчерпал бесплатный лимит. Купи PRO (/buy) или попробуй позже."
        )
        return

    await message.reply("Обрабатываю ссылку, подожди...")

    try:
        # ==== TikTok ====
        if "tiktok.com" in url or "vt.tiktok.com" in url:
            api_url = TIKTOK_API.format(url=url)
            resp = requests.get(api_url, timeout=30)
            data = resp.json()
            video_url = (
                data.get("video_no_watermark")
                or data.get("no_watermark")
                or data.get("video")
            )

        # ==== Instagram ====
        elif "instagram.com" in url or "instagr.am" in url:
            video_url = get_instagram_video_url(url)

        else:
            await message.reply(
                "Ссылка не распознана как TikTok или Instagram. "
                "Отправь прямую ссылку на пост/ролик."
            )
            return

        if not video_url:
            await message.reply(
                "Не получилось получить прямой URL видео. "
                "Возможно, пост закрыт или Инста требует авторизацию."
            )
            return

        video_resp = requests.get(video_url, timeout=60)
        bio = io.BytesIO(video_resp.content)
        bio.seek(0)

        increment_used(message.from_user.id)

        await message.answer_video(
            video=InputFile(bio, filename="video.mp4")
        )

    except Exception as e:
        # на всякий случай, чтобы не палить внутренности сервера, можно укоротить текст
        await message.reply(f"Произошла ошибка при скачивании: {e}")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
