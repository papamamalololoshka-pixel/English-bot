import asyncio
import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ---------- Настройки (задаются в переменных окружения) ----------
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # ваш Telegram ID, чтобы видеть /stats
DAILY_HOUR_UTC = int(os.getenv("DAILY_HOUR_UTC", "6"))  # 6 UTC = 9:00 по Москве
DB_PATH = os.getenv("DB_PATH", "bot.db")
QUIZ_LEN = 5

# ---------- Слова: (английский, перевод, пример, перевод примера) ----------
WORDS = [
    ("achieve", "достигать", "She worked hard to achieve her goal.", "Она много работала, чтобы достичь цели."),
    ("borrow", "брать взаймы", "Can I borrow your pen?", "Можно взять твою ручку?"),
    ("choose", "выбирать", "It is hard to choose one dish.", "Трудно выбрать одно блюдо."),
    ("deliver", "доставлять", "They deliver pizza in 30 minutes.", "Они доставляют пиццу за 30 минут."),
    ("enough", "достаточно", "I have had enough coffee today.", "Мне сегодня хватит кофе."),
    ("forget", "забывать", "Don't forget your keys.", "Не забудь ключи."),
    ("gather", "собирать", "People gather in the square at noon.", "Люди собираются на площади в полдень."),
    ("honest", "честный", "He is an honest person.", "Он честный человек."),
    ("improve", "улучшать", "I want to improve my English.", "Я хочу улучшить свой английский."),
    ("journey", "путешествие", "The journey took three days.", "Путешествие заняло три дня."),
    ("knowledge", "знания", "Knowledge is power.", "Знание — сила."),
    ("lonely", "одинокий", "He felt lonely in a new city.", "Он чувствовал себя одиноко в новом городе."),
    ("manage", "справляться", "How do you manage to do it all?", "Как ты со всем справляешься?"),
    ("notice", "замечать", "Did you notice the new sign?", "Ты заметил новую вывеску?"),
    ("opportunity", "возможность", "This is a great opportunity.", "Это отличная возможность."),
    ("prefer", "предпочитать", "I prefer tea to coffee.", "Я предпочитаю чай кофе."),
    ("quickly", "быстро", "Please answer quickly.", "Пожалуйста, ответь быстро."),
    ("remind", "напоминать", "Remind me to call mom.", "Напомни мне позвонить маме."),
    ("suggest", "предлагать", "I suggest we go home.", "Я предлагаю пойти домой."),
    ("tired", "уставший", "I am too tired to talk.", "Я слишком устал, чтобы говорить."),
    ("useful", "полезный", "This app is very useful.", "Это приложение очень полезное."),
    ("village", "деревня", "She grew up in a small village.", "Она выросла в маленькой деревне."),
    ("warn", "предупреждать", "I warned him about the traffic.", "Я предупредил его о пробках."),
    ("wonder", "интересоваться", "I wonder what time it is.", "Интересно, который час."),
    ("anxious", "тревожный", "She felt anxious before the exam.", "Она тревожилась перед экзаменом."),
    ("believe", "верить", "I believe in you.", "Я верю в тебя."),
    ("career", "карьера", "He started his career as a teacher.", "Он начал карьеру учителем."),
    ("decide", "решать", "We need to decide today.", "Нам нужно решить сегодня."),
    ("expensive", "дорогой", "This watch is too expensive.", "Эти часы слишком дорогие."),
    ("familiar", "знакомый", "This song sounds familiar.", "Эта песня звучит знакомо."),
]

# ---------- База данных ----------
db = sqlite3.connect(DB_PATH)
db.execute(
    """CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        streak INTEGER DEFAULT 0,
        last_day TEXT,
        best INTEGER DEFAULT 0,
        joined TEXT
    )"""
)
db.commit()


def today():
    return datetime.now(timezone.utc).date()


def add_user(uid):
    db.execute("INSERT OR IGNORE INTO users(user_id, joined) VALUES (?, ?)", (uid, str(today())))
    db.commit()


def get_user(uid):
    add_user(uid)
    row = db.execute("SELECT streak, last_day, best FROM users WHERE user_id=?", (uid,)).fetchone()
    return {"streak": row[0], "last_day": row[1], "best": row[2]}


def finish_quiz_record(uid, score):
    u = get_user(uid)
    t = today()
    if u["last_day"] == str(t):
        streak = u["streak"]
    elif u["last_day"] == str(t - timedelta(days=1)):
        streak = u["streak"] + 1
    else:
        streak = 1
    best = max(u["best"], score)
    db.execute(
        "UPDATE users SET streak=?, last_day=?, best=? WHERE user_id=?",
        (streak, str(t), best, uid),
    )
    db.commit()
    return streak


# ---------- Вспомогательное ----------
BOT_USERNAME = ""
QUIZ = {}  # состояние квиза по user_id (в памяти)


def word_of_day():
    return WORDS[today().toordinal() % len(WORDS)]


def format_word(w):
    en, ru, ex, ex_ru = w
    return f"📚 <b>Слово дня</b>\n\n<b>{en}</b> — {ru}\n\n💬 {ex}\n<i>{ex_ru}</i>"


def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📚 Слово дня", callback_data="word")
    kb.button(text="🎯 Квиз", callback_data="quiz")
    kb.button(text="🔥 Моя серия", callback_data="streak")
    kb.adjust(1, 2)
    return kb.as_markup()


def quiz_button():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Пройти квиз", callback_data="quiz")
    return kb.as_markup()


def share_url(score, streak):
    text = f"Я набрал {score}/{QUIZ_LEN} в квизе по английскому, серия {streak} дн. подряд! Попробуй и ты 👇"
    return f"https://t.me/share/url?url={quote('https://t.me/' + BOT_USERNAME)}&text={quote(text)}"


# ---------- Обработчики ----------
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    add_user(message.from_user.id)
    await message.answer(
        "Привет! Я помогу учить английский по чуть-чуть каждый день 🇬🇧\n\n"
        "Каждое утро присылаю новое слово, а квиз из 5 вопросов помогает его запомнить. "
        "Проходи квиз каждый день и копи серию 🔥",
        reply_markup=main_menu(),
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    new_today = db.execute("SELECT COUNT(*) FROM users WHERE joined=?", (str(today()),)).fetchone()[0]
    await message.answer(f"👥 Всего пользователей: {total}\n🆕 Сегодня: {new_today}")


@dp.callback_query(F.data == "word")
async def cb_word(call: CallbackQuery):
    add_user(call.from_user.id)
    await call.message.answer(format_word(word_of_day()), reply_markup=quiz_button())
    await call.answer()


@dp.callback_query(F.data == "streak")
async def cb_streak(call: CallbackQuery):
    u = get_user(call.from_user.id)
    t = today()
    alive = u["last_day"] in (str(t), str(t - timedelta(days=1)))
    streak = u["streak"] if alive else 0
    await call.message.answer(
        f"🔥 Серия: <b>{streak}</b> дн. подряд\n🏆 Лучший результат: <b>{u['best']}/{QUIZ_LEN}</b>",
        reply_markup=quiz_button(),
    )
    await call.answer()


async def send_question(message: Message, uid):
    st = QUIZ[uid]
    correct_idx = st["order"][st["i"]]
    wrong = random.sample([x for x in range(len(WORDS)) if x != correct_idx], 3)
    options = wrong + [correct_idx]
    random.shuffle(options)
    st["options"] = options
    st["question"] = f"Вопрос {st['i'] + 1}/{QUIZ_LEN}\nКак переводится <b>{WORDS[correct_idx][0]}</b>?"
    kb = InlineKeyboardBuilder()
    for pos, idx in enumerate(options):
        kb.button(text=WORDS[idx][1], callback_data=f"ans:{pos}")
    kb.adjust(2)
    await message.answer(st["question"], reply_markup=kb.as_markup())


@dp.callback_query(F.data == "quiz")
async def cb_quiz(call: CallbackQuery):
    uid = call.from_user.id
    add_user(uid)
    QUIZ[uid] = {"order": random.sample(range(len(WORDS)), QUIZ_LEN), "i": 0, "score": 0}
    await call.answer()
    await send_question(call.message, uid)


@dp.callback_query(F.data.startswith("ans:"))
async def cb_answer(call: CallbackQuery):
    uid = call.from_user.id
    st = QUIZ.get(uid)
    if not st or "options" not in st:
        await call.answer("Квиз устарел, начни заново", show_alert=True)
        return
    pos = int(call.data.split(":")[1])
    chosen = st["options"][pos]
    correct = st["order"][st["i"]]
    if chosen == correct:
        st["score"] += 1
        verdict = "✅ Верно!"
    else:
        verdict = f"❌ Неверно. Правильно: <b>{WORDS[correct][1]}</b>"
    await call.message.edit_text(f"{st['question']}\n\n{verdict}")
    await call.answer()

    st["i"] += 1
    st.pop("options", None)
    if st["i"] < QUIZ_LEN:
        await send_question(call.message, uid)
        return

    score = st["score"]
    streak = finish_quiz_record(uid, score)
    QUIZ.pop(uid, None)
    kb = InlineKeyboardBuilder()
    kb.button(text="🔁 Ещё раз", callback_data="quiz")
    kb.button(text="📤 Поделиться результатом", url=share_url(score, streak))
    kb.adjust(1)
    await call.message.answer(
        f"🏁 Результат: <b>{score}/{QUIZ_LEN}</b>\n🔥 Серия: <b>{streak}</b> дн. подряд\n\n"
        "Возвращайся завтра, чтобы не потерять серию!",
        reply_markup=kb.as_markup(),
    )


# ---------- Ежедневная рассылка ----------
async def daily_loop(bot: Bot):
    while True:
        now = datetime.now(timezone.utc)
        nxt = now.replace(hour=DAILY_HOUR_UTC, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        await asyncio.sleep((nxt - now).total_seconds())
        for (uid,) in db.execute("SELECT user_id FROM users").fetchall():
            try:
                await bot.send_message(uid, format_word(word_of_day()), reply_markup=quiz_button())
            except Exception:
                pass  # пользователь заблокировал бота
            await asyncio.sleep(0.05)


async def main():
    global BOT_USERNAME
    if not TOKEN:
        raise SystemExit("Не задана переменная BOT_TOKEN")
    logging.basicConfig(level=logging.INFO)
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    BOT_USERNAME = (await bot.get_me()).username
    daily_task = asyncio.create_task(daily_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        daily_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
