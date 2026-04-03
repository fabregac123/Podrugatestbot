#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бот для создания тестов для подруг @PodrugaTestBot
Версия: 52.0 - ФИНАЛЬНАЯ КОМПАКТНАЯ ВЕРСИЯ
"""

import logging
import json
import sqlite3
import random
import os
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

# === ГРУППЫ ВОПРОСОВ ===
FREE_QUESTION_GROUPS = {
    'friendship': '👭 Дружба', 'love': '💖 Любовь',
    'humor': '😂 Юмор', 'myself': '🌸 О себе'
}

PREMIUM_QUESTION_GROUPS = {
    'friendship': '👭 Дружба', 'love': '💖 Любовь', 'humor': '😂 Юмор', 'myself': '🌸 О себе',
    'family': '🏠 Семья', 'school': '📚 Школа', 'travel': '✈️ Путешествия',
    'food': '🍕 Еда', 'style': '👗 Стиль', 'animals': '🐾 Животные'
}

# === ВОПРОСЫ ПО ГРУППАМ ===
QUESTIONS_BY_GROUP = {
    'friendship': [
        "Как долго мы дружим?", "Где мы познакомились?", "Какой мой любимый цвет?",
        "Какая моя любимая еда?", "Какое у меня хобби?", "Какой мой любимый фильм?",
        "Что меня может разозлить?", "Какая у меня мечта?"
    ],
    'love': [
        "Какой тип парня мне нравится?", "Что для меня важно в отношениях?",
        "Как я проявляю симпатию?", "Куда я хочу на свидание?", "Что меня влюбляет?",
        "Какой подарок я хочу получить?", "Как я понимаю, что влюблена?",
        "Что меня раздражает в парнях?"
    ],
    'humor': [
        "Что я делаю, когда опаздываю?", "Какая у меня самая нелепая привычка?",
        "Как я танцую?", "Что я ем, когда никто не видит?", "Как я веду себя, когда вру?",
        "Что я делаю, если увидела таракана?", "Мой самый смешной страх?",
        "Что я говорю, когда просыпаюсь?"
    ],
    'myself': [
        "Какая моя главная черта характера?", "Что меня вдохновляет?", "Какая у меня суперсила?",
        "Что мне нужно для счастья?", "Как я справляюсь со стрессом?", "Кем я хочу стать в будущем?",
        "Что я люблю в себе?", "Мой главный страх?"
    ],
    'family': [
        "Кто мой самый близкий родственник?", "Что я люблю делать с семьей?",
        "Какая у нас семейная традиция?", "На кого я похожа?", "Что меня бесит в родителях?",
        "Как я провожу время с мамой?", "Есть ли у меня брат или сестра?", "Что я ценю в своей семье?"
    ],
    'school': [
        "Мой любимый предмет?", "Какой предмет я ненавижу?", "Что я делаю на скучных уроках?",
        "С кем я сижу за партой?", "Как я списываю?", "Что я ем в столовой?",
        "Что я делаю на перемене?", "Кого я боюсь в школе?"
    ],
    'travel': [
        "Куда я мечтаю поехать?", "Что я беру в поездку?", "Как я добираюсь до места?",
        "Что я делаю в дороге?", "Мой идеальный отдых?", "Где я уже была?",
        "С кем я хочу путешествовать?", "Что я делаю, если потерялась?"
    ],
    'food': [
        "Мое любимое блюдо?", "Что я ненавижу есть?", "Что я умею готовить?",
        "Что я заказываю в кафе?", "Какие сладости я люблю?", "Что я ем на завтрак?",
        "Мое любимое кафе?", "Какую еду я никогда не буду есть?"
    ],
    'style': [
        "Мой любимый цвет в одежде?", "Какой стиль я люблю?", "Что я никогда не надену?",
        "Какой у меня must-have?", "Что я надеваю на вечеринку?", "Какую обувь я предпочитаю?",
        "Что я делаю с волосами?", "Какой парфюм я люблю?"
    ],
    'animals': [
        "Какое мое любимое животное?", "Есть ли у меня домашний питомец?",
        "Какое животное я хотела бы завести?", "Боюсь ли я животных?",
        "Люблю ли я кошек или собак?", "Что я делаю, когда вижу бездомное животное?",
        "Было ли у меня животное в детстве?", "Какое животное мне кажется самым умным?"
    ]
}

# === УРОВНИ ===
LEVELS = [
    {'name': '🌱 НОВИЧОК', 'min_score': 0},
    {'name': '📚 ЗНАТОК', 'min_score': 500},
    {'name': '💎 ЭКСПЕРТ', 'min_score': 1500},
    {'name': '👑 МАСТЕР', 'min_score': 3500},
    {'name': '🌟 ГУРУ', 'min_score': 7000},
    {'name': '👸 ЛЕГЕНДА', 'min_score': 15000}
]

DAILY_TASKS = {
    'complete_test': {'name': '📝 Пройти тест', 'points': 5},
    'send_test': {'name': '📤 Отправить тест', 'points': 10},
    'get_result': {'name': '🎯 Получить результат', 'points': 15},
    'create_test': {'name': '✨ Создать тест', 'points': 20},
    'invite_friend': {'name': '👭 Пригласить подругу', 'points': 30}
}

PREMIUM_SHOP_ITEMS = {
    'frame_gold': {'name': '🖼️ Золотая рамка', 'price': 49},
    'frame_diamond': {'name': '🖼️ Алмазная рамка', 'price': 99},
    'frame_royal': {'name': '🖼️ Королевская рамка', 'price': 199},
    'vip_badge': {'name': '⭐ VIP-значок', 'price': 29},
    'gold_nickname': {'name': '✨ Золотой никнейм', 'price': 49}
}

STREAK_REWARDS = {
    7: {'points': 50, 'tests': 1},
    14: {'points': 100, 'tests': 2},
    30: {'points': 300, 'premium_days': 7},
    100: {'points': 1000, 'premium_days': 30}
}

DIPLOMS = {
    'free': {'name': '📜 Классический', 'icon': '📜', 'border': '📜📜📜'},
    'premium_1': {'name': '👑 Королевский', 'icon': '👑', 'border': '✨👑✨'},
    'premium_2': {'name': '💎 Алмазный', 'icon': '💎', 'border': '✨💎✨'},
    'premium_3': {'name': '🌟 Звездный', 'icon': '🌟', 'border': '✨🌟✨'},
    'premium_4': {'name': '🦄 Волшебный', 'icon': '🦄', 'border': '✨🦄✨'},
    'premium_5': {'name': '🌸 Цветочный', 'icon': '🌸', 'border': '✨🌸✨'}
}

WOW_EMOJIS = {
    'start': '✨', 'success': '🎉', 'error': '❌', 'test': '📝',
    'friend': '👯', 'crown': '👑', 'star': '⭐', 'daily': '🎁',
    'achievement': '🏆', 'shop': '🛍️', 'money': '💰', 'top': '🏆',
    'back': '🔙', 'stats': '📊', 'cancel': '❌', 'task': '📋', 'level': '📈'
}

# === БАЗА ДАННЫХ ===
def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        tests_created INTEGER DEFAULT 0, tests_available INTEGER DEFAULT 3,
        total_points INTEGER DEFAULT 0, daily_streak INTEGER DEFAULT 0,
        last_daily TEXT, unlimited_until TEXT DEFAULT NULL,
        referral_code TEXT UNIQUE, referral_count INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT NULL, selected_diplom TEXT DEFAULT 'free',
        selected_frame TEXT DEFAULT 'none', selected_badge TEXT DEFAULT 'none',
        gold_nickname INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER,
        creator_name TEXT, creator_username TEXT, title TEXT,
        questions TEXT, options TEXT, correct_answers TEXT,
        greeting_type TEXT, greeting_file_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        likes INTEGER DEFAULT 0, shares INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, test_id INTEGER,
        friend_id INTEGER, friend_name TEXT, friend_username TEXT,
        answers TEXT, score REAL, completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(test_id, friend_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS saved_tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        test_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, test_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        task_date TEXT, task_type TEXT, completed INTEGER DEFAULT 0,
        UNIQUE(user_id, task_date, task_type)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS achievements (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        achievement_type TEXT, achieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, achievement_type)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER,
        referred_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY, reward_type TEXT, reward_value INTEGER,
        expires_at TIMESTAMP, used_by INTEGER DEFAULT NULL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tests_creator ON tests(creator_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_attempts_test ON attempts(test_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_saved_tests_user ON saved_tests(user_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_daily_tasks_user ON daily_tasks(user_id, task_date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)')
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

init_db()

# === ФУНКЦИИ БАЗЫ ДАННЫХ ===
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(user_id, username=None, first_name=None, referred_by=None):
    conn = get_db()
    c = conn.cursor()
    code = f"{user_id}{random.randint(1000, 9999)}"
    c.execute('''INSERT INTO users (user_id, username, first_name, referral_code, referred_by, tests_available)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (user_id, username, first_name, code, referred_by, START_TESTS))
    
    if referred_by and referred_by != user_id:
        referrer = get_user(referred_by)
        if referrer:
            c.execute('UPDATE users SET tests_available = tests_available + 1, referral_count = referral_count + 1 WHERE user_id = ?', (referred_by,))
            c.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (referred_by, user_id))
            add_achievement(referred_by, 'first_invite')
            complete_daily_task(referred_by, 'invite_friend')
            logger.info(f"✅ Пользователь {referred_by} пригласил {user_id}, получил +1 тест")
    conn.commit()
    conn.close()
    return True

def update_user(user_id, username=None, first_name=None):
    conn = get_db()
    c = conn.cursor()
    if username:
        c.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
    if first_name:
        c.execute('UPDATE users SET first_name = ? WHERE user_id = ?', (first_name, user_id))
    conn.commit()
    conn.close()

def add_tests(user_id, count):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET tests_available = tests_available + ? WHERE user_id = ?', (count, user_id))
    conn.commit()
    conn.close()

def use_test(user_id, test_id=None):
    user = get_user(user_id)
    if user and user.get('unlimited_until'):
        try:
            if datetime.fromisoformat(user['unlimited_until']) > datetime.now():
                return True
        except: pass
    
    if test_id:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id FROM attempts WHERE test_id = ? AND friend_id = ?', (test_id, user_id))
        if c.fetchone():
            conn.close()
            return False
        conn.close()
    
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET tests_available = tests_available - 1 WHERE user_id = ? AND tests_available > 0', (user_id,))
    conn.commit()
    success = c.rowcount > 0
    conn.close()
    return success

def get_available_tests(user_id):
    user = get_user(user_id)
    if not user:
        return START_TESTS
    if user.get('unlimited_until'):
        try:
            if datetime.fromisoformat(user['unlimited_until']) > datetime.now():
                return 999
        except: pass
    return user.get('tests_available', START_TESTS)

def add_points(user_id, points):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET total_points = total_points + ? WHERE user_id = ?', (points, user_id))
    conn.commit()
    conn.close()
    check_level_up(user_id)

def get_rank(score):
    for level in reversed(LEVELS):
        if score >= level['min_score']:
            return level
    return LEVELS[0]

def check_level_up(user_id):
    user = get_user(user_id)
    if not user:
        return
    points = user.get('total_points', 0)
    for level in LEVELS:
        if points >= level['min_score'] and level['min_score'] > 0:
            achievement_key = f'level_{level["min_score"]}'
            if not has_achievement(user_id, achievement_key):
                add_achievement(user_id, achievement_key)

def is_premium(user_id):
    user = get_user(user_id)
    if not user:
        return False
    unlimited = user.get('unlimited_until')
    if unlimited:
        try:
            if datetime.fromisoformat(unlimited) > datetime.now():
                return True
        except: pass
    return False

def get_daily_bonus(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT last_daily, daily_streak FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    today = datetime.now().date().isoformat()
    
    if row and row[0]:
        last_bonus = row[0]
        streak = row[1] or 0
        if last_bonus == today:
            conn.close()
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
            if reward.get('tests', 0) > 0:
                add_tests(user_id, reward['tests'])
            if reward.get('premium_days', 0) > 0:
                unlimited_until = (datetime.now() + timedelta(days=reward['premium_days'])).isoformat()
                c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (unlimited_until, user_id))
            add_achievement(user_id, f'streak_{streak}')
        c.execute('UPDATE users SET total_points = total_points + ?, last_daily = ?, daily_streak = ? WHERE user_id = ?',
                  (bonus, today, streak, user_id))
        conn.commit()
        conn.close()
        return bonus, streak
    else:
        c.execute('UPDATE users SET total_points = total_points + ?, last_daily = ?, daily_streak = 1 WHERE user_id = ?',
                  (DAILY_BONUS_POINTS, today, user_id))
        conn.commit()
        conn.close()
        return DAILY_BONUS_POINTS, 1

def create_test(creator_id, creator_name, creator_username, title, questions, options, correct_answers, greeting_type=None, greeting_file_id=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO tests (creator_id, creator_name, creator_username, title, questions, options, correct_answers, greeting_type, greeting_file_id)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (creator_id, creator_name, creator_username, title, json.dumps(questions), json.dumps(options), json.dumps(correct_answers), greeting_type, greeting_file_id))
    test_id = c.lastrowid
    c.execute('UPDATE users SET tests_created = tests_created + 1 WHERE user_id = ?', (creator_id,))
    conn.commit()
    conn.close()
    add_achievement(creator_id, 'first_test')
    complete_daily_task(creator_id, 'create_test')
    return test_id

def get_test_by_id(test_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM tests WHERE id = ?', (test_id,))
    row = c.fetchone()
    conn.close()
    if row:
        test = dict(row)
        test['questions'] = json.loads(test['questions']) if test['questions'] else []
        test['options'] = json.loads(test['options']) if test['options'] else []
        test['correct_answers'] = json.loads(test['correct_answers']) if test['correct_answers'] else []
        return test
    return None

def get_user_tests(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, title, likes, shares, created_at FROM tests WHERE creator_id = ? ORDER BY created_at DESC', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def save_test(user_id, test_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO saved_tests (user_id, test_id) VALUES (?, ?)', (user_id, test_id))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def unsave_test(user_id, test_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM saved_tests WHERE user_id = ? AND test_id = ?', (user_id, test_id))
    conn.commit()
    conn.close()

def get_saved_tests(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT t.id, t.title, t.creator_name FROM saved_tests s JOIN tests t ON s.test_id = t.id 
                 WHERE s.user_id = ? ORDER BY s.created_at DESC''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_saved_tests_count(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM saved_tests WHERE user_id = ?', (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def can_attempt_test(test_id, friend_id):
    test = get_test_by_id(test_id)
    if not test or test['creator_id'] == friend_id:
        return False
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM attempts WHERE test_id = ? AND friend_id = ?', (test_id, friend_id))
    row = c.fetchone()
    conn.close()
    return row is None

def save_attempt(test_id, friend_id, friend_name, friend_username, answers, score):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO attempts (test_id, friend_id, friend_name, friend_username, answers, score)
                 VALUES (?, ?, ?, ?, ?, ?)''', (test_id, friend_id, friend_name, friend_username, json.dumps(answers), score))
    c.execute('UPDATE tests SET shares = shares + 1 WHERE id = ?', (test_id,))
    conn.commit()
    test = get_test_by_id(test_id)
    if test:
        complete_daily_task(test['creator_id'], 'get_result')
    complete_daily_task(friend_id, 'complete_test')
    conn.close()

def add_achievement(user_id, achievement_type):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO achievements (user_id, achievement_type) VALUES (?, ?)', (user_id, achievement_type))
        conn.commit()
    except:
        pass
    finally:
        conn.close()

def has_achievement(user_id, achievement_type):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM achievements WHERE user_id = ? AND achievement_type = ?', (user_id, achievement_type))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_achievements(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT achievement_type, achieved_at FROM achievements WHERE user_id = ? ORDER BY achieved_at DESC', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_daily_tasks(user_id):
    conn = get_db()
    c = conn.cursor()
    today = datetime.now().date().isoformat()
    tasks = []
    for task_type in DAILY_TASKS:
        c.execute('SELECT completed FROM daily_tasks WHERE user_id = ? AND task_date = ? AND task_type = ?', (user_id, today, task_type))
        row = c.fetchone()
        completed = row['completed'] if row else 0
        tasks.append({'type': task_type, 'name': DAILY_TASKS[task_type]['name'], 'points': DAILY_TASKS[task_type]['points'], 'completed': completed})
    conn.close()
    return tasks

def complete_daily_task(user_id, task_type):
    conn = get_db()
    c = conn.cursor()
    today = datetime.now().date().isoformat()
    c.execute('''INSERT INTO daily_tasks (user_id, task_date, task_type, completed) VALUES (?, ?, ?, 1) 
                 ON CONFLICT(user_id, task_date, task_type) DO UPDATE SET completed = 1''', (user_id, today, task_type))
    conn.commit()
    if task_type in DAILY_TASKS:
        add_points(user_id, DAILY_TASKS[task_type]['points'])
    conn.close()

def apply_promocode(user_id, code):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM promocodes WHERE code = ? AND (used_by IS NULL OR used_by = ?) AND expires_at > ?', (code, user_id, datetime.now().isoformat()))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "Промокод не найден или истек"
    reward_type = row['reward_type']
    reward_value = row['reward_value']
    if reward_type == 'tests':
        add_tests(user_id, reward_value)
    elif reward_type == 'points':
        add_points(user_id, reward_value)
    elif reward_type == 'premium':
        unlimited_until = (datetime.now() + timedelta(days=reward_value)).isoformat()
        c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (unlimited_until, user_id))
    c.execute('UPDATE promocodes SET used_by = ? WHERE code = ?', (user_id, code))
    conn.commit()
    conn.close()
    return True, f"Промокод активирован! +{reward_value} {reward_type}"

def get_top_users(limit=20):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id, first_name, username, total_points FROM users ORDER BY total_points DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_attempts_stats(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT a.test_id, t.title, COUNT(a.id) as attempts_count, AVG(a.score) as avg_score
                 FROM attempts a JOIN tests t ON a.test_id = t.id WHERE t.creator_id = ?
                 GROUP BY a.test_id ORDER BY avg_score DESC''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_friendship_status(score):
    if score >= 95: return "👑 АБСОЛЮТНЫЕ БЛИЗНЕЦЫ"
    if score >= 85: return "💎 ЛУЧШИЕ ПОДРУГИ НАВЕК"
    if score >= 75: return "🌟 НАСТОЯЩИЕ ПОДРУГИ"
    if score >= 65: return "💕 ХОРОШИЕ ПОДРУГИ"
    if score >= 55: return "🤝 ПОДРУГИ"
    if score >= 45: return "👋 ХОРОШИЕ ЗНАКОМЫЕ"
    if score >= 35: return "🤔 ПРОСТО ЗНАКОМЫЕ"
    if score >= 25: return "😅 ШАТКОЕ ЗНАКОМСТВО"
    if score >= 15: return "🤨 СЛУЧАЙНЫЕ ПРОХОЖИЕ"
    return "😱 КТО ВЫ ТАКИЕ?"

def get_next_level_points(current_points):
    for level in LEVELS:
        if level['min_score'] > current_points:
            return level['min_score'] - current_points
    return 0

def update_selected_diplom(user_id, diplom_key):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET selected_diplom = ? WHERE user_id = ?', (diplom_key, user_id))
    conn.commit()
    conn.close()

def get_selected_diplom(user_id):
    user = get_user(user_id)
    return user.get('selected_diplom', 'free') if user else 'free'

# === КЛАВИАТУРЫ ===
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📝 Создать тест"), KeyboardButton("👑 Мои тесты")],
        [KeyboardButton("📊 Профиль"), KeyboardButton("🎁 Награды")],
        [KeyboardButton("💰 Пригласить"), KeyboardButton("🛍️ Магазин")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Отмена")]], resize_keyboard=True, one_time_keyboard=True)

def get_back_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton(f"{WOW_EMOJIS['back']} Назад")]], resize_keyboard=True, one_time_keyboard=True)

def get_question_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Другой вопрос", callback_data="next_question")],
        [InlineKeyboardButton("✅ Этот вопрос", callback_data="select_question")],
        [InlineKeyboardButton("🔙 Назад к группам", callback_data="back_to_groups")]
    ])

def get_options_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("➕ Добавить вариант"), KeyboardButton("✅ Готово"), KeyboardButton("🔙 Назад к вопросам")]],
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
        [InlineKeyboardButton("💎 30 дней — 299 ₽", callback_data="buy_premium_month")],
        [InlineKeyboardButton("💎 3 месяца — 699 ₽", callback_data="buy_premium_3months")],
        [InlineKeyboardButton("💎 ГОД — 1999 ₽", callback_data="buy_premium_year")],
        [InlineKeyboardButton("🛍️ Премиум-магазин", callback_data="premium_shop")]
    ])

def get_premium_shop_keyboard():
    keyboard = []
    for key, item in PREMIUM_SHOP_ITEMS.items():
        keyboard.append([InlineKeyboardButton(f"{item['name']} — {item['price']} ₽", callback_data=f"buy_item_{key}")])
    return InlineKeyboardMarkup(keyboard)

def get_share_confirm_keyboard(test_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, отправить", callback_data=f"confirm_share_{test_id}"),
         InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_share")],
        [InlineKeyboardButton("👭 Отправить подруге", 
            switch_inline_query=f"🌸 @{BOT_USERNAME} - твоя подруга приглашает тебя пройти тест! https://t.me/{BOT_USERNAME}?start=test_{test_id}")]
    ])

def get_start_test_keyboard(test_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_test_{test_id}"),
        InlineKeyboardButton("⭐ Сохранить", callback_data=f"save_test_{test_id}")
    ]])

def get_saved_test_keyboard(test_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑️ Удалить", callback_data=f"unsave_test_{test_id}"),
        InlineKeyboardButton("📖 Подробнее", callback_data=f"details_{test_id}"),
        InlineKeyboardButton("📤 Отправить", callback_data=f"share_saved_{test_id}")
    ]])

# === ОСНОВНЫЕ ХЕНДЛЕРЫ ===
async def send_referral_notification(bot, referrer_id, new_user_name):
    try:
        referrer = get_user(referrer_id)
        count = referrer.get('referral_count', 0) if referrer else 0
        text = (f"🌸 *Новая подруга!*\n\n"
                f"💕 {new_user_name} перешла по твоей ссылке!\n"
                f"🎁 Ты получила +1 тест!\n"
                f"👭 Всего приглашено: {count}")
        await bot.send_message(chat_id=referrer_id, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Ошибка уведомления: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None
    bot = context.bot
    
    if context.args and len(context.args) > 0:
        if context.args[0].isdigit():
            referred_by = int(context.args[0])
            if referred_by == user.id:
                referred_by = None
        elif context.args[0].startswith("test_"):
            try:
                test_id = int(context.args[0].split("_")[1])
                test = get_test_by_id(test_id)
                if test:
                    creator = get_user(test['creator_id'])
                    creator_name = creator.get('first_name', 'Подруга') if creator else 'Подруга'
                    text = (f"🌸 *Привет, {user.first_name or 'Дорогая'}!*\n\n"
                            f"💕 {creator_name} приглашает тебя пройти тест!\n"
                            f"📝 {test['title']}\n\n"
                            f"👇 *Нажми на кнопку*")
                    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, 
                                                   reply_markup=get_start_test_keyboard(test_id))
                    return
            except: pass
    
    existing = get_user(user.id)
    if not existing:
        create_user(user.id, user.username, user.first_name, referred_by)
        if referred_by:
            new_user_name = user.first_name or user.username or f"ID {user.id}"
            await send_referral_notification(bot, referred_by, new_user_name)
    else:
        update_user(user.id, user.username, user.first_name)
    
    user_data = get_user(user.id)
    points = user_data.get('total_points', 0)
    rank = get_rank(points)
    tests = get_available_tests(user.id)
    premium_status = "🔓" if not is_premium(user.id) else "💎"
    
    text = (f"{WOW_EMOJIS['start']} *Привет, {user.first_name or 'Подруга'}!*\n\n"
            f"🎀 {premium_status} | 🎁 {tests} тестов | ⭐ {points}\n"
            f"🏆 {rank['name']}\n\n"
            f"📝 *Создай тест* и проверь подругу!\n"
            f"👇 Нажми кнопку 👇")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    available = get_available_tests(user_id)
    if available <= 0:
        await update.message.reply_text(f"{WOW_EMOJIS['error']} Закончились тесты!\n🎁 Получи бонус или пригласи подругу!", reply_markup=get_main_keyboard())
        return
    context.user_data['create_test'] = {'step': 'title', 'questions_data': []}
    await update.message.reply_text(f"{WOW_EMOJIS['test']} *Создаем тест*\n📦 Доступно: {available}\n\n🌸 Придумай название:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

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
    if text == f"{WOW_EMOJIS['back']} Назад":
        if data.get('step') == 'waiting_question_count':
            data['step'] = 'group'
            user_id = update.effective_user.id
            await update.message.reply_text("✨ Выбери группу вопросов:", reply_markup=get_question_groups_keyboard(user_id))
        elif data.get('step') == 'collecting_options':
            data['step'] = 'selecting_question'
            await show_current_question(update, context)
        return
    step = data.get('step')
    if step == 'title':
        if len(text.strip()) < 3:
            await update.message.reply_text("⚠️ Минимум 3 символа")
            return
        data['title'] = text.strip()
        data['step'] = 'group'
        user_id = update.effective_user.id
        await update.message.reply_text("✨ Выбери группу вопросов:", reply_markup=get_question_groups_keyboard(user_id))
    elif step == 'waiting_question_count':
        try:
            count = int(text.strip())
            has_premium = is_premium(update.effective_user.id)
            max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
            if count < 2 or count > max_q:
                await update.message.reply_text(f"⚠️ От 2 до {max_q}")
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
            await update.message.reply_text("⚠️ Напиши число")
    elif step == 'collecting_options':
        if data.get('waiting_for_option'):
            option_text = text.strip()
            if option_text:
                if len(option_text) > 100:
                    await update.message.reply_text("⚠️ Слишком длинный вариант")
                    return
                data['current_options'].append(option_text)
                data['waiting_for_option'] = False
                await update.message.reply_text(f"✅ Вариант {len(data['current_options'])} добавлен!\n📋 {', '.join(data['current_options'])}", reply_markup=get_options_keyboard())

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
    await update.message.reply_text(f"📝 *Вопрос {data['current_q']+1}/{data['total_q']}*\n\n{question_text}", parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_keyboard())

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('create_test')
    if not data:
        await query.message.reply_text("Ошибка, начни заново", reply_markup=get_main_keyboard())
        return
    current_idx = data.get('current_question_index', 0)
    questions = data.get('group_questions', [])
    current_idx = (current_idx + 1) % len(questions)
    data['current_question_index'] = current_idx
    question_text = questions[current_idx]
    data['current_question_text'] = question_text
    await query.message.edit_text(f"📝 *Вопрос {data['current_q']+1}/{data['total_q']}*\n\n{question_text}", parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_keyboard())

async def select_current_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('create_test')
    if not data:
        await query.message.reply_text("Ошибка", reply_markup=get_main_keyboard())
        return
    data['step'] = 'collecting_options'
    data['current_options'] = []
    data['waiting_for_option'] = True
    await query.message.reply_text(f"📝 *Вопрос {data['current_q']+1}/{data['total_q']}*\n\n❓ {data['current_question_text']}\n\n✏️ Напиши вариант №1:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def select_question_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        group = query.data.split("_")[1]
    except:
        await query.message.reply_text("Ошибка")
        return
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
    await query.message.reply_text(f"✨ {group_name}\n\n📊 Сколько вопросов? (2-{max_q})", reply_markup=get_back_keyboard())

async def premium_group_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(f"{WOW_EMOJIS['error']} 💎 Только в премиум!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Магазин", callback_data="open_shop")]]))

async def add_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data or data.get('step') != 'collecting_options':
        return
    if len(data['current_options']) >= MAX_OPTIONS:
        await update.message.reply_text(f"⚠️ Максимум {MAX_OPTIONS} вариантов", reply_markup=get_options_keyboard())
        return
    data['waiting_for_option'] = True
    opt_num = len(data['current_options']) + 1
    await update.message.reply_text(f"✏️ Вариант №{opt_num}:", reply_markup=get_cancel_keyboard())

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
        await update.message.reply_text(f"⚠️ Минимум {MIN_OPTIONS} варианта", reply_markup=get_cancel_keyboard())
        data['waiting_for_option'] = True
        return
    data['step'] = 'select_correct'
    keyboard = []
    row = []
    for i, opt in enumerate(options):
        row.append(InlineKeyboardButton(f"{i+1}. {opt[:20]}", callback_data=f"correct_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    await update.message.reply_text(f"📝 *Вопрос {data['current_q']+1}/{data['total_q']}*\n\n❓ {data['current_question_text']}\n\n📋 {', '.join(options)}\n\n👇 *Выбери правильный ответ:*", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def select_correct_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        correct_idx = int(query.data.split("_")[1])
    except:
        await query.message.reply_text("Ошибка")
        return
    data = context.user_data.get('create_test')
    if not data:
        await query.message.reply_text("Ошибка")
        return
    options = data['current_options']
    data['questions_data'].append({'text': data['current_question_text'], 'options': options.copy(), 'correct': correct_idx})
    data['current_q'] += 1
    data['step'] = 'selecting_question'
    data['current_question_index'] = (data.get('current_question_index', 0) + 1) % len(data.get('group_questions', [1]))
    await query.message.reply_text(f"✅ Вопрос {data['current_q']}/{data['total_q']} сохранен!")
    if data['current_q'] < data['total_q']:
        await show_next_question(query, context)
    else:
        await finish_creation_from_callback(query, context, query.from_user.id)

async def show_next_question(query, context):
    data = context.user_data.get('create_test')
    if not data:
        await query.message.reply_text("Ошибка")
        return
    current_idx = data.get('current_question_index', 0)
    questions = data.get('group_questions', [])
    if current_idx >= len(questions):
        current_idx = 0
        data['current_question_index'] = 0
    question_text = questions[current_idx]
    data['current_question_text'] = question_text
    await query.message.reply_text(f"📝 *Вопрос {data['current_q']+1}/{data['total_q']}*\n\n{question_text}", parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_keyboard())

async def finish_creation_from_callback(query, context, user_id):
    data = context.user_data.get('create_test', {})
    if not data:
        return
    questions, options, correct_answers = [], [], []
    for q in data['questions_data']:
        questions.append(q['text'])
        options.append(q['options'])
        correct_answers.append(q['correct'])
    test_id = create_test(user_id, query.from_user.first_name, query.from_user.username, data['title'], questions, options, correct_answers)
    if test_id:
        save_test(user_id, test_id)
        await query.message.reply_text(f"{WOW_EMOJIS['success']} *Тест создан!*\n📝 {data['title']}\n🔢 {data['total_q']} вопросов\n\n👇 Отправь подруге:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_confirm_keyboard(test_id))
    else:
        await query.message.reply_text(f"{WOW_EMOJIS['error']} Ошибка", reply_markup=get_main_keyboard())
    del context.user_data['create_test']

# === ПРОФИЛЬ, НАГРАДЫ, ПРИГЛАШЕНИЯ, МАГАЗИН ===
async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Ошибка", reply_markup=get_main_keyboard())
        return
    points = user.get('total_points', 0)
    rank = get_rank(points)
    streak = user.get('daily_streak', 0)
    created = user.get('tests_created', 0)
    referrals = user.get('referral_count', 0)
    tests_left = get_available_tests(user_id)
    saved_count = get_saved_tests_count(user_id)
    max_saved = SAVED_TESTS_PREMIUM if is_premium(user_id) else SAVED_TESTS_FREE
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM attempts WHERE friend_id = ?', (user_id,))
    tests_passed = c.fetchone()[0]
    c.execute('SELECT COUNT(*) + 1 FROM users WHERE total_points > ?', (points,))
    rating = c.fetchone()[0]
    conn.close()
    
    text = (f"{WOW_EMOJIS['stats']} *Твой профиль*\n\n"
            f"👤 {user.get('first_name', 'Подруга')}\n"
            f"🏆 {rank['name']} | ⭐ {points}\n"
            f"🔥 {streak} дней | 📊 {rating} место\n\n"
            f"📝 Создано: {created}\n"
            f"🎯 Пройдено: {tests_passed}\n"
            f"👭 Приглашено: {referrals}\n"
            f"📦 Тестов: {tests_left}\n"
            f"⭐ Сохранено: {saved_count}/{max_saved}\n\n"
            f"👇 *Выбери раздел:*")
    
    keyboard = [
        [InlineKeyboardButton("🏆 Топ подруг", callback_data="top_friends")],
        [InlineKeyboardButton("📈 Рейтинг", callback_data="rating")],
        [InlineKeyboardButton("📊 Статистика тестов", callback_data="detailed_stats")]
    ]
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def rewards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = get_daily_tasks(user_id)
    completed = sum(1 for t in tasks if t['completed'])
    
    text = (f"{WOW_EMOJIS['daily']} *Награды*\n\n"
            f"🎁 Бонус: +{DAILY_BONUS_POINTS}⭐/день\n"
            f"📋 Задания: до +{sum(t['points'] for t in DAILY_TASKS.values())}⭐\n"
            f"🏆 Достижения: особые награды\n\n"
            f"📊 Выполнено: {completed}/{len(tasks)}\n\n"
            f"👇 *Выбери:*")
    
    keyboard = [
        [InlineKeyboardButton("🎁 Получить бонус", callback_data="daily_bonus")],
        [InlineKeyboardButton("📋 Мои задания", callback_data="daily_tasks")],
        [InlineKeyboardButton("🏆 Мои достижения", callback_data="achievements")]
    ]
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def daily_bonus_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = get_daily_bonus(user_id)
    if result[0] is None:
        await update.message.reply_text(f"{WOW_EMOJIS['daily']} *Бонус*\n🔥 Серия: {result[1]} дней\n⏰ Завтра будет новая награда!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(f"{WOW_EMOJIS['daily']} *+{result[0]} очков!*\n🔥 Серия: {result[1]} дней", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def daily_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = get_daily_tasks(user_id)
    text = f"{WOW_EMOJIS['task']} *Задания*\n\n"
    for task in tasks:
        status = "✅" if task['completed'] else "⬜"
        text += f"{status} {task['name']} +{task['points']}⭐\n"
    completed = sum(1 for t in tasks if t['completed'])
    text += f"\n📊 {completed}/{len(tasks)} выполнено"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def achievements_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    achievements = get_achievements(user_id)
    if not achievements:
        await update.message.reply_text(f"{WOW_EMOJIS['achievement']} *Достижения*\n\n🏆 Пока нет достижений\n🌟 Выполняй задания!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
        return
    achievement_names = {'first_test': '🎯 Первый тест', 'first_invite': '👭 Первое приглашение',
                         'streak_7': '🔥 7 дней', 'streak_14': '⭐ 14 дней', 'streak_30': '💎 30 дней',
                         'streak_100': '👑 100 дней', 'level_500': '📚 ЗНАТОК', 'level_1500': '💎 ЭКСПЕРТ',
                         'level_3500': '👑 МАСТЕР', 'level_7000': '🌟 ГУРУ', 'level_15000': '👸 ЛЕГЕНДА'}
    text = f"{WOW_EMOJIS['achievement']} *Достижения*\n\n"
    for ach in achievements[:10]:
        name = achievement_names.get(ach['achievement_type'], ach['achievement_type'])
        text += f"🏆 {name}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def rating_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    top_users = get_top_users(20)
    user = get_user(user_id)
    text = f"{WOW_EMOJIS['level']} *Рейтинг*\n\n"
    for i, u in enumerate(top_users[:10], 1):
        medal = "👑" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
        name = u['first_name'] or f"ID {u['user_id']}"
        text += f"{medal} {i}. {name[:15]} — {u['total_points']}⭐\n"
    if user:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) + 1 FROM users WHERE total_points > ?', (user['total_points'],))
        place = c.fetchone()[0]
        conn.close()
        text += f"\n📊 Твое место: {place}"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def top_friends_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT a.friend_id, a.friend_name, a.friend_username, AVG(a.score) as avg_score, COUNT(a.id) as tests_count
                 FROM attempts a WHERE a.test_id IN (SELECT id FROM tests WHERE creator_id = ?)
                 GROUP BY a.friend_id ORDER BY avg_score DESC LIMIT 10''', (user_id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text(f"{WOW_EMOJIS['top']} *Топ подруг*\n\nПока никто не проходил твои тесты", parse_mode=ParseMode.MARKDOWN)
        return
    text = f"{WOW_EMOJIS['top']} *Топ подруг*\n\n"
    for i, f in enumerate(rows, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "💕"
        name = f['friend_name'] or 'Подруга'
        text += f"{medal} {name} — {f['avg_score']:.0f}%\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def detailed_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_premium(user_id):
        await query.message.reply_text(f"{WOW_EMOJIS['error']} 💎 Детальная статистика только в премиум!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Оформить", callback_data="shop")]]))
        return
    stats = get_attempts_stats(user_id)
    if not stats:
        await query.message.reply_text("📊 Статистика пуста")
        return
    text = f"{WOW_EMOJIS['stats']} *Статистика тестов*\n\n"
    for s in stats[:5]:
        text += f"📝 {s['title']}\n   👥 {s['attempts_count']} | 📊 {s['avg_score']:.0f}%\n\n"
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def invite_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Ошибка")
        return
    code = user.get('referral_code', str(user_id))
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    referrals = user.get('referral_count', 0)
    text = (f"{WOW_EMOJIS['money']} *Пригласи подругу*\n\n"
            f"🎁 За каждую новую подругу → +1 тест\n"
            f"👭 Приглашено: {referrals}\n\n"
            f"🔗 {link}")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(), disable_web_page_preview=False)

async def shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        message = update.callback_query.message
    else:
        user_id = update.effective_user.id
        message = update.message
    if not message:
        return
    user = get_user(user_id)
    points = user.get('total_points', 0) if user else 0
    rank = get_rank(points)
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    saved_count = get_saved_tests_count(user_id)
    max_saved = SAVED_TESTS_PREMIUM if has_premium else SAVED_TESTS_FREE
    
    text = (f"{WOW_EMOJIS['shop']} *Премиум*\n\n"
            f"🏆 {rank['name']} | ⭐ {points}\n"
            f"🔢 Вопросов: до {max_q}\n"
            f"📦 Сохранено: {saved_count}/{max_saved}\n\n"
            f"✅ До 10 вопросов\n✅ 10 групп вопросов\n✅ До 10 сохраненных\n✅ Полная статистика\n✅ 5 дипломов\n\n"
            f"💎 30 дней — 299 ₽\n💎 3 месяца — 699 ₽\n💎 ГОД — 1999 ₽")
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_shop_keyboard())

async def my_tests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    saved = get_saved_tests(user_id)
    has_premium = is_premium(user_id)
    max_saved = SAVED_TESTS_PREMIUM if has_premium else SAVED_TESTS_FREE
    if not saved:
        await update.message.reply_text(f"{WOW_EMOJIS['test']} *Мои тесты*\n\nУ тебя пока нет сохраненных тестов", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())
        return
    text = f"{WOW_EMOJIS['crown']} *Мои тесты* ({len(saved)}/{max_saved})\n\n"
    for t in saved:
        text += f"📝 {t['title']}\n👤 {t['creator_name']}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def save_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        test_id = int(query.data.split("_")[2])
    except:
        await query.message.reply_text("Ошибка")
        return
    user_id = query.from_user.id
    has_premium = is_premium(user_id)
    saved_count = get_saved_tests_count(user_id)
    max_saved = SAVED_TESTS_PREMIUM if has_premium else SAVED_TESTS_FREE
    if saved_count >= max_saved:
        await query.message.reply_text(f"{WOW_EMOJIS['error']} Лимит {max_saved} тестов!\n💎 Премиум до {SAVED_TESTS_PREMIUM}", parse_mode=ParseMode.MARKDOWN)
        return
    if save_test(user_id, test_id):
        await query.message.reply_text(f"{WOW_EMOJIS['success']} Тест сохранен!", parse_mode=ParseMode.MARKDOWN)
    else:
        await query.message.reply_text(f"{WOW_EMOJIS['error']} Уже сохранен", parse_mode=ParseMode.MARKDOWN)

async def unsave_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        test_id = int(query.data.split("_")[2])
    except:
        await query.message.reply_text("Ошибка")
        return
    unsave_test(query.from_user.id, test_id)
    await query.message.reply_text("✅ Тест удален")

async def test_details_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        test_id = int(query.data.split("_")[1])
    except:
        await query.message.reply_text("Ошибка")
        return
    test = get_test_by_id(test_id)
    if not test:
        await query.message.reply_text("Тест не найден")
        return
    text = f"📝 *{test['title']}*\n👤 {test['creator_name']}\n📅 {test['created_at'][:10]}\n❤️ {test['likes']} | 📤 {test['shares']}\n\n*Вопросы:*\n"
    for i, q in enumerate(test['questions'], 1):
        text += f"{i}. {q}\n"
        for j, opt in enumerate(test['options'][i-1], 1):
            mark = "✅" if test['correct_answers'][i-1] == j-1 else "➖"
            text += f"   {mark} {j}. {opt}\n"
        text += "\n"
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def share_saved_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        test_id = int(query.data.split("_")[2])
    except:
        await query.message.reply_text("Ошибка")
        return
    test = get_test_by_id(test_id)
    if not test:
        await query.message.reply_text("Тест не найден")
        return
    if use_test(query.from_user.id, test_id):
        await query.message.reply_text(f"{WOW_EMOJIS['success']} *Тест готов к отправке!*\n📝 {test['title']}", parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_confirm_keyboard(test_id))
        complete_daily_task(query.from_user.id, 'send_test')
    else:
        await query.message.reply_text(f"{WOW_EMOJIS['error']} Не удалось отправить", reply_markup=get_main_keyboard())

async def confirm_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        test_id = int(query.data.split("_")[2])
    except:
        await query.message.reply_text("Ошибка")
        return
    if use_test(query.from_user.id, test_id):
        await query.message.reply_text(f"{WOW_EMOJIS['success']} *Тест отправлен!*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_confirm_keyboard(test_id))
        complete_daily_task(query.from_user.id, 'send_test')
    else:
        await query.message.reply_text(f"{WOW_EMOJIS['error']} Ошибка", reply_markup=get_main_keyboard())

async def cancel_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("❌ Отменено", reply_markup=get_main_keyboard())

async def back_to_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("✨ Выбери группу вопросов:", reply_markup=get_question_groups_keyboard(query.from_user.id))

async def open_shop_from_premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await shop_handler(update, context)

async def premium_shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_premium(query.from_user.id):
        await query.message.reply_text(f"{WOW_EMOJIS['error']} 💎 Только для премиум!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Оформить", callback_data="shop")]]))
        return
    await query.message.reply_text("🛍️ *Премиум-магазин*\n\n👇 Выбери предмет:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_premium_shop_keyboard())

async def buy_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_premium(query.from_user.id):
        await query.message.reply_text(f"{WOW_EMOJIS['error']} 💎 Только для премиум!")
        return
    await query.message.reply_text("💰 Для оплаты напишите @LavaTopBot")

async def promocode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🎁 Использование: /promocode КОД")
        return
    success, msg = apply_promocode(update.effective_user.id, context.args[0].upper())
    await update.message.reply_text(f"{'✅' if success else '❌'} {msg}")

async def start_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        test_id = int(query.data.split("_")[2])
    except:
        await query.message.reply_text("Ошибка")
        return
    test = get_test_by_id(test_id)
    if not test:
        await query.message.reply_text("Тест не найден")
        return
    if not can_attempt_test(test_id, query.from_user.id):
        await query.message.reply_text(f"{WOW_EMOJIS['error']} Ты уже проходила этот тест!")
        return
    context.user_data['taking_test'] = {'test': test, 'current': 0, 'answers': [], 'options': test['options'], 'correct_answers': test['correct_answers'], 'test_id': test_id}
    await send_question_handler(query, context, test['questions'][0], test['options'][0], 1, len(test['questions']))

async def send_question_handler(query, context, question, options, current, total):
    text = f"{WOW_EMOJIS['star']} *Вопрос {current}/{total}*\n\n📝 {question}"
    keyboard = []
    row = []
    for i, opt in enumerate(options):
        row.append(InlineKeyboardButton(opt, callback_data=f"answer_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def take_test_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        answer_idx = int(query.data.split("_")[1])
    except:
        await query.message.reply_text("Ошибка")
        return
    data = context.user_data.get('taking_test')
    if not data:
        await query.message.reply_text("Тест не найден")
        return
    data['answers'].append(answer_idx)
    data['current'] += 1
    if data['current'] < len(data['test']['questions']):
        await send_question_handler(query, context, data['test']['questions'][data['current']], data['options'][data['current']], data['current'] + 1, len(data['test']['questions']))
    else:
        await finish_test_handler(query, context, data)
        del context.user_data['taking_test']

async def finish_test_handler(query, context, data):
    test = data['test']
    answers = data['answers']
    correct_answers = data['correct_answers']
    user = query.from_user
    score = 0
    for i, ans in enumerate(answers):
        if i < len(correct_answers) and ans == correct_answers[i]:
            score += 100 / len(test['questions'])
    save_attempt(data['test_id'], user.id, user.first_name, user.username, answers, score)
    add_points(user.id, int(score))
    selected_diplom = get_selected_diplom(test['creator_id'])
    diplom = DIPLOMS.get(selected_diplom, DIPLOMS['free'])
    status = get_friendship_status(score)
    text = (f"{diplom['border']}\n{diplom['icon']} *Результат: {score:.0f}%*\n{diplom['border']}\n\n{status}\n\n✨ Спасибо за прохождение!")
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

# === АДМИН-КОМАНДЫ ===
async def admin_set_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Нет доступа")
        return
    if not context.args:
        await update.message.reply_text("📖 /setpremium @username [дни]\n/removepremium @username\n/checkpremium @username\n/addtests @username N\n/addpoints @username N\n/createpromo tests/points/premium N\n/users\n/checkref @username")
        return
    cmd = context.args[0].lower()
    
    if cmd == "users":
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT user_id, first_name, username, total_points, unlimited_until FROM users ORDER BY total_points DESC LIMIT 20')
        rows = c.fetchall()
        conn.close()
        text = "👥 *Пользователи*\n\n"
        for i, r in enumerate(rows, 1):
            name = r['first_name'] or f"ID {r['user_id']}"
            prem = "💎" if r['unlimited_until'] and datetime.fromisoformat(r['unlimited_until']) > datetime.now() else ""
            text += f"{i}. {name} — {r['total_points']}⭐ {prem}\n"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return
    
    if cmd == "checkref":
        if len(context.args) < 2:
            await update.message.reply_text("❌ /checkref @username")
            return
        username = context.args[1].replace('@', '')
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (username,))
        row = c.fetchone()
        conn.close()
        if not row:
            await update.message.reply_text(f"❌ @{username} не найден")
            return
        target_id, target_name = row['user_id'], row['first_name']
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (target_id,))
        count = c.fetchone()[0]
        c.execute('SELECT u.first_name, u.username FROM referrals r JOIN users u ON r.referred_id = u.user_id WHERE r.referrer_id = ?', (target_id,))
        rows = c.fetchall()
        conn.close()
        text = f"📊 *Рефералы {target_name}* — {count}\n\n"
        for i, r in enumerate(rows, 1):
            name = r['first_name'] or 'Подруга'
            uname = f"(@{r['username']})" if r['username'] else ''
            text += f"{i}. {name} {uname}\n"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return
    
    if cmd == "createpromo":
        if len(context.args) < 3:
            await update.message.reply_text("❌ /createpromo tests/points/premium N")
            return
        reward_type = context.args[1]
        try:
            reward_value = int(context.args[2])
        except:
            await update.message.reply_text("❌ Число")
            return
        code = f"{reward_type.upper()}{random.randint(10000, 99999)}"
        expires = (datetime.now() + timedelta(days=30)).isoformat()
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO promocodes (code, reward_type, reward_value, expires_at) VALUES (?, ?, ?, ?)', (code, reward_type, reward_value, expires))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Промокод: `{code}`\n🎁 {reward_value} {reward_type}", parse_mode=ParseMode.MARKDOWN)
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(f"❌ Укажите пользователя: /{cmd} @username")
        return
    
    username = context.args[1].replace('@', '')
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        await update.message.reply_text(f"❌ @{username} не найден")
        return
    target_id, target_name = row['user_id'], row['first_name']
    
    if cmd == "setpremium":
        days = 30
        if len(context.args) > 2 and context.args[2].isdigit():
            days = int(context.args[2])
        until = (datetime.now() + timedelta(days=days)).isoformat()
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (until, target_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ {target_name} получил премиум на {days} дней")
    elif cmd == "removepremium":
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE users SET unlimited_until = NULL WHERE user_id = ?', (target_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Премиум у {target_name} удален")
    elif cmd == "checkpremium":
        user = get_user(target_id)
        if user and user.get('unlimited_until'):
            until = datetime.fromisoformat(user['unlimited_until'])
            if until > datetime.now():
                await update.message.reply_text(f"✅ {target_name} имеет премиум до {until.strftime('%d.%m.%Y')}")
            else:
                await update.message.reply_text(f"❌ Премиум истек")
        else:
            await update.message.reply_text(f"❌ Нет премиума")
    elif cmd == "addtests":
        if len(context.args) < 3 or not context.args[2].isdigit():
            await update.message.reply_text("❌ /addtests @username N")
            return
        add_tests(target_id, int(context.args[2]))
        await update.message.reply_text(f"✅ +{context.args[2]} тестов {target_name}")
    elif cmd == "addpoints":
        if len(context.args) < 3 or not context.args[2].isdigit():
            await update.message.reply_text("❌ /addpoints @username N")
            return
        add_points(target_id, int(context.args[2]))
        await update.message.reply_text(f"✅ +{context.args[2]} очков {target_name}")
    else:
        await update.message.reply_text(f"❌ Неизвестная команда")

# === ОБРАБОТЧИКИ ===
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📝 Создать тест":
        await create_test_start(update, context)
    elif text == "👑 Мои тесты":
        await my_tests_handler(update, context)
    elif text == "📊 Профиль":
        await profile_handler(update, context)
    elif text == "🎁 Награды":
        await rewards_handler(update, context)
    elif text == "💰 Пригласить":
        await invite_handler(update, context)
    elif text == "🛍️ Магазин":
        await shop_handler(update, context)
    elif text == "➕ Добавить вариант":
        await add_option(update, context)
    elif text == "✅ Готово":
        await finish_options(update, context)
    elif text == f"{WOW_EMOJIS['back']} Назад":
        await back_to_questions(update, context)
    elif text == "🔙 Назад к вопросам":
        await back_to_questions(update, context)
    else:
        data = context.user_data.get('create_test')
        if data:
            await handle_create_test(update, context)
        else:
            await update.message.reply_text("Используй кнопки меню!", reply_markup=get_main_keyboard())

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    logger.info(f"Callback: {data}")
    
    if data.startswith("group_"):
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
    elif data.startswith("details_"):
        await test_details_handler(update, context)
    elif data.startswith("share_saved_"):
        await share_saved_test_handler(update, context)
    elif data.startswith("answer_"):
        await take_test_answer_handler(update, context)
    elif data == "open_shop":
        await open_shop_from_premium_handler(update, context)
    elif data == "premium_shop":
        await premium_shop_handler(update, context)
    elif data.startswith("buy_item_"):
        await buy_item_handler(update, context)
    elif data == "top_friends":
        await top_friends_handler(update, context)
    elif data == "rating":
        await rating_handler(update, context)
    elif data == "detailed_stats":
        await detailed_stats_handler(update, context)
    elif data == "daily_bonus":
        await daily_bonus_handler(update, context)
    elif data == "daily_tasks":
        await daily_tasks_handler(update, context)
    elif data == "achievements":
        await achievements_handler(update, context)
    elif data.startswith("buy_"):
        await query.message.reply_text(f"💎 Покупка: {data[4:]}\n💰 Напишите @LavaTopBot")
    elif data == "shop":
        await shop_handler(update, context)
    else:
        logger.warning(f"Неизвестный callback: {data}")
    await query.answer()

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpremium", admin_set_premium))
    app.add_handler(CommandHandler("removepremium", admin_set_premium))
    app.add_handler(CommandHandler("checkpremium", admin_set_premium))
    app.add_handler(CommandHandler("addtests", admin_set_premium))
    app.add_handler(CommandHandler("addpoints", admin_set_premium))
    app.add_handler(CommandHandler("createpromo", admin_set_premium))
    app.add_handler(CommandHandler("users", admin_set_premium))
    app.add_handler(CommandHandler("checkref", admin_set_premium))
    app.add_handler(CommandHandler("promocode", promocode_handler))
    
    app.add_handler(MessageHandler(filters.Regex("^📝 Создать тест$"), create_test_start))
    app.add_handler(MessageHandler(filters.Regex("^👑 Мои тесты$"), my_tests_handler))
    app.add_handler(MessageHandler(filters.Regex("^📊 Профиль$"), profile_handler))
    app.add_handler(MessageHandler(filters.Regex("^🎁 Награды$"), rewards_handler))
    app.add_handler(MessageHandler(filters.Regex("^💰 Пригласить$"), invite_handler))
    app.add_handler(MessageHandler(filters.Regex("^🛍️ Магазин$"), shop_handler))
    
    app.add_handler(MessageHandler(filters.Regex("^➕ Добавить вариант$"), add_option))
    app.add_handler(MessageHandler(filters.Regex("^✅ Готово$"), finish_options))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['back']} Назад$"), back_to_questions))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Назад к вопросам$"), back_to_questions))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.Regex("^❌ Отмена$"), cancel_creation))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🚀 Бот запущен! Версия 52.0 - компактная")
    app.run_polling()

if __name__ == "__main__":
    main()
