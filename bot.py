#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бот для создания тестов для подруг @PodrugaTestBot
Версия: 81.0 - ПОЛНАЯ ВЕРСИЯ СО ВСЕМИ ИСПРАВЛЕНИЯМИ
"""

import logging
import json
import sqlite3
import random
import os
import asyncio
import hashlib
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageColor
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

# === НАСТРОЙКА ===
BOT_USERNAME = "PodrugaTestBot"
DB_NAME = 'bot_database.db'
START_TESTS = 3
DAILY_BONUS_POINTS = 10
MAX_OPTIONS = 4
MIN_OPTIONS = 2
MAX_QUESTIONS_FREE = 5
MAX_QUESTIONS_PREMIUM = 10
MAX_CREATED_FREE = 3
MAX_CREATED_PREMIUM = 10
MAX_SAVED_FREE = 3
MAX_SAVED_PREMIUM = 10
ADMIN_ID = 710623393

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === ФУНКЦИЯ ДЛЯ СКЛОНЕНИЯ СЛОВ ===
def decline_word(number, word1, word2, word3):
    if 11 <= number % 100 <= 19:
        return word3
    if number % 10 == 1:
        return word1
    if 2 <= number % 10 <= 4:
        return word2
    return word3

def escape_markdown(text):
    """Экранирует специальные символы Markdown"""
    if not text:
        return ""
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

# === ГРУППЫ ВОПРОСОВ ===
FREE_QUESTION_GROUPS = {
    'friendship': '👭 Дружба',
    'love': '💖 Любовь',
    'humor': '😂 Приколы',
    'myself': '🌸 Про меня'
}

PREMIUM_QUESTION_GROUPS = {
    'friendship': '👭 Дружба',
    'love': '💖 Любовь',
    'humor': '😂 Приколы',
    'myself': '🌸 Про меня',
    'family': '🏠 Семья',
    'school': '📚 Школа',
    'style': '👗 Стиль',
    'social': '📱 Соцсети',
    'dreams': '✨ Мечты',
    'kpop': '🎤 K-pop',
    'animals': '🐾 Животные',
    'travel': '✈️ Путешествия',
    'food': '🍕 Еда',
    'games': '🎮 Игры',
    'movies': '🎬 Кино',
    'sport': '⚽ Спорт'
}

# === ВОПРОСЫ ПО ГРУППАМ ===
QUESTIONS_BY_GROUP = {
    'friendship': [
        "✨ Как долго мы дружим? ✨", "💕 Где мы познакомились? 💕", "🎨 Мой любимый цвет? 🎨",
        "🍕 Моя любимая еда? 🍕", "💃 Моё любимое занятие? 💃", "📺 Мой любимый сериал? 📺",
        "😤 Что меня бесит? 😤", "🌟 Моя заветная мечта? 🌟", "🎵 Мой любимый исполнитель? 🎵", "📚 Моя любимая книга? 📚"
    ],
    'love': [
        "💘 Какой тип парня мне нравится? 💘", "💕 Что для меня важно в отношениях? 💕",
        "😳 Как я показываю симпатию? 😳", "🌹 Моё идеальное свидание? 🌹", "✨ Что меня влюбляет? ✨",
        "🎁 Какой подарок я мечтаю получить? 🎁", "🙄 Что меня раздражает в парнях? 🙄",
        "📱 Мой краш из тиктока? 📱", "💋 Первый поцелуй - это важно? 💋", "💍 Хочу ли я замуж? 💍"
    ],
    'humor': [
        "🏃‍♀️ Что я делаю, когда опаздываю? 🏃‍♀️", "🤪 Моя самая странная привычка? 🤪",
        "💃 Как я танцую? 💃", "🍪 Что я ем ночью? 🍪", "👀 Как я вру? 👀",
        "😱 Что делаю при виде паука? 😱", "🐌 Мой смешной страх? 🐌", "💬 Моя коронная фраза? 💬",
        "🛌 Как я сплю? 🛌", "🎤 Моя песня в караоке? 🎤"
    ],
    'myself': [
        "💪 Моя суперсила? 💪", "🦄 Что мне нужно для счастья? 🦄", "🎧 Как я справляюсь со стрессом? 🎧",
        "👩‍🎤 Кем я хочу стать в будущем? 👩‍🎤", "💅 Что я больше всего люблю в себе? 💅",
        "😨 Мой главный страх? 😨", "✨ Моя фишка? ✨", "🌈 Что меня вдохновляет? 🌈",
        "🕰️ Моя лучшая черта характера? 🕰️", "💎 Моё самое большое достижение? 💎"
    ],
    'family': [
        "💕 С кем я самая близкая в семье? 💕", "🍿 Что я люблю делать с семьёй? 🍿",
        "🎄 Какая у нас семейная традиция? 🎄", "👩‍👧 На кого я похожа внешне? 👩‍👧",
        "😅 Что меня бесит в родителях? 😅", "👫 Есть ли у меня брат или сестра? 👫",
        "💖 Что я больше всего ценю в семье? 💖", "👵 Моя любимая бабушка? 👵",
        "📸 Люблю ли я семейные фото? 📸", "🏠 Хочу ли я жить отдельно? 🏠"
    ],
    'school': [
        "📖 Мой любимый предмет в школе? 📖", "😫 Самый ненавистный урок? 😫",
        "📱 Что я делаю на скучных уроках? 📱", "👯 С кем я сижу за партой? 👯",
        "🤫 Как я списываю? 🤫", "🍔 Что я ем в школьной столовой? 🍔",
        "👩‍🏫 Моя училка-краш? 👩‍🏫", "👻 Кого я боюсь в школе? 👻",
        "🏆 Моя лучшая оценка? 🏆", "🎒 Что всегда в моём рюкзаке? 🎒"
    ],
    'style': [
        "👗 Мой любимый стиль одежды? 👗", "🎀 Мой любимый цвет в одежде? 🎀",
        "🙅‍♀️ Что я никогда не надену? 🙅‍♀️", "🛍️ Моя вещь must-have? 🛍️",
        "✨ Что я надеваю на вечеринку? ✨", "👟 Моя любимая обувь? 👟",
        "💇‍♀️ Как я крашу волосы? 💇‍♀️", "🌸 Моя любимая косметика? 🌸",
        "💄 Моя любимая помада? 💄", "👜 Моя любимая сумка? 👜"
    ],
    'social': [
        "📱 Мой любимый тиктокер? 📱", "📸 Что я пощу в сторис? 📸",
        "❤️ Сколько лайков в среднем набираю? ❤️", "🦄 Мой любимый фильтр? 🦄",
        "👯 С кем я снимаю контент? 👯", "📺 От какого контента я зависаю? 📺",
        "🎵 Мой любимый звук в тиктоке? 🎵", "👑 Какая у меня подписей? 👑",
        "🔒 Мой аккаунт приватный или открытый? 🔒", "💬 Сколько времени сижу в телеграме? 💬"
    ],
    'dreams': [
        "✈️ Куда я мечтаю поехать? ✈️", "🌟 Моя самая заветная мечта? 🌟",
        "🚗 Какую машину я хочу? 🚗", "☀️ Мой идеальный день? ☀️",
        "🛍️ Что я хочу купить прямо сейчас? 🛍️", "📝 Что у меня в wishlist? 📝",
        "🏠 Где я хочу жить? 🏠", "💎 О чём я мечтаю каждый день? 💎",
        "🎓 Кем я вижу себя через 5 лет? 🎓", "💍 Какой я представляю свою свадьбу? 💍"
    ],
    'kpop': [
        "🎤 Моя любимая k-pop группа? 🎤", "💕 Мой биас (любимый участник)? 💕",
        "🎧 Какой трек сейчас на повторе? 🎧", "💜 На каком концерте я была? 💜",
        "⭐ С кем из айдолов хочу встретиться? ⭐", "💃 Какой танец я выучила? 💃",
        "🫶 Кто мой вайб? 🫶", "🎁 Какой мерч я хочу? 🎁",
        "📺 Моё любимое k-pop шоу? 📺", "🌙 Какой юнит или соло я люблю? 🌙"
    ],
    'animals': [
        "🐾 Моё любимое животное? 🐾", "🐱 Есть ли у меня домашний питомец? 🐱",
        "🦄 Какое животное я хотела бы завести? 🦄", "🐍 Боюсь ли я животных? 🐍",
        "🐶 Люблю ли я кошек или собак? 🐶", "🦁 Что делаю при виде бездомного животного? 🦁",
        "🐭 Было ли у меня животное в детстве? 🐭", "🐬 Какое животное мне кажется самым умным? 🐬",
        "🐘 Хочу ли я поехать на сафари? 🐘", "🐧 Какое животное отражает мой характер? 🐧"
    ],
    'travel': [
        "✈️ Куда я мечтаю поехать? ✈️", "🏖️ Мой идеальный отдых? 🏖️",
        "🎒 Что я беру в поездку? 🎒", "🚗 Как я добираюсь до места? 🚗",
        "📸 Что я делаю в дороге? 📸", "🌍 Где я уже была? 🌍",
        "👯 С кем я хочу путешествовать? 👯", "🗺️ Что делаю, если потерялась? 🗺️",
        "🏨 Отель или хостел? 🏨", "🍜 Какая национальная кухня нравится? 🍜"
    ],
    'food': [
        "🍕 Моё любимое блюдо? 🍕", "😖 Что я ненавижу есть? 😖",
        "👩‍🍳 Что я умею готовить? 👩‍🍳", "☕ Что я заказываю в кафе? ☕",
        "🍰 Какие сладости я люблю? 🍰", "🍳 Что я ем на завтрак? 🍳",
        "🏠 Моё любимое кафе? 🏠", "🚫 Какую еду я никогда не буду есть? 🚫",
        "🍜 Лапша или картошка? 🍜", "🥤 Мой любимый напиток? 🥤"
    ],
    'games': [
        "🎮 В какие игры я играю? 🎮", "👾 Моя любимая игра? 👾",
        "📱 Играю ли я в мобильные игры? 📱", "🎯 Мой ранг в любимой игре? 🎯",
        "🕹️ С кем я играю? 🕹️", "💰 Трачу ли я деньги на игры? 💰",
        "🎁 Какой скин хочу? 🎁", "🏆 Моё достижение в игре? 🏆",
        "💻 Играю на телефоне или компьютере? 💻", "🎮 Как часто я играю? 🎮"
    ],
    'movies': [
        "🎬 Мой любимый фильм? 🎬", "🍿 Какой жанр я люблю? 🍿",
        "🎭 Мой любимый актёр/актриса? 🎭", "📺 Какой сериал я смотрю? 📺",
        "😭 Какой фильм заставил меня плакать? 😭", "😂 Какой фильм меня рассмешил? 😂",
        "🎥 В кино или дома? 🎥", "🍿 С кем я смотрю фильмы? 🍿",
        "🎬 Какой фильм пересматривала много раз? 🎬", "📽️ Какой фильм жду с нетерпением? 📽️"
    ],
    'sport': [
        "⚽ Каким спортом я занимаюсь? ⚽", "🏆 Моя любимая команда? 🏆",
        "🏅 За кого болею? 🏅", "🏃‍♀️ Как часто я тренируюсь? 🏃‍♀️",
        "🧘‍♀️ Йога или фитнес? 🧘‍♀️", "🎾 Смотрю ли я спортивные соревнования? 🎾",
        "🏊‍♀️ Умею ли я плавать? 🏊‍♀️", "🚴‍♀️ Люблю ли велосипед? 🚴‍♀️",
        "🥇 Моё спортивное достижение? 🥇", "🏋️‍♀️ Хожу ли в зал? 🏋️‍♀️"
    ]
}

# === УРОВНИ ===
LEVELS = [
    {'name': '🌱 НОВЕНЬКАЯ', 'min_score': 0, 'reward': 'обычный диплом'},
    {'name': '📚 ЗНАТОК', 'min_score': 500, 'reward': '+1 тест'},
    {'name': '💎 БРИЛЛИАНТ', 'min_score': 1500, 'reward': '+2 теста'},
    {'name': '👑 КОРОЛЕВА', 'min_score': 3500, 'reward': '+3 теста'},
    {'name': '🌟 ЗВЕЗДА', 'min_score': 7000, 'reward': '+5 тестов'},
    {'name': '👸 ЛЕГЕНДА', 'min_score': 15000, 'reward': 'месяц премиума'}
]

DAILY_TASKS = {
    'complete_test': {'name': '📝 Пройти тест', 'points': 5, 'description': 'Пройди любой тест от подруги ✨'},
    'send_test': {'name': '📤 Отправить тест', 'points': 10, 'description': 'Отправь тест подруге 💕'},
    'get_result': {'name': '🎯 Получить результат', 'points': 15, 'description': 'Дождись, пока подруга пройдёт твой тест 🌸'},
    'create_test': {'name': '✨ Создать тест', 'points': 20, 'description': 'Создай новый тест о себе 🎀'},
    'invite_friend': {'name': '👭 Пригласить подругу', 'points': 30, 'description': 'Пригласи подругу по ссылке 💖'}
}

STREAK_REWARDS = {
    7: {'points': 50, 'tests': 1, 'premium_days': 0, 'description': '50 очков + 1 тест'},
    14: {'points': 100, 'tests': 2, 'premium_days': 0, 'description': '100 очков + 2 теста'},
    30: {'points': 300, 'tests': 0, 'premium_days': 7, 'description': '300 очков + 7 дней премиума'},
    100: {'points': 1000, 'tests': 0, 'premium_days': 30, 'description': '1000 очков + 30 дней премиума'}
}

DIPLOMS = {
    'free': {
        'name': '🌸 КЛАССИЧЕСКИЙ ДИПЛОМ 🌸',
        'icon': '📜',
        'text': 'Ты супер! Так держать, подружка! 💕',
        'color': '#FF69B4',
        'accent': '#FFB6C1',
        'bg_start': '#FFF5F7',
        'bg_end': '#FFE4E9'
    },
    'premium_royal': {
        'name': '👑 КОРОЛЕВСКИЙ ДИПЛОМ 👑',
        'icon': '👑',
        'text': 'Ты настоящая королева дружбы! 👸💎',
        'color': '#FFD700',
        'accent': '#DAA520',
        'bg_start': '#FFF8DC',
        'bg_end': '#FFEFD5'
    },
    'premium_diamond': {
        'name': '💎 БРИЛЛИАНТОВЫЙ ДИПЛОМ 💎',
        'icon': '💎',
        'text': 'Ты сияешь ярче бриллианта! ✨💕',
        'color': '#00CED1',
        'accent': '#48D1CC',
        'bg_start': '#E0FFFF',
        'bg_end': '#AFEEEE'
    },
    'premium_star': {
        'name': '🌟 ЗВЁЗДНЫЙ ДИПЛОМ 🌟',
        'icon': '🌟',
        'text': 'Ты настоящая звезда! 🌟⭐✨',
        'color': '#9370DB',
        'accent': '#BA55D3',
        'bg_start': '#F3E5F5',
        'bg_end': '#E1BEE7'
    },
    'premium_unicorn': {
        'name': '🦄 ВОЛШЕБНЫЙ ДИПЛОМ 🦄',
        'icon': '🦄',
        'text': 'Ты уникальна, как единорог! 🦄💖',
        'color': '#FF69B4',
        'accent': '#FF85C8',
        'bg_start': '#FFE4E1',
        'bg_end': '#FFD1DC'
    },
    'premium_flower': {
        'name': '🌸 ЦВЕТОЧНЫЙ ДИПЛОМ 🌸',
        'icon': '🌸',
        'text': 'Ты нежная и красивая, как цветок! 🌸💗',
        'color': '#FF7F50',
        'accent': '#FFA07A',
        'bg_start': '#FFF0F5',
        'bg_end': '#FFE4E1'
    }
}

WOW_EMOJIS = {
    'start': '🌸', 'success': '🎉', 'error': '💔',
    'test': '📝', 'friend': '👯', 'crown': '👑',
    'star': '⭐', 'heart': '💗', 'daily': '🎁',
    'achievement': '🏆', 'shop': '🛍️', 'money': '💰',
    'top': '🏆', 'back': '🔙', 'stats': '📊', 'cancel': '❌',
    'favorite': '💖', 'diplom': '🎓', 'task': '📋', 'level': '📈',
    'sparkle': '✨', 'cute': '🎀', 'fire': '🔥', 'random': '🎲'
}

# === БАЗА ДАННЫХ ===
def get_db():
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Ошибка БД: {e}")
        raise

def init_db():
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            tests_created INTEGER DEFAULT 0,
            tests_available INTEGER DEFAULT 3,
            total_points INTEGER DEFAULT 0,
            weekly_points INTEGER DEFAULT 0,
            daily_streak INTEGER DEFAULT 0,
            last_daily TEXT,
            unlimited_until TEXT DEFAULT NULL,
            referral_code TEXT UNIQUE,
            referral_count INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL,
            selected_diplom TEXT DEFAULT 'free',
            selected_frame TEXT DEFAULT 'none',
            selected_badge TEXT DEFAULT 'none',
            gold_nickname INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER,
            creator_name TEXT,
            creator_username TEXT,
            title TEXT,
            questions TEXT,
            options TEXT,
            correct_answers TEXT,
            greeting_type TEXT,
            greeting_file_id TEXT,
            greeting_duration INTEGER DEFAULT 0,
            diplom_type TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Добавляем поле diplom_type если его нет
        try:
            c.execute('ALTER TABLE tests ADD COLUMN diplom_type TEXT DEFAULT "free"')
        except:
            pass
        
        c.execute('''CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER,
            friend_id INTEGER,
            friend_name TEXT,
            friend_username TEXT,
            answers TEXT,
            score REAL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(test_id, friend_id)
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS saved_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            test_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, test_id)
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS daily_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_date TEXT,
            task_type TEXT,
            completed INTEGER DEFAULT 0,
            UNIQUE(user_id, task_date, task_type)
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            achievement_type TEXT,
            achieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, achievement_type)
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        c.execute('CREATE INDEX IF NOT EXISTS idx_tests_creator ON tests(creator_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_attempts_test ON attempts(test_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_saved_tests_user ON saved_tests(user_id)')
        
        conn.commit()
        logger.info("✅ База данных готова")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        raise
    finally:
        if conn:
            conn.close()

init_db()

# === ФУНКЦИИ ДЛЯ РАБОТЫ С БД ===
def get_test_attempts_count(test_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM attempts WHERE test_id = ?', (test_id,))
        return c.fetchone()[0]
    finally:
        conn.close()

def get_user_created_tests(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        has_premium = is_premium(user_id)
        limit = MAX_CREATED_PREMIUM if has_premium else MAX_CREATED_FREE
        c.execute('SELECT id, title, created_at FROM tests WHERE creator_id = ? ORDER BY created_at DESC LIMIT ?', (user_id, limit))
        tests = []
        for row in c.fetchall():
            test = dict(row)
            test['attempts_count'] = get_test_attempts_count(test['id'])
            test_data = get_test_by_id(test['id'])
            test['questions_count'] = len(test_data['questions']) if test_data else 0
            tests.append(test)
        return tests
    finally:
        conn.close()

def get_test_by_id(test_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM tests WHERE id = ?', (test_id,))
        row = c.fetchone()
        if row:
            test = dict(row)
            test['questions'] = json.loads(test['questions'] or '[]')
            test['options'] = json.loads(test['options'] or '[]')
            test['correct_answers'] = json.loads(test['correct_answers'] or '[]')
            test['attempts_count'] = get_test_attempts_count(test_id)
            return test
        return None
    finally:
        conn.close()

def get_user(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def generate_referral_code(user_id: int) -> str:
    hash_obj = hashlib.md5(f"{user_id}{random.randint(1000, 9999)}".encode())
    code = hash_obj.hexdigest()[:8].upper()
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT user_id FROM users WHERE referral_code = ?', (code,))
        if c.fetchone():
            return generate_referral_code(user_id + random.randint(1, 100))
        return code
    finally:
        conn.close()

def get_user_by_referral_code(code: str):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT user_id FROM users WHERE referral_code = ?', (code,))
        row = c.fetchone()
        return row['user_id'] if row else None
    finally:
        conn.close()

def create_user(user_id, username=None, first_name=None, referred_by=None):
    conn = get_db()
    try:
        c = conn.cursor()
        code = generate_referral_code(user_id)
        c.execute('''INSERT INTO users 
            (user_id, username, first_name, referral_code, referred_by, tests_available)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (user_id, username, first_name, code, referred_by, START_TESTS))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка создания пользователя: {e}")
        return False
    finally:
        conn.close()

def update_user(user_id, username=None, first_name=None):
    conn = get_db()
    try:
        c = conn.cursor()
        if username:
            c.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
        if first_name:
            c.execute('UPDATE users SET first_name = ? WHERE user_id = ?', (first_name, user_id))
        conn.commit()
        return True
    finally:
        conn.close()

def add_tests(user_id, count):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('UPDATE users SET tests_available = tests_available + ? WHERE user_id = ?', (count, user_id))
        conn.commit()
        return True
    finally:
        conn.close()

def add_weekly_points(user_id, points):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('UPDATE users SET weekly_points = weekly_points + ? WHERE user_id = ?', (points, user_id))
        conn.commit()
        return True
    finally:
        conn.close()

def reset_weekly_points():
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('UPDATE users SET weekly_points = 0')
        conn.commit()
        return True
    finally:
        conn.close()

def get_top_users_weekly(limit=10):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT u.user_id, u.first_name, u.username, u.weekly_points, u.tests_created, u.referral_count,
                   (SELECT COUNT(*) FROM attempts WHERE friend_id = u.user_id) as tests_passed
            FROM users u
            ORDER BY u.weekly_points DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def use_attempt(user_id):
    user = get_user(user_id)
    if user and user.get('unlimited_until'):
        try:
            if datetime.fromisoformat(user['unlimited_until']) > datetime.now():
                return True
        except:
            pass
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('UPDATE users SET tests_available = tests_available - 1 WHERE user_id = ? AND tests_available > 0', (user_id,))
        conn.commit()
        return c.rowcount > 0
    finally:
        conn.close()

def can_attempt_test(test_id, friend_id):
    test = get_test_by_id(test_id)
    if not test or test['creator_id'] == friend_id:
        return False
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT id FROM attempts WHERE test_id = ? AND friend_id = ?', (test_id, friend_id))
        return c.fetchone() is None
    finally:
        conn.close()

def get_available_tests(user_id):
    user = get_user(user_id)
    if not user:
        return START_TESTS
    if user.get('unlimited_until'):
        try:
            if datetime.fromisoformat(user['unlimited_until']) > datetime.now():
                return -1
        except:
            pass
    return user.get('tests_available', START_TESTS)

def add_points(user_id, points):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('UPDATE users SET total_points = total_points + ?, weekly_points = weekly_points + ? WHERE user_id = ?', (points, points, user_id))
        conn.commit()
        return True
    finally:
        conn.close()

def get_rank(score):
    for level in reversed(LEVELS):
        if score >= level['min_score']:
            return level
    return LEVELS[0]

def is_premium(user_id):
    user = get_user(user_id)
    if not user:
        return False
    unlimited = user.get('unlimited_until')
    if unlimited:
        try:
            if datetime.fromisoformat(unlimited) > datetime.now():
                return True
        except:
            pass
    return False

def get_premium_expiry(user_id):
    user = get_user(user_id)
    if not user:
        return None
    unlimited = user.get('unlimited_until')
    if unlimited:
        try:
            return datetime.fromisoformat(unlimited)
        except:
            pass
    return None

def get_daily_bonus(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT last_daily, daily_streak FROM users WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        today = datetime.now().date().isoformat()
        
        if row and row[0]:
            last_bonus = row[0]
            streak = row[1] or 0
            
            if last_bonus == today:
                return None, streak, None
            
            yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
            if last_bonus == yesterday:
                streak += 1
            else:
                streak = 1
            
            bonus = DAILY_BONUS_POINTS
            reward_info = None
            
            if streak in STREAK_REWARDS:
                reward = STREAK_REWARDS[streak]
                bonus += reward['points']
                if reward['tests'] > 0:
                    add_tests(user_id, reward['tests'])
                if reward['premium_days'] > 0:
                    until = (datetime.now() + timedelta(days=reward['premium_days'])).isoformat()
                    c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (until, user_id))
                add_achievement(user_id, f'streak_{streak}')
                reward_info = reward['description']
            
            c.execute('UPDATE users SET total_points = total_points + ?, last_daily = ?, daily_streak = ? WHERE user_id = ?',
                      (bonus, today, streak, user_id))
            conn.commit()
            return bonus, streak, reward_info
        else:
            c.execute('UPDATE users SET total_points = total_points + ?, last_daily = ?, daily_streak = 1 WHERE user_id = ?',
                      (DAILY_BONUS_POINTS, today, user_id))
            conn.commit()
            return DAILY_BONUS_POINTS, 1, None
    finally:
        conn.close()

def create_test(creator_id, creator_name, creator_username, title, questions, options, correct_answers, 
                greeting_type=None, greeting_file_id=None, greeting_duration=None, diplom_type='free'):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''INSERT INTO tests 
            (creator_id, creator_name, creator_username, title, questions, options, correct_answers, 
             greeting_type, greeting_file_id, greeting_duration, diplom_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (creator_id, creator_name, creator_username, title, json.dumps(questions), 
             json.dumps(options), json.dumps(correct_answers), greeting_type, greeting_file_id, 
             greeting_duration, diplom_type))
        test_id = c.lastrowid
        c.execute('UPDATE users SET tests_created = tests_created + 1 WHERE user_id = ?', (creator_id,))
        conn.commit()
        
        add_points(creator_id, 20)
        add_weekly_points(creator_id, 20)
        complete_daily_task(creator_id, 'create_test')
        add_achievement(creator_id, 'first_test')
        
        return test_id
    except Exception as e:
        logger.error(f"Ошибка создания теста: {e}")
        return None
    finally:
        conn.close()

def can_save_test(user_id, test_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT creator_id FROM tests WHERE id = ?', (test_id,))
        row = c.fetchone()
        if row and row['creator_id'] == user_id:
            return False
        
        saved_count = get_saved_tests_count(user_id)
        has_premium = is_premium(user_id)
        max_saved = MAX_SAVED_PREMIUM if has_premium else MAX_SAVED_FREE
        return saved_count < max_saved
    finally:
        conn.close()

def save_test(user_id, test_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT creator_id FROM tests WHERE id = ?', (test_id,))
        row = c.fetchone()
        if row and row['creator_id'] == user_id:
            return False
        
        if not can_save_test(user_id, test_id):
            return False
        
        c.execute('INSERT INTO saved_tests (user_id, test_id) VALUES (?, ?)', (user_id, test_id))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def unsave_test(user_id, test_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('DELETE FROM saved_tests WHERE user_id = ? AND test_id = ?', (user_id, test_id))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_saved_tests(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        has_premium = is_premium(user_id)
        limit = MAX_SAVED_PREMIUM if has_premium else MAX_SAVED_FREE
        c.execute('''SELECT t.id, t.title, t.creator_name, t.creator_id, t.creator_username, t.questions
                     FROM saved_tests s 
                     JOIN tests t ON s.test_id = t.id 
                     WHERE s.user_id = ?
                     ORDER BY s.created_at DESC
                     LIMIT ?''', (user_id, limit))
        tests = []
        for row in c.fetchall():
            test = dict(row)
            test['questions'] = json.loads(test['questions'] or '[]')
            test['questions_count'] = len(test['questions'])
            test['attempts_count'] = get_test_attempts_count(test['id'])
            tests.append(test)
        return tests
    finally:
        conn.close()

def get_saved_tests_count(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT COUNT(*) 
            FROM saved_tests s 
            JOIN tests t ON s.test_id = t.id 
            WHERE s.user_id = ? AND t.creator_id != ?
        ''', (user_id, user_id))
        return c.fetchone()[0]
    finally:
        conn.close()

async def save_attempt_async(test_id, friend_id, friend_name, friend_username, answers, score, bot=None):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO attempts (test_id, friend_id, friend_name, friend_username, answers, score)
            VALUES (?, ?, ?, ?, ?, ?)''', 
            (test_id, friend_id, friend_name, friend_username, json.dumps(answers), score))
        conn.commit()
        
        test = get_test_by_id(test_id)
        if test:
            add_points(test['creator_id'], 15)
            add_weekly_points(test['creator_id'], 15)
            complete_daily_task(test['creator_id'], 'get_result')
            
            if bot:
                await send_test_completed_notification(bot, test['creator_id'], friend_name, test['title'], score)
        
        add_points(friend_id, int(score))
        add_weekly_points(friend_id, int(score))
        complete_daily_task(friend_id, 'complete_test')
        
        conn.close()
        logger.info(f"✅ Попытка сохранена в фоне: user={friend_id}, score={score}")
    except Exception as e:
        logger.error(f"Ошибка сохранения попытки: {e}")

async def send_test_completed_notification(bot, creator_id, friend_name, test_title, score):
    try:
        text = (f"🎉💖 УРА! НОВЫЙ РЕЗУЛЬТАТ! 💖🎉\n\n"
                f"💕 {friend_name} прошла твой тестик\n"
                f"📝 {test_title}\n"
                f"🎯 Результат: {score:.0f}%\n"
                f"🏆 Статус: {get_friendship_status(score)}\n\n"
                f"✨ Ты получила +15 очков за задание! ✨")
        
        await safe_send_message(bot, creator_id, text)
    except Exception as e:
        logger.error(f"Ошибка уведомления: {e}")

async def send_greeting_delayed(bot, user_id, test):
    try:
        await asyncio.sleep(1)
        caption = f"🎬✨ ПОЗДРАВЛЕНИЕ ОТ ПОДРУЖКИ ✨🎬\n\n💕 Автор теста приготовила для тебя сюрприз! 💕"
        if test.get('greeting_type') == 'voice':
            await bot.send_voice(chat_id=user_id, voice=test['greeting_file_id'], caption=caption)
        elif test.get('greeting_type') == 'video':
            await bot.send_video(chat_id=user_id, video=test['greeting_file_id'], caption=caption)
        logger.info(f"✅ Поздравление отправлено: user={user_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки поздравления: {e}")

def add_achievement(user_id, achievement_type):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO achievements (user_id, achievement_type) VALUES (?, ?)', (user_id, achievement_type))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_achievements(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT achievement_type, achieved_at FROM achievements WHERE user_id = ? ORDER BY achieved_at DESC', (user_id,))
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_daily_tasks(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        today = datetime.now().date().isoformat()
        tasks = []
        for task_type in DAILY_TASKS:
            c.execute('SELECT completed FROM daily_tasks WHERE user_id = ? AND task_date = ? AND task_type = ?', 
                     (user_id, today, task_type))
            row = c.fetchone()
            completed = row['completed'] if row else 0
            tasks.append({
                'type': task_type,
                'name': DAILY_TASKS[task_type]['name'],
                'points': DAILY_TASKS[task_type]['points'],
                'description': DAILY_TASKS[task_type]['description'],
                'completed': completed
            })
        return tasks
    finally:
        conn.close()

def complete_daily_task(user_id, task_type):
    conn = get_db()
    try:
        c = conn.cursor()
        today = datetime.now().date().isoformat()
        
        c.execute('SELECT completed FROM daily_tasks WHERE user_id = ? AND task_date = ? AND task_type = ?', 
                 (user_id, today, task_type))
        row = c.fetchone()
        
        if row and row['completed'] == 1:
            logger.info(f"Задание {task_type} уже выполнено сегодня для {user_id}")
            return False
        
        c.execute('''INSERT INTO daily_tasks (user_id, task_date, task_type, completed) 
                     VALUES (?, ?, ?, 1) 
                     ON CONFLICT(user_id, task_date, task_type) DO UPDATE SET completed = 1''',
                  (user_id, today, task_type))
        
        if task_type in DAILY_TASKS:
            points = DAILY_TASKS[task_type]['points']
            add_points(user_id, points)
            add_weekly_points(user_id, points)
            logger.info(f"✅ Пользователю {user_id} начислено {points} очков за задание {task_type}")
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка выполнения задания: {e}")
        return False
    finally:
        conn.close()

def get_referral_stats(user_id: int) -> dict:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
        total = c.fetchone()[0]
        
        c.execute('''
            SELECT COUNT(DISTINCT r.referred_id) 
            FROM referrals r
            JOIN attempts a ON a.friend_id = r.referred_id
            WHERE r.referrer_id = ?
        ''', (user_id,))
        active = c.fetchone()[0] or 0
        
        return {'total': total, 'active': active}
    finally:
        conn.close()

def get_top_users_full(limit=10):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT u.user_id, u.first_name, u.username, u.total_points, u.tests_created, u.referral_count,
                   (SELECT COUNT(*) FROM attempts WHERE friend_id = u.user_id) as tests_passed
            FROM users u
            ORDER BY u.total_points DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_user_full_stats(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT tests_created, total_points, weekly_points, referral_count FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        c.execute('SELECT COUNT(*) FROM attempts WHERE friend_id = ?', (user_id,))
        tests_passed = c.fetchone()[0]
        return {
            'created': user['tests_created'] if user else 0,
            'points': user['total_points'] if user else 0,
            'weekly_points': user['weekly_points'] if user else 0,
            'invited': user['referral_count'] if user else 0,
            'passed': tests_passed
        }
    finally:
        conn.close()

def get_friend_answers_details(user_id, friend_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT t.id, t.title, t.questions, t.options, t.correct_answers,
                   a.answers, a.score, a.completed_at, a.friend_name
            FROM attempts a
            JOIN tests t ON a.test_id = t.id
            WHERE t.creator_id = ? AND a.friend_id = ?
            ORDER BY a.completed_at DESC
        ''', (user_id, friend_id))
        results = []
        for row in c.fetchall():
            result = dict(row)
            result['questions'] = json.loads(result['questions'])
            result['options'] = json.loads(result['options'])
            result['correct_answers'] = json.loads(result['correct_answers'])
            result['answers'] = json.loads(result['answers'])
            results.append(result)
        return results
    finally:
        conn.close()

def get_friendship_status(score):
    if score >= 95: return "👯‍♀️ СЁСТРЫ НАВЕК! 💕"
    if score >= 85: return "💎 ЛУЧШИЕ ПОДРУГИ НАВСЕГДА! 💎"
    if score >= 75: return "🌸 НАСТОЯЩИЕ ПОДРУЖКИ! 🌸"
    if score >= 65: return "💗 ОЧЕНЬ ХОРОШИЕ ПОДРУГИ! 💗"
    if score >= 55: return "👭 ХОРОШИЕ ПОДРУЖКИ! 👭"
    if score >= 45: return "👋 ПРИЯТЕЛЬНИЦЫ! 👋"
    if score >= 35: return "🤔 ХОРОШИЕ ЗНАКОМЫЕ 🤔"
    if score >= 25: return "😅 ЕЩЁ УЧИМСЯ ДРУГ ДРУГА 😅"
    if score >= 15: return "👀 ПРИСМАТРИВАЮСЬ К ТЕБЕ 👀"
    return "❓ КТО ТЫ, ПОДРУЖКА? ❓"

def get_next_level_points(current_points):
    for level in LEVELS:
        if level['min_score'] > current_points:
            return level['min_score'] - current_points
    return 0

def get_selected_diplom(user_id):
    user = get_user(user_id)
    return user.get('selected_diplom', 'free') if user else 'free'

def get_random_questions(user_id, count):
    has_premium = is_premium(user_id)
    if has_premium:
        all_questions = []
        for group in PREMIUM_QUESTION_GROUPS.keys():
            all_questions.extend(QUESTIONS_BY_GROUP.get(group, []))
    else:
        all_questions = []
        for group in FREE_QUESTION_GROUPS.keys():
            all_questions.extend(QUESTIONS_BY_GROUP.get(group, []))
    
    random.shuffle(all_questions)
    if len(all_questions) < count:
        return all_questions
    return all_questions[:count]

def get_user_created_tests_count(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM tests WHERE creator_id = ?', (user_id,))
        return c.fetchone()[0]
    finally:
        conn.close()

# === ФУНКЦИИ ДЛЯ ГЕНЕРАЦИИ ДИПЛОМОВ ===
def create_gradient_background(width, height, color1, color2):
    image = Image.new('RGB', (width, height), color1)
    draw = ImageDraw.Draw(image)
    
    if color1.startswith('#'):
        r1, g1, b1 = int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16)
        r2, g2, b2 = int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16)
    else:
        c1 = ImageColor.getrgb(color1)
        c2 = ImageColor.getrgb(color2)
        r1, g1, b1 = c1
        r2, g2, b2 = c2
    
    for y in range(height):
        ratio = y / height
        r = int(r1 + (r2 - r1) * ratio)
        g = int(g1 + (g2 - g1) * ratio)
        b = int(b1 + (b2 - b1) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    return image

def draw_ornate_border(draw, width, height, color):
    draw.rectangle([8, 8, width-9, height-9], outline=color, width=4)
    draw.rectangle([14, 14, width-15, height-15], outline=color, width=1)
    draw.rectangle([18, 18, width-19, height-19], outline=color, width=1)

def draw_double_border(draw, width, height, color1, color2):
    draw.rectangle([25, 25, width-26, height-26], outline=color1, width=2)
    draw.rectangle([30, 30, width-31, height-31], outline=color2, width=1)

def draw_corner_ornaments(draw, width, height, color):
    corners = [(35, 35), (width-35, 35), (35, height-35), (width-35, height-35)]
    for x, y in corners:
        draw.ellipse([x-8, y-8, x+8, y+8], outline=color, width=2)
        draw.ellipse([x-4, y-4, x+4, y+4], fill=color)

def draw_banner(draw, width, color1, color2):
    y1, y2 = 70, 78
    draw.rectangle([50, y1, width-50, y2], fill=color1)
    draw.rectangle([50, y2, width-50, y2+2], fill=color2)

def draw_banner_bottom(draw, width, height, color1, color2):
    y1, y2 = 570, 578
    draw.rectangle([50, y1, width-50, y2], fill=color1)
    draw.rectangle([50, y2, width-50, y2+2], fill=color2)

def draw_text_with_shadow(draw, position, text, font, color):
    x, y = position
    draw.text((x+1, y+1), text, fill='#CCCCCC', font=font)
    draw.text((x, y), text, fill=color, font=font)

def draw_sparkles(draw, width, height, color1, color2):
    import random
    random.seed(42)
    sparkles = ["✨", "⭐", "💫", "🌟", "✦", "✧"]
    for _ in range(12):
        x = random.randint(60, width-60)
        y = random.randint(150, 550)
        sparkle = random.choice(sparkles)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", random.randint(14, 20))
        except:
            font = ImageFont.load_default()
        color = color1 if random.random() > 0.5 else color2
        draw.text((x, y), sparkle, fill=color, font=font)

async def generate_diploma_image(user_name, test_title, score, status, points, diplom_type='free'):
    diplom = DIPLOMS.get(diplom_type, DIPLOMS['free'])
    width, height = 900, 700
    
    image = create_gradient_background(width, height, diplom.get('bg_start', '#FFF5F7'), diplom.get('bg_end', '#FFE4E9'))
    draw = ImageDraw.Draw(image)
    
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
        font_subtitle = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 22)
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_cursive = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf", 20)
    except:
        try:
            font_title = ImageFont.truetype("arial.ttf", 38)
            font_subtitle = ImageFont.truetype("arial.ttf", 24)
            font_text = ImageFont.truetype("arial.ttf", 22)
            font_big = ImageFont.truetype("arial.ttf", 52)
            font_cursive = ImageFont.truetype("arial.ttf", 20)
        except:
            font_title = ImageFont.load_default()
            font_subtitle = ImageFont.load_default()
            font_text = ImageFont.load_default()
            font_big = ImageFont.load_default()
            font_cursive = ImageFont.load_default()
    
    border_color = diplom.get('color', '#FF69B4')
    accent_color = diplom.get('accent', '#FFB6C1')
    
    draw_ornate_border(draw, width, height, border_color)
    draw_double_border(draw, width, height, border_color, accent_color)
    draw_corner_ornaments(draw, width, height, border_color)
    draw_banner(draw, width, border_color, accent_color)
    
    title_text = diplom['name']
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    title_width = bbox[2] - bbox[0]
    x, y = width//2 - title_width//2, 95
    draw.text((x+2, y+2), title_text, fill='#CCCCCC', font=font_title)
    draw.text((x, y), title_text, fill=border_color, font=font_title)
    
    subtitle = "СВИДЕТЕЛЬСТВО ДРУЖБЫ"
    bbox = draw.textbbox((0, 0), subtitle, font=font_subtitle)
    sub_width = bbox[2] - bbox[0]
    draw.text((width//2 - sub_width//2, 140), subtitle, fill=accent_color, font=font_subtitle)
    
    icon = diplom['icon']
    icon_y = 180
    circle_center = (width//2, icon_y + 30)
    draw.ellipse([circle_center[0]-45, circle_center[1]-45, circle_center[0]+45, circle_center[1]+45], outline=border_color, width=3)
    draw.ellipse([circle_center[0]-40, circle_center[1]-40, circle_center[0]+40, circle_center[1]+40], outline=accent_color, width=1)
    
    bbox = draw.textbbox((0, 0), icon, font=font_big)
    icon_width = bbox[2] - bbox[0]
    draw.text((width//2 - icon_width//2, icon_y), icon, fill=border_color, font=font_big)
    
    y = 280
    draw.rounded_rectangle([40, y-10, width-40, y+220], radius=15, fill='#FFFFFF', outline=accent_color, width=2)
    
    y += 20
    draw_text_with_shadow(draw, (60, y), "👤 Подружка:", font_subtitle, '#555555')
    name_display = user_name[:25] + "..." if len(user_name) > 25 else user_name
    draw_text_with_shadow(draw, (220, y), name_display, font_subtitle, border_color)
    
    y += 45
    draw_text_with_shadow(draw, (60, y), "📝 Тест:", font_subtitle, '#555555')
    test_display = test_title[:30] + "..." if len(test_title) > 30 else test_title
    draw_text_with_shadow(draw, (220, y), test_display, font_subtitle, border_color)
    
    y += 45
    draw_text_with_shadow(draw, (60, y), "🎯 Результат:", font_subtitle, '#555555')
    score_color = '#4CAF50' if score >= 70 else '#FF9800' if score >= 50 else '#F44336'
    draw_text_with_shadow(draw, (220, y), f"{score:.0f}%", font_subtitle, score_color)
    
    y += 45
    status_short = status[:35] + "..." if len(status) > 35 else status
    bbox = draw.textbbox((0, 0), status_short, font=font_text)
    status_width = bbox[2] - bbox[0]
    draw_text_with_shadow(draw, (width//2 - status_width//2, y), status_short, font_text, border_color)
    
    y += 40
    draw_text_with_shadow(draw, (60, y), "💗 Получено очков:", font_subtitle, '#555555')
    draw_text_with_shadow(draw, (260, y), f"+{points}", font_subtitle, '#FFD700')
    
    y = 530
    signature = diplom['text']
    bbox = draw.textbbox((0, 0), signature, font=font_cursive)
    sig_width = bbox[2] - bbox[0]
    draw_text_with_shadow(draw, (width//2 - sig_width//2, y), signature, font_cursive, border_color)
    
    draw_banner_bottom(draw, width, height, border_color, accent_color)
    draw_sparkles(draw, width, height, border_color, accent_color)
    
    date_text = datetime.now().strftime("%d.%m.%Y")
    draw.text((width-150, height-35), date_text, fill=accent_color, font=font_text)
    
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG', quality=95)
    img_byte_arr.seek(0)
    
    return img_byte_arr

# === КЛАВИАТУРЫ ===
def get_main_keyboard(user_id=None):
    keyboard = [
        [KeyboardButton("🌸 Создать тест"), KeyboardButton("👑 Мои тесты")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("🎀 Бонус и задания")],
        [KeyboardButton("👭 Пригласить"), KeyboardButton("🛍️ Магазин")]
    ]
    if user_id and user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("🔧 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_bonus_tasks_keyboard():
    keyboard = [
        [KeyboardButton("🎁 Бонус"), KeyboardButton("📋 Задания")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("👑 Выдать премиум"), KeyboardButton("🔻 Снять премиум")],
        [KeyboardButton("➕ Добавить тесты"), KeyboardButton("⭐ Добавить очки")],
        [KeyboardButton("📋 Список пользователей"), KeyboardButton("🔄 Сброс недельного рейтинга")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True)

def get_back_keyboard():
    return ReplyKeyboardMarkup([[f"{WOW_EMOJIS['back']} Назад"]], resize_keyboard=True, one_time_keyboard=True)

def get_question_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Другой вопрос", callback_data="next_question"),
         InlineKeyboardButton("🎲 Рандомный", callback_data="random_question")],
        [InlineKeyboardButton("✅ Этот вопрос", callback_data="select_question")],
        [InlineKeyboardButton("🔙 Назад к темам", callback_data="back_to_groups")]
    ])

def get_options_keyboard():
    return ReplyKeyboardMarkup(
        [["➕ Добавить вариант", "✅ Готово", "🔙 Назад"]],
        resize_keyboard=True, one_time_keyboard=True
    )

def get_question_groups_keyboard(user_id):
    has_premium = is_premium(user_id)
    keyboard = []
    row = []
    
    for key, name in FREE_QUESTION_GROUPS.items():
        row.append(InlineKeyboardButton(name, callback_data=f"group_{key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    if has_premium:
        row = []
        for key, name in PREMIUM_QUESTION_GROUPS.items():
            if key not in FREE_QUESTION_GROUPS:
                row.append(InlineKeyboardButton(name, callback_data=f"group_{key}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
        if row:
            keyboard.append(row)
    else:
        row = []
        for key, name in PREMIUM_QUESTION_GROUPS.items():
            if key not in FREE_QUESTION_GROUPS:
                row.append(InlineKeyboardButton(f"🔒 {name}", callback_data=f"premium_group_{key}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
        if row:
            keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🎲 Рандомные вопросы", callback_data="random_group")])
    return InlineKeyboardMarkup(keyboard)

def get_diplom_choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Королевский диплом", callback_data="diplom_premium_royal")],
        [InlineKeyboardButton("💎 Бриллиантовый диплом", callback_data="diplom_premium_diamond")],
        [InlineKeyboardButton("🌟 Звёздный диплом", callback_data="diplom_premium_star")],
        [InlineKeyboardButton("🦄 Волшебный диплом", callback_data="diplom_premium_unicorn")],
        [InlineKeyboardButton("🌸 Цветочный диплом", callback_data="diplom_premium_flower")],
        [InlineKeyboardButton("📜 Классический диплом", callback_data="diplom_free")]
    ])

def get_shop_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Премиум 30 дней — 199 ₽", callback_data="buy_premium_month")],
        [InlineKeyboardButton("💎 Премиум 3 месяца — 459 ₽", callback_data="buy_premium_3months")],
        [InlineKeyboardButton("💎 Премиум ГОД — 1299 ₽", callback_data="buy_premium_year")]
    ])

def get_share_confirm_keyboard(test_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Сохранить в мои тесты", callback_data=f"save_after_create_{test_id}"),
         InlineKeyboardButton("❌ Отмена", callback_data="cancel_share")],
        [InlineKeyboardButton("👭 Поделиться ссылкой", 
            switch_inline_query=f"💕 Привет! Подружка приглашает тебя пройти тест 💕\n\n🎀 Узнай, насколько хорошо ты её знаешь! 🎀\n\n👉 Переходи по ссылке и начинай! 👈\n\nhttps://t.me/{BOT_USERNAME}?start=test_{test_id}")]
    ])

def get_start_test_keyboard(test_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_test_{test_id}"),
        InlineKeyboardButton("⭐ Сохранить", callback_data=f"save_test_{test_id}")
    ]])

def get_my_tests_keyboard(has_created, has_saved, is_premium_user):
    keyboard = []
    if has_created:
        keyboard.append([InlineKeyboardButton("📝 Мои тесты", callback_data="show_created_tests")])
    if has_saved:
        keyboard.append([InlineKeyboardButton("⭐ Сохранённые тесты", callback_data="show_saved_tests")])
    if not is_premium_user:
        keyboard.append([InlineKeyboardButton("💎 Купить премиум", callback_data="shop")])
    keyboard.append([InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_paginated_tests_keyboard(tests, page, prefix):
    keyboard = []
    start = page * 5
    end = start + 5
    for test in tests[start:end]:
        keyboard.append([InlineKeyboardButton(f"📝 {test['title'][:25]}", callback_data=f"{prefix}_test_{test['id']}")])
    
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"{prefix}_page_{page-1}"))
    if end < len(tests):
        nav.append(InlineKeyboardButton("Вперёд ▶️", callback_data=f"{prefix}_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_my_tests")])
    return InlineKeyboardMarkup(keyboard)

def get_test_action_keyboard(test_id, is_owner=False, is_saved=False):
    keyboard = []
    if not is_owner:
        keyboard.append([InlineKeyboardButton("🎮 Пройти тест", callback_data=f"start_test_{test_id}")])
        if not is_saved:
            keyboard.append([InlineKeyboardButton("⭐ Сохранить", callback_data=f"save_test_{test_id}")])
        else:
            keyboard.append([InlineKeyboardButton("🗑️ Удалить из сохранённых", callback_data=f"unsave_test_{test_id}")])
    
    keyboard.append([InlineKeyboardButton("📖 Посмотреть тест", callback_data=f"view_full_test_{test_id}")])
    
    if is_owner:
        keyboard.append([InlineKeyboardButton("📤 Поделиться", callback_data=f"share_test_{test_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_my_tests")])
    return InlineKeyboardMarkup(keyboard)

def get_full_test_keyboard(test_id, is_owner):
    keyboard = []
    if not is_owner:
        keyboard.append([InlineKeyboardButton("🎮 Пройти тест", callback_data=f"start_test_{test_id}")])
    keyboard.append([InlineKeyboardButton("📤 Поделиться", callback_data=f"share_test_{test_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_my_tests")])
    return InlineKeyboardMarkup(keyboard)

def get_rating_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 За всё время", callback_data="rating_all"),
         InlineKeyboardButton("📅 За неделю", callback_data="rating_week")]
    ])

# === ОСНОВНЫЕ ХЕНДЛЕРЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
        user = query.from_user
        bot = context.bot
    else:
        message = update.message
        user = update.effective_user
        bot = context.bot
    
    referred_by = None
    test_id = None
    
    if context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith("test_"):
            try:
                test_id = int(arg.split("_")[1])
            except:
                pass
        else:
            referrer_id = get_user_by_referral_code(arg)
            if referrer_id and referrer_id != user.id:
                referred_by = referrer_id
    
    existing = get_user(user.id)
    
    if not existing:
        create_user(user.id, user.username, user.first_name, referred_by)
        if referred_by:
            await send_referral_notification(bot, referred_by, user.first_name or "Подружка", user.username, is_new_user=True)
            await apply_referral_bonus(referred_by, user.id)
    else:
        update_user(user.id, user.username, user.first_name)
        if referred_by and not existing.get('referred_by'):
            await send_referral_notification(bot, referred_by, user.first_name or "Подружка", user.username, is_new_user=False)
            await apply_referral_bonus(referred_by, user.id)
    
    if test_id:
        test = get_test_by_id(test_id)
        if test:
            creator = get_user(test['creator_id'])
            creator_name = creator.get('first_name', 'Подружка') if creator else 'Подружка'
            text = (f"🌸✨ ПРИВЕТ, {user.first_name or 'ПОДРУЖКА'}! ✨🌸\n\n"
                    f"💕 {creator_name} приглашает тебя пройти супер-тестик!\n\n"
                    f"📝 {test['title']}\n\n"
                    f"✨ Узнай, насколько хорошо ты знаешь свою подружку! ✨\n\n"
                    f"👇 Нажми на кнопку и вперёд! 👇")
            await message.reply_text(text, reply_markup=get_start_test_keyboard(test_id))
            return
    
    user_data = get_user(user.id)
    points = user_data.get('total_points', 0) if user_data else 0
    rank = get_rank(points)
    tests = get_available_tests(user.id)
    premium = "💎 ПРЕМИУМ" if is_premium(user.id) else "🔓 БЕСПЛАТНЫЙ"
    
    tests_text = "♾️" if tests == -1 else f"{tests}"
    test_word = decline_word(tests, "тест", "теста", "тестов") if tests != -1 else ""
    tests_display = f"{tests_text} {test_word}" if tests != -1 else tests_text
    
    text = (f"{WOW_EMOJIS['start']}{WOW_EMOJIS['sparkle']} ПРИВЕТ, {user.first_name or 'ПОДРУЖКА'}! {WOW_EMOJIS['sparkle']}{WOW_EMOJIS['start']}\n\n"
            f"🌸 Добро пожаловать в PodrugaTestBot — место, где мы проверяем, насколько круто мы знаем друг друга! 🌸\n\n"
            f"🎀 Твой статус: {premium}\n"
            f"🎁 Доступно тестов: {tests_display}\n"
            f"⭐ Очков: {points}\n"
            f"🏆 Ранг: {rank['name']}\n\n"
            f"💫 Что тебя ждёт?\n"
            f"• ✨ Создавай тесты о себе\n"
            f"• 💕 Отправляй их подружкам\n"
            f"• 🎯 Узнавай, насколько хорошо тебя знают\n"
            f"• 🎓 Получай милые дипломы\n"
            f"• 📋 Выполняй задания и получай бонусы\n"
            f"• 🏆 Соревнуйся в рейтинге\n\n"
            f"💖 Поехали! Нажимай на кнопки ниже 💖")
    
    await message.reply_text(text, reply_markup=get_main_keyboard(user.id))

async def send_referral_notification(bot, referrer_id, new_user_name, new_user_username=None, is_new_user=True):
    try:
        referrer = get_user(referrer_id)
        if not referrer:
            return
        
        stats = get_referral_stats(referrer_id)
        user_display = new_user_name
        if new_user_username:
            user_display += f" (@{new_user_username})"
        
        if is_new_user:
            text = (f"🎉✨ УРА! НОВАЯ ПОДРУЖКА! ✨🎉\n\n"
                    f"💕 {user_display} присоединилась к боту по твоей ссылке!\n\n"
                    f"🎁 Ты получаешь:\n"
                    f"   ➕ +1 тестик\n"
                    f"   ⭐ +200 очков\n\n"
                    f"📊 Твоя статистика приглашений:\n"
                    f"   👭 Всего подружек: {stats['total']}\n"
                    f"   ⭐ Активных: {stats['active']}\n\n"
                    f"💖 Продолжай приглашать подружек и получай ещё больше бонусов! 💖")
        else:
            text = (f"🌸 ТВОЯ ПОДРУЖКА УЖЕ С НАМИ 🌸\n\n"
                    f"💕 {user_display} уже была зарегистрирована в боте!\n\n"
                    f"📊 Статистика приглашений:\n"
                    f"   👭 Всего подружек: {stats['total']}\n"
                    f"   ⭐ Активных: {stats['active']}\n\n"
                    f"💫 Отправляй ссылку другим подружкам, чтобы получить бонусы! 💫")
        
        await safe_send_message(bot, referrer_id, text)
    except Exception as e:
        logger.error(f"Ошибка уведомления о реферале: {e}")

async def safe_send_message(bot, chat_id, text, **kwargs):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception as e:
        if "blocked" in str(e).lower():
            logger.warning(f"Пользователь {chat_id} заблокировал бота")
        else:
            logger.error(f"Ошибка отправки: {e}")
        return None

async def apply_referral_bonus(referrer_id: int, new_user_id: int):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('UPDATE users SET referral_count = referral_count + 1, tests_available = tests_available + 1 WHERE user_id = ?', (referrer_id,))
        c.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (referrer_id, new_user_id))
        c.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', (referrer_id, new_user_id))
        conn.commit()
        add_points(referrer_id, 200)
        add_weekly_points(referrer_id, 200)
        add_achievement(referrer_id, 'first_invite')
        complete_daily_task(referrer_id, 'invite_friend')
        return True
    except Exception as e:
        logger.error(f"Ошибка бонуса: {e}")
        return False
    finally:
        conn.close()

async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    created_count = get_user_created_tests_count(user_id)
    has_premium = is_premium(user_id)
    max_created = MAX_CREATED_PREMIUM if has_premium else MAX_CREATED_FREE
    
    if created_count >= max_created:
        if has_premium:
            await update.message.reply_text(
                f"💔 Ой! Достигнут лимит созданных тестов! 💔\n\n"
                f"📊 Ты создала: {created_count}/{max_created} тестов\n\n"
                f"🌟 Ты уже создала максимум тестов! 🌟\n"
                f"✨ Продолжай делиться ими с подружками! ✨",
                reply_markup=get_main_keyboard(user_id)
            )
        else:
            await update.message.reply_text(
                f"💔 ОЙ! ЛИМИТ НА СОЗДАНИЕ ТЕСТОВ! 💔\n\n"
                f"📊 Ты создала: {created_count}/{max_created} тестов\n\n"
                f"💎✨ ПРИОБРЕТИ ПРЕМИУМ И ПОЛУЧИ: ✨💎\n\n"
                f"✅ Создавай до {MAX_CREATED_PREMIUM} тестов\n"
                f"✅ 5 красивых дипломов на выбор\n"
                f"✅ Голосовые и видео поздравления\n\n"
                f"👇 Нажми на кнопку: 👇",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 Купить премиум", callback_data="shop")],
                    [InlineKeyboardButton("🔙 В главное меню", callback_data="back_to_main")]
                ])
            )
        return
    
    context.user_data['create_test'] = {
        'step': 'title',
        'questions_data': [],
        'selected_diplom': 'free'
    }
    
    available = get_available_tests(user_id)
    tests_text = "♾️" if available == -1 else f"{available}"
    test_word = decline_word(available, "тест", "теста", "тестов") if available != -1 else ""
    tests_display = f"{tests_text} {test_word}" if available != -1 else tests_text
    
    created_word = decline_word(created_count, "тест", "теста", "тестов")
    
    text = (f"{WOW_EMOJIS['sparkle']} СОЗДАЁМ НОВЫЙ ТЕСТИК! {WOW_EMOJIS['sparkle']}\n\n"
            f"📊 Создано тестов: {created_count}/{max_created} {created_word}\n"
            f"📦 Доступно для отправки: {tests_display}\n\n")
    
    if has_premium:
        text += f"💎 Премиум активен! 💎\n\n"
    else:
        text += f"💎 Хочешь красивые дипломы и видео-поздравления?\n👇 Приобрети премиум: /shop\n\n"
    
    text += (f"🌸 Придумай красивое название\n"
             f"Например: «Насколько хорошо ты меня знаешь?»\n\n"
             f"✏️ Напиши название теста:\n\n"
             f"❌ Отмена - чтобы выйти")
    
    await update.message.reply_text(text, reply_markup=get_cancel_keyboard())

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'create_test' in context.user_data:
        del context.user_data['create_test']
    await update.message.reply_text("❌ Создание теста отменено ❌", reply_markup=get_main_keyboard(update.effective_user.id))

async def handle_create_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data:
        return
    
    text = update.message.text
    
    if text == "❌ Отмена":
        await cancel_creation(update, context)
        return
    
    if text == f"{WOW_EMOJIS['back']} Назад" or text == "🔙 Назад":
        if data.get('step') == 'waiting_question_count':
            data['step'] = 'group'
            user_id = update.effective_user.id
            await update.message.reply_text("✨ Выбери тему для вопросов: ✨", reply_markup=get_question_groups_keyboard(user_id))
        elif data.get('step') == 'collecting_options':
            data['step'] = 'selecting_question'
            await show_current_question(update, context)
        return
    
    step = data.get('step')
    
    if step == 'title':
        if len(text.strip()) < 3:
            await update.message.reply_text("⚠️ Название должно быть длиннее 3 символов! Попробуй ещё раз ⚠️")
            return
        data['title'] = text.strip()
        user_id = update.effective_user.id
        has_premium = is_premium(user_id)
        
        if has_premium:
            data['step'] = 'choose_diplom'
            await update.message.reply_text(
                f"🎓✨ ВЫБЕРИ ДИПЛОМ ДЛЯ ТЕСТА ✨🎓\n\n"
                f"📝 Твой тест: {data['title']}\n\n"
                f"👇 Выбери красивый диплом: 👇",
                reply_markup=get_diplom_choice_keyboard()
            )
        else:
            data['step'] = 'group'
            await update.message.reply_text("✨ Отлично! Теперь выбери тему для вопросов: ✨", reply_markup=get_question_groups_keyboard(user_id))
    
    elif step == 'waiting_question_count':
        try:
            count = int(text.strip())
            user_id = update.effective_user.id
            has_premium = is_premium(user_id)
            max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
            
            if count < 2 or count > max_q:
                await update.message.reply_text(f"⚠️ Количество вопросов должно быть от 2 до {max_q}! Попробуй ещё ⚠️")
                return
            
            data['total_q'] = count
            data['current_q'] = 0
            data['step'] = 'selecting_question'
            
            group = data.get('group')
            if group == 'random':
                data['group_questions'] = get_random_questions(user_id, 30)
            else:
                data['group_questions'] = QUESTIONS_BY_GROUP.get(group, []).copy()
            random.shuffle(data['group_questions'])
            data['current_question_index'] = 0
            
            await show_current_question(update, context)
        except ValueError:
            await update.message.reply_text("⚠️ Напиши число! Например: 5 ⚠️")
    
    elif step == 'collecting_options' and data.get('waiting_for_option'):
        option_text = text.strip()
        if option_text:
            if len(option_text) > 100:
                await update.message.reply_text("⚠️ Вариант слишком длинный! Максимум 100 символов ⚠️")
                return
            data['current_options'].append(option_text)
            data['waiting_for_option'] = False
            
            options_list = "\n".join([f"{i+1}. {o}" for i, o in enumerate(data['current_options'])])
            await update.message.reply_text(
                f"✅ Вариант {len(data['current_options'])} добавлен! ✅\n\n"
                f"📋 Твои варианты:\n{options_list}\n\n"
                f"➕ Можешь добавить ещё или нажать «Готово»",
                reply_markup=get_options_keyboard()
            )

async def choose_diplom_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    diplom_key = query.data.replace("diplom_", "")
    data = context.user_data.get('create_test')
    
    if not data:
        return
    
    data['selected_diplom'] = diplom_key
    data['step'] = 'greeting'
    
    user_id = query.from_user.id
    has_premium = is_premium(user_id)
    
    if has_premium:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎤 Голосовое", callback_data="greeting_voice"),
             InlineKeyboardButton("🎥 Видео", callback_data="greeting_video")],
            [InlineKeyboardButton("⏭️ Пропустить", callback_data="greeting_skip")]
        ])
        await query.message.reply_text(
            f"🎬✨ ДОБАВЬ ПОЗДРАВЛЕНИЕ! ✨🎬\n\n"
            f"Твоя подружка получит это после прохождения теста!\n\n"
            f"📝 Твой тест: {data['title']}\n\n"
            f"👇 Выбери тип поздравления: 👇",
            reply_markup=keyboard
        )
    else:
        data['step'] = 'group'
        await query.message.reply_text("✨ Выбери тему для вопросов: ✨", reply_markup=get_question_groups_keyboard(user_id))

async def ask_for_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = context.user_data.get('create_test')
    
    if not data:
        return
    
    if not is_premium(user_id):
        await query.answer("💎 Только для ПРЕМИУМ!", show_alert=True)
        await query.message.reply_text(
            f"💎✨ ГОЛОСОВЫЕ И ВИДЕО ПОЗДРАВЛЕНИЯ ✨💎\n\n"
            f"🎤 Хочешь добавить особенный сюрприз для подружки?\n\n"
            f"💕 С ПРЕМИУМ ты сможешь:\n"
            f"• 🎤 Записать голосовое поздравление\n"
            f"• 🎥 Добавить видео-обращение\n\n"
            f"👇 Нажми на кнопку ниже: 👇",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Купить премиум", callback_data="shop")],
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="greeting_skip")]
            ])
        )
        return
    
    greeting_type = query.data.split("_")[1]
    
    if greeting_type == "skip":
        data['step'] = 'group'
        await query.message.reply_text("✨ Выбери тему для вопросов: ✨", reply_markup=get_question_groups_keyboard(user_id))
        return
    
    data['waiting_greeting'] = greeting_type
    
    if greeting_type == "voice":
        text = "🎤 Отправь голосовое сообщение (до 15 секунд)\n\n❌ Отмена - чтобы пропустить"
    else:
        text = "🎥 Отправь видео (до 15 секунд)\n\n❌ Отмена - чтобы пропустить"
    
    await query.message.reply_text(text, reply_markup=get_cancel_keyboard())

async def save_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data or not data.get('waiting_greeting'):
        return
    
    greeting_type = data['waiting_greeting']
    
    if greeting_type == "voice":
        if not update.message.voice:
            await update.message.reply_text("❌ Отправь голосовое сообщение!")
            return
        file_id = update.message.voice.file_id
        duration = update.message.voice.duration
    else:
        if not update.message.video:
            await update.message.reply_text("❌ Отправь видео!")
            return
        file_id = update.message.video.file_id
        duration = update.message.video.duration
    
    data['greeting_type'] = greeting_type
    data['greeting_file_id'] = file_id
    data['greeting_duration'] = duration
    del data['waiting_greeting']
    data['step'] = 'group'
    
    await update.message.reply_text(
        f"✅ Поздравление сохранено! 🎉\n\n"
        f"Теперь твоя подружка получит его после прохождения теста! 💕\n\n"
        f"✨ Выбери тему для вопросов: ✨",
        reply_markup=get_question_groups_keyboard(update.effective_user.id)
    )

async def show_current_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data:
        return
    
    current_idx = data.get('current_question_index', 0)
    questions = data.get('group_questions', [])
    
    if current_idx >= len(questions):
        current_idx = 0
        data['current_question_index'] = 0
    
    question_text = questions[current_idx]
    data['current_question_text'] = question_text
    
    await update.message.reply_text(
        f"{WOW_EMOJIS['star']} Вопрос {data['current_q'] + 1}/{data['total_q']} {WOW_EMOJIS['star']}\n\n"
        f"{question_text}\n\n"
        f"👇 Что делаем с этим вопросом? 👇",
        reply_markup=get_question_keyboard()
    )

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = context.user_data.get('create_test')
    if not data:
        return
    
    current_idx = (data.get('current_question_index', 0) + 1) % len(data.get('group_questions', [1]))
    data['current_question_index'] = current_idx
    data['current_question_text'] = data['group_questions'][current_idx]
    
    await query.message.edit_text(
        f"{WOW_EMOJIS['star']} Вопрос {data['current_q'] + 1}/{data['total_q']} {WOW_EMOJIS['star']}\n\n"
        f"{data['current_question_text']}\n\n"
        f"👇 Что делаем? 👇",
        reply_markup=get_question_keyboard()
    )

async def random_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = context.user_data.get('create_test')
    if not data:
        return
    
    user_id = query.from_user.id
    questions = get_random_questions(user_id, 30)
    random.shuffle(questions)
    data['group_questions'] = questions
    data['current_question_index'] = 0
    data['current_question_text'] = questions[0]
    
    await query.message.edit_text(
        f"{WOW_EMOJIS['star']} Вопрос {data['current_q'] + 1}/{data['total_q']} {WOW_EMOJIS['star']}\n\n"
        f"{data['current_question_text']}\n\n"
        f"👇 Что делаем? 👇",
        reply_markup=get_question_keyboard()
    )

async def select_current_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = context.user_data.get('create_test')
    if not data:
        return
    
    data['step'] = 'collecting_options'
    data['current_options'] = []
    data['waiting_for_option'] = True
    
    await query.message.reply_text(
        f"📝 Вопрос: {data['current_question_text']}\n\n"
        f"✏️ Напиши вариант ответа №1:\n\n"
        f"💡 Совет: Варианты должны быть разными и понятными",
        reply_markup=get_cancel_keyboard()
    )

async def select_question_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    group = query.data.split("_")[1]
    data = context.user_data.get('create_test')
    
    if not data:
        data = {'step': 'group', 'questions_data': []}
        context.user_data['create_test'] = data
    
    data['group'] = group
    data['step'] = 'waiting_question_count'
    
    user_id = query.from_user.id
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    group_name = PREMIUM_QUESTION_GROUPS.get(group, FREE_QUESTION_GROUPS.get(group))
    
    await query.message.reply_text(
        f"✨ Выбрана тема: {group_name} ✨\n\n"
        f"📊 Сколько вопросов будет в тесте?\n"
        f"🔹 От 2 до {max_q} вопросов\n\n"
        f"✏️ Напиши число:",
        reply_markup=get_back_keyboard()
    )

async def random_group_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = context.user_data.get('create_test')
    
    if not data:
        data = {'step': 'group', 'questions_data': []}
        context.user_data['create_test'] = data
    
    data['group'] = 'random'
    data['step'] = 'waiting_question_count'
    
    user_id = query.from_user.id
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    
    await query.message.reply_text(
        f"🎲✨ ВЫБРАНЫ РАНДОМНЫЕ ВОПРОСЫ! ✨🎲\n\n"
        f"📊 Сколько вопросов будет в тесте?\n"
        f"🔹 От 2 до {max_q} вопросов\n\n"
        f"✏️ Напиши число:",
        reply_markup=get_back_keyboard()
    )

async def premium_group_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        f"💔 Ой! Эта тема только в ПРЕМИУМЕ! 💔\n\n"
        f"🌟 Купи премиум и получи:\n"
        f"• 16 крутых тем\n"
        f"• До 10 вопросов в тесте\n"
        f"• Полную статистику\n"
        f"• Красивые дипломы\n\n"
        f"👇 Переходи в магазин! 👇",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ В МАГАЗИН", callback_data="open_shop")]])
    )

async def add_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data or data.get('step') != 'collecting_options':
        return
    
    if len(data['current_options']) >= MAX_OPTIONS:
        await update.message.reply_text(f"⚠️ Максимум {MAX_OPTIONS} вариантов ответа! Нажми «Готово» ⚠️", reply_markup=get_options_keyboard())
        return
    
    data['waiting_for_option'] = True
    await update.message.reply_text(f"✏️ Напиши вариант №{len(data['current_options']) + 1}:", reply_markup=get_cancel_keyboard())

async def back_to_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data:
        return
    
    data['step'] = 'selecting_question'
    await show_current_question(update, context)

async def finish_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data or data.get('step') != 'collecting_options':
        return
    
    options = data.get('current_options', [])
    
    if len(options) < MIN_OPTIONS:
        await update.message.reply_text(f"⚠️ Нужно минимум {MIN_OPTIONS} варианта ответа! Добавь ещё ⚠️", reply_markup=get_cancel_keyboard())
        data['waiting_for_option'] = True
        return
    
    data['step'] = 'select_correct'
    
    keyboard = []
    for i, opt in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {opt[:25]}", callback_data=f"correct_{i}")])
    
    await update.message.reply_text(
        f"❓ Вопрос: {data['current_question_text']}\n\n"
        f"👇 Какой вариант ПРАВИЛЬНЫЙ? 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def select_correct_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    correct_idx = int(query.data.split("_")[1])
    data = context.user_data.get('create_test')
    
    if not data:
        return
    
    data['questions_data'].append({
        'text': data['current_question_text'],
        'options': data['current_options'].copy(),
        'correct': correct_idx
    })
    
    data['current_q'] += 1
    
    if data['current_q'] < data['total_q']:
        data['step'] = 'selecting_question'
        data['current_question_index'] = (data.get('current_question_index', 0) + 1) % len(data.get('group_questions', [1]))
        
        await query.message.reply_text(f"✅ Вопрос {data['current_q']} сохранён! ✅\n\nПереходим к следующему вопросу...")
        await show_next_question(query, context)
    else:
        await query.message.reply_text(f"✅ Все {data['total_q']} вопросов сохранены! ✅\n\n🎉 Создаём тест...")
        await finish_creation(query, context, query.from_user.id)

async def show_next_question(query, context):
    data = context.user_data.get('create_test')
    if not data:
        return
    
    current_idx = data.get('current_question_index', 0)
    questions = data.get('group_questions', [])
    
    if current_idx >= len(questions):
        current_idx = 0
        data['current_question_index'] = 0
    
    data['current_question_text'] = questions[current_idx]
    
    await query.message.reply_text(
        f"{WOW_EMOJIS['star']} Вопрос {data['current_q'] + 1}/{data['total_q']} {WOW_EMOJIS['star']}\n\n"
        f"{data['current_question_text']}\n\n"
        f"👇 Что делаем? 👇",
        reply_markup=get_question_keyboard()
    )

async def finish_creation(query_or_update, context, user_id):
    data = context.user_data.get('create_test', {})
    if not data:
        return
    
    created_count = get_user_created_tests_count(user_id)
    has_premium = is_premium(user_id)
    max_created = MAX_CREATED_PREMIUM if has_premium else MAX_CREATED_FREE
    
    if created_count >= max_created:
        msg = f"💔 Лимит созданных тестов исчерпан! 💔"
        if hasattr(query_or_update, 'message'):
            await query_or_update.message.reply_text(msg, reply_markup=get_main_keyboard(user_id))
        else:
            await query_or_update.message.reply_text(msg, reply_markup=get_main_keyboard(user_id))
        del context.user_data['create_test']
        return
    
    questions = [q['text'] for q in data['questions_data']]
    options = [q['options'] for q in data['questions_data']]
    correct = [q['correct'] for q in data['questions_data']]
    
    test_id = create_test(
        user_id,
        query_or_update.from_user.first_name if hasattr(query_or_update, 'from_user') else query_or_update.effective_user.first_name,
        query_or_update.from_user.username if hasattr(query_or_update, 'from_user') else query_or_update.effective_user.username,
        data['title'],
        questions,
        options,
        correct,
        data.get('greeting_type'),
        data.get('greeting_file_id'),
        data.get('greeting_duration'),
        data.get('selected_diplom', 'free')
    )
    
    if test_id:
        created_after = get_user_created_tests_count(user_id)
        text = (f"🎉✨ ТЕСТИК ГОТОВ! ✨🎉\n\n"
                f"📝 Название: {data['title']}\n"
                f"🔢 Вопросов: {data['total_q']}\n"
                f"📊 Всего создано: {created_after}/{max_created}\n\n"
                f"💖 Ты молодец! Теперь поделись им с подружкой! 💖\n\n"
                f"👇 Выбери действие: 👇")
        
        if hasattr(query_or_update, 'message'):
            await query_or_update.message.reply_text(text, reply_markup=get_share_confirm_keyboard(test_id))
        else:
            await query_or_update.message.reply_text(text, reply_markup=get_share_confirm_keyboard(test_id))
    else:
        await query_or_update.message.reply_text("💔 Ошибка при создании теста! Попробуй ещё раз 💔", reply_markup=get_main_keyboard(user_id))
    
    del context.user_data['create_test']

async def save_after_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[3])
    user_id = query.from_user.id
    test = get_test_by_id(test_id)
    
    if not test:
        await query.answer("❌ Тест не найден", show_alert=True)
        return
    
    if test['creator_id'] == user_id:
        await query.answer("✨ Этот тест уже в разделе «Мои тесты»!", show_alert=True)
        return
    
    if save_test(user_id, test_id):
        await query.answer("⭐ Тест сохранён!", show_alert=True)
    else:
        if not can_save_test(user_id, test_id):
            has_premium = is_premium(user_id)
            max_saved = MAX_SAVED_PREMIUM if has_premium else MAX_SAVED_FREE
            await query.answer(f"❌ Лимит сохранённых тестов: {max_saved}!", show_alert=True)
        else:
            await query.answer("❌ Не удалось сохранить", show_alert=True)

# === ОСНОВНЫЕ ХЕНДЛЕРЫ МЕНЮ ===
async def my_tests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
        user_id = query.from_user.id
    else:
        message = update.message
        user_id = update.effective_user.id
    
    has_premium = is_premium(user_id)
    created_tests = get_user_created_tests(user_id)
    saved_tests_list = get_saved_tests(user_id)
    created_count = get_user_created_tests_count(user_id)
    saved_count = get_saved_tests_count(user_id)
    
    context.user_data['my_tests'] = {
        'created': created_tests, 
        'saved': saved_tests_list, 
        'page': 0,
        'current_list': None
    }
    
    created_max = MAX_CREATED_PREMIUM if has_premium else MAX_CREATED_FREE
    saved_max = MAX_SAVED_PREMIUM if has_premium else MAX_SAVED_FREE
    
    text = f"👑✨ МОИ ТЕСТЫ ✨👑\n\n"
    if created_tests:
        created_word = decline_word(created_count, "тест", "теста", "тестов")
        text += f"📝 Создано мной: {created_count}/{created_max} {created_word}\n"
    if saved_tests_list:
        saved_word = decline_word(saved_count, "тест", "теста", "тестов")
        text += f"⭐ Сохранено: {saved_count}/{saved_max} {saved_word}\n"
    if not created_tests and not saved_tests_list:
        text += "🌸 У тебя пока нет тестиков 🌸\n\nСоздай свой первый тест или сохрани чужой!"
    
    await message.reply_text(text, reply_markup=get_my_tests_keyboard(bool(created_tests), bool(saved_tests_list), has_premium))

async def show_created_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    my_tests = context.user_data.get('my_tests', {})
    tests = my_tests.get('created', [])
    page = my_tests.get('page', 0)
    
    if not tests:
        await query.message.reply_text("📝 У тебя пока нет созданных тестиков 📝\n\nСоздай первый тест через главное меню!")
        return
    
    context.user_data['my_tests']['current_list'] = 'created'
    
    text = f"👑✨ МОИ ТЕСТЫ ✨👑\n\n"
    start = page * 5
    for test in tests[start:start+5]:
        question_word = decline_word(test['questions_count'], "вопрос", "вопроса", "вопросов")
        text += f"📝 {test['title'][:30]}\n"
        text += f"   ❓ {test['questions_count']} {question_word}\n"
        text += f"   👥 Прошло: {test['attempts_count']}\n"
        text += f"   📅 {test['created_at'][:10]}\n\n"
    
    await query.message.edit_text(text, reply_markup=get_paginated_tests_keyboard(tests, page, "created"))

async def show_saved_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    my_tests = context.user_data.get('my_tests', {})
    tests = my_tests.get('saved', [])
    page = my_tests.get('page', 0)
    
    if not tests:
        await query.message.reply_text("⭐ У тебя пока нет сохранённых тестиков ⭐\n\nСохраняй тесты подружек, чтобы проходить их позже!")
        return
    
    context.user_data['my_tests']['current_list'] = 'saved'
    
    text = f"⭐✨ СОХРАНЁННЫЕ ТЕСТЫ ✨⭐\n\n"
    start = page * 5
    for test in tests[start:start+5]:
        username = f"(@{test.get('creator_username', '')})" if test.get('creator_username') else ''
        question_word = decline_word(test['questions_count'], "вопрос", "вопроса", "вопросов")
        text += f"📝 {test['title'][:30]}\n"
        text += f"   👤 Автор: {test['creator_name']} {username}\n"
        text += f"   ❓ {test['questions_count']} {question_word}\n"
        text += f"   👥 Прошло: {test['attempts_count']}\n\n"
    
    await query.message.edit_text(text, reply_markup=get_paginated_tests_keyboard(tests, page, "saved"))

async def show_test_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    test_id = int(parts[2])
    
    test = get_test_by_id(test_id)
    if not test:
        await query.message.reply_text("💔 Тестик не найден 💔")
        return
    
    user_id = query.from_user.id
    is_owner = test['creator_id'] == user_id
    is_saved = test_id in [t['id'] for t in context.user_data.get('my_tests', {}).get('saved', [])]
    
    text = (f"📝✨ {test['title']} ✨📝\n\n"
            f"👤 Автор: {test['creator_name']}\n"
            f"📅 Создан: {test['created_at'][:10]}\n"
            f"👥 Прошло: {test['attempts_count']}\n\n"
            f"👇 Что хочешь сделать? 👇")
    
    await query.message.edit_text(text, reply_markup=get_test_action_keyboard(test_id, is_owner, is_saved))

async def view_full_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[3])
    test = get_test_by_id(test_id)
    
    if not test:
        await query.message.reply_text("💔 Тестик не найден 💔")
        return
    
    user_id = query.from_user.id
    is_owner = test['creator_id'] == user_id
    
    text = f"📖✨ ПОЛНЫЙ ТЕСТИК ✨📖\n\n📝 {test['title']}\n\n*Вопросы и ответы:*\n\n"
    
    for i, q in enumerate(test['questions'], 1):
        text += f"{i}. {q}\n"
        for j, opt in enumerate(test['options'][i-1], 1):
            if test['correct_answers'][i-1] == j-1:
                text += f"   ✅ {j}. {opt} (правильный)\n"
            else:
                text += f"   ➖ {j}. {opt}\n"
        text += "\n"
    
    if len(text) > 4000:
        text = text[:3500] + "\n\n... и ещё вопросы (слишком длинный тест)"
    
    await query.message.edit_text(text, reply_markup=get_full_test_keyboard(test_id, is_owner))

async def share_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    test = get_test_by_id(test_id)
    
    if not test:
        await query.message.reply_text("💔 Тестик не найден")
        return
    
    user_id = query.from_user.id
    has_premium = is_premium(user_id)
    
    if not has_premium:
        available = get_available_tests(user_id)
        if available == 0:
            await query.message.reply_text(
                f"💔 Ой-ой! Не хватает тестиков! 💔\n\n"
                f"🎁 Забери ежедневный бонус\n"
                f"👭 Пригласи подружку\n"
                f"💎 Или купи премиум в магазине\n\n"
                f"✨ Не сдавайся! ✨",
                reply_markup=get_main_keyboard(user_id)
            )
            return
        
        use_attempt(user_id)
        available_after = get_available_tests(user_id)
        tests_word = decline_word(available_after, "тест", "теста", "тестов")
    
    text = f"🎉✨ ТЕСТИК ГОТОВ К ОТПРАВКЕ! ✨🎉\n\n📝 {test['title']}\n\n"
    
    if not has_premium:
        text += f"📦 Списана 1 попытка\n🎁 Осталось: {available_after} {tests_word}\n\n"
    
    text += f"💖 Поделись им с подружкой через кнопку ниже! 💖"
    
    await query.message.edit_text(text, reply_markup=get_share_confirm_keyboard(test_id))
    complete_daily_task(user_id, 'send_test')

async def daily_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = get_daily_tasks(user_id)
    
    text = f"🎀✨ ЗАДАНИЯ НА СЕГОДНЯ ✨🎀\n\nВыполняй задания и получай звёздочки! ⭐\n\n"
    
    completed = 0
    for task in tasks:
        status = "✅" if task['completed'] else "⬜"
        text += f"{status} {task['name']} +{task['points']} ⭐\n   {task['description']}\n\n"
        if task['completed']:
            completed += 1
    
    text += f"\n📊 Выполнено: {completed}/{len(tasks)}"
    
    if completed == len(tasks):
        text += f"\n\n🎉✨ ТЫ СУПЕР-ПУПЕР ЗВЕЗДОЧКА! ✨🎉\nВсе задания выполнены! Завтра будут новые! 🌸"
    else:
        remaining_word = decline_word(len(tasks) - completed, "задание", "задания", "заданий")
        text += f"\n\n💪 Осталось всего {len(tasks) - completed} {remaining_word}! Ты справишься! 💪"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard(user_id))

async def daily_bonus_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = get_daily_bonus(user_id)
    
    if result[0] is None:
        streak = result[1]
        next_reward = ""
        for s in STREAK_REWARDS:
            if s > streak:
                next_reward = f"\n\n🎯 Через {s - streak} дня получишь: {STREAK_REWARDS[s]['description']}"
                break
        
        await update.message.reply_text(
            f"🎀✨ БОНУСИК ✨🎀\n\n"
            f"🌸 Ты уже забирала бонус сегодня! 🌸\n"
            f"🔥 Серия: {streak} дней{next_reward}\n\n"
            f"⏰ Возвращайся завтра за новой порцией! 💕",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    bonus, streak, reward_info = result
    
    text = f"🎀✨ БОНУС ПОЛУЧЕН! ✨🎀\n\n⭐ +{bonus} очков ⭐\n🔥 Серия: {streak} дней\n\n"
    
    if reward_info:
        text += f"🎉✨ ОСОБАЯ НАГРАДА! ✨🎉\n🎁 Ты получила: {reward_info}\n\n"
    
    text += f"💫 Завтра будет новая награда! Приходи снова! 💫"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard(user_id))

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
        user_id = query.from_user.id
    else:
        message = update.message
        user_id = update.effective_user.id
    
    user = get_user(user_id)
    if not user:
        await message.reply_text("❌ Ошибка", reply_markup=get_main_keyboard(user_id))
        return
    
    points = user.get('total_points', 0)
    weekly_points = user.get('weekly_points', 0)
    rank = get_rank(points)
    streak = user.get('daily_streak', 0)
    created = get_user_created_tests_count(user_id)
    referrals = user.get('referral_count', 0)
    tests_left = get_available_tests(user_id)
    has_premium = is_premium(user_id)
    saved_count = get_saved_tests_count(user_id)
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM attempts WHERE friend_id = ?', (user_id,))
        passed = c.fetchone()[0]
        c.execute('SELECT COUNT(*) + 1 FROM users WHERE total_points > ?', (points,))
        rating = c.fetchone()[0]
    finally:
        conn.close()
    
    tests_text = "♾️" if tests_left == -1 else f"{tests_left}"
    test_word = decline_word(tests_left, "тест", "теста", "тестов") if tests_left != -1 else ""
    tests_display = f"{tests_text} {test_word}" if tests_left != -1 else tests_text
    
    created_word = decline_word(created, "тест", "теста", "тестов")
    passed_word = decline_word(passed, "тест", "теста", "тестов")
    referrals_word = decline_word(referrals, "подругу", "подруги", "подруг")
    saved_word = decline_word(saved_count, "тест", "теста", "тестов")
    
    text = (f"📊✨ ТВОЯ СТАТИСТИКА ✨📊\n\n"
            f"👤 Имя: {user.get('first_name', 'Подружка')}\n"
            f"🏆 Ранг: {rank['name']}\n"
            f"⭐ Очки: {points}\n"
            f"⭐ За неделю: {weekly_points}\n"
            f"📊 Место: {rating}\n"
            f"🔥 Серия: {streak} дней\n"
            f"🎯 До след. ранга: {get_next_level_points(points)} очков\n\n"
            f"📝 Создано тестов: {created} {created_word}\n"
            f"🎯 Пройдено тестов: {passed} {passed_word}\n"
            f"👭 Приглашено подруг: {referrals} {referrals_word}\n"
            f"📦 Сохранено тестов: {saved_count} {saved_word}\n"
            f"🎁 Доступно: {tests_display}")
    
    keyboard = [
        [InlineKeyboardButton("🏆 За всё время", callback_data="rating_all"),
         InlineKeyboardButton("📅 За неделю", callback_data="rating_week")],
        [InlineKeyboardButton("👭 Топ подруг", callback_data="top_friends")]
    ]
    
    if update.callback_query:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def rating_all_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    top_users = get_top_users_full(10)
    my_stats = get_user_full_stats(query.from_user.id)
    
    text = f"🏆✨ ТОП-10 ЗА ВСЁ ВРЕМЯ ✨🏆\n\n"
    
    for i, u in enumerate(top_users, 1):
        medal = "👑" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
        name = u['first_name'] or f"ID {u['user_id']}"
        username = f"(@{u['username']})" if u['username'] else ''
        text += f"{medal} {i}. {name} {username}\n   ⭐ Очки: {u['total_points']}\n\n"
    
    text += f"\n📊 Твоя статистика:\n   ⭐ Очки: {my_stats['points']}"
    
    await query.message.edit_text(text, reply_markup=get_rating_keyboard())

async def rating_week_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    top_users = get_top_users_weekly(10)
    my_stats = get_user_full_stats(query.from_user.id)
    
    text = f"🏆✨ ТОП-10 ЗА НЕДЕЛЮ ✨🏆\n\n"
    
    for i, u in enumerate(top_users, 1):
        medal = "👑" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
        name = u['first_name'] or f"ID {u['user_id']}"
        username = f"(@{u['username']})" if u['username'] else ''
        text += f"{medal} {i}. {name} {username}\n   ⭐ Очки за неделю: {u['weekly_points']}\n\n"
    
    text += f"\n📊 Твоя статистика за неделю:\n   ⭐ Очки: {my_stats['weekly_points']}"
    
    await query.message.edit_text(text, reply_markup=get_rating_keyboard())

async def top_friends_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    has_premium = is_premium(user_id)
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT a.friend_id, a.friend_name, a.friend_username, 
                   AVG(a.score) as avg_score, COUNT(a.id) as tests_count
            FROM attempts a
            WHERE a.test_id IN (SELECT id FROM tests WHERE creator_id = ?)
            GROUP BY a.friend_id
            ORDER BY avg_score DESC
            LIMIT 20
        ''', (user_id,))
        friends = c.fetchall()
    finally:
        conn.close()
    
    if not friends:
        await query.message.edit_text(
            "👭✨ ТОП ПОДРУЖЕК ✨👭\n\n"
            "🌸 Пока никто не проходил твои тестики 🌸\n\n"
            "Создай тест и отправь подружкам! 💕",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_stats")]])
        )
        return
    
    text = "👭✨ ТВОЙ ТОП ПОДРУЖЕК ✨👭\n\n"
    keyboard = []
    
    for i, friend in enumerate(friends, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "💕"
        name = friend['friend_name'] or 'Подружка'
        username = f"(@{friend['friend_username']})" if friend['friend_username'] else ''
        
        text += f"{medal} {i}. {name} {username}\n"
        text += f"   📊 Средний балл: {friend['avg_score']:.0f}%\n"
        text += f"   📝 Прошла: {friend['tests_count']}\n"
        
        if has_premium:
            text += f"   👆 Нажми на кнопку ниже, чтобы увидеть ответы\n"
            keyboard.append([InlineKeyboardButton(f"📊 Ответы {name}", callback_data=f"friend_details_{friend['friend_id']}")])
        
        text += "\n"
    
    if not has_premium:
        text += (f"\n✨ ХОЧЕШЬ УВИДЕТЬ ПОДРОБНУЮ СТАТИСТИКУ? ✨\n"
                 f"💎 Приобрети ПРЕМИУМ и смотри:\n"
                 f"• 📋 Как именно ответила каждая подружка\n"
                 f"• ❌ Где она ошиблась\n"
                 f"• ✅ Какие ответы были правильными\n\n"
                 f"👇 Нажми на кнопку ниже: 👇")
        keyboard.append([InlineKeyboardButton("💎 Купить премиум", callback_data="shop")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад к статистике", callback_data="back_to_stats")])
    
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_friend_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    friend_id = int(query.data.split("_")[2])
    
    if not is_premium(user_id):
        await query.answer("💎 Эта функция доступна только в ПРЕМИУМ!", show_alert=True)
        await query.message.reply_text(
            "💎✨ ТОЛЬКО ДЛЯ ПРЕМИУМ! ✨💎\n\n"
            "🌸 Хочешь увидеть, как подружки ответили на твои вопросы?\n\n"
            "💫 С ПРЕМИУМ ты сможешь смотреть детальные ответы каждой подружки!\n\n"
            "👇 Нажми на кнопку и открой все возможности: 👇",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Купить премиум", callback_data="shop")],
                [InlineKeyboardButton("🔙 Назад", callback_data="top_friends")]
            ])
        )
        return
    
    answers_details = get_friend_answers_details(user_id, friend_id)
    
    if not answers_details:
        await query.message.edit_text(
            "💔 Нет данных об ответах 💔\n\nПодружка ещё не проходила твои тесты.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="top_friends")]])
        )
        return
    
    text = "📝✨ ОТВЕТЫ ПОДРУЖКИ ✨📝\n\n"
    
    for test in answers_details[:3]:
        friend_name = test.get('friend_name', 'Подружка')
        text += f"👤 {friend_name}\n📋 Тест: {test['title']}\n🎯 Результат: {test['score']:.0f}%\n\n"
        
        for i, q in enumerate(test['questions'][:5]):
            if i < len(test['answers']) and test['answers'][i] < len(test['options'][i]):
                user_answer = test['options'][i][test['answers'][i]]
                is_correct = test['answers'][i] == test['correct_answers'][i]
                correct_answer = test['options'][i][test['correct_answers'][i]]
                
                if is_correct:
                    text += f"✅ {i+1}. {q}\n   └── {user_answer}\n\n"
                else:
                    text += f"❌ {i+1}. {q}\n   ├── Ответила: {user_answer}\n   └── Правильно: {correct_answer}\n\n"
        
        text += "▸▸▸▸▸▸▸▸▸▸▸▸▸▸▸▸\n\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к списку подруг", callback_data="top_friends")],
        [InlineKeyboardButton("📊 К статистике", callback_data="back_to_stats")]
    ]
    
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        await query.message.edit_text(parts[0], reply_markup=InlineKeyboardMarkup(keyboard))
        for part in parts[1:]:
            await query.message.reply_text(part)
    else:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def back_to_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await stats_handler(update, context)

async def invite_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        return
    
    code = user.get('referral_code')
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    stats = get_referral_stats(user_id)
    
    text = (f"👭✨ ПРИГЛАСИ ПОДРУЖКУ ✨👭\n\n"
            f"🌸 Отправь ссылку и получи +1 тестик и +200 очков! 🌸\n\n"
            f"🔗 Твоя пригласительная ссылка:\n{link}\n\n"
            f"📊 Твоя статистика:\n"
            f"   👭 Приглашено: {stats['total']}\n"
            f"   ⭐ Активных: {stats['active']}\n\n"
            f"💡 Как это работает:\n"
            f"1️⃣ Отправь ссылку подружке\n"
            f"2️⃣ Она начинает играть\n"
            f"3️⃣ Ты получаешь +1 тестик и +200 очков!\n\n"
            f"✨ Чем больше подруг, тем веселее! ✨")
    
    share_text = (
        f"💕 Привет, подружка! 💕\n\n"
        f"👭 Твоя подруга приглашает тебя в бот 👭\n"
        f"✨ PodrugaTestBot — здесь мы создаём тесты о себе,\n"
        f"отправляем их подружкам и узнаём, кто знает нас лучше всех! ✨\n\n"
        f"🌸 Что тебя ждёт? 🌸\n"
        f"• 📝 Создавай крутые тесты о себе\n"
        f"• 💕 Делись ими с подружками\n"
        f"• 🎯 Узнавай, насколько хорошо тебя знают\n"
        f"• 🎓 Получай милые дипломы\n"
        f"• 🏆 Соревнуйся в рейтинге\n\n"
        f"👇 Переходи по ссылке и присоединяйся! 👇\n\n{link}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👭 Поделиться", switch_inline_query=share_text)]
    ])
    
    await update.message.reply_text(text, reply_markup=keyboard, disable_web_page_preview=True)

async def shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        msg = update.callback_query.message
    else:
        user_id = update.effective_user.id
        msg = update.message
    
    if not msg:
        return
    
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    saved = get_saved_tests_count(user_id)
    max_saved = MAX_SAVED_PREMIUM if has_premium else MAX_SAVED_FREE
    created = get_user_created_tests_count(user_id)
    max_created = MAX_CREATED_PREMIUM if has_premium else MAX_CREATED_FREE
    
    text = (f"🛍️✨ ПРЕМИУМ ПОДПИСКА ✨🛍️\n\n"
            f"👑 Твой статус: {'💎 ПРЕМИУМ' if has_premium else '🔓 БЕСПЛАТНЫЙ'}\n"
            f"📊 Создано тестов: {created}/{max_created}\n"
            f"🔢 Вопросов в тесте: до {max_q}\n"
            f"📦 Сохранено тестов: {saved}/{max_saved}\n\n"
            f"💎 ЧТО ДАЁТ ПРЕМИУМ?\n\n"
            f"✅ До 10 вопросов в тесте (вместо 5)\n"
            f"✅ 16 крутых тем (вместо 4)\n"
            f"✅ До 10 созданных тестов (вместо 3)\n"
            f"✅ До 10 сохранённых тестов (вместо 3)\n"
            f"✅ 5 красивых дипломов на выбор\n"
            f"✅ Голосовые и видео поздравления\n"
            f"✅ Полная статистика ответов\n"
            f"✅ Бесконечные попытки делиться\n\n"
            f"🎁 СТОИМОСТЬ ПРЕМИУМ:\n\n"
            f"• 💎 30 дней — 199 ₽\n"
            f"• 💎 3 месяца — 459 ₽\n"
            f"• 💎 ГОД — 1299 ₽")
    
    await msg.reply_text(text, reply_markup=get_shop_keyboard())

async def save_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    test = get_test_by_id(test_id)
    user_id = query.from_user.id
    
    if not test:
        return
    
    if test['creator_id'] == user_id:
        await query.message.reply_text("💔 Нельзя сохранить свой собственный тестик! 💔\nОн уже есть в разделе «Мои тесты»", reply_markup=get_main_keyboard(user_id))
        return
    
    if not can_save_test(user_id, test_id):
        has_premium = is_premium(user_id)
        max_saved = MAX_SAVED_PREMIUM if has_premium else MAX_SAVED_FREE
        await query.message.reply_text(
            f"💔 Лимит сохранённых тестов: {max_saved}! 💔\n\n"
            f"💎 Купи премиум для {MAX_SAVED_PREMIUM} сохранённых тестов!",
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    if save_test(user_id, test_id):
        await query.message.reply_text("⭐✨ Тестик сохранён в «Мои тесты»! ✨⭐", reply_markup=get_main_keyboard(user_id))
    else:
        await query.message.reply_text("💔 Этот тестик уже сохранён! 💔", reply_markup=get_main_keyboard(user_id))

async def unsave_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    if unsave_test(query.from_user.id, test_id):
        await query.message.reply_text("🗑️ Тестик удалён из сохранённых 🗑️", reply_markup=get_main_keyboard(query.from_user.id))
    else:
        await query.message.reply_text("💔 Ошибка при удалении 💔", reply_markup=get_main_keyboard(query.from_user.id))

async def confirm_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    test = get_test_by_id(test_id)
    
    if test:
        await query.message.edit_text(
            f"🎉✨ ТЕСТИК ГОТОВ К ОТПРАВКЕ! ✨🎉\n\n"
            f"📝 {test['title']}\n\n"
            f"💖 Поделись с подружкой через кнопку ниже! 💖",
            reply_markup=get_share_confirm_keyboard(test_id)
        )

async def cancel_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("❌ Отменено")
    
    user_id = query.from_user.id
    
    try:
        await query.message.delete()
    except:
        try:
            await query.message.edit_text("❌ Отменено ❌")
        except:
            pass
    
    await context.bot.send_message(
        chat_id=user_id,
        text="🌸 Главное меню 🌸\n\nЧто хочешь сделать?",
        reply_markup=get_main_keyboard(user_id)
    )
    
    if 'create_test' in context.user_data:
        del context.user_data['create_test']

async def back_to_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("✨ Выбери тему для вопросов: ✨", reply_markup=get_question_groups_keyboard(query.from_user.id))

async def open_shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await shop_handler(update, context)

async def start_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    test = get_test_by_id(test_id)
    user_id = query.from_user.id
    
    if not test:
        await query.message.reply_text("💔 Тестик не найден 💔")
        return
    
    if not can_attempt_test(test_id, user_id):
        await query.message.reply_text("💔 Ты уже проходила этот тестик! 💔\n\nКаждую подружку можно проверить только один раз ✨")
        return
    
    context.user_data['taking_test'] = {
        'test': test,
        'current': 0,
        'answers': [],
        'options': test['options'],
        'correct': test['correct_answers'],
        'test_id': test_id
    }
    
    await send_question(query, context, test['questions'][0], test['options'][0], 1, len(test['questions']))

async def send_question(query, context, question, options, current, total):
    text = f"{WOW_EMOJIS['star']} Вопрос {current}/{total} {WOW_EMOJIS['star']}\n\n{question}\n\n👇 Выбери ответ: 👇"
    
    keyboard = []
    row = []
    for i, opt in enumerate(options):
        row.append(InlineKeyboardButton(opt[:30], callback_data=f"answer_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def take_test_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    answer_idx = int(query.data.split("_")[1])
    data = context.user_data.get('taking_test')
    
    if not data:
        return
    
    data['answers'].append(answer_idx)
    data['current'] += 1
    
    if data['current'] < len(data['test']['questions']):
        await send_question(query, context,
            data['test']['questions'][data['current']],
            data['options'][data['current']],
            data['current'] + 1, len(data['test']['questions']))
    else:
        await finish_test(query, context, data)
        del context.user_data['taking_test']

async def finish_test(query, context, data):
    test = data['test']
    answers = data['answers']
    correct = data['correct']
    user = query.from_user
    
    await query.message.chat.send_action(action="upload_photo")
    
    score = 0
    for i, ans in enumerate(answers):
        if i < len(correct) and ans == correct[i]:
            score += 100 / len(test['questions'])
    
    asyncio.create_task(save_attempt_async(data['test_id'], user.id, user.first_name, user.username, answers, score, context.bot))
    
    diplom_key = test.get('diplom_type', 'free')
    status = get_friendship_status(score)
    points = int(score)
    
    try:
        diploma_image = await generate_diploma_image(
            user.first_name or 'Подружка',
            test['title'],
            score,
            status,
            points,
            diplom_key
        )
        
        await query.message.reply_photo(
            photo=diploma_image,
            caption=f"🎉✨ ПОЗДРАВЛЯЕМ! ✨🎉\n\n💕 {user.first_name or 'Подружка'}, ты прошла тест!\n🎯 Твой результат сохранён в дипломе выше! 👆",
            reply_markup=get_main_keyboard(user.id)
        )
    except Exception as e:
        logger.error(f"Ошибка создания диплома: {e}")
        diplom = DIPLOMS.get(diplom_key, DIPLOMS['free'])
        text = (f"{diplom['border']}\n{diplom['icon']} {diplom['name']} {diplom['icon']}\n{diplom['border']}\n\n"
                f"👤 Подружка: {user.first_name or 'Участница'}\n📝 Тест: {test['title']}\n🎯 Результат: {score:.0f}%\n{status}\n\n"
                f"💗 +{points} очков\n{diplom['text']}\n\n{diplom['border']}\n✨ СПАСИБО ЗА ПРОХОЖДЕНИЕ! ✨\n{diplom['border']}")
        await query.message.reply_text(text, reply_markup=get_main_keyboard(user.id))
    
    if test.get('greeting_file_id') and context.bot:
        asyncio.create_task(send_greeting_delayed(context.bot, user.id, test))

async def bonus_tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎀 Выбери, что тебя интересует: 🎀", reply_markup=get_bonus_tasks_keyboard())

# === АДМИН-КОМАНДЫ ===
async def is_admin(user_id):
    return user_id == ADMIN_ID

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        await update.message.reply_text("❌ У вас нет доступа к админ-панели!", reply_markup=get_main_keyboard(user_id))
        return
    
    await update.message.reply_text("🔧 АДМИН-ПАНЕЛЬ 🔧\n\nВыберите действие:", reply_markup=get_admin_keyboard())

async def admin_set_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    context.user_data['admin_action'] = 'set_premium'
    await update.message.reply_text("👑 Выдать премиум\n\nНапишите username пользователя (например @anna) или его ID:", reply_markup=get_cancel_keyboard())

async def admin_remove_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    context.user_data['admin_action'] = 'remove_premium'
    await update.message.reply_text("🔻 Снять премиум\n\nНапишите username пользователя (например @anna) или его ID:", reply_markup=get_cancel_keyboard())

async def admin_add_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    context.user_data['admin_action'] = 'add_tests'
    await update.message.reply_text("➕ Добавить тесты\n\nВведите username и количество через пробел\nНапример: @anna 5", reply_markup=get_cancel_keyboard())

async def admin_add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    context.user_data['admin_action'] = 'add_points'
    await update.message.reply_text("⭐ Добавить очки\n\nВведите username и количество через пробел\nНапример: @anna 100", reply_markup=get_cancel_keyboard())

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT user_id, first_name, username, total_points, unlimited_until FROM users ORDER BY total_points DESC LIMIT 30')
        rows = c.fetchall()
        
        text = "👥 СПИСОК ПОЛЬЗОВАТЕЛЕЙ 👥\n\n"
        for i, row in enumerate(rows, 1):
            name = row['first_name'] or f"ID {row['user_id']}"
            username = f"(@{row['username']})" if row['username'] else ''
            premium = "💎" if row['unlimited_until'] and datetime.fromisoformat(row['unlimited_until']) > datetime.now() else ""
            text += f"{i}. {name} {username} — {row['total_points']}⭐ {premium}\n"
        
        await update.message.reply_text(text, reply_markup=get_admin_keyboard())
    finally:
        conn.close()

async def admin_reset_weekly_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    reset_weekly_points()
    await update.message.reply_text("✅ Недельный рейтинг сброшен!", reply_markup=get_admin_keyboard())

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    action = context.user_data.get('admin_action')
    if not action:
        return
    
    text = update.message.text.strip()
    
    if action == 'set_premium':
        parts = text.split()
        target = parts[0].lstrip('@')
        days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
        
        conn = get_db()
        try:
            c = conn.cursor()
            if target.isdigit():
                c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(target),))
            else:
                c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
            row = c.fetchone()
            
            if not row:
                await update.message.reply_text(f"❌ Пользователь {target} не найден", reply_markup=get_admin_keyboard())
                del context.user_data['admin_action']
                return
            
            target_user_id = row['user_id']
            target_name = row['first_name'] or target
            
            until = (datetime.now() + timedelta(days=days)).isoformat()
            c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (until, target_user_id))
            conn.commit()
            
            await update.message.reply_text(f"✅ {target_name} получил премиум на {days} дней! 🎉", reply_markup=get_admin_keyboard())
        finally:
            conn.close()
    
    elif action == 'remove_premium':
        target = text.lstrip('@')
        conn = get_db()
        try:
            c = conn.cursor()
            if target.isdigit():
                c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(target),))
            else:
                c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
            row = c.fetchone()
            
            if not row:
                await update.message.reply_text(f"❌ Пользователь {target} не найден", reply_markup=get_admin_keyboard())
                del context.user_data['admin_action']
                return
            
            target_user_id = row['user_id']
            target_name = row['first_name'] or target
            
            c.execute('UPDATE users SET unlimited_until = NULL WHERE user_id = ?', (target_user_id,))
            conn.commit()
            
            await update.message.reply_text(f"✅ У {target_name} удалён премиум", reply_markup=get_admin_keyboard())
        finally:
            conn.close()
    
    elif action == 'add_tests':
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Введите username и количество", reply_markup=get_admin_keyboard())
            del context.user_data['admin_action']
            return
        
        target = parts[0].lstrip('@')
        try:
            count = int(parts[1])
        except:
            await update.message.reply_text("❌ Количество должно быть числом", reply_markup=get_admin_keyboard())
            del context.user_data['admin_action']
            return
        
        conn = get_db()
        try:
            c = conn.cursor()
            if target.isdigit():
                c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(target),))
            else:
                c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
            row = c.fetchone()
            
            if not row:
                await update.message.reply_text(f"❌ Пользователь {target} не найден", reply_markup=get_admin_keyboard())
                del context.user_data['admin_action']
                return
            
            target_user_id = row['user_id']
            target_name = row['first_name'] or target
            
            add_tests(target_user_id, count)
            
            await update.message.reply_text(f"✅ {target_name} +{count} тестов! 🎉", reply_markup=get_admin_keyboard())
        finally:
            conn.close()
    
    elif action == 'add_points':
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Введите username и количество", reply_markup=get_admin_keyboard())
            del context.user_data['admin_action']
            return
        
        target = parts[0].lstrip('@')
        try:
            count = int(parts[1])
        except:
            await update.message.reply_text("❌ Количество должно быть числом", reply_markup=get_admin_keyboard())
            del context.user_data['admin_action']
            return
        
        conn = get_db()
        try:
            c = conn.cursor()
            if target.isdigit():
                c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(target),))
            else:
                c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
            row = c.fetchone()
            
            if not row:
                await update.message.reply_text(f"❌ Пользователь {target} не найден", reply_markup=get_admin_keyboard())
                del context.user_data['admin_action']
                return
            
            target_user_id = row['user_id']
            target_name = row['first_name'] or target
            
            add_points(target_user_id, count)
            
            await update.message.reply_text(f"✅ {target_name} +{count} очков! ⭐", reply_markup=get_admin_keyboard())
        finally:
            conn.close()
    
    del context.user_data['admin_action']

async def admin_set_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    if not context.args:
        await update.message.reply_text("📖 /setpremium @username [дни]\nПример: /setpremium @anna 30")
        return
    
    target = context.args[0].lstrip('@')
    days = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 30
    
    conn = get_db()
    try:
        c = conn.cursor()
        if target.isdigit():
            c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(target),))
        else:
            c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
        row = c.fetchone()
        
        if not row:
            await update.message.reply_text(f"❌ Пользователь {target} не найден")
            return
        
        target_user_id = row['user_id']
        target_name = row['first_name'] or target
        
        until = (datetime.now() + timedelta(days=days)).isoformat()
        c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (until, target_user_id))
        conn.commit()
        
        await update.message.reply_text(f"✅ {target_name} получил премиум на {days} дней! 🎉")
    finally:
        conn.close()

async def admin_remove_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    if not context.args:
        await update.message.reply_text("📖 /removepremium @username")
        return
    
    target = context.args[0].lstrip('@')
    conn = get_db()
    try:
        c = conn.cursor()
        if target.isdigit():
            c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(target),))
        else:
            c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
        row = c.fetchone()
        
        if not row:
            await update.message.reply_text(f"❌ Пользователь {target} не найден")
            return
        
        target_user_id = row['user_id']
        target_name = row['first_name'] or target
        
        c.execute('UPDATE users SET unlimited_until = NULL WHERE user_id = ?', (target_user_id,))
        conn.commit()
        
        await update.message.reply_text(f"✅ У {target_name} удалён премиум")
    finally:
        conn.close()

async def admin_add_tests_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("📖 /addtests @username кол-во\nПример: /addtests @anna 5")
        return
    
    target = context.args[0].lstrip('@')
    try:
        count = int(context.args[1])
    except:
        await update.message.reply_text("❌ Кол-во должно быть числом")
        return
    
    conn = get_db()
    try:
        c = conn.cursor()
        if target.isdigit():
            c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(target),))
        else:
            c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
        row = c.fetchone()
        
        if not row:
            await update.message.reply_text(f"❌ Пользователь {target} не найден")
            return
        
        target_user_id = row['user_id']
        target_name = row['first_name'] or target
        
        add_tests(target_user_id, count)
        
        await update.message.reply_text(f"✅ {target_name} +{count} тестов! 🎉")
    finally:
        conn.close()

async def admin_add_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("📖 /addpoints @username кол-во\nПример: /addpoints @anna 100")
        return
    
    target = context.args[0].lstrip('@')
    try:
        count = int(context.args[1])
    except:
        await update.message.reply_text("❌ Кол-во должно быть числом")
        return
    
    conn = get_db()
    try:
        c = conn.cursor()
        if target.isdigit():
            c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(target),))
        else:
            c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
        row = c.fetchone()
        
        if not row:
            await update.message.reply_text(f"❌ Пользователь {target} не найден")
            return
        
        target_user_id = row['user_id']
        target_name = row['first_name'] or target
        
        add_points(target_user_id, count)
        
        await update.message.reply_text(f"✅ {target_name} +{count} очков! ⭐")
    finally:
        conn.close()

async def admin_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT user_id, first_name, username, total_points, unlimited_until FROM users ORDER BY total_points DESC LIMIT 30')
        rows = c.fetchall()
        
        text = "👥 ПОЛЬЗОВАТЕЛИ БОТА 👥\n\n"
        for i, row in enumerate(rows, 1):
            name = row['first_name'] or f"ID {row['user_id']}"
            username = f"(@{row['username']})" if row['username'] else ''
            premium = "💎" if row['unlimited_until'] and datetime.fromisoformat(row['unlimited_until']) > datetime.now() else ""
            text += f"{i}. {name} {username} — {row['total_points']}⭐ {premium}\n"
        
        await update.message.reply_text(text)
    finally:
        conn.close()

async def admin_reset_weekly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        return
    
    reset_weekly_points()
    await update.message.reply_text("✅ Недельный рейтинг сброшен!")

# === ОБРАБОТЧИКИ ===
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "🌸 Создать тест":
        await create_test_start(update, context)
    elif text == "👑 Мои тесты":
        await my_tests_handler(update, context)
    elif text == "📊 Статистика":
        await stats_handler(update, context)
    elif text == "🎀 Бонус и задания":
        await bonus_tasks_menu(update, context)
    elif text == "🎁 Бонус":
        await daily_bonus_handler(update, context)
    elif text == "📋 Задания":
        await daily_tasks_handler(update, context)
    elif text == "👭 Пригласить":
        await invite_handler(update, context)
    elif text == "🛍️ Магазин":
        await shop_handler(update, context)
    elif text == "🔧 Админ-панель" and user_id == ADMIN_ID:
        await admin_panel(update, context)
    elif text == "👑 Выдать премиум" and user_id == ADMIN_ID:
        await admin_set_premium(update, context)
    elif text == "🔻 Снять премиум" and user_id == ADMIN_ID:
        await admin_remove_premium(update, context)
    elif text == "➕ Добавить тесты" and user_id == ADMIN_ID:
        await admin_add_tests(update, context)
    elif text == "⭐ Добавить очки" and user_id == ADMIN_ID:
        await admin_add_points(update, context)
    elif text == "📋 Список пользователей" and user_id == ADMIN_ID:
        await admin_list_users(update, context)
    elif text == "🔄 Сброс недельного рейтинга" and user_id == ADMIN_ID:
        await admin_reset_weekly_command(update, context)
    elif text == "🔙 Назад":
        await start(update, context)
    elif text == "➕ Добавить вариант":
        await add_option(update, context)
    elif text == "✅ Готово":
        await finish_options(update, context)
    else:
        data = context.user_data.get('create_test')
        admin_action = context.user_data.get('admin_action')
        if data:
            await handle_create_test(update, context)
        elif admin_action:
            await handle_admin_input(update, context)
        else:
            await update.message.reply_text("🌸 Используй кнопки меню! 🌸", reply_markup=get_main_keyboard(user_id))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "show_created_tests":
        await show_created_tests(update, context)
    elif data == "show_saved_tests":
        await show_saved_tests(update, context)
    elif data == "back_to_my_tests":
        await my_tests_handler(update, context)
    elif data == "back_to_main":
        await start(update, context)
    elif data.startswith("created_page_"):
        page = int(data.split("_")[2])
        context.user_data['my_tests']['page'] = page
        await show_created_tests(update, context)
    elif data.startswith("saved_page_"):
        page = int(data.split("_")[2])
        context.user_data['my_tests']['page'] = page
        await show_saved_tests(update, context)
    elif data.startswith("created_test_"):
        await show_test_details(update, context)
    elif data.startswith("saved_test_"):
        await show_test_details(update, context)
    elif data.startswith("view_full_test_"):
        await view_full_test(update, context)
    elif data.startswith("share_test_"):
        await share_test_handler(update, context)
    elif data.startswith("group_"):
        await select_question_group(update, context)
    elif data.startswith("premium_group_"):
        await premium_group_click(update, context)
    elif data == "random_group":
        await random_group_click(update, context)
    elif data == "next_question":
        await next_question(update, context)
    elif data == "random_question":
        await random_question(update, context)
    elif data == "select_question":
        await select_current_question(update, context)
    elif data == "back_to_groups":
        await back_to_groups_handler(update, context)
    elif data.startswith("correct_"):
        await select_correct_answer(update, context)
    elif data.startswith("greeting_"):
        await ask_for_greeting(update, context)
    elif data.startswith("diplom_"):
        await choose_diplom_handler(update, context)
    elif data.startswith("confirm_share_"):
        await confirm_share_handler(update, context)
    elif data.startswith("save_after_create_"):
        await save_after_create(update, context)
    elif data == "cancel_share":
        await cancel_share_handler(update, context)
    elif data.startswith("start_test_"):
        await start_test_handler(update, context)
    elif data.startswith("save_test_"):
        await save_test_handler(update, context)
    elif data.startswith("unsave_test_"):
        await unsave_test_handler(update, context)
    elif data.startswith("answer_"):
        await take_test_answer(update, context)
    elif data == "rating_all":
        await rating_all_handler(update, context)
    elif data == "rating_week":
        await rating_week_handler(update, context)
    elif data == "top_friends":
        await top_friends_handler(update, context)
    elif data.startswith("friend_details_"):
        await show_friend_details(update, context)
    elif data == "back_to_stats":
        await back_to_stats(update, context)
    elif data == "open_shop":
        await open_shop_handler(update, context)
    elif data.startswith("buy_"):
        await query.message.reply_text("💎 Для оплаты напишите @LavaTopBot 💎")
    elif data == "shop":
        await shop_handler(update, context)
    
    await query.answer()

# === MAIN ===
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpremium", admin_set_premium_command))
    app.add_handler(CommandHandler("removepremium", admin_remove_premium_command))
    app.add_handler(CommandHandler("addtests", admin_add_tests_command))
    app.add_handler(CommandHandler("addpoints", admin_add_points_command))
    app.add_handler(CommandHandler("users", admin_users_command))
    app.add_handler(CommandHandler("resetweekly", admin_reset_weekly_cmd))
    
    app.add_handler(MessageHandler(filters.Regex("^🌸 Создать тест$"), create_test_start))
    app.add_handler(MessageHandler(filters.Regex("^👑 Мои тесты$"), my_tests_handler))
    app.add_handler(MessageHandler(filters.Regex("^📊 Статистика$"), stats_handler))
    app.add_handler(MessageHandler(filters.Regex("^🎀 Бонус и задания$"), bonus_tasks_menu))
    app.add_handler(MessageHandler(filters.Regex("^🎁 Бонус$"), daily_bonus_handler))
    app.add_handler(MessageHandler(filters.Regex("^📋 Задания$"), daily_tasks_handler))
    app.add_handler(MessageHandler(filters.Regex("^👭 Пригласить$"), invite_handler))
    app.add_handler(MessageHandler(filters.Regex("^🛍️ Магазин$"), shop_handler))
    app.add_handler(MessageHandler(filters.Regex("^🔧 Админ-панель$"), admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^👑 Выдать премиум$"), admin_set_premium))
    app.add_handler(MessageHandler(filters.Regex("^🔻 Снять премиум$"), admin_remove_premium))
    app.add_handler(MessageHandler(filters.Regex("^➕ Добавить тесты$"), admin_add_tests))
    app.add_handler(MessageHandler(filters.Regex("^⭐ Добавить очки$"), admin_add_points))
    app.add_handler(MessageHandler(filters.Regex("^📋 Список пользователей$"), admin_list_users))
    app.add_handler(MessageHandler(filters.Regex("^🔄 Сброс недельного рейтинга$"), admin_reset_weekly_command))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Назад$"), start))
    app.add_handler(MessageHandler(filters.Regex("^➕ Добавить вариант$"), add_option))
    app.add_handler(MessageHandler(filters.Regex("^✅ Готово$"), finish_options))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.Regex("^❌ Отмена$"), cancel_creation))
    app.add_handler(MessageHandler(filters.VOICE, save_greeting))
    app.add_handler(MessageHandler(filters.VIDEO, save_greeting))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🚀✨ Бот успешно запущен! ВСЕ ИСПРАВЛЕНИЯ ПРИМЕНЕНЫ! ✨🚀")
    app.run_polling()

if __name__ == "__main__":
    main()
