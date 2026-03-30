#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бот для создания тестов для подруг @PodrugaTestBot
Версия: 27.0 - ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ
"""

import logging
import json
import sqlite3
import random
import os
import httpx
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
DAILY_BONUS_POINTS = 10
MAX_REFERRAL_BONUS = 3
MAX_OPTIONS = 4
MIN_OPTIONS = 2
MAX_QUESTIONS_FREE = 5
MAX_QUESTIONS_PREMIUM = 10

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
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
    'star': '⭐', 'heart': '💖', 'daily': '🎁',
    'achievement': '🏆', 'shop': '🛍️', 'money': '💰',
    'top': '🏆', 'back': '🔙', 'stats': '📊'
}

# === БАЗА ДАННЫХ ===
def get_db():
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
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
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        raise
    finally:
        if conn:
            conn.close()

init_db()

# === ФУНКЦИИ БАЗЫ ДАННЫХ ===
def get_user(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def create_user(user_id, username=None, first_name=None, referred_by=None):
    conn = get_db()
    try:
        c = conn.cursor()
        code = f"{user_id}{random.randint(1000, 9999)}"
        c.execute('''INSERT INTO users 
            (user_id, username, first_name, referral_code, referred_by, tests_available)
            VALUES (?, ?, ?, ?, ?, ?)''',
            (user_id, username, first_name, code, referred_by, START_TESTS))
        
        if referred_by:
            referrer = get_user(referred_by)
            if referrer and referrer.get('referral_count', 0) < MAX_REFERRAL_BONUS:
                c.execute('UPDATE users SET tests_available = tests_available + 1, referral_count = referral_count + 1 WHERE user_id = ?', 
                         (referred_by,))
                c.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)', 
                         (referred_by, user_id))
        conn.commit()
        return True
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
        c.execute('UPDATE users SET tests_available = tests_available + ? WHERE user_id = ?', 
                 (count, user_id))
        conn.commit()
        return True
    finally:
        conn.close()

def use_test(user_id):
    user = get_user(user_id)
    
    if user and user.get('unlimited_until'):
        try:
            unlimited_until = datetime.fromisoformat(user['unlimited_until'])
            if unlimited_until > datetime.now():
                return True
        except (ValueError, TypeError):
            pass
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('UPDATE users SET tests_available = tests_available - 1 WHERE user_id = ? AND tests_available > 0', 
                 (user_id,))
        conn.commit()
        return c.rowcount > 0
    finally:
        conn.close()

def get_available_tests(user_id):
    user = get_user(user_id)
    if not user:
        return START_TESTS
    
    if user.get('unlimited_until'):
        try:
            unlimited_until = datetime.fromisoformat(user['unlimited_until'])
            if unlimited_until > datetime.now():
                return 999
        except (ValueError, TypeError):
            pass
    
    return user.get('tests_available', START_TESTS)

def add_points(user_id, points):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('UPDATE users SET total_points = total_points + ? WHERE user_id = ?', 
                 (points, user_id))
        conn.commit()
        return True
    finally:
        conn.close()

def get_rank(score):
    for rank in reversed(RANKS):
        if score >= rank['min_score']:
            return rank
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
        except (ValueError, TypeError):
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
        return test_id
    except Exception as e:
        logger.error(f"Ошибка создания теста: {e}")
        return None
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
            try:
                test['questions'] = json.loads(test['questions']) if test['questions'] else []
                test['options'] = json.loads(test['options']) if test['options'] else []
                test['correct_answers'] = json.loads(test['correct_answers']) if test['correct_answers'] else []
            except json.JSONDecodeError:
                test['questions'] = []
                test['options'] = []
                test['correct_answers'] = []
            return test
        return None
    finally:
        conn.close()

def get_user_tests(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT id, title, likes, shares, created_at FROM tests WHERE creator_id = ? ORDER BY created_at DESC', 
                 (user_id,))
        rows = c.fetchall()
        return rows
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
        row = c.fetchone()
        return row is None
    finally:
        conn.close()

def save_attempt(test_id, friend_id, friend_name, friend_username, answers, score):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''INSERT INTO attempts (test_id, friend_id, friend_name, friend_username, answers, score)
            VALUES (?, ?, ?, ?, ?, ?)''', 
            (test_id, friend_id, friend_name, friend_username, json.dumps(answers), score))
        c.execute('UPDATE tests SET shares = shares + 1 WHERE id = ?', (test_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения попытки: {e}")
        return False
    finally:
        conn.close()

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

# === КЛАВИАТУРЫ ===
def get_main_keyboard():
    keyboard = [
        [KeyboardButton(f"{WOW_EMOJIS['test']} Создать тест"), KeyboardButton(f"{WOW_EMOJIS['crown']} Мои тесты")],
        [KeyboardButton(f"{WOW_EMOJIS['stats']} Моя статистика"), KeyboardButton(f"{WOW_EMOJIS['daily']} Ежедневный бонус")],
        [KeyboardButton(f"{WOW_EMOJIS['money']} Пригласить подруг"), KeyboardButton(f"{WOW_EMOJIS['shop']} Магазин")],
        [KeyboardButton(f"{WOW_EMOJIS['top']} Топ подруг")]
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
    keyboard = [
        [InlineKeyboardButton("📦 5 тестов — 79 ₽", callback_data="buy_tests_5"), 
         InlineKeyboardButton("📦 10 тестов — 129 ₽", callback_data="buy_tests_10")],
        [InlineKeyboardButton("📦 20 тестов — 199 ₽", callback_data="buy_tests_20"), 
         InlineKeyboardButton("📦 50 тестов — 449 ₽", callback_data="buy_tests_50")],
        [InlineKeyboardButton("💎 Премиум 30 дней — 299 ₽", callback_data="buy_premium_month"), 
         InlineKeyboardButton("💎 Премиум 3 мес — 699 ₽", callback_data="buy_premium_3months")],
        [InlineKeyboardButton("💎 Премиум ГОД — 1999 ₽", callback_data="buy_premium_year"),
         InlineKeyboardButton("✨ Премиум-диплом — 49 ₽", callback_data="buy_premium_diploma")],
        [InlineKeyboardButton("🥇 Золотой диплом — 99 ₽", callback_data="buy_gold_diploma"),
         InlineKeyboardButton("🖼️ Золотая рамка — 29 ₽", callback_data="buy_frame_gold")],
        [InlineKeyboardButton("🖼️ Алмазная рамка — 49 ₽", callback_data="buy_frame_diamond"),
         InlineKeyboardButton("👑 Королевская рамка — 99 ₽", callback_data="buy_frame_royal")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_share_confirm_keyboard(test_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, отправить", callback_data=f"confirm_share_{test_id}"),
         InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_share")],
        [InlineKeyboardButton("👭 Отправить подруге", 
            switch_inline_query=f"🎉 @{BOT_USERNAME} - твоя подруга приглашает тебя пройти тест! https://t.me/{BOT_USERNAME}?start=test_{test_id}")]
    ])

def get_start_test_keyboard(test_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_test_{test_id}")
    ]])

# === ОСНОВНЫЕ ХЕНДЛЕРЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None
    
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
                    text = f"{WOW_EMOJIS['friend']} *ПРОЙДИ ТЕСТ ОТ ПОДРУГИ!*\n\n📝 {test['title']}"
                    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, 
                                                   reply_markup=get_start_test_keyboard(test_id))
                    return
            except (IndexError, ValueError) as e:
                logger.error(f"Ошибка парсинга test_id: {e}")
    
    existing = get_user(user.id)
    if not existing:
        create_user(user.id, user.username, user.first_name, referred_by)
    else:
        update_user(user.id, user.username, user.first_name)
    
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

async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    available = get_available_tests(user_id)
    
    if available <= 0:
        await update.message.reply_text(
            f"{WOW_EMOJIS['error']} У тебя закончились тесты!\n\n"
            "🎁 Получи ежедневный бонус или пригласи подругу!\n"
            "💎 Или загляни в магазин",
            reply_markup=get_main_keyboard()
        )
        return
    
    context.user_data['create_test'] = {
        'step': 'title',
        'questions_data': []
    }
    logger.info(f"✅ Создана новая сессия создания теста для {user_id}")
    
    await update.message.reply_text(
        f"{WOW_EMOJIS['test']} *Создаем тест!*\n\n"
        f"📦 *Доступно тестов:* {available}\n\n"
        "Придумай название (например: «Насколько хорошо ты меня знаешь?»):\n\n"
        "❌ Отмена - чтобы выйти",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'create_test' in context.user_data:
        logger.info(f"❌ Отмена создания теста пользователем {update.effective_user.id}")
        del context.user_data['create_test']
    await update.message.reply_text("❌ Создание теста отменено.", reply_markup=get_main_keyboard())

async def handle_create_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data:
        logger.warning("handle_create_test: нет данных create_test")
        return
    
    text = update.message.text
    
    if text == "❌ Отмена":
        await cancel_creation(update, context)
        return
    
    if text == f"{WOW_EMOJIS['back']} Назад":
        if data.get('step') == 'waiting_question_count':
            data['step'] = 'group'
            user_id = update.effective_user.id
            await update.message.reply_text(
                "✨ Выбери *группу вопросов*:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_question_groups_keyboard(user_id)
            )
        elif data.get('step') == 'collecting_options':
            data['step'] = 'selecting_question'
            await show_current_question(update, context)
        return
    
    step = data.get('step')
    logger.info(f"handle_create_test: step={step}, text={text[:50]}")
    
    if step == 'title':
        if len(text.strip()) < 3:
            await update.message.reply_text("⚠️ Название должно содержать минимум 3 символа. Попробуйте еще раз:")
            return
        data['title'] = text.strip()
        data['step'] = 'group'
        logger.info(f"✅ Сохранено название теста: {data['title']}")
        
        user_id = update.effective_user.id
        await update.message.reply_text(
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
                await update.message.reply_text(f"⚠️ Минимум 2 вопроса! Напишите число от 2 до {max_q}:")
                return
            if count > max_q:
                await update.message.reply_text(f"⚠️ Для вашего тарифа максимум {max_q} вопросов! Напишите число от 2 до {max_q}:")
                return
            
            data['total_q'] = count
            data['current_q'] = 0
            data['step'] = 'selecting_question'
            
            group = data.get('group')
            logger.info(f"Группа для вопросов: {group}")
            data['group_questions'] = QUESTIONS_BY_GROUP.get(group, []).copy()
            random.shuffle(data['group_questions'])
            data['current_question_index'] = 0
            
            if len(data['group_questions']) < count:
                await update.message.reply_text(
                    f"⚠️ В выбранной группе недостаточно вопросов. Выберите другую группу или уменьшите количество вопросов до {len(data['group_questions'])}.",
                    reply_markup=get_back_keyboard()
                )
                return
            
            logger.info(f"✅ Начинаем создание вопросов. Всего: {count}")
            await show_current_question(update, context)
        except ValueError:
            await update.message.reply_text("⚠️ Пожалуйста, напишите число (например: 5):")
    
    elif step == 'collecting_options':
        if data.get('waiting_for_option'):
            option_text = text.strip()
            if option_text:
                if len(option_text) > 100:
                    await update.message.reply_text("⚠️ Вариант ответа слишком длинный (максимум 100 символов):")
                    return
                data['current_options'].append(option_text)
                data['waiting_for_option'] = False
                logger.info(f"Добавлен вариант {len(data['current_options'])}: {option_text[:30]}")
                
                await update.message.reply_text(
                    f"✅ *Вариант {len(data['current_options'])} добавлен!*\n\n"
                    f"📋 Текущие варианты:\n" + "\n".join([f"{i+1}. {o}" for i, o in enumerate(data['current_options'])]),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_options_keyboard()
                )

async def show_current_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data:
        logger.error("show_current_question: нет данных create_test")
        return
    
    current_idx = data.get('current_question_index', 0)
    questions = data.get('group_questions', [])
    
    if current_idx >= len(questions):
        current_idx = 0
        data['current_question_index'] = 0
    
    question_text = questions[current_idx]
    data['current_question_text'] = question_text
    logger.info(f"Показываем вопрос {data['current_q'] + 1}/{data['total_q']}: {question_text[:50]}")
    
    await update.message.reply_text(
        f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{question_text}\n\n"
        f"❓ Что делать с этим вопросом?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_question_keyboard()
    )

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = context.user_data.get('create_test')
    if not data:
        await query.message.reply_text("Ошибка: сессия создания теста потеряна. Начните заново.", 
                                      reply_markup=get_main_keyboard())
        return
    
    current_idx = data.get('current_question_index', 0)
    questions = data.get('group_questions', [])
    
    current_idx = (current_idx + 1) % len(questions)
    data['current_question_index'] = current_idx
    
    question_text = questions[current_idx]
    data['current_question_text'] = question_text
    
    try:
        await query.message.edit_text(
            f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{question_text}\n\n"
            f"❓ Что делать с этим вопросом?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_question_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при смене вопроса: {e}")

async def select_current_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = context.user_data.get('create_test')
    if not data:
        await query.message.reply_text("Ошибка: сессия создания теста потеряна. Начните заново.",
                                      reply_markup=get_main_keyboard())
        return
    
    data['step'] = 'collecting_options'
    data['current_options'] = []
    data['waiting_for_option'] = True
    logger.info(f"Начинаем сбор вариантов для вопроса {data['current_q'] + 1}")
    
    try:
        await query.message.edit_text(
            f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n"
            f"❓ {data['current_question_text']}\n\n"
            f"✏️ Напишите *вариант ответа №1*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при выборе вопроса: {e}")

async def select_question_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    logger.info(f"=== select_question_group вызвана ===")
    logger.info(f"Callback data: {query.data}")
    
    try:
        group = query.data.split("_")[1]
        logger.info(f"✅ Выбрана группа: {group}")
    except IndexError:
        logger.error(f"Ошибка: неверный формат callback_data: {query.data}")
        await query.message.reply_text("Ошибка выбора группы")
        return
    
    data = context.user_data.get('create_test')
    
    if not data:
        logger.error("❌ Нет сессии создания теста! Создаем новую...")
        data = {
            'step': 'group',
            'questions_data': []
        }
        context.user_data['create_test'] = data
    else:
        logger.info(f"✅ Найдена сессия создания теста. Step: {data.get('step')}, Title: {data.get('title', 'не задан')}")
    
    data['group'] = group
    data['step'] = 'waiting_question_count'
    
    user_id = query.from_user.id
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    
    group_name = PREMIUM_QUESTION_GROUPS.get(group, FREE_QUESTION_GROUPS.get(group))
    if not group_name:
        group_name = "Вопросы"
    
    logger.info(f"✅ Переход к вводу количества вопросов для группы {group_name}")
    
    try:
        await query.message.edit_text(
            f"✨ Выбрана группа: {group_name}\n\n"
            f"📊 *Сколько вопросов будет в тесте?*\n"
            f"🔹 Для вашего тарифа: от 2 до {max_q}\n\n"
            f"✏️ Напишите число:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения: {e}")
        await query.message.reply_text(
            f"✨ Выбрана группа: {group_name}\n\n"
            f"📊 *Сколько вопросов будет в тесте?*\n"
            f"🔹 Для вашего тарифа: от 2 до {max_q}\n\n"
            f"✏️ Напишите число:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )

async def premium_group_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        f"{WOW_EMOJIS['error']} 💎 *Эта группа вопросов доступна только в премиум-версии!*\n\n"
        f"🌟 Приобретите премиум, чтобы получить доступ к 10 группам вопросов, "
        f"{MAX_QUESTIONS_PREMIUM} вопросам в тесте и другим преимуществам!\n\n"
        f"👇 Перейдите в магазин:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Перейти в магазин", callback_data="open_shop")]])
    )

async def add_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('create_test')
    if not data or data.get('step') != 'collecting_options':
        return
    
    if len(data['current_options']) >= MAX_OPTIONS:
        await update.message.reply_text(
            f"⚠️ Максимум {MAX_OPTIONS} вариантов ответа!\n"
            f"Нажмите «✅ Готово», чтобы продолжить.",
            reply_markup=get_options_keyboard()
        )
        return
    
    data['waiting_for_option'] = True
    opt_num = len(data['current_options']) + 1
    
    await update.message.reply_text(
        f"✏️ Напишите *вариант ответа №{opt_num}*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

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
        await update.message.reply_text(
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
    
    await update.message.reply_text(
        f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n"
        f"❓ {data['current_question_text']}\n\n"
        f"📋 Варианты ответов:\n" + "\n".join([f"{i+1}. {o}" for i, o in enumerate(options)]) + "\n\n"
        f"👇 *Выберите ПРАВИЛЬНЫЙ вариант ответа:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def select_correct_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        correct_idx = int(query.data.split("_")[1])
    except (IndexError, ValueError):
        await query.message.reply_text("Ошибка выбора ответа")
        return
    
    data = context.user_data.get('create_test')
    if not data:
        await query.message.reply_text("Ошибка: сессия создания теста потеряна")
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
    
    logger.info(f"✅ Сохранен вопрос {data['current_q']}/{data['total_q']}")
    
    await query.message.reply_text(
        f"✅ *Вопрос {data['current_q']}/{data['total_q']} сохранен!*\n\n"
        f"Правильный ответ: {options[correct_idx]}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    if data['current_q'] < data['total_q']:
        await show_current_question(update, context)
    else:
        await finish_creation(update, context, query.from_user.id)

async def finish_creation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
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
        context.user_data['pending_test'] = {
            'test_id': test_id,
            'title': data['title'],
            'total_q': data['total_q']
        }
        
        text = f"""{WOW_EMOJIS['success']} *ТЕСТ СОЗДАН!* {WOW_EMOJIS['success']}

📝 *Название:* {data['title']}
🔢 *Вопросов:* {data['total_q']}

✨ *Что дальше?*
• Поделись с подругой
• Получай дипломы
• Набирай очки

👇 *Подтверди отправку, чтобы списать тест*
"""
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, 
                                      reply_markup=get_share_confirm_keyboard(test_id))
    else:
        await update.message.reply_text(f"{WOW_EMOJIS['error']} Ошибка создания теста", 
                                       reply_markup=get_main_keyboard())
    
    del context.user_data['create_test']
    logger.info(f"✅ Тест {test_id} создан пользователем {user_id}")

# === ОСТАЛЬНЫЕ ХЕНДЛЕРЫ ===
async def my_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tests = get_user_tests(user_id)
    
    if not tests:
        await update.message.reply_text(
            f"{WOW_EMOJIS['test']} *Мои тесты*\n\nУ тебя пока нет созданных тестов.\nСоздай первый тест!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    text = f"{WOW_EMOJIS['crown']} *МОИ ТЕСТЫ* {WOW_EMOJIS['crown']}\n\n"
    for test in tests:
        text += f"📝 *{test['title']}*\n   ❤️ {test['likes']} лайков | 📤 {test['shares']} прохождений\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def top_friends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
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
            LIMIT 10
        ''', (user_id,))
        rows = c.fetchall()
    finally:
        conn.close()
    
    if not rows or len(rows) == 0:
        await update.message.reply_text(
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
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = "💕"
        
        text += f"{medal} *{name}*\n"
        text += f"   📊 Средний балл: {avg:.1f}%\n"
        text += f"   📝 Тестов пройдено: {friend['tests_count']}\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    points = user.get('total_points', 0)
    rank = get_rank(points)
    streak = user.get('daily_streak', 0)
    created = user.get('tests_created', 0)
    referrals = user.get('referral_count', 0)
    tests_left = get_available_tests(user_id)
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM attempts WHERE friend_id = ?', (user_id,))
        tests_passed = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) + 1 FROM users WHERE total_points > ?', (points,))
        rating = c.fetchone()[0]
    finally:
        conn.close()
    
    unlimited_text = ""
    if has_premium:
        unlimited_until = user['unlimited_until']
        if unlimited_until:
            try:
                unlimited_until = datetime.fromisoformat(unlimited_until)
                if unlimited_until > datetime.now():
                    unlimited_text = f"\n♾️ *Безлимит до:* {unlimited_until.strftime('%d.%m.%Y')}"
            except (ValueError, TypeError):
                pass
    
    text = f"""{WOW_EMOJIS['stats']} *СТАТИСТИКА ПРОФИЛЯ* {WOW_EMOJIS['stats']}

👤 *Имя:* {user.get('first_name', 'Подруга')}
🏆 *Ранг:* {rank['name']}
⭐ *Очки:* {points}
📊 *Место в рейтинге:* {rating}
🔥 *Серия дней:* {streak}

📝 *Создано тестов:* {created}
🎯 *Пройдено тестов:* {tests_passed}
👭 *Приглашено подруг:* {referrals}

📦 *Тестов доступно:* {tests_left}
🔢 *Максимум вопросов:* {max_q}{unlimited_text}

✨ *До следующего ранга:*
"""
    for r in RANKS:
        if r['min_score'] > points:
            need = r['min_score'] - points
            text += f"• {r['name']} — нужно {need} очков\n"
            break
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = get_daily_bonus(user_id)
    
    if result[0] is None:
        await update.message.reply_text(
            f"{WOW_EMOJIS['daily']} 🎁 *Ежедневный бонус*\n\n"
            f"Ты уже получала бонус сегодня!\n"
            f"🔥 Серия: {result[1]} дней\n"
            f"⏰ Возвращайся завтра!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    bonus, streak = result
    text = f"{WOW_EMOJIS['daily']} 🎁 *ЕЖЕДНЕВНЫЙ БОНУС!*\n\n✨ *+{bonus} очков!*\n🔥 *Серия:* {streak} дней\n\n💫 Приходи завтра снова!"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    code = user.get('referral_code', str(update.effective_user.id))
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    
    text = f"""{WOW_EMOJIS['money']} *ПРИГЛАСИ ПОДРУГУ* {WOW_EMOJIS['money']}

🎁 *За каждую подругу ты получаешь +1 тест!*
📌 *Максимум:* {MAX_REFERRAL_BONUS} теста

🔗 *Твоя ссылка:* 
{link}

👭 *Приглашено подруг:* {user.get('referral_count', 0)}

💡 *Отправь ссылку подруге, и она получит 1 тест на старт!*

✨ *Как это работает:*
1. Подруга переходит по ссылке
2. Начинает использовать бота
3. Ты получаешь +1 тест (максимум {MAX_REFERRAL_BONUS})"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    points = user.get('total_points', 0)
    rank = get_rank(points)
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    
    text = f"""{WOW_EMOJIS['shop']} *МАГАЗИН* {WOW_EMOJIS['shop']}

👑 *Ранг:* {rank['name']}
⭐ *Очки:* {points}
📦 *Тестов доступно:* {get_available_tests(user_id)}
🔢 *Вопросов в тесте:* до {max_q}

📦 *ПАКЕТЫ ТЕСТОВ:*
• 5 тестов — 79 ₽ (15.8 ₽/тест)
• 10 тестов — 129 ₽ (12.9 ₽/тест)
• 20 тестов — 199 ₽ (9.95 ₽/тест)
• 50 тестов — 449 ₽ (8.98 ₽/тест)

💎 *ПРЕМИУМ ПОДПИСКА:*
• 30 дней — 299 ₽ (10 ₽/день)
• 3 месяца — 699 ₽ (7.7 ₽/день)
• ГОД — 1999 ₽ (5.5 ₽/день)

✨ *Преимущества премиума:*
✅ Неограниченные тесты
✅ До {MAX_QUESTIONS_PREMIUM} вопросов
✅ 10 групп вопросов
✅ Эксклюзивные рамки

🎨 *ДИПЛОМЫ И РАМКИ:*
• Премиум-диплом — 49 ₽
• Золотой диплом — 99 ₽
• Золотая рамка — 29 ₽
• Алмазная рамка — 49 ₽
• Королевская рамка — 99 ₽

💡 *СОВЕТ:* Премиум выгоднее, чем покупка тестов по отдельности!
Если вы создаете более 10 тестов в месяц — берите премиум! 🎯

💰 *Оплата:* напишите @LavaTopBot"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_shop_keyboard())

async def confirm_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        test_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.message.reply_text("Ошибка подтверждения")
        return
    
    user_id = query.from_user.id
    
    if use_test(user_id):
        await query.message.reply_text(
            f"{WOW_EMOJIS['success']} *Тест готов к отправке!*\n\n"
            f"Поделитесь им с подругой через кнопку ниже 👇",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_share_confirm_keyboard(test_id)
        )
    else:
        await query.message.reply_text(
            f"{WOW_EMOJIS['error']} Не удалось списать тест. Возможно, у вас недостаточно тестов.",
            reply_markup=get_main_keyboard()
        )
    
    if 'pending_test' in context.user_data:
        del context.user_data['pending_test']

async def cancel_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if 'pending_test' in context.user_data:
        del context.user_data['pending_test']
        await query.message.reply_text(
            f"❌ Отправка теста отменена. Тест не был списан.",
            reply_markup=get_main_keyboard()
        )
    else:
        await query.message.reply_text(
            f"❌ Отмена",
            reply_markup=get_main_keyboard()
        )

async def back_to_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    try:
        await query.message.edit_text(
            "✨ Выбери *группу вопросов*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_question_groups_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Ошибка при возврате к группам: {e}")
        await query.message.reply_text(
            "✨ Выбери *группу вопросов*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_question_groups_keyboard(user_id)
        )

async def open_shop_from_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        await query.message.delete()
    except:
        pass
    
    await shop(update, context)

async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        test_id = int(query.data.split("_")[2])
    except (IndexError, ValueError) as e:
        logger.error(f"Ошибка извлечения test_id из {query.data}: {e}")
        await query.message.reply_text("Ошибка: неверный формат теста")
        return
    
    test = get_test_by_id(test_id)
    user_id = query.from_user.id
    
    if not test:
        await query.message.reply_text("Тест не найден")
        return
    
    if not can_attempt_test(test_id, user_id):
        await query.message.reply_text(
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
    
    await send_question(query, context, test['questions'][0], test['options'][0], 1, len(test['questions']))

async def send_question(query, context, question, options, current, total):
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
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, 
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def take_test_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        answer_idx = int(query.data.split("_")[1])
    except (IndexError, ValueError):
        await query.message.reply_text("Ошибка выбора ответа")
        return
    
    data = context.user_data.get('taking_test')
    if not data:
        await query.message.reply_text("Тест не найден")
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
    correct_answers = data['correct_answers']
    user = query.from_user
    
    score = 0
    for i, ans in enumerate(answers):
        if i < len(correct_answers) and ans == correct_answers[i]:
            score += 100 / len(test['questions'])
    
    save_attempt(data['test_id'], user.id, user.first_name, user.username, answers, score)
    add_points(user.id, int(score))
    
    text = f"{WOW_EMOJIS['crown']} *Результат:* {score:.1f}%\n\n{get_friendship_status(score)}"
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == f"{WOW_EMOJIS['test']} Создать тест":
        await create_test_start(update, context)
    elif text == f"{WOW_EMOJIS['crown']} Мои тесты":
        await my_tests(update, context)
    elif text == f"{WOW_EMOJIS['stats']} Моя статистика":
        await my_stats(update, context)
    elif text == f"{WOW_EMOJIS['daily']} Ежедневный бонус":
        await daily_bonus(update, context)
    elif text == f"{WOW_EMOJIS['money']} Пригласить подруг":
        await invite(update, context)
    elif text == f"{WOW_EMOJIS['shop']} Магазин":
        await shop(update, context)
    elif text == f"{WOW_EMOJIS['top']} Топ подруг":
        await top_friends(update, context)
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
    
    logger.info(f"📨 Получен callback: {data}")
    
    if data.startswith("group_"):
        await select_question_group(update, context)
    elif data.startswith("premium_group_"):
        await premium_group_click(update, context)
    elif data == "next_question":
        await next_question(update, context)
    elif data == "select_question":
        await select_current_question(update, context)
    elif data == "back_to_groups":
        await back_to_groups(update, context)
    elif data.startswith("correct_"):
        await select_correct_answer(update, context)
    elif data.startswith("confirm_share_"):
        await confirm_share(update, context)
    elif data == "cancel_share":
        await cancel_share(update, context)
    elif data.startswith("start_test_"):
        await start_test(update, context)
    elif data.startswith("answer_"):
        await take_test_answer(update, context)
    elif data == "open_shop":
        await open_shop_from_premium(update, context)
    elif data.startswith("buy_"):
        item = data[4:]
        await query.message.reply_text(
            f"💎 *Покупка:* {item}\n\n"
            f"💰 Оплата: напишите @LavaTopBot\n\n"
            f"✨ Для активации премиума напишите @LavaTopBot с чеком", 
            parse_mode=ParseMode.MARKDOWN
        )
    elif data == "shop":
        await shop(update, context)
    else:
        logger.warning(f"Неизвестный callback: {data}")
    
    await query.answer()

def main():
    try:
        timeout = httpx.Timeout(30.0, connect=30.0, read=30.0, write=30.0)
        http_client = httpx.AsyncClient(timeout=timeout)
        
        app = Application.builder().token(TOKEN).http_client(http_client).build()
        
        app.add_handler(CommandHandler("start", start))
        
        app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['test']} Создать тест$"), create_test_start))
        app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['crown']} Мои тесты$"), my_tests))
        app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['stats']} Моя статистика$"), my_stats))
        app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['daily']} Ежедневный бонус$"), daily_bonus))
        app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['money']} Пригласить подруг$"), invite))
        app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['shop']} Магазин$"), shop))
        app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['top']} Топ подруг$"), top_friends))
        
        app.add_handler(MessageHandler(filters.Regex("^➕ Добавить вариант$"), add_option))
        app.add_handler(MessageHandler(filters.Regex("^✅ Готово$"), finish_options))
        app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['back']} Назад$"), back_to_questions))
        app.add_handler(MessageHandler(filters.Regex("^🔙 Назад к вопросам$"), back_to_questions))
        
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
        app.add_handler(MessageHandler(filters.Regex("^❌ Отмена$"), cancel_creation))
        
        app.add_handler(CallbackQueryHandler(callback_handler))
        
        logger.info("🚀 Бот успешно запущен!")
        app.run_polling()
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    main()
