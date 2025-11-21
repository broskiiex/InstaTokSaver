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
    "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, free_used INTEGER DEFAULT 0, pro INTEGER DEFAULT 0)"
)
conn.commit()

FREE_LIMIT = 10  

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

URL_RE = re.compile(r'https?://\S+')


TIKTOK_API = "https://www.tikwm.com/api/?url={url}"
INSTAGRAM_API = "https://snapinst.app/api.php?url={url}"


def get_user(user_id):
    cur.execute("INSERT OR IGNORE INTO users (user_id, free_used, pro) VALUES (?,0,0)",
                (user_id,))
    conn.commit()
    cur.execute("SELECT free_used, pro FROM users WHERE user_id = ?",
                (user_id,))
    return cur.fetchone()


def increment_used(user_id):
    cur.execute(
        "UPDATE users SET free_used = free_used + 1 WHERE user_id = ?", (user_id,))
    conn.commit()


@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("TikTok", "Instagram", "PRO", "Баланс")

    text = (
        f"Привет! Я {SERVICE_NAME} 🤖\n"
        f"Скачиваю видео из TikTok и Instagram БЕЗ водяных знаков.\n"
        f"Бесплатно: {FREE_LIMIT} загрузок в день.\n\n"
        f"Отправь ссылку — и я скачаю видео."
    )
    await message.reply(text, reply_markup=kb)


@dp.message_handler(commands=['balance'])
async def balance(message: types.Message):
    used, pro = get_user(message.from_user.id)
    await message.reply(
        f"Использовано: {used}/{FREE_LIMIT}\nPRO: {'Да' if pro else 'Нет'}")


@dp.message_handler(commands=['buy'])
async def buy(message: types.Message):
    await message.reply("Для покупки PRO — напишите: @your_support")


@dp.message_handler()
async def handler(message: types.Message):
    text = message.text or ""
    urls = URL_RE.findall(text)

    if not urls:
        return await message.reply("Отправь ссылку на TikTok или Instagram.")

    url = urls[0]
    user_id = message.from_user.id
    used, pro = get_user(user_id)

    if not pro and used >= FREE_LIMIT:
        return await message.reply("Лимит исчерпан. Купите PRO (/buy)")

    await message.reply("Обрабатываю... 🔄")

    try:
        # TikTok
        if "tiktok.com" in url:
            api_url = TIKTOK_API.format(url=url)
            response = requests.get(api_url).json()

            play = response.get("data", {}).get("play")
            if not play:
                return await message.reply("Не удалось скачать видео. Попробуй другой URL.")

            video_bytes = requests.get(play).content

        # Instagram
        elif "instagram.com" in url:
            api_url = INSTAGRAM_API.format(url=url)
            response = requests.get(api_url).json()

            video = response.get("media")
            if not video:
                return await message.reply("Не удалось скачать. Возможно приватный профиль.")

            video_bytes = requests.get(video).content

        else:
            return await message.reply("Неверная ссылка.")

        increment_used(user_id)

        file = io.BytesIO(video_bytes)
        file.seek(0)

        await message.answer_video(InputFile(file, filename="video.mp4"))

    except Exception as e:
        await message.reply(f"Ошибка: {e}")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
