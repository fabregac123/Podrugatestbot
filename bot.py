#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бот для создания тестов для подруг @PodrugaTestBot
Версия: 67.0 - ОБНОВЛЕННОЕ МЕНЮ
"""

import logging
import json
import sqlite3
import random
import os
import asyncio
import hashlib
from datetime import datetime, timedelta
from dotenv import load_dotenv
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
MAX_SAVED_FREE = 3
MAX_SAVED_PREMIUM = 10
ADMIN_ID = 710623393

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
    'kpop': '🎤 K-pop'
}

QUESTIONS_BY_GROUP = {
    'friendship': [
        "✨ Как долго мы дружим? ✨",
        "💕 Где мы познакомились? 💕",
        "🎨 Мой любимый цвет? 🎨",
        "🍕 Моя любимая еда? 🍕",
        "💃 Моё любимое занятие? 💃",
        "📺 Мой любимый сериал? 📺",
        "😤 Что меня бесит? 😤",
        "🌟 Моя заветная мечта? 🌟"
    ],
    'love': [
        "💘 Какой тип парня мне нравится? 💘",
        "💕 Что для меня важно в отношениях? 💕",
        "😳 Как я показываю симпатию? 😳",
        "🌹 Моё идеальное свидание? 🌹",
        "✨ Что меня влюбляет? ✨",
        "🎁 Какой подарок я мечтаю получить? 🎁",
        "🙄 Что меня раздражает в парнях? 🙄",
        "📱 Мой краш из тиктока? 📱"
    ],
    'humor': [
        "🏃‍♀️ Что я делаю, когда опаздываю? 🏃‍♀️",
        "🤪 Моя самая странная привычка? 🤪",
        "💃 Как я танцую? 💃",
        "🍪 Что я ем ночью? 🍪",
        "👀 Как я вру? 👀",
        "😱 Что делаю при виде паука? 😱",
        "🐌 Мой смешной страх? 🐌",
        "💬 Моя коронная фраза? 💬"
    ],
    'myself': [
        "💪 Моя суперсила? 💪",
        "🦄 Что мне нужно для счастья? 🦄",
        "🎧 Как я справляюсь со стрессом? 🎧",
        "👩‍🎤 Кем я хочу стать в будущем? 👩‍🎤",
        "💅 Что я больше всего люблю в себе? 💅",
        "😨 Мой главный страх? 😨",
        "✨ Моя фишка? ✨",
        "🌈 Что меня вдохновляет? 🌈"
    ],
    'family': [
        "💕 С кем я самая близкая в семье? 💕",
        "🍿 Что я люблю делать с семьёй? 🍿",
        "🎄 Какая у нас семейная традиция? 🎄",
        "👩‍👧 На кого я похожа внешне? 👩‍👧",
        "😅 Что меня бесит в родителях? 😅",
        "👫 Есть ли у меня брат или сестра? 👫",
        "💖 Что я больше всего ценю в семье? 💖",
        "👵 Моя любимая бабушка? 👵"
    ],
    'school': [
        "📖 Мой любимый предмет в школе? 📖",
        "😫 Самый ненавистный урок? 😫",
        "📱 Что я делаю на скучных уроках? 📱",
        "👯 С кем я сижу за партой? 👯",
        "🤫 Как я списываю? 🤫",
        "🍔 Что я ем в школьной столовой? 🍔",
        "👩‍🏫 Моя училка-краш? 👩‍🏫",
        "👻 Кого я боюсь в школе? 👻"
    ],
    'style': [
        "👗 Мой любимый стиль одежды? 👗",
        "🎀 Мой любимый цвет в одежде? 🎀",
        "🙅‍♀️ Что я никогда не надену? 🙅‍♀️",
        "🛍️ Моя вещь must-have? 🛍️",
        "✨ Что я надеваю на вечеринку? ✨",
        "👟 Моя любимая обувь? 👟",
        "💇‍♀️ Как я крашу волосы? 💇‍♀️",
        "🌸 Моя любимая косметика? 🌸"
    ],
    'social': [
        "📱 Мой любимый тиктокер? 📱",
        "📸 Что я пощу в сторис? 📸",
        "❤️ Сколько лайков в среднем набираю? ❤️",
        "🦄 Мой любимый фильтр? 🦄",
        "👯 С кем я снимаю контент? 👯",
        "📺 От какого контента я зависаю? 📺",
        "🎵 Мой любимый звук в тиктоке? 🎵",
        "👑 Какая у меня подписей? 👑"
    ],
    'dreams': [
        "✈️ Куда я мечтаю поехать? ✈️",
        "🌟 Моя самая заветная мечта? 🌟",
        "🚗 Какую машину я хочу? 🚗",
        "☀️ Мой идеальный день? ☀️",
        "🛍️ Что я хочу купить прямо сейчас? 🛍️",
        "📝 Что у меня в wishlist? 📝",
        "🏠 Где я хочу жить? 🏠",
        "💎 О чём я мечтаю каждый день? 💎"
    ],
    'kpop': [
        "🎤 Моя любимая k-pop группа? 🎤",
        "💕 Мой биас (любимый участник)? 💕",
        "🎧 Какой трек сейчас на повторе? 🎧",
        "💜 На каком концерте я была? 💜",
        "⭐ С кем из айдолов хочу встретиться? ⭐",
        "💃 Какой танец я выучила? 💃",
        "🫶 Кто мой вайб? 🫶",
        "🎁 Какой мерч я хочу? 🎁"
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

PREMIUM_SHOP_ITEMS = {
    'frame_gold': {'name': '🖼️ Золотая рамка', 'price': 49, 'icon': '✨'},
    'frame_diamond': {'name': '🖼️ Алмазная рамка', 'price': 99, 'icon': '💎'},
    'frame_royal': {'name': '🖼️ Королевская рамка', 'price': 199, 'icon': '👑'},
    'animated_diplom': {'name': '🎬 Анимированный диплом', 'price': 99, 'icon': '🎬'},
    'vip_badge': {'name': '⭐ VIP-значок', 'price': 29, 'icon': '⭐'},
    'gold_nickname': {'name': '✨ Золотой ник', 'price': 49, 'icon': '✨'}
}

STREAK_REWARDS = {
    7: {'points': 50, 'tests': 1, 'premium_days': 0, 'description': '50 очков + 1 тест'},
    14: {'points': 100, 'tests': 2, 'premium_days': 0, 'description': '100 очков + 2 теста'},
    30: {'points': 300, 'tests': 0, 'premium_days': 7, 'description': '300 очков + 7 дней премиума'},
    100: {'points': 1000, 'tests': 0, 'premium_days': 30, 'description': '1000 очков + 30 дней премиума'}
}

DIPLOMS = {
    'free': {
        'name': '📜 КЛАССИЧЕСКИЙ ДИПЛОМ',
        'icon': '📜',
        'border': '🌸🌸🌸',
        'text': 'Ты супер! Так держать, подружка! 💕'
    },
    'premium_1': {
        'name': '👑 КОРОЛЕВСКИЙ ДИПЛОМ',
        'icon': '👑',
        'border': '✨👑✨',
        'text': 'Ты настоящая королева дружбы! 👸💎'
    },
    'premium_2': {
        'name': '💎 БРИЛЛИАНТОВЫЙ ДИПЛОМ',
        'icon': '💎',
        'border': '✨💎✨',
        'text': 'Ты сияешь ярче бриллианта! ✨💕'
    },
    'premium_3': {
        'name': '🌟 ЗВЁЗДНЫЙ ДИПЛОМ',
        'icon': '🌟',
        'border': '✨🌟✨',
        'text': 'Ты настоящая звезда! 🌟⭐✨'
    },
    'premium_4': {
        'name': '🦄 ВОЛШЕБНЫЙ ДИПЛОМ',
        'icon': '🦄',
        'border': '✨🦄✨',
        'text': 'Ты уникальна, как единорог! 🦄💖'
    },
    'premium_5': {
        'name': '🌸 ЦВЕТОЧНЫЙ ДИПЛОМ',
        'icon': '🌸',
        'border': '✨🌸✨',
        'text': 'Ты нежная и красивая, как цветок! 🌸💗'
    }
}

WOW_EMOJIS = {
    'start': '🌸', 'success': '🎉', 'error': '💔',
    'test': '📝', 'friend': '👯', 'crown': '👑',
    'star': '⭐', 'heart': '💗', 'daily': '🎁',
    'achievement': '🏆', 'shop': '🛍️', 'money': '💰',
    'top': '🏆', 'back': '🔙', 'stats': '📊', 'cancel': '❌',
    'favorite': '💖', 'diplom': '🎓', 'task': '📋', 'level': '📈',
    'sparkle': '✨', 'cute': '🎀', 'fire': '🔥'
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Добавляем колонки для голосовых/видео, если их нет
        try:
            c.execute('ALTER TABLE tests ADD COLUMN greeting_type TEXT')
        except sqlite3.OperationalError:
            pass
        try:
            c.execute('ALTER TABLE tests ADD COLUMN greeting_file_id TEXT')
        except sqlite3.OperationalError:
            pass
        try:
            c.execute('ALTER TABLE tests ADD COLUMN greeting_duration INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
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
        
        c.execute('''CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_type TEXT,
            price INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            reward_type TEXT,
            reward_value INTEGER,
            expires_at TIMESTAMP,
            used_by INTEGER DEFAULT NULL
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
        c.execute('SELECT id, title, created_at FROM tests WHERE creator_id = ? ORDER BY created_at DESC', (user_id,))
        tests = []
        for row in c.fetchall():
            test = dict(row)
            test['attempts_count'] = get_test_attempts_count(test['id'])
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
        c.execute('UPDATE users SET total_points = total_points + ? WHERE user_id = ?', (points, user_id))
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
                greeting_type=None, greeting_file_id=None, greeting_duration=None):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''INSERT INTO tests 
            (creator_id, creator_name, creator_username, title, questions, options, correct_answers, greeting_type, greeting_file_id, greeting_duration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (creator_id, creator_name, creator_username, title, json.dumps(questions), 
             json.dumps(options), json.dumps(correct_answers), greeting_type, greeting_file_id, greeting_duration))
        test_id = c.lastrowid
        c.execute('UPDATE users SET tests_created = tests_created + 1 WHERE user_id = ?', (creator_id,))
        conn.commit()
        
        add_points(creator_id, 20)
        complete_daily_task(creator_id, 'create_test')
        add_achievement(creator_id, 'first_test')
        
        return test_id
    except Exception as e:
        logger.error(f"Ошибка создания теста: {e}")
        return None
    finally:
        conn.close()

def can_save_test(user_id):
    saved_count = get_saved_tests_count(user_id)
    has_premium = is_premium(user_id)
    max_saved = MAX_SAVED_PREMIUM if has_premium else MAX_SAVED_FREE
    return saved_count < max_saved

def save_test(user_id, test_id):
    conn = get_db()
    try:
        if not can_save_test(user_id):
            return False
        
        c = conn.cursor()
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
        c.execute('''SELECT t.id, t.title, t.creator_name, t.creator_id, t.creator_username
                     FROM saved_tests s 
                     JOIN tests t ON s.test_id = t.id 
                     WHERE s.user_id = ? AND t.creator_id != ?
                     ORDER BY s.created_at DESC''', (user_id, user_id))
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_saved_tests_count(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM saved_tests WHERE user_id = ?', (user_id,))
        return c.fetchone()[0]
    finally:
        conn.close()

async def save_attempt(test_id, friend_id, friend_name, friend_username, answers, score, bot=None):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''INSERT INTO attempts (test_id, friend_id, friend_name, friend_username, answers, score)
            VALUES (?, ?, ?, ?, ?, ?)''', 
            (test_id, friend_id, friend_name, friend_username, json.dumps(answers), score))
        conn.commit()
        
        test = get_test_by_id(test_id)
        if test:
            add_points(test['creator_id'], 15)
            complete_daily_task(test['creator_id'], 'get_result')
            
            if bot and test.get('greeting_file_id'):
                try:
                    if test.get('greeting_type') == 'voice':
                        await bot.send_voice(chat_id=friend_id, voice=test['greeting_file_id'], duration=test.get('greeting_duration', 0))
                    elif test.get('greeting_type') == 'video':
                        await bot.send_video(chat_id=friend_id, video=test['greeting_file_id'], duration=test.get('greeting_duration', 0))
                except Exception as e:
                    logger.error(f"Ошибка отправки поздравления: {e}")
        
        add_points(friend_id, int(score))
        complete_daily_task(friend_id, 'complete_test')
        
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения попытки: {e}")
        return False
    finally:
        conn.close()

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
        
        if row and row['completed']:
            return False
        
        c.execute('''INSERT INTO daily_tasks (user_id, task_date, task_type, completed) 
                     VALUES (?, ?, ?, 1) 
                     ON CONFLICT(user_id, task_date, task_type) DO UPDATE SET completed = 1''',
                  (user_id, today, task_type))
        
        if task_type in DAILY_TASKS:
            points = DAILY_TASKS[task_type]['points']
            add_points(user_id, points)
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
        
        c.execute('''
            SELECT u.first_name, u.username, u.created_at,
                   COUNT(a.id) as tests_passed
            FROM referrals r
            JOIN users u ON r.referred_id = u.user_id
            LEFT JOIN attempts a ON a.friend_id = u.user_id
            WHERE r.referrer_id = ?
            GROUP BY u.user_id
            ORDER BY r.created_at DESC
            LIMIT 10
        ''', (user_id,))
        referrals = []
        for row in c.fetchall():
            referrals.append({
                'name': row['first_name'] or 'Подружка',
                'username': row['username'],
                'joined_at': row['created_at'][:10],
                'tests_passed': row['tests_passed']
            })
        
        return {'total': total, 'active': active, 'referrals': referrals}
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
        c.execute('SELECT tests_created, total_points, referral_count FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        c.execute('SELECT COUNT(*) FROM attempts WHERE friend_id = ?', (user_id,))
        tests_passed = c.fetchone()[0]
        return {
            'created': user['tests_created'] if user else 0,
            'points': user['total_points'] if user else 0,
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
                   a.answers, a.score, a.completed_at
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

# === КЛАВИАТУРЫ ===
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📝 Создать тест"), KeyboardButton("👑 Мои тесты")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("🎁 Задания и бонусы")],
        [KeyboardButton("👭 Пригласить"), KeyboardButton("🛍️ Магазин")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True)

def get_back_keyboard():
    return ReplyKeyboardMarkup([[f"{WOW_EMOJIS['back']} Назад"]], resize_keyboard=True, one_time_keyboard=True)

def get_question_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Другой вопрос", callback_data="next_question")],
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
    
    return InlineKeyboardMarkup(keyboard)

def get_shop_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Премиум 30 дней — 299 ₽", callback_data="buy_premium_month")],
        [InlineKeyboardButton("💎 Премиум 3 месяца — 699 ₽", callback_data="buy_premium_3months")],
        [InlineKeyboardButton("💎 Премиум ГОД — 1999 ₽", callback_data="buy_premium_year")]
    ])

def get_share_confirm_keyboard(test_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Отправить подруге", callback_data=f"confirm_share_{test_id}"),
         InlineKeyboardButton("💾 Сохранить в мои тесты", callback_data=f"save_after_create_{test_id}"),
         InlineKeyboardButton("❌ Отмена", callback_data="cancel_share")],
        [InlineKeyboardButton("👭 Поделиться ссылкой", 
            switch_inline_query=f"🌸✨ ПРИВЕТ, ПОДРУЖКА! ✨🌸\n\n💕 Твоя подруга приглашает тебя пройти тестик!\n\n📝 Узнай, насколько хорошо ты её знаешь!\n\n👉 Нажми и начни!\n\nhttps://t.me/{BOT_USERNAME}?start=test_{test_id}")]
    ])

def get_start_test_keyboard(test_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_test_{test_id}"),
        InlineKeyboardButton("⭐ Сохранить", callback_data=f"save_test_{test_id}")
    ]])

def get_my_tests_keyboard(has_created, has_saved):
    keyboard = []
    if has_created:
        keyboard.append([InlineKeyboardButton("📝 Мои создания", callback_data="show_created_tests")])
    if has_saved:
        keyboard.append([InlineKeyboardButton("⭐ Сохранённые тесты", callback_data="show_saved_tests")])
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

# === ОСНОВНЫЕ ХЕНДЛЕРЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await send_referral_notification(bot, referred_by, user.first_name or f"ID {user.id}", is_new_user=True)
            await apply_referral_bonus(referred_by, user.id)
    else:
        update_user(user.id, user.username, user.first_name)
        if referred_by and not existing.get('referred_by'):
            await send_referral_notification(bot, referred_by, user.first_name or f"ID {user.id}", is_new_user=False)
            await apply_referral_bonus(referred_by, user.id)
    
    if test_id:
        test = get_test_by_id(test_id)
        if test:
            creator = get_user(test['creator_id'])
            creator_name = creator.get('first_name', 'Подружка') if creator else 'Подружка'
            creator_username = f"(@{creator.get('username', '')})" if creator and creator.get('username') else ''
            text = (f"🌸✨ ПРИВЕТ, {user.first_name or 'ПОДРУЖКА'}! ✨🌸\n\n"
                    f"💕 {creator_name} {creator_username} приглашает тебя пройти супер-тестик!\n\n"
                    f"📝 *{test['title']}*\n\n"
                    f"✨ Узнай, насколько хорошо ты знаешь свою подружку! ✨\n\n"
                    f"👇 Нажми на кнопку и вперёд! 👇")
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_start_test_keyboard(test_id))
            return
    
    user_data = get_user(user.id)
    points = user_data.get('total_points', 0) if user_data else 0
    rank = get_rank(points)
    tests = get_available_tests(user.id)
    premium = "💎 ПРЕМИУМ" if is_premium(user.id) else "🔓 БЕСПЛАТНЫЙ"
    
    tests_text = "♾️" if tests == -1 else f"{tests}"
    
    text = (f"{WOW_EMOJIS['start']}{WOW_EMOJIS['sparkle']} *ПРИВЕТ, {user.first_name or 'ПОДРУЖКА'}!* {WOW_EMOJIS['sparkle']}{WOW_EMOJIS['start']}\n\n"
            f"🌸 *Добро пожаловать в PodrugaTestBot* — место, где мы проверяем, насколько круто мы знаем друг друга! 🌸\n\n"
            f"🎀 *Твой статус:* {premium}\n"
            f"🎁 *Доступно:* {tests_text}\n"
            f"⭐ *Очков:* {points}\n"
            f"🏆 *Ранг:* {rank['name']}\n\n"
            f"💫 *Что тебя ждёт?*\n"
            f"• ✨ Создавай тесты о себе\n"
            f"• 💕 Отправляй их подружкам\n"
            f"• 🎯 Узнавай, насколько хорошо тебя знают\n"
            f"• 🎓 Получай милые дипломы\n"
            f"• 📋 Выполняй задания и получай бонусы\n"
            f"• 🏆 Соревнуйся в рейтинге\n\n"
            f"💖 *Поехали! Нажимай на кнопки ниже* 💖")
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def send_referral_notification(bot, referrer_id, new_user_name, is_new_user=True):
    try:
        referrer = get_user(referrer_id)
        if not referrer:
            return
        
        stats = get_referral_stats(referrer_id)
        
        if is_new_user:
            text = (f"🌸✨ *НОВЕНЬКАЯ ПОДРУЖКА* ✨🌸\n\n"
                    f"💕 *{new_user_name}* перешла по твоей ссылочке!\n\n"
                    f"🎁 Ты получила *+1 тестик* в подарок!\n"
                    f"👭 Всего подружек: {stats['total']}\n"
                    f"⭐ Активных: {stats['active']}\n\n"
                    f"✨ *Продолжай приглашать девчонок!* ✨")
        else:
            text = (f"🌸 *ПОДРУЖКА УЖЕ С НАМИ!* 🌸\n\n"
                    f"💕 *{new_user_name}* уже была зарегистрирована в боте!\n\n"
                    f"👭 Всего подружек: {stats['total']}\n"
                    f"⭐ Активных: {stats['active']}\n\n"
                    f"💖 *Всё равно спасибо, что зовёшь подруг!* 💖")
        
        await safe_send_message(bot, referrer_id, text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Ошибка уведомления: {e}")

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
    available = get_available_tests(user_id)
    
    if available == 0:
        await update.message.reply_text(
            f"💔 *Ой-ой! Тестики закончились!* 💔\n\n"
            f"🎁 Забери *ежедневный бонус*\n"
            f"👭 *Пригласи подружку* по ссылке\n"
            f"💎 Или купи *премиум* в магазине\n\n"
            f"✨ Не сдавайся, у тебя всё получится! ✨",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    context.user_data['create_test'] = {
        'step': 'title',
        'questions_data': []
    }
    
    tests_text = "♾️" if available == -1 else f"{available}"
    
    await update.message.reply_text(
        f"{WOW_EMOJIS['sparkle']} *СОЗДАЁМ НОВЫЙ ТЕСТИК!* {WOW_EMOJIS['sparkle']}\n\n"
        f"📦 *Осталось попыток:* {tests_text}\n\n"
        f"🌸 *Придумай красивое название*\n"
        f"Например: «Насколько хорошо ты меня знаешь?» или «Твоя любимая подружка»\n\n"
        f"✏️ *Напиши название теста:*\n\n"
        f"❌ *Отмена* - чтобы выйти",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'create_test' in context.user_data:
        del context.user_data['create_test']
    await update.message.reply_text("❌ *Создание теста отменено* ❌", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

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
            await update.message.reply_text("✨ *Выбери тему для вопросов:* ✨", parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_groups_keyboard(user_id))
        elif data.get('step') == 'collecting_options':
            data['step'] = 'selecting_question'
            await show_current_question(update, context)
        return
    
    step = data.get('step')
    
    if step == 'title':
        if len(text.strip()) < 3:
            await update.message.reply_text("⚠️ *Название должно быть длиннее 3 символов!* Попробуй ещё раз ⚠️", parse_mode=ParseMode.MARKDOWN)
            return
        data['title'] = text.strip()
        data['step'] = 'greeting'
        user_id = update.effective_user.id
        
        if is_premium(user_id):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎤 Голосовое", callback_data="greeting_voice"),
                 InlineKeyboardButton("🎥 Видео", callback_data="greeting_video")],
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="greeting_skip")]
            ])
            await update.message.reply_text(
                f"🎬✨ *ДОБАВЬ ПОЗДРАВЛЕНИЕ!* ✨🎬\n\n"
                f"Твоя подружка получит это после прохождения теста!\n\n"
                f"📝 *Твой тест:* {data['title']}\n\n"
                f"👇 *Выбери тип поздравления:* 👇",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                f"✨ *Отлично! Теперь выбери тему для вопросов:* ✨",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_question_groups_keyboard(user_id)
            )
    
    elif step == 'waiting_question_count':
        try:
            count = int(text.strip())
            user_id = update.effective_user.id
            has_premium = is_premium(user_id)
            max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
            
            if count < 2 or count > max_q:
                await update.message.reply_text(f"⚠️ *Количество вопросов должно быть от 2 до {max_q}!* Попробуй ещё ⚠️", parse_mode=ParseMode.MARKDOWN)
                return
            
            data['total_q'] = count
            data['current_q'] = 0
            data['step'] = 'selecting_question'
            
            group = data.get('group')
            data['group_questions'] = QUESTIONS_BY_GROUP.get(group, []).copy()
            random.shuffle(data['group_questions'])
            data['current_question_index'] = 0
            
            await show_current_question(update, context)
        except ValueError:
            await update.message.reply_text("⚠️ *Напиши число!* Например: 5 ⚠️", parse_mode=ParseMode.MARKDOWN)
    
    elif step == 'collecting_options' and data.get('waiting_for_option'):
        option_text = text.strip()
        if option_text:
            if len(option_text) > 100:
                await update.message.reply_text("⚠️ *Вариант слишком длинный!* Максимум 100 символов ⚠️", parse_mode=ParseMode.MARKDOWN)
                return
            data['current_options'].append(option_text)
            data['waiting_for_option'] = False
            
            options_list = "\n".join([f"{i+1}. {o}" for i, o in enumerate(data['current_options'])])
            await update.message.reply_text(
                f"✅ *Вариант {len(data['current_options'])} добавлен!* ✅\n\n"
                f"📋 *Твои варианты:*\n{options_list}\n\n"
                f"➕ *Можешь добавить ещё или нажать «Готово»*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_options_keyboard()
            )

async def ask_for_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = context.user_data.get('create_test')
    
    if not data:
        return
    
    greeting_type = query.data.split("_")[1]
    
    if greeting_type == "skip":
        data['step'] = 'group'
        await query.message.reply_text("✨ *Выбери тему для вопросов:* ✨", parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_groups_keyboard(user_id))
        return
    
    data['waiting_greeting'] = greeting_type
    
    if greeting_type == "voice":
        text = "🎤 *Отправь голосовое сообщение* (до 15 секунд)\n\n❌ *Отмена* - чтобы пропустить"
    else:
        text = "🎥 *Отправь видео* (до 15 секунд)\n\n❌ *Отмена* - чтобы пропустить"
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def save_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data or not data.get('waiting_greeting'):
        return
    
    greeting_type = data['waiting_greeting']
    
    if greeting_type == "voice":
        if not update.message.voice:
            await update.message.reply_text("❌ *Отправь голосовое сообщение!*", parse_mode=ParseMode.MARKDOWN)
            return
        file_id = update.message.voice.file_id
        duration = update.message.voice.duration
    else:
        if not update.message.video:
            await update.message.reply_text("❌ *Отправь видео!*", parse_mode=ParseMode.MARKDOWN)
            return
        file_id = update.message.video.file_id
        duration = update.message.video.duration
    
    data['greeting_type'] = greeting_type
    data['greeting_file_id'] = file_id
    data['greeting_duration'] = duration
    del data['waiting_greeting']
    data['step'] = 'group'
    
    await update.message.reply_text(
        f"✅ *Поздравление сохранено!* 🎉\n\n"
        f"Теперь твоя подружка получит его после прохождения теста! 💕\n\n"
        f"✨ *Выбери тему для вопросов:* ✨",
        parse_mode=ParseMode.MARKDOWN,
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
        f"{WOW_EMOJIS['star']} *Вопрос {data['current_q'] + 1}/{data['total_q']}* {WOW_EMOJIS['star']}\n\n"
        f"{question_text}\n\n"
        f"👇 *Что делаем с этим вопросом?* 👇",
        parse_mode=ParseMode.MARKDOWN,
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
        f"{WOW_EMOJIS['star']} *Вопрос {data['current_q'] + 1}/{data['total_q']}* {WOW_EMOJIS['star']}\n\n"
        f"{data['current_question_text']}\n\n"
        f"👇 *Что делаем?* 👇",
        parse_mode=ParseMode.MARKDOWN,
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
        f"📝 *Вопрос:* {data['current_question_text']}\n\n"
        f"✏️ *Напиши вариант ответа №1:*\n\n"
        f"💡 *Совет:* Варианты должны быть разными и понятными",
        parse_mode=ParseMode.MARKDOWN,
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
        f"✨ *Выбрана тема:* {group_name} ✨\n\n"
        f"📊 *Сколько вопросов будет в тесте?*\n"
        f"🔹 *От 2 до {max_q}* вопросов\n\n"
        f"✏️ *Напиши число:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_keyboard()
    )

async def premium_group_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        f"💔 *Ой! Эта тема только в ПРЕМИУМЕ!* 💔\n\n"
        f"🌟 *Купи премиум и получи:*\n"
        f"• 10 крутых тем\n"
        f"• До 10 вопросов в тесте\n"
        f"• Полную статистику\n"
        f"• Красивые дипломы\n\n"
        f"👇 *Переходи в магазин!* 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ В МАГАЗИН", callback_data="open_shop")]])
    )

async def add_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data or data.get('step') != 'collecting_options':
        return
    
    if len(data['current_options']) >= MAX_OPTIONS:
        await update.message.reply_text(f"⚠️ *Максимум {MAX_OPTIONS} вариантов ответа!* Нажми «Готово» ⚠️", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
        return
    
    data['waiting_for_option'] = True
    await update.message.reply_text(f"✏️ *Напиши вариант №{len(data['current_options']) + 1}:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

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
        await update.message.reply_text(f"⚠️ *Нужно минимум {MIN_OPTIONS} варианта ответа!* Добавь ещё ⚠️", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())
        data['waiting_for_option'] = True
        return
    
    data['step'] = 'select_correct'
    
    keyboard = []
    for i, opt in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {opt[:25]}", callback_data=f"correct_{i}")])
    
    await update.message.reply_text(
        f"❓ *Вопрос:* {data['current_question_text']}\n\n"
        f"👇 *Какой вариант ПРАВИЛЬНЫЙ?* 👇",
        parse_mode=ParseMode.MARKDOWN,
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
    data['step'] = 'selecting_question'
    data['current_question_index'] = (data.get('current_question_index', 0) + 1) % len(data.get('group_questions', [1]))
    
    await query.message.reply_text(f"✅ *Вопрос {data['current_q']}/{data['total_q']} сохранён!* ✅", parse_mode=ParseMode.MARKDOWN)
    
    if data['current_q'] < data['total_q']:
        await show_next_question(query, context)
    else:
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
        f"{WOW_EMOJIS['star']} *Вопрос {data['current_q'] + 1}/{data['total_q']}* {WOW_EMOJIS['star']}\n\n"
        f"{data['current_question_text']}\n\n"
        f"👇 *Что делаем?* 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_question_keyboard()
    )

async def finish_creation(query_or_update, context, user_id):
    data = context.user_data.get('create_test', {})
    if not data:
        return
    
    if not use_attempt(user_id):
        msg = ("💔 *Ой-ой! Не хватает тестиков!* 💔\n\n"
               "🎁 *Забери ежедневный бонус*\n"
               "👭 *Пригласи подружку*\n\n"
               "✨ Не сдавайся! ✨")
        if hasattr(query_or_update, 'message'):
            await query_or_update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
        else:
            await query_or_update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
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
        data.get('greeting_duration')
    )
    
    if test_id:
        text = (f"🎉✨ *УРА! ТЕСТИК ГОТОВ!* ✨🎉\n\n"
                f"📝 *Название:* {data['title']}\n"
                f"🔢 *Вопросов:* {data['total_q']}\n\n"
                f"💖 *Ты молодец! Теперь поделись им с подружкой!* 💖\n\n"
                f"👇 *Выбери действие:* 👇")
        
        if hasattr(query_or_update, 'message'):
            await query_or_update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_confirm_keyboard(test_id))
        else:
            await query_or_update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_confirm_keyboard(test_id))
    else:
        add_tests(user_id, 1)
        await query_or_update.message.reply_text("💔 *Ошибка при создании теста!* Попробуй ещё раз 💔", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
    
    del context.user_data['create_test']

async def save_after_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[3])
    user_id = query.from_user.id
    
    if save_test(user_id, test_id):
        await query.message.reply_text("⭐ *Тест сохранён в «Мои тесты»!* ⭐", parse_mode=ParseMode.MARKDOWN)
    else:
        await query.message.reply_text("💔 *Тест уже сохранён!* 💔", parse_mode=ParseMode.MARKDOWN)

# === ОСНОВНЫЕ ХЕНДЛЕРЫ МЕНЮ ===
async def my_tests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    created = get_user_created_tests(user_id)
    saved = get_saved_tests(user_id)
    
    context.user_data['my_tests'] = {
        'created': created, 
        'saved': saved, 
        'page': 0,
        'current_list': None
    }
    
    text = (f"👑✨ *МОИ ТЕСТИКИ* ✨👑\n\n")
    if created:
        text += f"📝 *Создано мной:* {len(created)}\n"
    if saved:
        text += f"⭐ *Сохранено:* {len(saved)}\n"
    if not created and not saved:
        text += "🌸 *У тебя пока нет тестиков* 🌸\n\nСоздай свой первый тест или сохрани чужой!"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, 
                                   reply_markup=get_my_tests_keyboard(bool(created), bool(saved)))

async def show_created_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    my_tests = context.user_data.get('my_tests', {})
    tests = my_tests.get('created', [])
    page = my_tests.get('page', 0)
    
    if not tests:
        await query.message.reply_text("📝 *У тебя пока нет созданных тестиков* 📝\n\nСоздай первый тест через главное меню!", parse_mode=ParseMode.MARKDOWN)
        return
    
    context.user_data['my_tests']['current_list'] = 'created'
    
    text = f"👑✨ *МОИ ТЕСТИКИ* ✨👑\n\n"
    start = page * 5
    for test in tests[start:start+5]:
        text += f"📝 *{test['title'][:30]}*\n"
        text += f"   👥 Прошло: {test['attempts_count']} подружек\n"
        text += f"   📅 {test['created_at'][:10]}\n\n"
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                                 reply_markup=get_paginated_tests_keyboard(tests, page, "created"))

async def show_saved_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    my_tests = context.user_data.get('my_tests', {})
    tests = my_tests.get('saved', [])
    page = my_tests.get('page', 0)
    
    if not tests:
        await query.message.reply_text("⭐ *У тебя пока нет сохранённых тестиков* ⭐\n\nСохраняй тесты подружек, чтобы проходить их позже!", parse_mode=ParseMode.MARKDOWN)
        return
    
    context.user_data['my_tests']['current_list'] = 'saved'
    
    text = f"⭐✨ *СОХРАНЁННЫЕ ТЕСТИКИ* ✨⭐\n\n"
    start = page * 5
    for test in tests[start:start+5]:
        username = f"(@{test.get('creator_username', '')})" if test.get('creator_username') else ''
        text += f"📝 *{test['title'][:30]}*\n"
        text += f"   👤 Автор: {test['creator_name']} {username}\n\n"
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                                 reply_markup=get_paginated_tests_keyboard(tests, page, "saved"))

async def show_test_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    prefix = parts[0]
    test_id = int(parts[2])
    
    test = get_test_by_id(test_id)
    if not test:
        await query.message.reply_text("💔 *Тестик не найден* 💔", parse_mode=ParseMode.MARKDOWN)
        return
    
    user_id = query.from_user.id
    is_owner = test['creator_id'] == user_id
    is_saved = test_id in [t['id'] for t in context.user_data.get('my_tests', {}).get('saved', [])]
    
    text = (f"📝✨ *{test['title']}* ✨📝\n\n"
            f"👤 *Автор:* {test['creator_name']}\n"
            f"📅 *Создан:* {test['created_at'][:10]}\n"
            f"👥 *Прошло:* {test['attempts_count']} подружек\n\n"
            f"👇 *Что хочешь сделать?* 👇")
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                                 reply_markup=get_test_action_keyboard(test_id, is_owner, is_saved))

async def view_full_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[3])
    test = get_test_by_id(test_id)
    
    if not test:
        await query.message.reply_text("💔 *Тестик не найден* 💔", parse_mode=ParseMode.MARKDOWN)
        return
    
    user_id = query.from_user.id
    is_owner = test['creator_id'] == user_id
    
    text = (f"📖✨ *ПОЛНЫЙ ТЕСТИК* ✨📖\n\n"
            f"📝 *{test['title']}*\n\n"
            f"*Вопросы и ответы:*\n\n")
    
    for i, q in enumerate(test['questions'], 1):
        text += f"*{i}. {q}*\n"
        for j, opt in enumerate(test['options'][i-1], 1):
            if test['correct_answers'][i-1] == j-1:
                text += f"   ✅ *{j}. {opt}* (правильный)\n"
            else:
                text += f"   ➖ {j}. {opt}\n"
        text += "\n"
    
    if len(text) > 4000:
        text = text[:3500] + "\n\n... и ещё вопросы (слишком длинный тест)"
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                                 reply_markup=get_full_test_keyboard(test_id, is_owner))

async def share_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    test = get_test_by_id(test_id)
    
    if not test:
        await query.message.reply_text("💔 *Тестик не найден*", parse_mode=ParseMode.MARKDOWN)
        return
    
    user_id = query.from_user.id
    is_owner = test['creator_id'] == user_id
    
    if not is_owner and not use_attempt(user_id):
        await query.message.reply_text(
            "💔 *Ой-ой! Не хватает тестиков!* 💔\n\n"
            "🎁 Забери *ежедневный бонус*\n"
            "👭 *Пригласи подружку*\n\n"
            "✨ Не сдавайся! ✨",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    text = (f"🎉✨ *ТЕСТИК ГОТОВ К ОТПРАВКЕ!* ✨🎉\n\n"
            f"📝 *{test['title']}*\n\n"
            f"💖 *Поделись им с подружкой через кнопку ниже!* 💖")
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=get_share_confirm_keyboard(test_id))
    
    if not is_owner:
        complete_daily_task(user_id, 'send_test')

async def daily_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = get_daily_tasks(user_id)
    
    text = (f"🎀✨ *ЗАДАНИЯ НА СЕГОДНЯ* ✨🎀\n\n"
            f"Выполняй задания и получай *звёздочки*! ⭐\n\n")
    
    completed = 0
    for task in tasks:
        status = "✅" if task['completed'] else "⬜"
        text += f"{status} *{task['name']}* +{task['points']} ⭐\n"
        text += f"   _{task['description']}_\n\n"
        if task['completed']:
            completed += 1
    
    text += f"\n📊 *Выполнено:* {completed}/{len(tasks)}"
    
    if completed == len(tasks):
        text += f"\n\n🎉✨ *ТЫ СУПЕР-ПУПЕР ЗВЕЗДОЧКА!* ✨🎉\nВсе задания выполнены! Завтра будут новые! 🌸"
    else:
        text += f"\n\n💪 *Осталось всего {len(tasks) - completed} заданий!* Ты справишься! 💪"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def achievements_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    achievements = get_achievements(user_id)
    
    achievement_names = {
        'first_test': '🎯 *Первый тест* - Создала свой первый тестик',
        'first_invite': '👭 *Первое приглашение* - Пригласила первую подружку',
        'streak_7': '🔥 *7 дней подряд* - Целая неделя активностей!',
        'streak_14': '⭐ *14 дней подряд* - Две недели без остановки!',
        'streak_30': '💎 *30 дней подряд* - Месяц с нами! Ты легенда!',
        'streak_100': '👑 *100 дней подряд* - НЕВЕРОЯТНО! Ты королева!',
        'level_500': '📚 *Уровень ЗНАТОК* - 500 очков!',
        'level_1500': '💎 *Уровень БРИЛЛИАНТ* - 1500 очков!',
        'level_3500': '👑 *Уровень КОРОЛЕВА* - 3500 очков!',
        'level_7000': '🌟 *Уровень ЗВЕЗДА* - 7000 очков!',
        'level_15000': '👸 *Уровень ЛЕГЕНДА* - 15000 очков!'
    }
    
    text = (f"🏆✨ *МОИ ДОСТИЖЕНИЯ* ✨🏆\n\n")
    
    if not achievements:
        text += "🌸 *У тебя пока нет достижений* 🌸\n\nВыполняй задания, создавай тесты и приглашай подружек, чтобы получать награды! 💪✨"
    else:
        for ach in achievements[:5]:
            name = achievement_names.get(ach['achievement_type'], ach['achievement_type'])
            text += f"🏆 {name}\n"
            text += f"   📅 *{ach['achieved_at'][:10]}*\n\n"
        
        if len(achievements) > 5:
            text += f"\n✨ *И ещё {len(achievements) - 5} достижений!* ✨"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        return
    
    points = user.get('total_points', 0)
    rank = get_rank(points)
    streak = user.get('daily_streak', 0)
    created = user.get('tests_created', 0)
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
    
    premium_text = ""
    if has_premium:
        expiry = get_premium_expiry(user_id)
        if expiry:
            premium_text = f"\n💎 *Премиум до:* {expiry.strftime('%d.%m.%Y')}"
    
    text = (f"📊✨ *ТВОЯ СТАТИСТИКА* ✨📊\n\n"
            f"👤 *Имя:* {user.get('first_name', 'Подружка')}\n"
            f"🏆 *Ранг:* {rank['name']}\n"
            f"⭐ *Очки:* {points}\n"
            f"📊 *Место:* {rating}\n"
            f"🔥 *Серия:* {streak} дней\n"
            f"🎯 *До след. ранга:* {get_next_level_points(points)} очков{premium_text}\n\n"
            f"📝 *Создано тестов:* {created}\n"
            f"🎯 *Пройдено тестов:* {passed}\n"
            f"👭 *Приглашено подруг:* {referrals}\n"
            f"📦 *Сохранено тестов:* {saved_count}\n"
            f"🎁 *Доступно:* {tests_text}")
    
    keyboard = [
        [InlineKeyboardButton("🏆 Топ-10 рейтинга", callback_data="top_rating")],
        [InlineKeyboardButton("👭 Топ подруг", callback_data="top_friends")]
    ]
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def top_rating_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    top_users = get_top_users_full(10)
    my_stats = get_user_full_stats(query.from_user.id)
    
    text = (f"🏆✨ *ТОП-10 РЕЙТИНГА* ✨🏆\n\n")
    
    for i, u in enumerate(top_users, 1):
        if i == 1:
            medal = "👑"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = "📌"
        
        name = u['first_name'] or f"ID {u['user_id']}"
        username = f"(@{u['username']})" if u['username'] else ''
        text += f"{medal} *{i}. {name}* {username}\n"
        text += f"   ⭐ Очки: *{u['total_points']}*\n"
        text += f"   📝 Создала: {u['tests_created']} | 🎯 Прошла: {u['tests_passed']}\n"
        text += f"   👭 Пригласила: {u['referral_count']}\n\n"
    
    text += f"📊 *Твоя статистика:*\n"
    text += f"   ⭐ Очки: {my_stats['points']}\n"
    text += f"   📝 Создала: {my_stats['created']} тестов\n"
    text += f"   🎯 Прошла: {my_stats['passed']} тестов\n"
    text += f"   👭 Пригласила: {my_stats['invited']} подруг\n"
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) + 1 FROM users WHERE total_points > ?', (my_stats['points'],))
        place = c.fetchone()[0]
        text += f"\n📊 *Твоё место в рейтинге:* {place}"
    finally:
        conn.close()
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)

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
        await query.message.reply_text(
            "👭✨ *ТОП ПОДРУЖЕК* ✨👭\n\n"
            "🌸 *Пока никто не проходил твои тестики* 🌸\n\n"
            "Создай тест и отправь подружкам! 💕",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    text = (f"👭✨ *ТВОЙ ТОП ПОДРУЖЕК* ✨👭\n\n")
    
    keyboard = []
    for i, friend in enumerate(friends, 1):
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = "💕"
        
        name = friend['friend_name'] or 'Подружка'
        username = f"(@{friend['friend_username']})" if friend['friend_username'] else ''
        text += f"{medal} *{name}* {username}\n"
        text += f"   📊 Средний балл: {friend['avg_score']:.0f}%\n"
        text += f"   📝 Прошла тестов: {friend['tests_count']}\n\n"
        
        if has_premium:
            keyboard.append([InlineKeyboardButton(
                f"📊 Ответы {name}", 
                callback_data=f"friend_all_answers_{friend['friend_id']}"
            )])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_stats")])
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, 
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def show_friend_all_answers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    friend_id = int(query.data.split("_")[3])
    
    if not is_premium(user_id):
        await query.message.reply_text(
            "💎 *Только для ПРЕМИУМ!* 💎\n\n"
            "Купи премиум, чтобы видеть детальные ответы подружек!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Купить премиум", callback_data="shop")]])
        )
        return
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT friend_name, friend_username FROM attempts WHERE friend_id = ? LIMIT 1', (friend_id,))
        friend_info = c.fetchone()
    finally:
        conn.close()
    
    friend_name = friend_info['friend_name'] if friend_info else 'Подружка'
    friend_username = f"(@{friend_info['friend_username']})" if friend_info and friend_info['friend_username'] else ''
    
    answers_details = get_friend_answers_details(user_id, friend_id)
    
    if not answers_details:
        await query.message.reply_text("💔 *Нет данных об ответах*", parse_mode=ParseMode.MARKDOWN)
        return
    
    text = (f"📝✨ *ОТВЕТЫ ПОДРУЖКИ* ✨📝\n\n"
            f"👤 *{friend_name}* {friend_username}\n"
            f"📊 *Всего тестов пройдено:* {len(answers_details)}\n\n")
    
    for test in answers_details[:3]:
        text += f"📋 *Тест:* {test['title']}\n"
        text += f"🎯 *Результат:* {test['score']:.0f}%\n"
        text += f"📅 *Дата:* {test['completed_at'][:10]}\n\n"
        
        for i, q in enumerate(test['questions'][:5]):
            if i < len(test['answers']) and test['answers'][i] < len(test['options'][i]):
                user_answer = test['options'][i][test['answers'][i]]
                is_correct = test['answers'][i] == test['correct_answers'][i]
                mark = "✅" if is_correct else "❌"
                text += f"{mark} *Вопрос {i+1}:* {user_answer}\n"
            else:
                text += f"❓ *Вопрос {i+1}:* нет ответа\n"
        
        if len(test['questions']) > 5:
            text += f"... и ещё {len(test['questions'])-5} вопросов\n"
        text += "\n" + "─" * 30 + "\n\n"
        
        if len(text) > 3500:
            text += "\n... и ещё результаты (слишком много)"
            break
    
    if len(answers_details) > 3:
        text += f"\n✨ *И ещё {len(answers_details)-3} тестов*\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад к подружкам", callback_data="top_friends")]]
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def back_to_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    points = user.get('total_points', 0) if user else 0
    rank = get_rank(points)
    streak = user.get('daily_streak', 0) if user else 0
    created = user.get('tests_created', 0) if user else 0
    referrals = user.get('referral_count', 0) if user else 0
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
    
    premium_text = ""
    if has_premium:
        expiry = get_premium_expiry(user_id)
        if expiry:
            premium_text = f"\n💎 *Премиум до:* {expiry.strftime('%d.%m.%Y')}"
    
    text = (f"📊✨ *ТВОЯ СТАТИСТИКА* ✨📊\n\n"
            f"👤 *Имя:* {user.get('first_name', 'Подружка') if user else 'Подружка'}\n"
            f"🏆 *Ранг:* {rank['name']}\n"
            f"⭐ *Очки:* {points}\n"
            f"📊 *Место:* {rating}\n"
            f"🔥 *Серия:* {streak} дней\n"
            f"🎯 *До след. ранга:* {get_next_level_points(points)} очков{premium_text}\n\n"
            f"📝 *Создано тестов:* {created}\n"
            f"🎯 *Пройдено тестов:* {passed}\n"
            f"👭 *Приглашено подруг:* {referrals}\n"
            f"📦 *Сохранено тестов:* {saved_count}\n"
            f"🎁 *Доступно:* {tests_text}")
    
    keyboard = [
        [InlineKeyboardButton("🏆 Топ-10 рейтинга", callback_data="top_rating")],
        [InlineKeyboardButton("👭 Топ подруг", callback_data="top_friends")]
    ]
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def daily_bonus_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = get_daily_bonus(user_id)
    
    if result[0] is None:
        streak = result[1]
        next_reward = ""
        for s in STREAK_REWARDS:
            if s > streak:
                next_reward = f"\n\n🎯 *Через {s - streak} дня получишь:* {STREAK_REWARDS[s]['description']}"
                break
        
        await update.message.reply_text(
            f"🎀✨ *БОНУСИК* ✨🎀\n\n"
            f"🌸 *Ты уже забирала бонус сегодня!* 🌸\n"
            f"🔥 *Серия:* {streak} дней{next_reward}\n\n"
            f"⏰ *Возвращайся завтра за новой порцией!* 💕",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    bonus, streak, reward_info = result
    
    text = (f"🎀✨ *БОНУС ПОЛУЧЕН!* ✨🎀\n\n"
            f"⭐ *+{bonus} очков* ⭐\n"
            f"🔥 *Серия:* {streak} дней\n\n")
    
    if reward_info:
        text += f"🎉✨ *ОСОБАЯ НАГРАДА!* ✨🎉\n"
        text += f"🎁 *Ты получила:* {reward_info}\n\n"
    
    text += f"💫 *Завтра будет новая награда! Приходи снова!* 💫"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def invite_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        return
    
    code = user.get('referral_code')
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    stats = get_referral_stats(user_id)
    
    text = (f"👭✨ *ПРИГЛАСИ ПОДРУЖКУ* ✨👭\n\n"
            f"🌸 *Отправь ссылку и получи +1 тестик!* 🌸\n\n"
            f"🔗 *Твоя пригласительная ссылка:*\n"
            f"[👉 НАЖМИ, ЧТОБЫ СКОПИРОВАТЬ 👈](https://t.me/share/url?url=https://t.me/{BOT_USERNAME}?start={code})\n\n"
            f"📊 *Твоя статистика:*\n"
            f"   👭 *Приглашено:* {stats['total']}\n"
            f"   ⭐ *Активных:* {stats['active']}\n\n"
            f"💡 *Как это работает:*\n"
            f"1️⃣ Отправь ссылку подружке\n"
            f"2️⃣ Она начинает играть\n"
            f"3️⃣ Ты получаешь +1 тестик!\n\n"
            f"✨ *Чем больше подруг, тем веселее!* ✨")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Скопировать ссылку", callback_data="copy_link"),
         InlineKeyboardButton("👭 Поделиться", switch_inline_query=f"Привет! 👋\n\nДавай проверим, насколько хорошо мы знаем друг друга! 🎀\n\nПереходи по ссылке и начинай:\n{link}")]
    ])
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard, disable_web_page_preview=False)

async def copy_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if user:
        code = user.get('referral_code')
        link = f"https://t.me/{BOT_USERNAME}?start={code}"
        await query.answer(text=f"🔗 Ссылка скопирована!", show_alert=True)
        await query.message.reply_text(
            f"📋 *Вот твоя пригласительная ссылка:*\n"
            f"`{link}`\n\n"
            f"Отправь её подружке 💕",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await query.answer("❌ Ошибка! Попробуй позже", show_alert=True)

async def shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        msg = update.callback_query.message
    else:
        user_id = update.effective_user.id
        msg = update.message
    
    if not msg:
        return
    
    user = get_user(user_id)
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    saved = get_saved_tests_count(user_id)
    max_saved = MAX_SAVED_PREMIUM if has_premium else MAX_SAVED_FREE
    
    text = (f"🛍️✨ *ПРЕМИУМ ПОДПИСКА* ✨🛍️\n\n"
            f"👑 *Твой статус:* {'💎 ПРЕМИУМ' if has_premium else '🔓 БЕСПЛАТНЫЙ'}\n"
            f"🔢 *Вопросов в тесте:* до {max_q}\n"
            f"📦 *Сохранено тестов:* {saved}/{max_saved}\n\n"
            f"💎 *ЧТО ДАЁТ ПРЕМИУМ?*\n\n"
            f"✅ *До 10 вопросов* в тесте (вместо 5)\n"
            f"✅ *10 крутых тем* (вместо 4)\n"
            f"✅ *До 10 сохранённых* тестов (вместо 3)\n"
            f"✅ *Полная статистика* по тестам\n"
            f"✅ *5 красивых дипломов* на выбор\n"
            f"✅ *Эксклюзивные рамки* и значки\n"
            f"✅ *Бесконечные тесты* — твори сколько хочешь!\n\n"
            f"🎁 *СТОИМОСТЬ ПРЕМИУМ:*\n\n"
            f"• 💎 30 дней — *299 ₽*\n"
            f"• 💎 3 месяца — *699 ₽*\n"
            f"• 💎 ГОД — *1999 ₽*\n\n"
            f"💡 *Совет:* Если ты создаёшь больше 10 тестов в месяц — премиум для тебя! 💡")
    
    await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_shop_keyboard())

async def save_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    test = get_test_by_id(test_id)
    user_id = query.from_user.id
    
    if not test:
        return
    
    if test['creator_id'] == user_id:
        await query.message.reply_text("💔 *Нельзя сохранить свой собственный тестик!* 💔\nОн уже есть в разделе «Мои тесты»", parse_mode=ParseMode.MARKDOWN)
        return
    
    if not can_save_test(user_id):
        has_premium = is_premium(user_id)
        max_saved = MAX_SAVED_PREMIUM if has_premium else MAX_SAVED_FREE
        await query.message.reply_text(
            f"💔 *Лимит сохранённых тестов: {max_saved}!* 💔\n\n"
            f"💎 *Купи премиум для {MAX_SAVED_PREMIUM} сохранённых тестов!*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if save_test(user_id, test_id):
        await query.message.reply_text("⭐✨ *Тестик сохранён в «Мои тесты»!* ✨⭐", parse_mode=ParseMode.MARKDOWN)
    else:
        await query.message.reply_text("💔 *Этот тестик уже сохранён!* 💔", parse_mode=ParseMode.MARKDOWN)

async def unsave_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    if unsave_test(query.from_user.id, test_id):
        await query.message.reply_text("🗑️ *Тестик удалён из сохранённых* 🗑️", parse_mode=ParseMode.MARKDOWN)
    else:
        await query.message.reply_text("💔 *Ошибка при удалении* 💔", parse_mode=ParseMode.MARKDOWN)

async def confirm_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    test = get_test_by_id(test_id)
    
    if test:
        await query.message.edit_text(
            f"🎉✨ *ТЕСТИК ГОТОВ К ОТПРАВКЕ!* ✨🎉\n\n"
            f"📝 *{test['title']}*\n\n"
            f"💖 *Поделись с подружкой через кнопку ниже!* 💖",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_share_confirm_keyboard(test_id)
        )

async def cancel_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("❌ *Отменено* ❌", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def back_to_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("✨ *Выбери тему для вопросов:* ✨", parse_mode=ParseMode.MARKDOWN, 
                                  reply_markup=get_question_groups_keyboard(query.from_user.id))

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
        await query.message.reply_text("💔 *Тестик не найден* 💔", parse_mode=ParseMode.MARKDOWN)
        return
    
    if not can_attempt_test(test_id, user_id):
        await query.message.reply_text(
            "💔 *Ты уже проходила этот тестик!* 💔\n\n"
            "Каждую подружку можно проверить только один раз ✨",
            parse_mode=ParseMode.MARKDOWN
        )
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
    text = (f"{WOW_EMOJIS['star']} *Вопрос {current}/{total}* {WOW_EMOJIS['star']}\n\n"
            f"{question}\n\n"
            f"👇 *Выбери ответ:* 👇")
    
    keyboard = []
    row = []
    for i, opt in enumerate(options):
        row.append(InlineKeyboardButton(opt[:30], callback_data=f"answer_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

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
    
    score = 0
    for i, ans in enumerate(answers):
        if i < len(correct) and ans == correct[i]:
            score += 100 / len(test['questions'])
    
    await save_attempt(data['test_id'], user.id, user.first_name, user.username, answers, score, context.bot)
    
    diplom_key = get_selected_diplom(test['creator_id'])
    diplom = DIPLOMS.get(diplom_key, DIPLOMS['free'])
    status = get_friendship_status(score)
    
    text = (f"{diplom['border']}\n"
            f"{diplom['icon']} *{diplom['name']}* {diplom['icon']}\n"
            f"{diplom['border']}\n\n"
            f"👤 *Подружка:* {user.first_name or 'Участница'}\n"
            f"📝 *Тест:* {test['title']}\n"
            f"🎯 *Результат:* {score:.0f}%\n"
            f"{status}\n\n"
            f"💗 *+{int(score)} очков*\n"
            f"{diplom['text']}\n\n"
            f"{diplom['border']}\n"
            f"✨ *СПАСИБО ЗА ПРОХОЖДЕНИЕ!* ✨\n"
            f"{diplom['border']}")
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

# === АДМИН-КОМАНДЫ ===
async def is_admin(user_id):
    return user_id == ADMIN_ID

async def admin_set_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("📖 `/setpremium @username [дни]`\nПример: /setpremium @anna 30", parse_mode=ParseMode.MARKDOWN)
        return
    
    target = context.args[0].lstrip('@')
    days = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 30
    
    conn = get_db()
    try:
        c = conn.cursor()
        if target.isdigit():
            c.execute('SELECT first_name FROM users WHERE user_id = ?', (int(target),))
        else:
            c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
        row = c.fetchone()
        
        if not row:
            await update.message.reply_text(f"❌ Пользователь {target} не найден")
            return
        
        user_id = row['user_id'] if 'user_id' in row.keys() else int(target)
        name = row['first_name'] if 'first_name' in row.keys() else target
        
        until = (datetime.now() + timedelta(days=days)).isoformat()
        c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (until, user_id))
        conn.commit()
        await update.message.reply_text(f"✅ *{name}* получил премиум на {days} дней! 🎉", parse_mode=ParseMode.MARKDOWN)
    finally:
        conn.close()

async def admin_remove_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("📖 `/removepremium @username`", parse_mode=ParseMode.MARKDOWN)
        return
    
    target = context.args[0].lstrip('@')
    conn = get_db()
    try:
        c = conn.cursor()
        if target.isdigit():
            c.execute('SELECT first_name FROM users WHERE user_id = ?', (int(target),))
        else:
            c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
        row = c.fetchone()
        
        if not row:
            await update.message.reply_text(f"❌ Пользователь {target} не найден")
            return
        
        user_id = row['user_id'] if 'user_id' in row.keys() else int(target)
        name = row['first_name'] if 'first_name' in row.keys() else target
        
        c.execute('UPDATE users SET unlimited_until = NULL WHERE user_id = ?', (user_id,))
        conn.commit()
        await update.message.reply_text(f"✅ У *{name}* удалён премиум", parse_mode=ParseMode.MARKDOWN)
    finally:
        conn.close()

async def admin_add_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("📖 `/addtests @username кол-во`\nПример: /addtests @anna 5", parse_mode=ParseMode.MARKDOWN)
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
            c.execute('SELECT first_name FROM users WHERE user_id = ?', (int(target),))
        else:
            c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
        row = c.fetchone()
        
        if not row:
            await update.message.reply_text(f"❌ Пользователь {target} не найден")
            return
        
        user_id = row['user_id'] if 'user_id' in row.keys() else int(target)
        name = row['first_name'] if 'first_name' in row.keys() else target
        
        add_tests(user_id, count)
        await update.message.reply_text(f"✅ *{name}* +{count} тестов! 🎉", parse_mode=ParseMode.MARKDOWN)
    finally:
        conn.close()

async def admin_add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("📖 `/addpoints @username кол-во`\nПример: /addpoints @anna 100", parse_mode=ParseMode.MARKDOWN)
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
            c.execute('SELECT first_name FROM users WHERE user_id = ?', (int(target),))
        else:
            c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
        row = c.fetchone()
        
        if not row:
            await update.message.reply_text(f"❌ Пользователь {target} не найден")
            return
        
        user_id = row['user_id'] if 'user_id' in row.keys() else int(target)
        name = row['first_name'] if 'first_name' in row.keys() else target
        
        add_points(user_id, count)
        await update.message.reply_text(f"✅ *{name}* +{count} очков! ⭐", parse_mode=ParseMode.MARKDOWN)
    finally:
        conn.close()

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT user_id, first_name, username, total_points, unlimited_until FROM users ORDER BY total_points DESC LIMIT 30')
        rows = c.fetchall()
        
        text = "👥 *ПОЛЬЗОВАТЕЛИ БОТА* 👥\n\n"
        for i, row in enumerate(rows, 1):
            name = row['first_name'] or f"ID {row['user_id']}"
            username = f"(@{row['username']})" if row['username'] else ''
            premium = "💎" if row['unlimited_until'] and datetime.fromisoformat(row['unlimited_until']) > datetime.now() else ""
            text += f"{i}. *{name}* {username} — {row['total_points']}⭐ {premium}\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    finally:
        conn.close()

async def promocode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🎁 *Активация промокода*\n\n"
            "Использование: `/promocode КОД`\n\n"
            "Получить промокоды можно в наших соцсетях и у блогеров! 🌸",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    code = context.args[0].upper()
    await update.message.reply_text(f"✅ *Промокод {code} активирован!* +5 тестов в подарок! 🎉", parse_mode=ParseMode.MARKDOWN)
    add_tests(update.effective_user.id, 5)

# === ОБРАБОТЧИКИ ===
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📝 Создать тест":
        await create_test_start(update, context)
    elif text == "👑 Мои тесты":
        await my_tests_handler(update, context)
    elif text == "📊 Статистика":
        await stats_handler(update, context)
    elif text == "🎁 Задания и бонусы":
        await daily_tasks_handler(update, context)
        await daily_bonus_handler(update, context)
    elif text == "👭 Пригласить":
        await invite_handler(update, context)
    elif text == "🛍️ Магазин":
        await shop_handler(update, context)
    elif text == "➕ Добавить вариант":
        await add_option(update, context)
    elif text == "✅ Готово":
        await finish_options(update, context)
    elif text == "🔙 Назад":
        await back_to_questions(update, context)
    else:
        data = context.user_data.get('create_test')
        if data:
            await handle_create_test(update, context)
        else:
            await update.message.reply_text("🌸 *Используй кнопки меню!* 🌸", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    logger.info(f"Callback: {data}")
    
    # Навигация по моим тестам
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
    
    # Создание теста
    elif data.startswith("group_"):
        await select_question_group(update, context)
    elif data.startswith("premium_group_"):
        await premium_group_click(update, context)
    elif data == "next_question":
        await next_question(update, context)
    elif data == "select_question":
        await select_current_question(update, context)
    elif data == "back_to_groups":
        await back_to_groups_handler(update, context)
    elif data.startswith("correct_"):
        await select_correct_answer(update, context)
    elif data.startswith("greeting_"):
        await ask_for_greeting(update, context)
    
    # Тесты
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
    
    # Статистика
    elif data == "top_rating":
        await top_rating_handler(update, context)
    elif data == "top_friends":
        await top_friends_handler(update, context)
    elif data.startswith("friend_all_answers_"):
        await show_friend_all_answers(update, context)
    elif data == "back_to_stats":
        await back_to_stats(update, context)
    
    # Магазин
    elif data == "open_shop":
        await open_shop_handler(update, context)
    elif data.startswith("buy_"):
        await query.message.reply_text("💎 *Для оплаты напишите @LavaTopBot* 💎", parse_mode=ParseMode.MARKDOWN)
    elif data == "shop":
        await shop_handler(update, context)
    elif data == "copy_link":
        await copy_link_handler(update, context)
    
    else:
        logger.warning(f"Неизвестный callback: {data}")
    
    await query.answer()

# === MAIN ===
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Пользовательские команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("promocode", promocode_handler))
    
    # Админ-команды
    app.add_handler(CommandHandler("setpremium", admin_set_premium))
    app.add_handler(CommandHandler("removepremium", admin_remove_premium))
    app.add_handler(CommandHandler("addtests", admin_add_tests))
    app.add_handler(CommandHandler("addpoints", admin_add_points))
    app.add_handler(CommandHandler("users", admin_users))
    
    # Кнопки главного меню
    app.add_handler(MessageHandler(filters.Regex("^📝 Создать тест$"), create_test_start))
    app.add_handler(MessageHandler(filters.Regex("^👑 Мои тесты$"), my_tests_handler))
    app.add_handler(MessageHandler(filters.Regex("^📊 Статистика$"), stats_handler))
    app.add_handler(MessageHandler(filters.Regex("^🎁 Задания и бонусы$"), handle_buttons))
    app.add_handler(MessageHandler(filters.Regex("^👭 Пригласить$"), invite_handler))
    app.add_handler(MessageHandler(filters.Regex("^🛍️ Магазин$"), shop_handler))
    
    # Кнопки создания теста
    app.add_handler(MessageHandler(filters.Regex("^➕ Добавить вариант$"), add_option))
    app.add_handler(MessageHandler(filters.Regex("^✅ Готово$"), finish_options))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Назад$"), back_to_questions))
    
    # Общие обработчики
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.Regex("^❌ Отмена$"), cancel_creation))
    app.add_handler(MessageHandler(filters.VOICE, save_greeting))
    app.add_handler(MessageHandler(filters.VIDEO, save_greeting))
    
    # Callback обработчик
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🚀✨ Бот успешно запущен! ВСЁ ИСПРАВЛЕНО! ✨🚀")
    app.run_polling()

if __name__ == "__main__":
    main()
