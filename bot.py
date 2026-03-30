#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бот для создания тестов для подруг @PodrugaTestBot
Версия: 20.0 - ДЛЯ СЕРВЕРА В ГЕРМАНИИ
"""

import logging
import json
import sqlite3
import random
import os
import math
from difflib import SequenceMatcher
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
START_TESTS = 1
DAILY_BONUS_POINTS = 5
MAX_REFERRAL_BONUS = 3
MAX_OPTIONS = 4
MIN_OPTIONS = 2
MAX_QUESTIONS_FREE = 5
MAX_QUESTIONS_PREMIUM = 10

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# === ГРУППЫ ВОПРОСОВ ===
FREE_QUESTION_GROUPS = {
    'friendship': '👭 Дружба',
    'love': '💖 Любовь',
    'humor': '😂 Юмор',
    'myself': '🌸 О себе'
}

PREMIUM_QUESTION_GROUPS = {
    'friendship': '👭 Дружба',
    'love': '💖 Любовь',
    'humor': '😂 Юмор',
    'myself': '🌸 О себе',
    'family': '🏠 Семья',
    'school': '📚 Школа',
    'travel': '✈️ Путешествия',
    'food': '🍕 Еда',
    'style': '👗 Стиль',
    'animals': '🐾 Животные'
}

QUESTIONS_BY_GROUP = {
    'friendship': ["Как долго мы дружим?", "Где мы познакомились?", "Какой мой любимый цвет?", "Какая моя любимая еда?"],
    'love': ["Какой тип парня мне нравится?", "Что для меня важно в отношениях?", "Как я проявляю симпатию?", "Куда я хочу на свидание?"],
    'humor': ["Что я делаю, когда опаздываю?", "Какая у меня самая нелепая привычка?", "Как я танцую?", "Что я ем, когда никто не видит?"],
    'myself': ["Какая моя главная черта характера?", "Что меня вдохновляет?", "Какая у меня суперсила?", "Что мне нужно для счастья?"],
    'family': ["Кто мой самый близкий родственник?", "Что я люблю делать с семьей?", "Какая у нас семейная традиция?", "На кого я похожа?"],
    'school': ["Мой любимый предмет?", "Какой предмет я ненавижу?", "Что я делаю на скучных уроках?", "С кем я сижу за партой?"],
    'travel': ["Куда я мечтаю поехать?", "Что я беру в поездку?", "Как я добираюсь до места?", "Что я делаю в дороге?"],
    'food': ["Мое любимое блюдо?", "Что я ненавижу есть?", "Что я умею готовить?", "Что я заказываю в кафе?"],
    'style': ["Мой любимый цвет в одежде?", "Какой стиль я люблю?", "Что я никогда не надену?", "Какой у меня must-have?"],
    'animals': ["Какое мое любимое животное?", "Есть ли у меня домашний питомец?", "Какое животное я хотела бы завести?", "Боюсь ли я животных?"]
}

RANKS = [
    {'name': '🌱 НОВИЧОК', 'min_score': 0},
    {'name': '📚 ЭКСПЕРТ', 'min_score': 100},
    {'name': '💎 МАСТЕР', 'min_score': 500},
    {'name': '👑 ГУРУ', 'min_score': 2000},
    {'name': '🌟 ЛЕГЕНДА', 'min_score': 5000},
    {'name': '👸 КОРОЛЕВА', 'min_score': 10000}
]

WOW_EMOJIS = {
    'start': '✨', 'success': '🎉', 'error': '❌',
    'test': '📝', 'friend': '👯', 'crown': '👑',
    'star': '⭐', 'heart': '💖', 'daily': '📅',
    'achievement': '🏅', 'shop': '🛍️', 'money': '💰',
    'top': '🏆'
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
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        tests_created INTEGER DEFAULT 0,
        tests_available INTEGER DEFAULT 1,
        total_points INTEGER DEFAULT 0,
        daily_streak INTEGER DEFAULT 0,
        last_daily TEXT,
        unlimited_until TEXT DEFAULT NULL,
        referral_code TEXT UNIQUE,
        referral_count INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT NULL,
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
        likes INTEGER DEFAULT 0,
        shares INTEGER DEFAULT 0
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
    
    c.execute('CREATE INDEX IF NOT EXISTS idx_tests_creator ON tests(creator_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_attempts_test ON attempts(test_id)')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

init_db()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
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
    c.execute('''INSERT INTO users 
        (user_id, username, first_name, referral_code, referred_by, tests_available)
        VALUES (?, ?, ?, ?, ?, ?)''',
        (user_id, username, first_name, code, referred_by, START_TESTS))
    
    if referred_by:
        c.execute('UPDATE users SET tests_available = tests_available + 1, referral_count = referral_count + 1 WHERE user_id = ?', (referred_by,))
        c.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)', (referred_by, user_id))
    conn.commit()
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

def use_test(user_id):
    user = get_user(user_id)
    if user and user.get('unlimited_until'):
        try:
            if datetime.fromisoformat(user['unlimited_until']) > datetime.now():
                return True
        except:
            pass
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET tests_available = tests_available - 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    return True

def add_points(user_id, points):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET total_points = total_points + ? WHERE user_id = ?', (points, user_id))
    conn.commit()
    conn.close()

def get_rank(score):
    for i in range(len(RANKS) - 1, -1, -1):
        if score >= RANKS[i]['min_score']:
            return RANKS[i]
    return RANKS[0]

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

def create_test(creator_id, creator_name, creator_username, title, questions, options, correct_answers, greeting_type=None, greeting_file_id=None):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO tests 
            (creator_id, creator_name, creator_username, title, questions, options, correct_answers, greeting_type, greeting_file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (creator_id, creator_name, creator_username, title, json.dumps(questions), json.dumps(options), json.dumps(correct_answers), greeting_type, greeting_file_id))
        test_id = c.lastrowid
        c.execute('UPDATE users SET tests_created = tests_created + 1 WHERE user_id = ?', (creator_id,))
        conn.commit()
        conn.close()
        return test_id
    except Exception as e:
        logger.error(f"Ошибка создания теста: {e}")
        return None

def get_test_by_id(test_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM tests WHERE id = ?', (test_id,))
    row = c.fetchone()
    conn.close()
    if row:
        test = dict(row)
        try:
            test['questions'] = json.loads(test['questions']) if test['questions'] else []
            test['options'] = json.loads(test['options']) if test['options'] else []
            test['correct_answers'] = json.loads(test['correct_answers']) if test['correct_answers'] else []
        except:
            test['questions'] = []
            test['options'] = []
            test['correct_answers'] = []
        return test
    return None

def get_user_tests(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, title, likes, shares, created_at FROM tests WHERE creator_id = ? ORDER BY created_at DESC', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

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
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO attempts (test_id, friend_id, friend_name, friend_username, answers, score)
            VALUES (?, ?, ?, ?, ?, ?)''', (test_id, friend_id, friend_name, friend_username, json.dumps(answers), score))
        c.execute('UPDATE tests SET shares = shares + 1 WHERE id = ?', (test_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения попытки: {e}")
        return False

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
        if streak == 7: bonus = 15
        elif streak == 30: bonus = 50
        elif streak == 100: bonus = 100
        
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

# === КЛАВИАТУРЫ ===
def get_main_keyboard():
    keyboard = [
        [KeyboardButton(f"{WOW_EMOJIS['test']} Создать тест"), KeyboardButton(f"{WOW_EMOJIS['crown']} Мои тесты")],
        [KeyboardButton(f"{WOW_EMOJIS['achievement']} Мои ачивки"), KeyboardButton(f"{WOW_EMOJIS['daily']} Ежедневный бонус")],
        [KeyboardButton(f"{WOW_EMOJIS['money']} Пригласить подруг"), KeyboardButton(f"{WOW_EMOJIS['shop']} Магазин")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("📋 Топ подруг")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Отмена")]], resize_keyboard=True, one_time_keyboard=True)

def get_question_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Другой вопрос", callback_data="next_question")],
        [InlineKeyboardButton("✅ Этот вопрос", callback_data="select_question")]
    ])

def get_options_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("➕ Добавить вариант"), KeyboardButton("✅ Готово")]],
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

def get_share_confirm_keyboard(test_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("👭 Отправить подруге", 
            switch_inline_query=f"🎉 @{BOT_USERNAME} - твоя подруга приглашает тебя пройти тест! https://t.me/{BOT_USERNAME}?start=test_{test_id}")
    ]])

def get_start_test_keyboard(test_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_test_{test_id}")
    ]])

def get_shop_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 5 тестов — 99 ₽", callback_data="buy_tests_5"), InlineKeyboardButton("📦 10 тестов — 149 ₽", callback_data="buy_tests_10")],
        [InlineKeyboardButton("📦 20 тестов — 249 ₽", callback_data="buy_tests_20"), InlineKeyboardButton("📦 50 тестов — 499 ₽", callback_data="buy_tests_50")],
        [InlineKeyboardButton("💎 Премиум-диплом — 49 ₽", callback_data="buy_premium_diploma"), InlineKeyboardButton("🥇 Золотой диплом — 99 ₽", callback_data="buy_gold_diploma")],
        [InlineKeyboardButton("🖼️ Золотая рамка — 29 ₽", callback_data="buy_frame_gold"), InlineKeyboardButton("🖼️ Алмазная рамка — 49 ₽", callback_data="buy_frame_diamond")],
        [InlineKeyboardButton("👑 Королевская рамка — 99 ₽", callback_data="buy_frame_royal"), InlineKeyboardButton("♾️ Безлимит (месяц) — 199 ₽", callback_data="buy_unlimited_month")],
        [InlineKeyboardButton("♾️ 3 месяца безлимита — 499 ₽", callback_data="buy_unlimited_3months"), InlineKeyboardButton("♾️ Год безлимита — 1499 ₽", callback_data="buy_unlimited_year")]
    ])

# === ХЕНДЛЕРЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None
    
    if context.args and len(context.args) > 0:
        if context.args[0].isdigit():
            referred_by = int(context.args[0])
            if referred_by == user.id:
                referred_by = None
        elif context.args[0].startswith("test_"):
            test_id = int(context.args[0].split("_")[1])
            test = get_test_by_id(test_id)
            if test:
                text = f"{WOW_EMOJIS['friend']} *ПРОЙДИ ТЕСТ ОТ ПОДРУГИ!*\n\n📝 {test['title']}"
                await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_start_test_keyboard(test_id))
                return
    
    existing = get_user(user.id)
    if not existing:
        create_user(user.id, user.username, user.first_name, referred_by)
    
    user_data = get_user(user.id)
    points = user_data.get('total_points', 0) if user_data else 0
    rank = get_rank(points)
    tests = get_available_tests(user.id)
    premium_status = "🔓 Бесплатный" if not is_premium(user.id) else "💎 Премиум"
    
    text = f"""{WOW_EMOJIS['start']} *ПРИВЕТ, {user.first_name or 'ПОДРУГА'}!*

✨ Добро пожаловать в *PodrugaTestBot*!

🎀 *Твой статус:* {premium_status}
🎁 *У тебя:* {tests} тестов
⭐ *Очки:* {points}
🏆 *Ранг:* {rank['name']}

💫 *Начни с создания теста!* Нажми «Создать тест» ✨
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

# [ПРОДОЛЖЕНИЕ СЛЕДУЕТ - ДОПИШУ ВСЕ ОСТАЛЬНЫЕ ХЕНДЛЕРЫ]
