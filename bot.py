#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бот для создания тестов для подруг @PodrugaTestBot
Версия: 53.0 - ДЕВЧАЧЬЯ + ИСПРАВЛЕНИЯ
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
SAVED_TESTS_FREE = 3
SAVED_TESTS_PREMIUM = 10
ADMIN_ID = 710623393

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === ГРУППЫ ВОПРОСОВ (ДЕВЧАЧЬИ, КОРОТКИЕ) ===
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
        "Как долго мы дружим?",
        "Где познакомились? 🏫",
        "Мой любимый цвет? 🎨",
        "Моя любимая еда? 🍕",
        "Моё хобби? 💃",
        "Мой любимый сериал? 📺",
        "Что меня бесит? 😤",
        "Моя мечта? 🌟"
    ],
    'love': [
        "Мой тип парня? 💘",
        "Что важно в отношениях? 💕",
        "Как я показываю симпатию? 😳",
        "Идеальное свидание? 🌹",
        "Что меня влюбляет? ✨",
        "Какой подарок хочу? 🎁",
        "Что бесит в парнях? 🙄",
        "Мой краш? 📱"
    ],
    'humor': [
        "Что делаю, когда опаздываю? 🏃‍♀️",
        "Моя странная привычка? 🤪",
        "Как я танцую? 💃",
        "Что ем ночью? 🍪",
        "Как я вру? 👀",
        "Что делаю при виде паука? 😱",
        "Мой смешной страх? 🐌",
        "Моя коронная фраза? 💬"
    ],
    'myself': [
        "Моя суперсила? 💪",
        "Что нужно для счастья? 🦄",
        "Как справляюсь со стрессом? 🎧",
        "Кем хочу стать? 👩‍🎤",
        "Что люблю в себе? 💅",
        "Мой главный страх? 😨",
        "Моя фишка? ✨",
        "Что вдохновляет? 🌈"
    ],
    'family': [
        "С кем я близка? 💕",
        "Что люблю делать с семьёй? 🍿",
        "Наша традиция? 🎄",
        "На кого похожа? 👩‍👧",
        "Что бесит в родителях? 😅",
        "Есть ли брат/сестра? 👫",
        "Что ценю в семье? 💖"
    ],
    'school': [
        "Любимый предмет? 📖",
        "Ненавистный урок? 😫",
        "Что делаю на скучных уроках? 📱",
        "С кем сижу за партой? 👯",
        "Как списываю? 🤫",
        "Что ем в столовой? 🍔",
        "Моя училка-краш? 👩‍🏫"
    ],
    'style': [
        "Мой стиль? 👗",
        "Любимый цвет? 🎀",
        "Что никогда не надену? 🙅‍♀️",
        "Мой must-have? 🛍️",
        "Что надеваю на вечеринку? ✨",
        "Любимая обувь? 👟",
        "Мой парфюм? 🌸"
    ],
    'social': [
        "Мой любимый тиктокер? 📱",
        "Что пощу в сторис? 📸",
        "Сколько лайков в среднем? ❤️",
        "Мой любимый фильтр? 🦄",
        "С кем делаю контент? 👯",
        "Мой залипательный контент? 📺"
    ],
    'dreams': [
        "Куда хочу поехать? ✈️",
        "Моя мечта? 🌟",
        "Какую машину хочу? 🚗",
        "Мой идеальный день? ☀️",
        "Что хочу купить? 🛍️",
        "Мой wishlist? 📝"
    ],
    'kpop': [
        "Моя любимая группа? 🎤",
        "Мой биас? 💕",
        "Какой трек залипаю? 🎧",
        "Какой мерч хочу? 💜",
        "С кем из айдолов встретиться? ⭐",
        "Мой любимый танец? 💃"
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
    'complete_test': {'name': '📝 Пройти тест', 'points': 5, 'description': 'Пройди тест от подруги'},
    'send_test': {'name': '📤 Отправить тест', 'points': 10, 'description': 'Отправь тест подруге'},
    'get_result': {'name': '🎯 Получить результат', 'points': 15, 'description': 'Дождись, пока подруга пройдёт тест'},
    'create_test': {'name': '✨ Создать тест', 'points': 20, 'description': 'Создай новый тест о себе'},
    'invite_friend': {'name': '👭 Пригласить подругу', 'points': 30, 'description': 'Пригласи подругу по ссылке'}
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
    7: {'points': 50, 'tests': 1, 'premium_days': 0},
    14: {'points': 100, 'tests': 2, 'premium_days': 0},
    30: {'points': 300, 'tests': 0, 'premium_days': 7},
    100: {'points': 1000, 'tests': 0, 'premium_days': 30}
}

DIPLOMS = {
    'free': {
        'name': '📜 Классика',
        'icon': '📜',
        'border': '🌸🌸🌸',
        'text': 'Ты классная! Так держать! 💕'
    },
    'premium_1': {
        'name': '👑 КОРОЛЕВА',
        'icon': '👑',
        'border': '✨👑✨',
        'text': 'Ты настоящая королева дружбы! 👸'
    },
    'premium_2': {
        'name': '💎 БРИЛЛИАНТ',
        'icon': '💎',
        'border': '✨💎✨',
        'text': 'Ты сияешь! Лучшая подруга! ✨'
    },
    'premium_3': {
        'name': '🌟 ЗВЕЗДА',
        'icon': '🌟',
        'border': '✨🌟✨',
        'text': 'Ты звезда! 🌟'
    },
    'premium_4': {
        'name': '🦄 ЕДИНОРОГ',
        'icon': '🦄',
        'border': '✨🦄✨',
        'text': 'Ты уникальна! 🦄'
    },
    'premium_5': {
        'name': '🌸 ЛАВАНДА',
        'icon': '🌸',
        'border': '✨🌸✨',
        'text': 'Ты нежная и красивая! 💗'
    }
}

WOW_EMOJIS = {
    'start': '🌸', 'success': '🎉', 'error': '💔',
    'test': '📝', 'friend': '👯', 'crown': '👑',
    'star': '⭐', 'heart': '💗', 'daily': '🎁',
    'achievement': '🏆', 'shop': '🛍️', 'money': '💰',
    'top': '🏆', 'back': '🔙', 'stats': '📊', 'cancel': '❌',
    'favorite': '💖', 'diplom': '🎓', 'task': '📋', 'level': '📈'
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            attempts_count INTEGER DEFAULT 0
        )''')
        
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

# === КЭШ ДЛЯ ТЕСТОВ ===
_test_cache = {}
_CACHE_TTL = 300

def get_test_by_id(test_id):
    now = datetime.now().timestamp()
    if test_id in _test_cache:
        test, timestamp = _test_cache[test_id]
        if now - timestamp < _CACHE_TTL:
            return test.copy() if test else None
    
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
            _test_cache[test_id] = (test.copy(), now)
            return test
        return None
    finally:
        conn.close()

def invalidate_test_cache(test_id):
    if test_id in _test_cache:
        del _test_cache[test_id]

# === ФУНКЦИИ ПОЛЬЗОВАТЕЛЕЙ ===
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
                return 999
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
                return None, streak
            
            yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
            if last_bonus == yesterday:
                streak += 1
            else:
                streak = 1
            
            bonus = DAILY_BONUS_POINTS
            
            if streak in STREAK_REWARDS:
                reward = STREAK_REWARDS[streak]
                bonus += reward['points']
                if reward['tests'] > 0:
                    add_tests(user_id, reward['tests'])
                if reward['premium_days'] > 0:
                    until = (datetime.now() + timedelta(days=reward['premium_days'])).isoformat()
                    c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (until, user_id))
            
            c.execute('UPDATE users SET total_points = total_points + ?, last_daily = ?, daily_streak = ? WHERE user_id = ?',
                      (bonus, today, streak, user_id))
            conn.commit()
            return bonus, streak
        else:
            c.execute('UPDATE users SET total_points = total_points + ?, last_daily = ?, daily_streak = 1 WHERE user_id = ?',
                      (DAILY_BONUS_POINTS, today, user_id))
            conn.commit()
            return DAILY_BONUS_POINTS, 1
    finally:
        conn.close()

def create_test(creator_id, creator_name, creator_username, title, questions, options, correct_answers, 
                greeting_type=None, greeting_file_id=None):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''INSERT INTO tests 
            (creator_id, creator_name, creator_username, title, questions, options, correct_answers, greeting_type, greeting_file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (creator_id, creator_name, creator_username, title, json.dumps(questions), 
             json.dumps(options), json.dumps(correct_answers), greeting_type, greeting_file_id))
        test_id = c.lastrowid
        c.execute('UPDATE users SET tests_created = tests_created + 1 WHERE user_id = ?', (creator_id,))
        conn.commit()
        invalidate_test_cache(test_id)
        return test_id
    except Exception as e:
        logger.error(f"Ошибка создания теста: {e}")
        return None
    finally:
        conn.close()

def get_user_created_tests(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT id, title, attempts_count, created_at FROM tests WHERE creator_id = ? ORDER BY created_at DESC', (user_id,))
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def save_test(user_id, test_id):
    conn = get_db()
    try:
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
        c.execute('''SELECT t.id, t.title, t.creator_name, t.creator_id
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

def save_attempt(test_id, friend_id, friend_name, friend_username, answers, score):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''INSERT INTO attempts (test_id, friend_id, friend_name, friend_username, answers, score)
            VALUES (?, ?, ?, ?, ?, ?)''', 
            (test_id, friend_id, friend_name, friend_username, json.dumps(answers), score))
        c.execute('UPDATE tests SET attempts_count = attempts_count + 1 WHERE id = ?', (test_id,))
        conn.commit()
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
        c.execute('INSERT INTO achievements (user_id, achievement_type) VALUES (?, ?)', (user_id, achievement_type))
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
        c.execute('''INSERT INTO daily_tasks (user_id, task_date, task_type, completed) 
                     VALUES (?, ?, ?, 1) 
                     ON CONFLICT(user_id, task_date, task_type) DO UPDATE SET completed = 1''',
                  (user_id, today, task_type))
        conn.commit()
        if task_type in DAILY_TASKS:
            add_points(user_id, DAILY_TASKS[task_type]['points'])
        return True
    except:
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
                'joined_at': row['created_at'][:10],
                'tests_passed': row['tests_passed']
            })
        
        return {'total': total, 'active': active, 'referrals': referrals}
    finally:
        conn.close()

def get_top_users(limit=20):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT user_id, first_name, username, total_points FROM users ORDER BY total_points DESC LIMIT ?', (limit,))
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_friendship_status(score):
    if score >= 95: return "👯‍♀️ СЁСТРЫ НАВЕК"
    if score >= 85: return "💕 ЛУЧШИЕ ПОДРУГИ"
    if score >= 75: return "🌸 НАСТОЯЩИЕ ПОДРУГИ"
    if score >= 65: return "💗 ХОРОШИЕ ПОДРУГИ"
    if score >= 55: return "👭 ПОДРУЖКИ"
    if score >= 45: return "👋 ПРИЯТЕЛЬНИЦЫ"
    if score >= 35: return "🤔 ЗНАКОМЫЕ"
    if score >= 25: return "😅 ЕЩЁ УЧИМСЯ"
    if score >= 15: return "👀 ПРИСМАТРИВАЮСЬ"
    return "❓ КТО ТЫ?"

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
        [KeyboardButton("📊 Статистика"), KeyboardButton("🎁 Бонус")],
        [KeyboardButton("📋 Задания"), KeyboardButton("🏆 Достижения")],
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
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_groups")]
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
        [InlineKeyboardButton("💎 Премиум ГОД — 1999 ₽", callback_data="buy_premium_year")],
        [InlineKeyboardButton("🛍️ Магазин", callback_data="premium_shop")]
    ])

def get_premium_shop_keyboard():
    keyboard = []
    for key, item in PREMIUM_SHOP_ITEMS.items():
        keyboard.append([InlineKeyboardButton(f"{item['icon']} {item['name']} — {item['price']} ₽", callback_data=f"buy_item_{key}")])
    return InlineKeyboardMarkup(keyboard)

def get_share_confirm_keyboard(test_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Отправить", callback_data=f"confirm_share_{test_id}"),
         InlineKeyboardButton("❌ Отмена", callback_data="cancel_share")],
        [InlineKeyboardButton("👭 Поделиться", 
            switch_inline_query=f"🌸 Твоя подруга приглашает пройти тест!\n\n📝 Узнай, насколько хорошо ты её знаешь!\n\n👉 https://t.me/{BOT_USERNAME}?start=test_{test_id}")]
    ])

def get_start_test_keyboard(test_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 Начать", callback_data=f"start_test_{test_id}"),
        InlineKeyboardButton("⭐ Сохранить", callback_data=f"save_test_{test_id}")
    ]])

def get_my_tests_keyboard(has_created, has_saved):
    keyboard = []
    if has_created:
        keyboard.append([InlineKeyboardButton("📝 Мои тесты", callback_data="show_created_tests")])
    if has_saved:
        keyboard.append([InlineKeyboardButton("⭐ Сохранённые", callback_data="show_saved_tests")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_paginated_tests_keyboard(tests, page, prefix):
    keyboard = []
    start = page * 5
    end = start + 5
    for test in tests[start:end]:
        keyboard.append([InlineKeyboardButton(f"📝 {test['title'][:25]}", callback_data=f"{prefix}_test_{test['id']}")])
    
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"{prefix}_page_{page-1}"))
    if end < len(tests):
        nav.append(InlineKeyboardButton("▶️", callback_data=f"{prefix}_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_my_tests")])
    return InlineKeyboardMarkup(keyboard)

def get_test_action_keyboard(test_id, is_owner=False, is_saved=False):
    keyboard = []
    if not is_owner:
        keyboard.append([InlineKeyboardButton("🎮 Пройти", callback_data=f"start_test_{test_id}")])
        if not is_saved:
            keyboard.append([InlineKeyboardButton("⭐ Сохранить", callback_data=f"save_test_{test_id}")])
        else:
            keyboard.append([InlineKeyboardButton("🗑️ Удалить", callback_data=f"unsave_test_{test_id}")])
    keyboard.append([InlineKeyboardButton("📤 Поделиться", callback_data=f"share_test_{test_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_my_tests")])
    return InlineKeyboardMarkup(keyboard)

# === ОСНОВНЫЕ ХЕНДЛЕРЫ ===
async def send_referral_notification(bot, referrer_id, new_user_name):
    try:
        referrer = get_user(referrer_id)
        if not referrer:
            return
        stats = get_referral_stats(referrer_id)
        
        text = (f"🌸 *НОВАЯ ПОДРУГА!* 🌸\n\n"
                f"💕 *{new_user_name}* перешла по твоей ссылке!\n\n"
                f"🎁 Ты получила *+1 тест*!\n"
                f"👭 Всего подруг: {stats['total']}\n\n"
                f"✨ Продолжай приглашать! ✨")
        
        await bot.send_message(chat_id=referrer_id, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Ошибка уведомления: {e}")

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
            await send_referral_notification(bot, referred_by, user.first_name or f"ID {user.id}")
            await apply_referral_bonus(referred_by, user.id)
    else:
        update_user(user.id, user.username, user.first_name)
    
    if test_id:
        test = get_test_by_id(test_id)
        if test:
            creator = get_user(test['creator_id'])
            creator_name = creator.get('first_name', 'Подруга') if creator else 'Подруга'
            text = (f"🌸 Привет, {user.first_name or 'подружка'}! 🌸\n\n"
                    f"💕 {creator_name} приглашает тебя пройти тест!\n\n"
                    f"📝 {test['title']}\n\n"
                    f"👇 Нажми «Начать»")
            await update.message.reply_text(text, reply_markup=get_start_test_keyboard(test_id))
            return
    
    user_data = get_user(user.id)
    points = user_data.get('total_points', 0) if user_data else 0
    rank = get_rank(points)
    tests = get_available_tests(user.id)
    premium = "💎" if is_premium(user.id) else "🔓"
    
    text = (f"{WOW_EMOJIS['start']} Привет, {user.first_name or 'подружка'}! {WOW_EMOJIS['start']}\n\n"
            f"🎀 Статус: {premium}\n"
            f"🎁 Тестов: {tests}\n"
            f"⭐ Очков: {points}\n"
            f"🏆 Ранг: {rank['name']}\n\n"
            f"💫 Создай тест о себе и отправь подруге!\n\n"
            f"👇 Выбирай кнопку 👇")
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())

async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    available = get_available_tests(user_id)
    
    if available <= 0:
        await update.message.reply_text(
            f"💔 Ой, тесты закончились!\n\n"
            f"🎁 Забери бонус или пригласи подругу!\n"
            f"💎 Или купи премиум 💎",
            reply_markup=get_main_keyboard()
        )
        return
    
    context.user_data['create_test'] = {
        'step': 'title',
        'questions_data': []
    }
    
    await update.message.reply_text(
        f"✨ СОЗДАЁМ ТЕСТИК ✨\n\n"
        f"📦 Осталось: {available}\n\n"
        f"🌸 Придумай название (например: «Как ты меня знаешь?»):\n\n"
        f"❌ Отмена",
        reply_markup=get_cancel_keyboard()
    )

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'create_test' in context.user_data:
        del context.user_data['create_test']
    await update.message.reply_text("❌ Отменено", reply_markup=get_main_keyboard())

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
            await update.message.reply_text("✨ Выбери тему:", reply_markup=get_question_groups_keyboard(user_id))
        elif data.get('step') == 'collecting_options':
            data['step'] = 'selecting_question'
            await show_current_question(update, context)
        return
    
    step = data.get('step')
    
    if step == 'title':
        if len(text.strip()) < 3:
            await update.message.reply_text("⚠️ Минимум 3 символа:")
            return
        data['title'] = text.strip()
        data['step'] = 'group'
        user_id = update.effective_user.id
        await update.message.reply_text("✨ Выбери тему:", reply_markup=get_question_groups_keyboard(user_id))
    
    elif step == 'waiting_question_count':
        try:
            count = int(text.strip())
            user_id = update.effective_user.id
            has_premium = is_premium(user_id)
            max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
            
            if count < 2 or count > max_q:
                await update.message.reply_text(f"⚠️ От 2 до {max_q}:")
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
            await update.message.reply_text("⚠️ Напиши число:")
    
    elif step == 'collecting_options' and data.get('waiting_for_option'):
        option_text = text.strip()
        if option_text:
            if len(option_text) > 100:
                await update.message.reply_text("⚠️ Слишком длинно:")
                return
            data['current_options'].append(option_text)
            data['waiting_for_option'] = False
            
            await update.message.reply_text(
                f"✅ Вариант {len(data['current_options'])} добавлен!\n\n"
                f"📋 Варианты:\n" + "\n".join([f"{i+1}. {o}" for i, o in enumerate(data['current_options'])]),
                reply_markup=get_options_keyboard()
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
        f"📝 Вопрос {data['current_q'] + 1}/{data['total_q']}\n\n{question_text}",
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
        f"📝 Вопрос {data['current_q'] + 1}/{data['total_q']}\n\n{data['current_question_text']}",
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
        f"📝 {data['current_question_text']}\n\n"
        f"✏️ Напиши вариант №1:",
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
    
    await query.message.reply_text(
        f"✨ Сколько вопросов? (2-{max_q}):",
        reply_markup=get_back_keyboard()
    )

async def premium_group_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        f"💔 Эта тема только в премиум!\n\n"
        f"🌟 Купи премиум в магазине!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Магазин", callback_data="open_shop")]])
    )

async def add_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data or data.get('step') != 'collecting_options':
        return
    
    if len(data['current_options']) >= MAX_OPTIONS:
        await update.message.reply_text(f"⚠️ Максимум {MAX_OPTIONS} вариантов!", reply_markup=get_options_keyboard())
        return
    
    data['waiting_for_option'] = True
    await update.message.reply_text(f"✏️ Вариант {len(data['current_options']) + 1}:", reply_markup=get_cancel_keyboard())

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
        await update.message.reply_text(f"⚠️ Нужно минимум {MIN_OPTIONS} варианта!", reply_markup=get_cancel_keyboard())
        data['waiting_for_option'] = True
        return
    
    data['step'] = 'select_correct'
    
    keyboard = []
    for i, opt in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {opt[:20]}", callback_data=f"correct_{i}")])
    
    await update.message.reply_text(
        f"❓ {data['current_question_text']}\n\n"
        f"👇 Какой вариант правильный?",
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
    
    await query.message.reply_text(f"✅ Вопрос сохранён!")
    
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
        f"📝 Вопрос {data['current_q'] + 1}/{data['total_q']}\n\n{data['current_question_text']}",
        reply_markup=get_question_keyboard()
    )

async def finish_creation(query_or_update, context, user_id):
    data = context.user_data.get('create_test', {})
    if not data:
        return
    
    if not use_attempt(user_id):
        msg = "💔 Не хватает тестов!\n\n🎁 Забери бонус!"
        if hasattr(query_or_update, 'message'):
            await query_or_update.message.reply_text(msg, reply_markup=get_main_keyboard())
        else:
            await query_or_update.message.reply_text(msg, reply_markup=get_main_keyboard())
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
        correct
    )
    
    if test_id:
        text = (f"🎉 ТЕСТ ГОТОВ! 🎉\n\n"
                f"📝 {data['title']}\n"
                f"🔢 {data['total_q']} вопросов\n\n"
                f"👇 Отправь подруге!")
        
        if hasattr(query_or_update, 'message'):
            await query_or_update.message.reply_text(text, reply_markup=get_share_confirm_keyboard(test_id))
        else:
            await query_or_update.message.reply_text(text, reply_markup=get_share_confirm_keyboard(test_id))
    else:
        add_tests(user_id, 1)
        await query_or_update.message.reply_text("💔 Ошибка создания", reply_markup=get_main_keyboard())
    
    del context.user_data['create_test']

# === ОСНОВНЫЕ ХЕНДЛЕРЫ МЕНЮ ===
async def my_tests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    created = get_user_created_tests(user_id)
    saved = get_saved_tests(user_id)
    
    context.user_data['my_tests'] = {'created': created, 'saved': saved, 'page': 0}
    
    text = f"👑 МОИ ТЕСТЫ 👑\n\n"
    if created:
        text += f"📝 Создано: {len(created)}\n"
    if saved:
        text += f"⭐ Сохранено: {len(saved)}\n"
    if not created and not saved:
        text += "У тебя пока нет тестов 🌸"
    
    await update.message.reply_text(text, reply_markup=get_my_tests_keyboard(bool(created), bool(saved)))

async def show_created_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    my_tests = context.user_data.get('my_tests', {})
    tests = my_tests.get('created', [])
    page = my_tests.get('page', 0)
    
    if not tests:
        await query.message.reply_text("📝 У тебя пока нет созданных тестов")
        return
    
    context.user_data['my_tests']['current_list'] = 'created'
    
    text = f"👑 МОИ ТЕСТЫ 👑\n\n"
    start = page * 5
    for test in tests[start:start+5]:
        text += f"📝 {test['title'][:30]}\n   👥 {test['attempts_count']}\n\n"
    
    await query.message.edit_text(text, reply_markup=get_paginated_tests_keyboard(tests, page, "created"))

async def show_saved_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    my_tests = context.user_data.get('my_tests', {})
    tests = my_tests.get('saved', [])
    page = my_tests.get('page', 0)
    
    if not tests:
        await query.message.reply_text("⭐ У тебя пока нет сохранённых тестов")
        return
    
    context.user_data['my_tests']['current_list'] = 'saved'
    
    text = f"⭐ СОХРАНЁННЫЕ ⭐\n\n"
    start = page * 5
    for test in tests[start:start+5]:
        text += f"📝 {test['title'][:30]}\n   👤 {test['creator_name']}\n\n"
    
    await query.message.edit_text(text, reply_markup=get_paginated_tests_keyboard(tests, page, "saved"))

async def show_test_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    prefix = parts[0]
    test_id = int(parts[2])
    
    test = get_test_by_id(test_id)
    if not test:
        await query.message.reply_text("Тест не найден 💔")
        return
    
    user_id = query.from_user.id
    is_owner = test['creator_id'] == user_id
    is_saved = test_id in [t['id'] for t in context.user_data.get('my_tests', {}).get('saved', [])]
    
    text = (f"📝 *{test['title']}*\n\n"
            f"👤 {test['creator_name']}\n"
            f"👥 Прошло: {test['attempts_count']}\n")
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, 
                                  reply_markup=get_test_action_keyboard(test_id, is_owner, is_saved))

async def share_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    test = get_test_by_id(test_id)
    
    if not test:
        await query.message.reply_text("Тест не найден")
        return
    
    user_id = query.from_user.id
    is_owner = test['creator_id'] == user_id
    
    if not is_owner and not use_attempt(user_id):
        await query.message.reply_text("💔 Не хватает тестов!\n\n🎁 Забери бонус!", reply_markup=get_main_keyboard())
        return
    
    text = f"🎉 Тест готов!\n\n📝 {test['title']}\n\n👇 Отправь подруге!"
    await query.message.edit_text(text, reply_markup=get_share_confirm_keyboard(test_id))
    
    if not is_owner:
        complete_daily_task(user_id, 'send_test')

async def daily_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = get_daily_tasks(user_id)
    
    text = "🎀 ЗАДАНИЯ 🎀\n\n"
    completed = 0
    
    for task in tasks:
        status = "✅" if task['completed'] else "⬜"
        text += f"{status} {task['name']} +{task['points']} ⭐\n"
        if task['completed']:
            completed += 1
    
    text += f"\n📊 Выполнено: {completed}/{len(tasks)}"
    if completed == len(tasks):
        text += "\n\n🎉 Ты супер! Завтра новые! 🌸"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())

async def achievements_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    achievements = get_achievements(user_id)
    
    names = {
        'first_test': '🎯 Первый тест',
        'first_invite': '👭 Первое приглашение',
        'streak_7': '🔥 7 дней',
        'streak_14': '⭐ 14 дней',
        'streak_30': '💎 30 дней',
        'level_500': '📚 Знаток',
        'level_1500': '💎 Бриллиант',
        'level_3500': '👑 Королева',
        'level_7000': '🌟 Звезда',
        'level_15000': '👸 Легенда'
    }
    
    text = "🏆 ДОСТИЖЕНИЯ 🏆\n\n"
    if not achievements:
        text += "Пока нет достижений 🌸"
    else:
        for ach in achievements:
            name = names.get(ach['achievement_type'], ach['achievement_type'])
            text += f"🏆 {name}\n   📅 {ach['achieved_at'][:10]}\n\n"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())

async def rating_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    top = get_top_users(20)
    user = get_user(user_id)
    
    text = "🏆 РЕЙТИНГ 🏆\n\n"
    for i, u in enumerate(top, 1):
        medal = "👑" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
        name = u['first_name'] or f"ID {u['user_id']}"
        text += f"{medal} {i}. {name} — {u['total_points']} ⭐\n"
    
    if user:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) + 1 FROM users WHERE total_points > ?', (user['total_points'],))
        place = c.fetchone()[0]
        conn.close()
        text += f"\n📊 Твоё место: {place}\n⭐ Очков: {user['total_points']}"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())

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
    max_saved = SAVED_TESTS_PREMIUM if has_premium else SAVED_TESTS_FREE
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM attempts WHERE friend_id = ?', (user_id,))
        passed = c.fetchone()[0]
        c.execute('SELECT COUNT(*) + 1 FROM users WHERE total_points > ?', (points,))
        rating = c.fetchone()[0]
    finally:
        conn.close()
    
    text = (f"📊 ТВОЯ СТАТИСТИКА 📊\n\n"
            f"👤 {user.get('first_name', 'Подружка')}\n"
            f"🏆 {rank['name']}\n"
            f"⭐ {points} очков\n"
            f"📊 Место: {rating}\n"
            f"🔥 Серия: {streak} дней\n\n"
            f"📝 Тестов создано: {created}\n"
            f"🎯 Пройдено: {passed}\n"
            f"👭 Приглашено: {referrals}\n"
            f"📦 Сохранено: {saved_count}/{max_saved}\n"
            f"🎁 Тестов доступно: {tests_left}")
    
    keyboard = [
        [InlineKeyboardButton("🏆 Топ подруг", callback_data="top_friends")],
        [InlineKeyboardButton("📈 Рейтинг", callback_data="rating")],
        [InlineKeyboardButton("📊 Статистика тестов", callback_data="detailed_stats")]
    ]
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def detailed_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_premium(query.from_user.id):
        await query.message.reply_text("💎 Только для премиум!", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Купить", callback_data="shop")]]))
        return
    
    user_id = query.from_user.id
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''SELECT t.title, COUNT(a.id) as cnt, AVG(a.score) as avg
                     FROM attempts a JOIN tests t ON a.test_id = t.id
                     WHERE t.creator_id = ? GROUP BY a.test_id''', (user_id,))
        rows = c.fetchall()
    finally:
        conn.close()
    
    if not rows:
        await query.message.reply_text("📊 Статистика пуста")
        return
    
    text = "📊 СТАТИСТИКА ТЕСТОВ 📊\n\n"
    for row in rows[:10]:
        text += f"📝 {row['title'][:25]}\n   👥 {row['cnt']} | 📊 {row['avg']:.0f}%\n\n"
    
    await query.message.reply_text(text)

async def top_friends_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT friend_name, AVG(score) as avg, COUNT(id) as cnt
            FROM attempts WHERE test_id IN (SELECT id FROM tests WHERE creator_id = ?)
            GROUP BY friend_id ORDER BY avg DESC LIMIT 10
        ''', (user_id,))
        rows = c.fetchall()
    finally:
        conn.close()
    
    if not rows:
        await query.message.reply_text("👭 Пока никто не проходил твои тесты\n\nСоздай тест и отправь подругам!")
        return
    
    text = "🏆 ТВОЙ ТОП ПОДРУГ 🏆\n\n"
    for i, row in enumerate(rows, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "💕"
        name = row['friend_name'] or 'Подружка'
        text += f"{medal} {name}\n   📊 {row['avg']:.0f}% | 📝 {row['cnt']}\n\n"
    
    await query.message.reply_text(text)

async def daily_bonus_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = get_daily_bonus(user_id)
    
    if result[0] is None:
        await update.message.reply_text(
            f"🎀 БОНУСИК 🎀\n\n"
            f"Ты уже забирала сегодня!\n"
            f"🔥 Серия: {result[1]} дней\n"
            f"⏰ Загляни завтра! 💕",
            reply_markup=get_main_keyboard()
        )
        return
    
    bonus, streak = result
    text = f"🎀 +{bonus} ОЧКОВ! 🎀\n\n🔥 Серия: {streak} дней"
    
    if streak in STREAK_REWARDS:
        reward = STREAK_REWARDS[streak]
        text += f"\n\n🎉 ОСОБАЯ НАГРАДА!\n"
        if reward['points'] > 0:
            text += f"⭐ +{reward['points']} очков\n"
        if reward['tests'] > 0:
            text += f"📦 +{reward['tests']} тестов\n"
        if reward['premium_days'] > 0:
            text += f"💎 +{reward['premium_days']} дней премиума\n"
    
    await update.message.reply_text(text, reply_markup=get_main_keyboard())

async def invite_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        return
    
    code = user.get('referral_code')
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    stats = get_referral_stats(user_id)
    
    text = (f"👭 ПРИГЛАСИ ПОДРУЖКУ 👭\n\n"
            f"🌸 Отправь ссылку и получи +1 тест!\n\n"
            f"🔗 `{link}`\n\n"
            f"👭 Приглашено: {stats['total']}\n"
            f"⭐ Активных: {stats['active']}\n\n"
            f"💡 Как это работает:\n"
            f"1. Отправь ссылку подруге\n"
            f"2. Она начинает играть\n"
            f"3. Ты получаешь бонус!\n\n"
            f"✨ Вместе веселее! ✨")
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

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
    max_saved = SAVED_TESTS_PREMIUM if has_premium else SAVED_TESTS_FREE
    
    text = (f"🛍️ ПРЕМИУМ 🛍️\n\n"
            f"🔢 Вопросов: до {max_q}\n"
            f"📦 Сохранено: {saved}/{max_saved}\n\n"
            f"💎 ПРЕИМУЩЕСТВА:\n"
            f"✅ До 10 вопросов\n"
            f"✅ 10 тем\n"
            f"✅ До 10 сохранённых\n"
            f"✅ Полная статистика\n"
            f"✅ Красивые дипломы\n"
            f"✅ Эксклюзивные рамки\n"
            f"✅ Безлимит тестов\n\n"
            f"🎁 СТОИМОСТЬ:\n"
            f"• 30 дней — 299 ₽\n"
            f"• 3 месяца — 699 ₽\n"
            f"• ГОД — 1999 ₽")
    
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
        await query.message.reply_text("💔 Нельзя сохранить свой тест!")
        return
    
    has_premium = is_premium(user_id)
    saved = get_saved_tests_count(user_id)
    max_saved = SAVED_TESTS_PREMIUM if has_premium else SAVED_TESTS_FREE
    
    if saved >= max_saved:
        await query.message.reply_text(f"💔 Лимит {max_saved} сохранённых!\n💎 Купи премиум для {SAVED_TESTS_PREMIUM}")
        return
    
    if save_test(user_id, test_id):
        await query.message.reply_text("⭐ Тест сохранён!")
    else:
        await query.message.reply_text("💔 Уже сохранён")

async def unsave_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    if unsave_test(query.from_user.id, test_id):
        await query.message.reply_text("✅ Удалено из сохранённых")
    else:
        await query.message.reply_text("💔 Ошибка")

async def confirm_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    test = get_test_by_id(test_id)
    
    if test:
        await query.message.edit_text(
            f"🎉 Тест готов!\n\n📝 {test['title']}\n\n👇 Отправь подруге!",
            reply_markup=get_share_confirm_keyboard(test_id)
        )

async def cancel_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("❌ Отменено", reply_markup=get_main_keyboard())

async def back_to_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("✨ Выбери тему:", reply_markup=get_question_groups_keyboard(query.from_user.id))

async def open_shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await shop_handler(update, context)

async def premium_shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_premium(query.from_user.id):
        await query.message.reply_text("💎 Только для премиум!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Купить", callback_data="shop")]]))
        return
    
    text = "🛍️ ПРЕМИУМ-МАГАЗИН 🛍️\n\n🖼️ Рамки, дипломы, значки!"
    await query.message.reply_text(text, reply_markup=get_premium_shop_keyboard())

async def buy_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_premium(query.from_user.id):
        await query.message.reply_text("💎 Только для премиум!")
        return
    
    item_key = query.data.split("_")[2]
    if item_key in PREMIUM_SHOP_ITEMS:
        item = PREMIUM_SHOP_ITEMS[item_key]
        await query.message.reply_text(
            f"{item['icon']} {item['name']} — {item['price']} ₽\n\n"
            f"💰 Для оплаты напишите @LavaTopBot"
        )

async def promocode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🎁 Использование: /promocode КОД")
        return
    
    # TODO: реализовать проверку промокодов в БД
    await update.message.reply_text("🎁 Промокод активирован! +5 тестов")

async def start_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.split("_")[2])
    test = get_test_by_id(test_id)
    user_id = query.from_user.id
    
    if not test:
        await query.message.reply_text("Тест не найден 💔")
        return
    
    if not can_attempt_test(test_id, user_id):
        await query.message.reply_text("💔 Ты уже проходила этот тест!")
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
    text = f"⭐ Вопрос {current}/{total} ⭐\n\n📝 {question}"
    
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
    
    score = 0
    for i, ans in enumerate(answers):
        if i < len(correct) and ans == correct[i]:
            score += 100 / len(test['questions'])
    
    save_attempt(data['test_id'], user.id, user.first_name, user.username, answers, score)
    add_points(user.id, int(score))
    
    diplom_key = get_selected_diplom(test['creator_id'])
    diplom = DIPLOMS.get(diplom_key, DIPLOMS['free'])
    status = get_friendship_status(score)
    
    text = (f"{diplom['border']}\n"
            f"{diplom['icon']} {diplom['name']} {diplom['icon']}\n"
            f"{diplom['border']}\n\n"
            f"👤 {user.first_name or 'Подружка'}\n"
            f"📝 {test['title']}\n"
            f"🎯 Результат: {score:.0f}%\n"
            f"{status}\n\n"
            f"💗 +{int(score)} очков\n"
            f"{diplom['text']}\n\n"
            f"{diplom['border']}")
    
    await query.message.reply_text(text, reply_markup=get_main_keyboard())

# === АДМИН-КОМАНДЫ ===
async def is_admin(user_id):
    return user_id == ADMIN_ID

async def admin_set_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("📖 /setpremium @username [дни]")
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
        await update.message.reply_text(f"✅ {name} получил премиум на {days} дней!")
    finally:
        conn.close()

async def admin_remove_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("📖 /removepremium @username")
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
        await update.message.reply_text(f"✅ У {name} удалён премиум")
    finally:
        conn.close()

async def admin_add_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("📖 /addtests @username кол-во")
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
        await update.message.reply_text(f"✅ {name} +{count} тестов")
    finally:
        conn.close()

async def admin_add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("📖 /addpoints @username кол-во")
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
        await update.message.reply_text(f"✅ {name} +{count} очков")
    finally:
        conn.close()

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT user_id, first_name, username, total_points, unlimited_until FROM users ORDER BY total_points DESC LIMIT 20')
        rows = c.fetchall()
        
        text = "👥 ПОЛЬЗОВАТЕЛИ 👥\n\n"
        for i, row in enumerate(rows, 1):
            name = row['first_name'] or f"ID {row['user_id']}"
            premium = "💎" if row['unlimited_until'] and datetime.fromisoformat(row['unlimited_until']) > datetime.now() else ""
            text += f"{i}. {name} — {row['total_points']}⭐ {premium}\n"
        
        await update.message.reply_text(text)
    finally:
        conn.close()

# === ОБРАБОТЧИКИ ===
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📝 Создать тест":
        await create_test_start(update, context)
    elif text == "👑 Мои тесты":
        await my_tests_handler(update, context)
    elif text == "📊 Статистика":
        await stats_handler(update, context)
    elif text == "🎁 Бонус":
        await daily_bonus_handler(update, context)
    elif text == "📋 Задания":
        await daily_tasks_handler(update, context)
    elif text == "🏆 Достижения":
        await achievements_handler(update, context)
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
            await update.message.reply_text("Используй кнопки меню 💕", reply_markup=get_main_keyboard())

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # Навигация
    if data == "show_created_tests":
        await show_created_tests(update, context)
    elif data == "show_saved_tests":
        await show_saved_tests(update, context)
    elif data == "back_to_my_tests":
        await my_tests_handler(update, context)
    elif data == "back_to_main":
        await start(update, context)
    elif data.startswith("created_page_"):
        context.user_data['my_tests']['page'] = int(data.split("_")[2])
        await show_created_tests(update, context)
    elif data.startswith("saved_page_"):
        context.user_data['my_tests']['page'] = int(data.split("_")[2])
        await show_saved_tests(update, context)
    elif data.startswith("created_test_"):
        await show_test_details(update, context)
    elif data.startswith("saved_test_"):
        await show_test_details(update, context)
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
    
    # Тесты
    elif data.startswith("confirm_share_"):
        await confirm_share_handler(update, context)
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
    
    # Магазин
    elif data == "open_shop":
        await open_shop_handler(update, context)
    elif data == "premium_shop":
        await premium_shop_handler(update, context)
    elif data.startswith("buy_item_"):
        await buy_item_handler(update, context)
    elif data.startswith("buy_"):
        await query.message.reply_text("💎 Для оплаты напишите @LavaTopBot")
    elif data == "shop":
        await shop_handler(update, context)
    
    # Статистика
    elif data == "top_friends":
        await top_friends_handler(update, context)
    elif data == "rating":
        await rating_handler(update, context)
    elif data == "detailed_stats":
        await detailed_stats_handler(update, context)
    
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
    
    # Кнопки
    app.add_handler(MessageHandler(filters.Regex("^📝 Создать тест$"), create_test_start))
    app.add_handler(MessageHandler(filters.Regex("^👑 Мои тесты$"), my_tests_handler))
    app.add_handler(MessageHandler(filters.Regex("^📊 Статистика$"), stats_handler))
    app.add_handler(MessageHandler(filters.Regex("^🎁 Бонус$"), daily_bonus_handler))
    app.add_handler(MessageHandler(filters.Regex("^📋 Задания$"), daily_tasks_handler))
    app.add_handler(MessageHandler(filters.Regex("^🏆 Достижения$"), achievements_handler))
    app.add_handler(MessageHandler(filters.Regex("^👭 Пригласить$"), invite_handler))
    app.add_handler(MessageHandler(filters.Regex("^🛍️ Магазин$"), shop_handler))
    
    app.add_handler(MessageHandler(filters.Regex("^➕ Добавить вариант$"), add_option))
    app.add_handler(MessageHandler(filters.Regex("^✅ Готово$"), finish_options))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Назад$"), back_to_questions))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.Regex("^❌ Отмена$"), cancel_creation))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
