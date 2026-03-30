#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бот для создания тестов для подруг @PodrugaTestBot
Версия: 20.0 - ФИНАЛЬНАЯ
"""

import logging
import json
import sqlite3
import random
import string
import time
import os
import io
import math
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters, CallbackQueryHandler
from telegram.error import Conflict, NetworkError, TimedOut

# === НАСТРОЙКА TOR ПРОКСИ ===
import socks
import socket

socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
#
socket.socket = socks.socksocket

def getaddrinfo(*args):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (args[0], args[1]))]
socket.getaddrinfo = getaddrinfo

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    TOKEN = "8724383380:AAEUwV3OQzabDZYNrgIWDloXV46v1xn0Pkw"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_USERNAME = "PodrugaTestBot"
DB_NAME = 'bot_database.db'
START_TESTS = 1
DAILY_BONUS_POINTS = 5
MAX_REFERRAL_BONUS = 3
MAX_OPTIONS = 4
MIN_OPTIONS = 2
MAX_QUESTIONS_FREE = 5
MAX_QUESTIONS_PREMIUM = 10

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
    'friendship': [
        "Как долго мы дружим?",
        "Где мы познакомились?",
        "Какой мой любимый цвет?",
        "Какая моя любимая еда?",
        "Какое у меня хобби?",
        "Какой мой любимый фильм?",
        "Что меня может разозлить?",
        "Какая у меня мечта?"
    ],
    'love': [
        "Какой тип парня мне нравится?",
        "Что для меня важно в отношениях?",
        "Как я проявляю симпатию?",
        "Куда я хочу на свидание?",
        "Что меня влюбляет?",
        "Какой подарок я хочу получить?",
        "Как я понимаю, что влюблена?",
        "Что меня раздражает в парнях?"
    ],
    'humor': [
        "Что я делаю, когда опаздываю?",
        "Какая у меня самая нелепая привычка?",
        "Как я танцую?",
        "Что я ем, когда никто не видит?",
        "Как я веду себя, когда вру?",
        "Что я делаю, если увидела таракана?",
        "Мой самый смешной страх?",
        "Что я говорю, когда просыпаюсь?"
    ],
    'myself': [
        "Какая моя главная черта характера?",
        "Что меня вдохновляет?",
        "Какая у меня суперсила?",
        "Что мне нужно для счастья?",
        "Как я справляюсь со стрессом?",
        "Кем я хочу стать в будущем?",
        "Что я люблю в себе?",
        "Мой главный страх?"
    ],
    'family': [
        "Кто мой самый близкий родственник?",
        "Что я люблю делать с семьей?",
        "Какая у нас семейная традиция?",
        "На кого я похожа?",
        "Что меня бесит в родителях?",
        "Как я провожу время с мамой?",
        "Есть ли у меня брат или сестра?",
        "Что я ценю в своей семье?"
    ],
    'school': [
        "Мой любимый предмет?",
        "Какой предмет я ненавижу?",
        "Что я делаю на скучных уроках?",
        "С кем я сижу за партой?",
        "Как я списываю?",
        "Что я ем в столовой?",
        "Что я делаю на перемене?",
        "Кого я боюсь в школе?"
    ],
    'travel': [
        "Куда я мечтаю поехать?",
        "Что я беру в поездку?",
        "Как я добираюсь до места?",
        "Что я делаю в дороге?",
        "Мой идеальный отдых?",
        "Где я уже была?",
        "С кем я хочу путешествовать?",
        "Что я делаю, если потерялась?"
    ],
    'food': [
        "Мое любимое блюдо?",
        "Что я ненавижу есть?",
        "Что я умею готовить?",
        "Что я заказываю в кафе?",
        "Какие сладости я люблю?",
        "Что я ем на завтрак?",
        "Мое любимое кафе?",
        "Какую еду я никогда не буду есть?"
    ],
    'style': [
        "Мой любимый цвет в одежде?",
        "Какой стиль я люблю?",
        "Что я никогда не надену?",
        "Какой у меня must-have?",
        "Что я надеваю на вечеринку?",
        "Какую обувь я предпочитаю?",
        "Что я делаю с волосами?",
        "Какой парфюм я люблю?"
    ],
    'animals': [
        "Какое мое любимое животное?",
        "Есть ли у меня домашний питомец?",
        "Какое животное я хотела бы завести?",
        "Боюсь ли я животных?",
        "Люблю ли я кошек или собак?",
        "Что я делаю, когда вижу бездомное животное?",
        "Было ли у меня животное в детстве?",
        "Какое животное мне кажется самым умным?"
    ]
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

def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

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

def use_test(user_id):
    user = get_user(user_id)
    if user and user.get('unlimited_until'):
        unlimited_until = user['unlimited_until']
        if isinstance(unlimited_until, str):
            try:
                unlimited_until = datetime.fromisoformat(unlimited_until)
            except:
                unlimited_until = None
        if unlimited_until and unlimited_until > datetime.now():
            return True
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE users SET tests_available = tests_available - 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_available_tests(user_id):
    user = get_user(user_id)
    if not user:
        return START_TESTS
    if user.get('unlimited_until'):
        unlimited_until = user['unlimited_until']
        if isinstance(unlimited_until, str):
            try:
                unlimited_until = datetime.fromisoformat(unlimited_until)
            except:
                unlimited_until = None
        if unlimited_until and unlimited_until > datetime.now():
            return 999
    return user.get('tests_available', START_TESTS)

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
        if streak == 7:
            bonus = 15
        elif streak == 30:
            bonus = 50
        elif streak == 100:
            bonus = 100
        
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

def is_premium(user_id):
    user = get_user(user_id)
    if not user:
        return False
    unlimited = user.get('unlimited_until')
    if unlimited:
        if isinstance(unlimited, str):
            try:
                unlimited = datetime.fromisoformat(unlimited)
            except:
                unlimited = None
        if unlimited and unlimited > datetime.now():
            return True
    return False

# === СОЗДАНИЕ ТЕСТА ===
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
    if not test:
        return False
    if test['creator_id'] == friend_id:
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
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        logger.error(f"Ошибка сохранения попытки: {e}")
        return False

def get_friendship_status(score):
    if score >= 95:
        return "👑 АБСОЛЮТНЫЕ БЛИЗНЕЦЫ"
    if score >= 85:
        return "💎 ЛУЧШИЕ ПОДРУГИ НАВЕК"
    if score >= 75:
        return "🌟 НАСТОЯЩИЕ ПОДРУГИ"
    if score >= 65:
        return "💕 ХОРОШИЕ ПОДРУГИ"
    if score >= 55:
        return "🤝 ПОДРУГИ"
    if score >= 45:
        return "👋 ХОРОШИЕ ЗНАКОМЫЕ"
    if score >= 35:
        return "🤔 ПРОСТО ЗНАКОМЫЕ"
    if score >= 25:
        return "😅 ШАТКОЕ ЗНАКОМСТВО"
    if score >= 15:
        return "🤨 СЛУЧАЙНЫЕ ПРОХОЖИЕ"
    return "😱 КТО ВЫ ТАКИЕ?"

def get_bot_link():
    return f"https://t.me/{BOT_USERNAME}"

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
    keyboard = [
        [InlineKeyboardButton("🔄 Другой вопрос", callback_data="next_question")],
        [InlineKeyboardButton("✅ Этот вопрос", callback_data="select_question")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_options_keyboard():
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("➕ Добавить вариант"), KeyboardButton("✅ Готово")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

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
    keyboard = [
        [InlineKeyboardButton("📦 5 тестов — 99 ₽", callback_data="buy_tests_5"), InlineKeyboardButton("📦 10 тестов — 149 ₽", callback_data="buy_tests_10")],
        [InlineKeyboardButton("📦 20 тестов — 249 ₽", callback_data="buy_tests_20"), InlineKeyboardButton("📦 50 тестов — 499 ₽", callback_data="buy_tests_50")],
        [InlineKeyboardButton("💎 Премиум-диплом — 49 ₽", callback_data="buy_premium_diploma"), InlineKeyboardButton("🥇 Золотой диплом — 99 ₽", callback_data="buy_gold_diploma")],
        [InlineKeyboardButton("🖼️ Золотая рамка — 29 ₽", callback_data="buy_frame_gold"), InlineKeyboardButton("🖼️ Алмазная рамка — 49 ₽", callback_data="buy_frame_diamond")],
        [InlineKeyboardButton("👑 Королевская рамка — 99 ₽", callback_data="buy_frame_royal"), InlineKeyboardButton("♾️ Безлимит (месяц) — 199 ₽", callback_data="buy_unlimited_month")],
        [InlineKeyboardButton("♾️ 3 месяца безлимита — 499 ₽", callback_data="buy_unlimited_3months"), InlineKeyboardButton("♾️ Год безлимита — 1499 ₽", callback_data="buy_unlimited_year")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_share_confirm_keyboard(test_id):
    keyboard = [[InlineKeyboardButton("👭 Отправить подруге", switch_inline_query=f"🎉 @{BOT_USERNAME} - твоя подруга приглашает тебя пройти тест! Переходи по ссылке: https://t.me/{BOT_USERNAME}?start=test_{test_id}")]]
    return InlineKeyboardMarkup(keyboard)

def get_start_test_keyboard(test_id):
    keyboard = [[InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_test_{test_id}")]]
    return InlineKeyboardMarkup(keyboard)

# === ХЕНДЛЕРЫ ===
def start(update: Update, context: CallbackContext):
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
                text = f"{WOW_EMOJIS['friend']} *ПРОЙДИ ТЕСТ ОТ ПОДРУГИ!*\n\n📝 {test['title']}\n\n👇 Нажми на кнопку, чтобы начать"
                update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_start_test_keyboard(test_id))
                return
    
    existing = get_user(user.id)
    if not existing:
        create_user(user.id, user.username, user.first_name, referred_by)
    else:
        update_user(user.id, user.username, user.first_name)
    
    user_data = get_user(user.id)
    if user_data:
        points = user_data.get('total_points', 0)
        rank = get_rank(points)
        tests = get_available_tests(user.id)
    else:
        points = 0
        rank = RANKS[0]
        tests = START_TESTS
    
    premium_status = "🔓 Бесплатный" if not is_premium(user.id) else "💎 Премиум"
    
    text = f"""{WOW_EMOJIS['start']} *ПРИВЕТ, {user.first_name or 'ПОДРУГА'}!*

✨ Добро пожаловать в *PodrugaTestBot*!

🎀 *Твой статус:* {premium_status}
🎁 *У тебя:* {tests} тестов
⭐ *Очки:* {points}
🏆 *Ранг:* {rank['name']}

💫 *Начни с создания теста!* Нажми «Создать тест» ✨
"""
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

# === СОЗДАНИЕ ТЕСТА ===
def create_test_start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    available = get_available_tests(user_id)
    
    if available <= 0:
        update.message.reply_text(
            f"{WOW_EMOJIS['error']} У тебя закончились тесты!\n\n"
            "🎁 Получи ежедневный бонус или пригласи подругу!\n"
            "💎 Или загляни в магазин",
            reply_markup=get_main_keyboard()
        )
        return
    
    context.user_data['create_test'] = {'step': 'title'}
    update.message.reply_text(
        f"{WOW_EMOJIS['test']} *Создаем тест!*\n\n"
        f"📦 *Доступно тестов:* {available}\n\n"
        "Придумай название (например: «Насколько хорошо ты меня знаешь?»):\n\n"
        "❌ Отмена - чтобы выйти",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

def handle_create_test(update: Update, context: CallbackContext):
    data = context.user_data.get('create_test')
    if not data:
        return
    
    text = update.message.text
    
    if text == "❌ Отмена":
        cancel_creation(update, context)
        return
    
    step = data.get('step')
    
    if step == 'title':
        data['title'] = text
        data['step'] = 'group'
        
        user_id = update.effective_user.id
        update.message.reply_text(
            "✨ Отлично! Теперь выбери *группу вопросов*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_question_groups_keyboard(user_id)
        )
    
    elif step == 'waiting_question_count':
        try:
            count = int(text.strip())
            user_id = update.effective_user.id
            has_premium = is_premium(user_id)
            max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
            
            if count < 2:
                update.message.reply_text(f"⚠️ Минимум 2 вопроса! Напишите число от 2 до {max_q}:")
                return
            if count > max_q:
                update.message.reply_text(f"⚠️ Для вашего тарифа максимум {max_q} вопросов! Напишите число от 2 до {max_q}:")
                return
            
            data['total_q'] = count
            data['current_q'] = 0
            data['questions_data'] = []
            data['step'] = 'selecting_question'
            
            group = data.get('group')
            data['group_questions'] = QUESTIONS_BY_GROUP.get(group, []).copy()
            random.shuffle(data['group_questions'])
            data['current_question_index'] = 0
            
            show_current_question(update, context)
        except ValueError:
            update.message.reply_text("⚠️ Пожалуйста, напишите число (например: 5):")
    
    elif step == 'collecting_options':
        if data.get('waiting_for_option'):
            option_text = text.strip()
            if option_text:
                data['current_options'].append(option_text)
                data['waiting_for_option'] = False
                
                update.message.reply_text(
                    f"✅ *Вариант {len(data['current_options'])} добавлен!*\n\n"
                    f"📋 Текущие варианты:\n" + "\n".join([f"{i+1}. {o}" for i, o in enumerate(data['current_options'])]),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_options_keyboard()
                )

def show_current_question(update, context):
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
    
    update.message.reply_text(
        f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{question_text}\n\n"
        f"❓ Что делать с этим вопросом?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_question_keyboard()
    )

def next_question(update: Update, context: CallbackContext):
    query = update.callback_query
    if not query or not query.message:
        return
    
    data = context.user_data.get('create_test')
    if not data:
        query.message.reply_text("Ошибка")
        return
    
    current_idx = data.get('current_question_index', 0)
    questions = data.get('group_questions', [])
    
    current_idx = (current_idx + 1) % len(questions)
    data['current_question_index'] = current_idx
    
    question_text = questions[current_idx]
    data['current_question_text'] = question_text
    
    query.message.edit_text(
        f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{question_text}\n\n"
        f"❓ Что делать с этим вопросом?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_question_keyboard()
    )
    query.answer()

def select_current_question(update: Update, context: CallbackContext):
    query = update.callback_query
    if not query or not query.message:
        return
    
    data = context.user_data.get('create_test')
    if not data:
        query.message.reply_text("Ошибка")
        return
    
    data['step'] = 'collecting_options'
    data['current_options'] = []
    data['waiting_for_option'] = True
    
    query.message.edit_text(
        f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n"
        f"❓ {data['current_question_text']}\n\n"
        f"✏️ Напишите *вариант ответа №1*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )
    query.answer()

def select_question_group(update: Update, context: CallbackContext):
    query = update.callback_query
    if not query or not query.message:
        return
    
    group = query.data.split("_")[1]
    
    data = context.user_data.get('create_test')
    if not data:
        data = {}
        context.user_data['create_test'] = data
    
    data['group'] = group
    data['step'] = 'waiting_question_count'
    
    user_id = query.from_user.id
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    
    query.message.reply_text(
        f"✨ Выбрана группа: {PREMIUM_QUESTION_GROUPS.get(group, FREE_QUESTION_GROUPS.get(group, 'Вопросы'))}\n\n"
        f"📊 *Сколько вопросов будет в тесте?*\n"
        f"🔹 Для вашего тарифа: от 2 до {max_q}\n\n"
        f"✏️ Напишите число:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )
    query.answer()

def premium_group_click(update: Update, context: CallbackContext):
    query = update.callback_query
    if not query or not query.message:
        return
    
    query.message.reply_text(
        f"{WOW_EMOJIS['error']} 💎 *Эта группа вопросов доступна только в премиум-версии!*\n\n"
        f"🌟 Приобретите премиум, чтобы получить доступ к 10 группам вопросов, "
        f"{MAX_QUESTIONS_PREMIUM} вопросам в тесте и другим преимуществам!\n\n"
        f"👇 Перейдите в магазин:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Перейти в магазин", callback_data="shop")]])
    )
    query.answer()

def add_option(update: Update, context: CallbackContext):
    data = context.user_data.get('create_test')
    if not data or data.get('step') != 'collecting_options':
        return
    
    data['waiting_for_option'] = True
    opt_num = len(data['current_options']) + 1
    
    update.message.reply_text(
        f"✏️ Напишите *вариант ответа №{opt_num}*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

def finish_options(update: Update, context: CallbackContext):
    data = context.user_data.get('create_test')
    if not data or data.get('step') != 'collecting_options':
        return
    
    options = data.get('current_options', [])
    
    if len(options) < MIN_OPTIONS:
        update.message.reply_text(
            f"⚠️ Минимум {MIN_OPTIONS} варианта ответа!\n"
            f"Сейчас добавлено: {len(options)}\n\n"
            f"Добавьте еще вариантов:",
            reply_markup=get_cancel_keyboard()
        )
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
    
    update.message.reply_text(
        f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n"
        f"❓ {data['current_question_text']}\n\n"
        f"📋 Варианты ответов:\n" + "\n".join([f"{i+1}. {o}" for i, o in enumerate(options)]) + "\n\n"
        f"👇 *Выберите ПРАВИЛЬНЫЙ вариант ответа:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def select_correct_answer(update: Update, context: CallbackContext):
    query = update.callback_query
    if not query or not query.message:
        return
    
    try:
        correct_idx = int(query.data.split("_")[1])
    except:
        query.answer()
        return
    
    data = context.user_data.get('create_test')
    if not data:
        query.message.reply_text("Ошибка")
        return
    
    options = data['current_options']
    data['questions_data'].append({
        'text': data['current_question_text'],
        'options': options.copy(),
        'correct': correct_idx
    })
    
    data['current_q'] += 1
    data['step'] = 'selecting_question'
    data['current_question_index'] = (data.get('current_question_index', 0) + 1) % len(data.get('group_questions', [1]))
    
    query.message.reply_text(
        f"✅ *Вопрос {data['current_q']}/{data['total_q']} сохранен!*\n\n"
        f"Правильный ответ: {options[correct_idx]}",
        parse_mode=ParseMode.MARKDOWN
    )
    query.answer()
    
    if data['current_q'] < data['total_q']:
        show_current_question(update, context)
    else:
        finish_creation(update, context, query.from_user.id)

def finish_creation(update, context, user_id):
    data = context.user_data.get('create_test', {})
    if not data:
        return
    
    questions = []
    options = []
    correct_answers = []
    
    for q in data['questions_data']:
        questions.append(q['text'])
        options.append(q['options'])
        correct_answers.append(q['correct'])
    
    test_id = create_test(
        user_id,
        update.effective_user.first_name,
        update.effective_user.username,
        data['title'],
        questions,
        options,
        correct_answers,
        None, None
    )
    
    if test_id:
        use_test(user_id)
        
        text = f"""{WOW_EMOJIS['success']} *ТЕСТ СОЗДАН!* {WOW_EMOJIS['success']}

📝 *Название:* {data['title']}
🔢 *Вопросов:* {data['total_q']}

✨ *Что дальше?*
• Поделись с подругой
• Получай дипломы
• Набирай очки

👇 *Нажми на кнопку, чтобы поделиться тестом*
"""
        update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_confirm_keyboard(test_id))
    else:
        update.message.reply_text(f"{WOW_EMOJIS['error']} Ошибка создания теста", reply_markup=get_main_keyboard())
    
    del context.user_data['create_test']

def cancel_creation(update: Update, context: CallbackContext):
    if 'create_test' in context.user_data:
        del context.user_data['create_test']
    update.message.reply_text("❌ Создание теста отменено.", reply_markup=get_main_keyboard())

def my_tests(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        update.message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    tests = get_user_tests(user_id)
    
    if not tests:
        update.message.reply_text(
            f"{WOW_EMOJIS['test']} *Мои тесты*\n\nУ тебя пока нет созданных тестов.\nСоздай первый тест!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    text = f"{WOW_EMOJIS['crown']} *МОИ ТЕСТЫ* {WOW_EMOJIS['crown']}\n\n"
    for test in tests:
        text += f"📝 *{test['title']}*\n   ❤️ {test['likes']} лайков | 📤 {test['shares']} прохождений\n\n"
    
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

def top_friends(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        update.message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT a.friend_id, a.friend_name, a.friend_username, 
               AVG(a.score) as avg_score, COUNT(a.id) as tests_count
        FROM attempts a
        WHERE a.test_id IN (SELECT id FROM tests WHERE creator_id = ?)
        GROUP BY a.friend_id
        ORDER BY avg_score DESC
        LIMIT 10
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()
    
    if not rows or len(rows) == 0:
        update.message.reply_text(
            f"{WOW_EMOJIS['top']} *ТОП ПОДРУГ*\n\n"
            "Пока никто не проходил твои тесты.\n"
            "Создай тест и отправь подругам!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    text = f"{WOW_EMOJIS['top']} *ТВОЙ ТОП ПОДРУГ* {WOW_EMOJIS['top']}\n\n"
    
    for i, friend in enumerate(rows, 1):
        name = friend['friend_name'] or friend['friend_username'] or f"ID {friend['friend_id']}"
        avg = friend['avg_score']
        
        if i == 1:
            medal = "👑"
        elif i == 2:
            medal = "💎"
        elif i == 3:
            medal = "🌟"
        else:
            medal = "💕"
        
        text += f"{medal} *{name}*\n"
        text += f"   📊 Средний балл: {avg:.1f}%\n"
        text += f"   📝 Тестов пройдено: {friend['tests_count']}\n\n"
    
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

def achievements_list(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        update.message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    points = user.get('total_points', 0)
    rank = get_rank(points)
    streak = user.get('daily_streak', 0)
    created = user.get('tests_created', 0)
    referrals = user.get('referral_count', 0)
    has_premium = is_premium(user_id)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM attempts WHERE friend_id = ?', (user_id,))
    tests_passed = c.fetchone()[0]
    conn.close()
    
    text = f"""{WOW_EMOJIS['achievement']} *ТВОИ ДОСТИЖЕНИЯ* {WOW_EMOJIS['achievement']}

🏆 *Ранг:* {rank['name']}
⭐ *Очки:* {points}
🔥 *Серия дней:* {streak}

📝 *Создано тестов:* {created}
🎯 *Пройдено тестов:* {tests_passed}
👭 *Приглашено подруг:* {referrals}
💎 *Премиум статус:* {'Да' if has_premium else 'Нет'}

🎯 *Следующие ранги:*
"""
    for r in RANKS:
        if r['min_score'] > points:
            text += f"• {r['name']} — нужно {r['min_score'] - points} очков\n"
            break
    
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

def daily_bonus(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    bonus, streak = get_daily_bonus(user_id)
    
    if bonus is None:
        update.message.reply_text(
            f"{WOW_EMOJIS['daily']} Ты уже получала бонус сегодня!\n"
            f"🔥 Серия: {streak} дней\n"
            f"⏰ Возвращайся завтра!",
            reply_markup=get_main_keyboard()
        )
        return
    
    text = f"{WOW_EMOJIS['daily']} *ЕЖЕДНЕВНЫЙ БОНУС!*\n\n+{bonus} очков!\n🔥 Серия: {streak} дней!"
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

def invite(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        update.message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    code = user.get('referral_code', str(update.effective_user.id))
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    
    text = f"""{WOW_EMOJIS['money']} *ПРИГЛАСИ ПОДРУГУ* {WOW_EMOJIS['money']}

🎁 *За каждую подругу ты получаешь +1 тест!*
📌 *Максимум: {MAX_REFERRAL_BONUS} теста*

🔗 *Твоя ссылка:* 
👉 `{link}` 👈

*(нажми на ссылку, чтобы скопировать)*

👭 *Приглашено подруг:* {user.get('referral_count', 0)}

💡 *Отправь ссылку подруге, и она получит 1 тест на старт!*
"""
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

def shop(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        update.message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    points = user.get('total_points', 0)
    rank = get_rank(points)
    has_premium = is_premium(update.effective_user.id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    
    text = f"""{WOW_EMOJIS['shop']} *МАГАЗИН* {WOW_EMOJIS['shop']}

👑 *Ранг:* {rank['name']}
⭐ *Очки:* {points}
📦 *Тестов доступно:* {get_available_tests(update.effective_user.id)}
🔢 *Вопросов в тесте:* до {max_q}

📦 *Пакеты тестов:*
• 5 тестов — 99 ₽
• 10 тестов — 149 ₽
• 20 тестов — 249 ₽
• 50 тестов — 499 ₽

✨ *Дипломы и рамки:*
• Премиум-диплом — 49 ₽
• Золотой диплом — 99 ₽
• Алмазный диплом — 199 ₽
• Золотая рамка — 29 ₽
• Алмазная рамка — 49 ₽
• Королевская рамка — 99 ₽

♾️ *Безлимит:*
• Месяц — 199 ₽
• 3 месяца — 499 ₽
• Год — 1499 ₽

💎 *Преимущества безлимита:*
• Неограниченные тесты
• До {MAX_QUESTIONS_PREMIUM} вопросов в тесте
• 10 групп вопросов
• Эксклюзивные рамки

💰 *Оплата:* напишите @LavaTopBot
"""
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_shop_keyboard())

def stats(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        update.message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    points = user.get('total_points', 0)
    rank = get_rank(points)
    streak = user.get('daily_streak', 0)
    created = user.get('tests_created', 0)
    referrals = user.get('referral_count', 0)
    tests_left = get_available_tests(update.effective_user.id)
    has_premium = is_premium(update.effective_user.id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM attempts WHERE friend_id = ?', (user_id,))
    tests_passed = c.fetchone()[0]
    conn.close()
    
    unlimited_text = ""
    if has_premium:
        unlimited_until = user['unlimited_until']
        if isinstance(unlimited_until, str):
            try:
                unlimited_until = datetime.fromisoformat(unlimited_until)
            except:
                unlimited_until = None
        if unlimited_until and unlimited_until > datetime.now():
            unlimited_text = f"\n♾️ *Безлимит до:* {unlimited_until.strftime('%d.%m.%Y')}"
    
    text = f"""{WOW_EMOJIS['star']} *ТВОЯ СТАТИСТИКА* {WOW_EMOJIS['star']}

👤 *Имя:* {user.get('first_name', 'Подруга')}
🏆 *Ранг:* {rank['name']}
⭐ *Очки:* {points}
🔥 *Серия дней:* {streak}

📝 *Создано тестов:* {created}
🎯 *Пройдено тестов:* {tests_passed}
👭 *Приглашено подруг:* {referrals}

📦 *Тестов доступно:* {tests_left}
🔢 *Максимум вопросов:* {max_q}{unlimited_text}
"""
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

def share_test_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    if not query or not query.message:
        return
    
    try:
        test_id = int(query.data.split("_")[2])
    except:
        query.answer()
        return
    
    test = get_test_by_id(test_id)
    user_id = query.from_user.id
    
    if not test:
        query.message.reply_text("Тест не найден")
        return
    
    available = get_available_tests(user_id)
    if available <= 0:
        query.message.reply_text(
            f"{WOW_EMOJIS['error']} У вас недостаточно тестов!\n\n"
            "🎁 Получите ежедневный бонус\n"
            "👭 Пригласите подругу\n"
            "💎 Или загляните в магазин",
            reply_markup=get_main_keyboard()
        )
        query.answer()
        return
    
    use_test(user_id)
    
    text = f"""{WOW_EMOJIS['friend']} *ПРОЙДИ МОЙ ТЕСТ!* {WOW_EMOJIS['friend']}

👤 *Приглашение от:* {query.from_user.first_name}
📝 *Название:* {test['title']}

💫 *Узнай, насколько хорошо ты меня знаешь!*

👇 *Нажми на кнопку, чтобы поделиться с подругой*
"""
    
    query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_confirm_keyboard(test_id))
    query.answer()

def start_test(update: Update, context: CallbackContext):
    query = update.callback_query
    if not query or not query.message:
        return
    
    try:
        test_id = int(query.data.split("_")[2])
    except:
        query.answer()
        return
    
    test = get_test_by_id(test_id)
    user_id = query.from_user.id
    
    if not test:
        query.message.reply_text("Тест не найден")
        return
    
    if not can_attempt_test(test_id, user_id):
        query.message.reply_text(
            f"{WOW_EMOJIS['error']} Ты уже проходила этот тест!\n"
            "Каждую подругу можно проверить только один раз 💕"
        )
        return
    
    context.user_data['taking_test'] = {
        'test': test,
        'current': 0,
        'answers': [],
        'options': test['options'],
        'correct_answers': test['correct_answers'],
        'test_id': test_id
    }
    
    send_question(query, context, test['questions'][0], test['options'][0], 1, len(test['questions']))
    query.answer()

def send_question(query, context, question, options, current, total):
    text = f"{WOW_EMOJIS['star']} *Вопрос {current}/{total}* {WOW_EMOJIS['star']}\n\n📝 {question}"
    
    keyboard = []
    row = []
    for i, opt in enumerate(options):
        row.append(InlineKeyboardButton(opt, callback_data=f"answer_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

def take_test_answer(update: Update, context: CallbackContext):
    query = update.callback_query
    if not query or not query.message:
        return
    
    try:
        answer_idx = int(query.data.split("_")[1])
    except:
        query.answer()
        return
    
    data = context.user_data.get('taking_test')
    if not data:
        query.message.reply_text("Тест не найден")
        return
    
    data['answers'].append(answer_idx)
    data['current'] += 1
    
    if data['current'] < len(data['test']['questions']):
        send_question(query, context, 
                     data['test']['questions'][data['current']],
                     data['options'][data['current']],
                     data['current'] + 1, len(data['test']['questions']))
    else:
        finish_test(query, context, data)
        del context.user_data['taking_test']
    
    query.answer()

def finish_test(query, context, data):
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
    
    text = f"{WOW_EMOJIS['crown']} *Результат:* {score:.1f}%\n\n{get_friendship_status(score)}"
    query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

def handle_buttons(update: Update, context: CallbackContext):
    text = update.message.text
    
    if text == f"{WOW_EMOJIS['test']} Создать тест":
        create_test_start(update, context)
    elif text == f"{WOW_EMOJIS['crown']} Мои тесты":
        my_tests(update, context)
    elif text == f"{WOW_EMOJIS['achievement']} Мои ачивки":
        achievements_list(update, context)
    elif text == f"{WOW_EMOJIS['daily']} Ежедневный бонус":
        daily_bonus(update, context)
    elif text == f"{WOW_EMOJIS['money']} Пригласить подруг":
        invite(update, context)
    elif text == f"{WOW_EMOJIS['shop']} Магазин":
        shop(update, context)
    elif text == "📊 Статистика":
        stats(update, context)
    elif text == "📋 Топ подруг":
        top_friends(update, context)
    elif text == "➕ Добавить вариант":
        add_option(update, context)
    elif text == "✅ Готово":
        finish_options(update, context)
    else:
        data = context.user_data.get('create_test')
        if data:
            handle_create_test(update, context)
        else:
            update.message.reply_text("Используй кнопки меню!", reply_markup=get_main_keyboard())

def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    if not query or not query.message:
        return
    
    data = query.data
    if not data:
        query.answer()
        return
    
    try:
        if data.startswith("group_"):
            select_question_group(update, context)
        elif data.startswith("premium_group_"):
            premium_group_click(update, context)
        elif data == "next_question":
            next_question(update, context)
        elif data == "select_question":
            select_current_question(update, context)
        elif data.startswith("correct_"):
            select_correct_answer(update, context)
        elif data.startswith("share_test_"):
            share_test_callback(update, context)
        elif data.startswith("start_test_"):
            start_test(update, context)
        elif data.startswith("answer_"):
            take_test_answer(update, context)
        elif data.startswith("buy_"):
            item = data[4:]
            query.message.reply_text(f"💎 *Покупка:* {item}\n\n💰 Оплата: напишите @LavaTopBot", parse_mode=ParseMode.MARKDOWN)
        elif data == "shop":
            shop(update, context)
        else:
            query.answer()
    except Exception as e:
        logger.error(f"Ошибка в callback: {e}")
        try:
            query.message.reply_text("❌ Произошла ошибка", reply_markup=get_main_keyboard())
        except:
            pass
    
    query.answer()

def error_handler(update, context):
    logger.error(f"Ошибка: {context.error}")

def kill_other_bots():
    try:
        import psutil
        current_pid = os.getpid()
        current_file = os.path.abspath(__file__)
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['pid'] == current_pid:
                    continue
                if 'python' in proc.info['name'].lower():
                    cmdline = proc.info['cmdline']
                    if cmdline and len(cmdline) > 1 and current_file in ' '.join(cmdline):
                        logger.warning(f"Завершаю старый процесс с PID: {proc.info['pid']}")
                        proc.terminate()
                        proc.wait(timeout=3)
            except:
                pass
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"Ошибка: {e}")

def safe_start(updater):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            updater.start_polling(timeout=60, poll_interval=1.0, drop_pending_updates=True)
            logger.info("Бот запущен через Tor")
            return True
        except Conflict as e:
            logger.error(f"Конфликт: {e}")
            if attempt < max_retries - 1:
                kill_other_bots()
                time.sleep(10)
            else:
                return False
        except (NetworkError, TimedOut) as e:
            logger.error(f"Сетевая ошибка: {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
            else:
                return False
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
            else:
                return False
    return False

def main():
    logger.info("Проверка Tor соединения...")
    try:
        import requests
        proxies = {
            "http": "socks5h://127.0.0.1:9050",
            "https": "socks5h://127.0.0.1:9050"
        }
        r = requests.get("https://check.torproject.org/", proxies=proxies, timeout=15)
        if "Congratulations" in r.text or "This browser is configured to use Tor" in r.text:
            logger.info("Tor прокси работает!")
        else:
            logger.warning("Tor прокси не обнаружен, но бот попробует подключиться")
    except Exception as e:
        logger.warning(f"Не удалось проверить Tor: {e}")
    
    kill_other_bots()
    init_db()
    
    updater = Updater(TOKEN, use_context=True, request_kwargs={'read_timeout': 60, 'connect_timeout': 60})
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    
    dp.add_handler(MessageHandler(Filters.regex(f"^{WOW_EMOJIS['test']} Создать тест$"), create_test_start))
    dp.add_handler(MessageHandler(Filters.regex(f"^{WOW_EMOJIS['crown']} Мои тесты$"), my_tests))
    dp.add_handler(MessageHandler(Filters.regex(f"^{WOW_EMOJIS['achievement']} Мои ачивки$"), achievements_list))
    dp.add_handler(MessageHandler(Filters.regex(f"^{WOW_EMOJIS['daily']} Ежедневный бонус$"), daily_bonus))
    dp.add_handler(MessageHandler(Filters.regex(f"^{WOW_EMOJIS['money']} Пригласить подруг$"), invite))
    dp.add_handler(MessageHandler(Filters.regex(f"^{WOW_EMOJIS['shop']} Магазин$"), shop))
    dp.add_handler(MessageHandler(Filters.regex("^📊 Статистика$"), stats))
    dp.add_handler(MessageHandler(Filters.regex("^📋 Топ подруг$"), top_friends))
    
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_buttons))
    dp.add_handler(MessageHandler(Filters.text & Filters.regex("^❌ Отмена$"), cancel_creation))
    
    dp.add_handler(CallbackQueryHandler(callback_handler))
    
    dp.add_error_handler(error_handler)
    
    if safe_start(updater):
        logger.info("Бот @PodrugaTestBot успешно запущен через Tor!")
        updater.idle()
    else:
        logger.error("Не удалось запустить бота. Проверьте:")
        logger.error("1. Tor Browser запущен и слушает порт 9050")
        logger.error("2. Интернет-соединение работает")
        logger.error("3. Токен бота правильный")

if __name__ == "__main__":
    main()
