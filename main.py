import os, re, requests, sqlite3, io
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InputFile

load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise SystemExit("TOKEN missing in .env")

SERVICE_NAME = "InstaTok Saver"
DB_PATH = "data.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, free_used INTEGER DEFAULT 0, pro INTEGER DEFAULT 0)")
conn.commit()

FREE_LIMIT = 5
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

TIKTOK_API = "https://api.sssapi.net/tiktok?url={url}"
INSTAGRAM_API = "https://api.sssapi.net/instagram?url={url}"
URL_RE = re.compile(r'https?://\S+')

def get_user(uid):
    cur.execute("INSERT OR IGNORE INTO users (user_id, free_used, pro) VALUES (?,0,0)", (uid,))
    cur.execute("SELECT free_used, pro FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def increment(uid):
    cur.execute("UPDATE users SET free_used = free_used + 1 WHERE user_id=?", (uid,))
    conn.commit()

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("TikTok", "Instagram", "PRO", "Баланс")
    
    text = (
        "Привет! Я InstaTok Saver — скачиваю видео из TikTok/Instagram без водяных знаков.\n"
        "Просто вставь ссылку ↓"
    )
    
    await message.reply(text, reply_markup=kb)

@dp.message_handler(commands=["balance"])
async def balance(message: types.Message):
    used, pro = get_user(message.from_user.id)
    await message.reply(f"Бесплатно: {used}/{FREE_LIMIT}. PRO: {'Да' if pro else 'Нет'}")

@dp.message_handler()
async def handle(message: types.Message):
    txt = message.text or ""
    urls = URL_RE.findall(txt)
    if not urls:
        return await message.reply("Пришли ссылку на TikTok или Instagram.")
    url = urls[0]

    used, pro = get_user(message.from_user.id)
    if not pro and used >= FREE_LIMIT:
        return await message.reply("Лимит исчерпан. Купи PRO.")

    await message.reply("Обрабатываю...")
    try:
        if "tiktok" in url:
            api = TIKTOK_API.format(url=url)
            data = requests.get(api).json()
            video = data.get("video_no_watermark") or data.get("video") 
        else:
            api = INSTAGRAM_API.format(url=url)
            data = requests.get(api).json()
            video = data.get("video") or data.get("url")

        if not video:
            return await message.reply("Не удалось получить видео.")

        file = requests.get(video).content
        bio = io.BytesIO(file)
        bio.seek(0)
        increment(message.from_user.id)
        await message.answer_video(InputFile(bio, "video.mp4"))
    except Exception as e:
        await message.reply("Ошибка: " + str(e))

if __name__ == "__main__":
    executor.start_polling(dp) 
