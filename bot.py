#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бот для создания тестов для подруг @PodrugaTestBot
Версия: 48.0 - С МЕХАНИКАМИ УДЕРЖАНИЯ И МОНЕТИЗАЦИИ
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
MAX_REFERRAL_BONUS = 999
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

# === УРОВНИ И ДОСТИЖЕНИЯ ===
LEVELS = [
    {'name': '🌱 НОВИЧОК', 'min_score': 0, 'reward': 'обычный диплом'},
    {'name': '📚 ЗНАТОК', 'min_score': 500, 'reward': '+1 тест, новая рамка'},
    {'name': '💎 ЭКСПЕРТ', 'min_score': 1500, 'reward': '+2 теста, серебряная рамка'},
    {'name': '👑 МАСТЕР', 'min_score': 3500, 'reward': '+3 теста, золотая рамка'},
    {'name': '🌟 ГУРУ', 'min_score': 7000, 'reward': '+5 тестов, алмазная рамка'},
    {'name': '👸 ЛЕГЕНДА', 'min_score': 15000, 'reward': 'месяц премиума в подарок'}
]

DAILY_TASKS = {
    'complete_test': {'name': '📝 Пройти тест', 'points': 5, 'description': 'Пройди любой тест от подруги'},
    'send_test': {'name': '📤 Отправить тест', 'points': 10, 'description': 'Отправь тест подруге'},
    'get_result': {'name': '🎯 Получить результат', 'points': 15, 'description': 'Дождись, пока подруга пройдет твой тест'},
    'create_test': {'name': '✨ Создать тест', 'points': 20, 'description': 'Создай новый тест о себе'},
    'invite_friend': {'name': '👭 Пригласить подругу', 'points': 30, 'description': 'Пригласи подругу по ссылке'}
}

PREMIUM_SHOP_ITEMS = {
    'frame_gold': {'name': '🖼️ Золотая рамка', 'price': 49, 'icon': '✨'},
    'frame_diamond': {'name': '🖼️ Алмазная рамка', 'price': 99, 'icon': '💎'},
    'frame_royal': {'name': '🖼️ Королевская рамка', 'price': 199, 'icon': '👑'},
    'animated_diplom': {'name': '🎬 Анимированный диплом', 'price': 99, 'icon': '🎬'},
    'vip_badge': {'name': '⭐ VIP-значок', 'price': 29, 'icon': '⭐'},
    'gold_nickname': {'name': '✨ Золотой никнейм', 'price': 49, 'icon': '✨'},
    'custom_color': {'name': '🎨 Свой цвет диплома', 'price': 39, 'icon': '🎨'}
}

STREAK_REWARDS = {
    7: {'points': 50, 'tests': 1, 'premium_days': 0},
    14: {'points': 100, 'tests': 2, 'premium_days': 0},
    30: {'points': 300, 'tests': 0, 'premium_days': 7},
    100: {'points': 1000, 'tests': 0, 'premium_days': 30}
}

WOW_EMOJIS = {
    'start': '✨', 'success': '🎉', 'error': '❌',
    'test': '📝', 'friend': '👯', 'crown': '👑',
    'star': '⭐', 'heart': '💖', 'daily': '🎁',
    'achievement': '🏆', 'shop': '🛍️', 'money': '💰',
    'top': '🏆', 'back': '🔙', 'stats': '📊', 'cancel': '❌', 
    'favorite': '⭐', 'diplom': '🎓', 'task': '📋', 'level': '📈'
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
        c.execute('CREATE INDEX IF NOT EXISTS idx_daily_tasks_user ON daily_tasks(user_id, task_date)')
        
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
            if referrer and referred_by != user_id:
                c.execute('UPDATE users SET tests_available = tests_available + 1, referral_count = referral_count + 1 WHERE user_id = ?', 
                         (referred_by,))
                c.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)', 
                         (referred_by, user_id))
                # Добавляем достижение за приглашение
                add_achievement(referred_by, 'first_invite')
                # Добавляем задание
                complete_daily_task(referred_by, 'invite_friend')
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
        c.execute('UPDATE users SET tests_available = tests_available + ? WHERE user_id = ?', 
                 (count, user_id))
        conn.commit()
        return True
    finally:
        conn.close()

def use_test(user_id, test_id=None):
    user = get_user(user_id)
    
    if user and user.get('unlimited_until'):
        try:
            unlimited_until = datetime.fromisoformat(user['unlimited_until'])
            if unlimited_until > datetime.now():
                return True
        except (ValueError, TypeError):
            pass
    
    if test_id:
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute('SELECT id FROM attempts WHERE test_id = ? AND friend_id = ?', (test_id, user_id))
            if c.fetchone():
                logger.info(f"Пользователь {user_id} уже проходил тест {test_id}")
                return False
        finally:
            conn.close()
    
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
        check_level_up(user_id)
        return True
    finally:
        conn.close()

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
    current_level = get_rank(points)
    
    # Проверяем достижения за уровень
    for level in LEVELS:
        if points >= level['min_score'] and level['min_score'] > 0:
            achievement_key = f'level_{level["min_score"]}'
            if not has_achievement(user_id, achievement_key):
                add_achievement(user_id, achievement_key)
                # Награда за уровень
                if 'reward' in level:
                    if '+1 тест' in level['reward']:
                        add_tests(user_id, 1)
                    elif '+2 теста' in level['reward']:
                        add_tests(user_id, 2)
                    elif '+3 теста' in level['reward']:
                        add_tests(user_id, 3)
                    elif '+5 тестов' in level['reward']:
                        add_tests(user_id, 5)
                    elif 'месяц премиума' in level['reward']:
                        # Даем месяц премиума
                        unlimited_until = (datetime.now() + timedelta(days=30)).isoformat()
                        conn = get_db()
                        c = conn.cursor()
                        c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (unlimited_until, user_id))
                        conn.commit()
                        conn.close()

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
            
            # Проверяем награды за стрик
            if streak in STREAK_REWARDS:
                reward = STREAK_REWARDS[streak]
                bonus += reward['points']
                if reward['tests'] > 0:
                    add_tests(user_id, reward['tests'])
                if reward['premium_days'] > 0:
                    unlimited_until = (datetime.now() + timedelta(days=reward['premium_days'])).isoformat()
                    c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (unlimited_until, user_id))
                # Добавляем достижение
                add_achievement(user_id, f'streak_{streak}')
            
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
        # Добавляем достижение за создание теста
        add_achievement(creator_id, 'first_test')
        # Добавляем задание
        complete_daily_task(creator_id, 'create_test')
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
        c.execute('''SELECT t.id, t.title, t.creator_name 
                     FROM saved_tests s 
                     JOIN tests t ON s.test_id = t.id 
                     WHERE s.user_id = ? 
                     ORDER BY s.created_at DESC''', (user_id,))
        return c.fetchall()
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
        # Добавляем задание для создателя теста
        test = get_test_by_id(test_id)
        if test:
            complete_daily_task(test['creator_id'], 'get_result')
        # Добавляем задание для прошедшего
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
        c.execute('INSERT INTO achievements (user_id, achievement_type) VALUES (?, ?)', (user_id, achievement_type))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def has_achievement(user_id, achievement_type):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT id FROM achievements WHERE user_id = ? AND achievement_type = ?', (user_id, achievement_type))
        return c.fetchone() is not None
    finally:
        conn.close()

def get_achievements(user_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT achievement_type, achieved_at FROM achievements WHERE user_id = ? ORDER BY achieved_at DESC', (user_id,))
        return c.fetchall()
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
        # Добавляем очки за задание
        if task_type in DAILY_TASKS:
            add_points(user_id, DAILY_TASKS[task_type]['points'])
        return True
    except:
        return False
    finally:
        conn.close()

def purchase_item(user_id, item_type):
    if item_type not in PREMIUM_SHOP_ITEMS:
        return False
    
    item = PREMIUM_SHOP_ITEMS[item_type]
    # Здесь должна быть интеграция с платежной системой
    # Пока просто записываем покупку
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('INSERT INTO purchases (user_id, item_type, price) VALUES (?, ?, ?)', 
                 (user_id, item_type, item['price']))
        # Активируем предмет
        if item_type.startswith('frame_'):
            c.execute('UPDATE users SET selected_frame = ? WHERE user_id = ?', (item_type, user_id))
        elif item_type == 'vip_badge':
            c.execute('UPDATE users SET selected_badge = ? WHERE user_id = ?', (item_type, user_id))
        elif item_type == 'gold_nickname':
            c.execute('UPDATE users SET gold_nickname = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def apply_promocode(user_id, code):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM promocodes WHERE code = ? AND (used_by IS NULL OR used_by = ?) AND expires_at > ?', 
                 (code, user_id, datetime.now().isoformat()))
        row = c.fetchone()
        if not row:
            return False, "Промокод не найден или истек"
        
        reward_type = row['reward_type']
        reward_value = row['reward_value']
        
        if reward_type == 'tests':
            add_tests(user_id, reward_value)
        elif reward_type == 'points':
            add_points(user_id, reward_value)
        elif reward_type == 'premium_days':
            unlimited_until = (datetime.now() + timedelta(days=reward_value)).isoformat()
            c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (unlimited_until, user_id))
        
        c.execute('UPDATE promocodes SET used_by = ? WHERE code = ?', (user_id, code))
        conn.commit()
        return True, f"Промокод активирован! Вы получили {reward_value} {reward_type}"
    except Exception as e:
        return False, f"Ошибка: {e}"
    finally:
        conn.close()

def get_top_users(limit=10):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT user_id, first_name, username, total_points FROM users ORDER BY total_points DESC LIMIT ?', (limit,))
        return c.fetchall()
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
        [KeyboardButton(f"{WOW_EMOJIS['stats']} Моя статистика"), KeyboardButton(f"{WOW_EMOJIS['daily']} Бонус")],
        [KeyboardButton(f"{WOW_EMOJIS['task']} Задания"), KeyboardButton(f"{WOW_EMOJIS['achievement']} Достижения")],
        [KeyboardButton(f"{WOW_EMOJIS['money']} Пригласить подруг"), KeyboardButton(f"{WOW_EMOJIS['shop']} Магазин")],
        [KeyboardButton(f"{WOW_EMOJIS['top']} Топ подруг"), KeyboardButton(f"{WOW_EMOJIS['level']} Рейтинг")]
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
        [InlineKeyboardButton("💎 Премиум 30 дней — 299 ₽", callback_data="buy_premium_month")],
        [InlineKeyboardButton("💎 Премиум 3 месяца — 699 ₽", callback_data="buy_premium_3months")],
        [InlineKeyboardButton("💎 Премиум ГОД — 1999 ₽", callback_data="buy_premium_year")],
        [InlineKeyboardButton("🛍️ Премиум-магазин", callback_data="premium_shop")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_premium_shop_keyboard():
    keyboard = []
    for key, item in PREMIUM_SHOP_ITEMS.items():
        keyboard.append([InlineKeyboardButton(f"{item['icon']} {item['name']} — {item['price']} ₽", callback_data=f"buy_item_{key}")])
    return InlineKeyboardMarkup(keyboard)

def get_share_confirm_keyboard(test_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, отправить", callback_data=f"confirm_share_{test_id}"),
         InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_share")],
        [InlineKeyboardButton("👭 Отправить подруге", 
            switch_inline_query=f"✨🌸 *ВНИМАНИЕ, ПОДРУГА!* 🌸✨\n\n💝 @{BOT_USERNAME} 💝\n\n🌟 *ТВОЯ ПОДРУГА ПРИГЛАШАЕТ ТЕБЯ ПРОЙТИ ТЕСТ!* 🌟\n\n📝 *«Насколько хорошо ты меня знаешь?»*\n\n🎀 *Давай проверим нашу дружбу!* 🎀\n\n✨ *УЗНАЙ, КАКАЯ ТЫ ПОДРУГА!* ✨\n\n👉 *ПЕРЕХОДИ ПО ССЫЛКЕ И НАЧИНАЙ!* 👈\n\nhttps://t.me/{BOT_USERNAME}?start=test_{test_id}\n\n💕 *Жду твой результат!* 💕")]
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

def get_top_friends_keyboard(has_premium):
    if has_premium:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💎 Оформить премиум", callback_data="shop")
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
                    creator = get_user(test['creator_id'])
                    creator_name = creator.get('first_name', 'Подруга') if creator else 'Подруга'
                    creator_username = f"(@{creator.get('username', '')})" if creator and creator.get('username') else ''
                    text = (f"🌸 *ПРИВЕТ, {user.first_name or 'ДОРОГАЯ'}!* 🌸\n\n"
                            f"💕 *{creator_name}* {creator_username} приглашает тебя пройти уютный тест о вашей дружбе!\n\n"
                            f"📝 *{test['title']}*\n\n"
                            f"✨ *Узнай, насколько хорошо ты знаешь свою подругу!* ✨\n\n"
                            f"👇 *Нажми на кнопку, чтобы начать* 👇")
                    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, 
                                                   reply_markup=get_start_test_keyboard(test_id))
                    return
            except (IndexError, ValueError) as e:
                logger.error(f"Ошибка парсинга test_id: {e}")
    
    existing = get_user(user.id)
    if not existing:
        create_user(user.id, user.username, user.first_name, referred_by)
        if referred_by:
            logger.info(f"Пользователь {user.id} зарегистрирован по реферальной ссылке от {referred_by}")
    else:
        update_user(user.id, user.username, user.first_name)
    
    user_data = get_user(user.id)
    points = user_data.get('total_points', 0) if user_data else 0
    rank = get_rank(points)
    tests = get_available_tests(user.id)
    premium_status = "🔓 Бесплатный" if not is_premium(user.id) else "💎 Премиум"
    
    text = (f"{WOW_EMOJIS['start']} *ПРИВЕТ, {user.first_name or 'ПОДРУГА'}!* {WOW_EMOJIS['start']}\n\n"
            f"🌸 Добро пожаловать в *PodrugaTestBot* — место, где мы проверяем, насколько хорошо мы знаем друг друга!\n\n"
            f"🎀 *Твой статус:* {premium_status}\n"
            f"🎁 *У тебя:* {tests} тестов\n"
            f"⭐ *Очки:* {points}\n"
            f"🏆 *Ранг:* {rank['name']}\n\n"
            f"💫 *Создай свой первый тест!* Нажми «Создать тест» и удиви подругу ✨\n\n"
            f"🌟 *Что тут можно делать?*\n"
            f"• Создавать тесты о себе\n"
            f"• Отправлять их подругам\n"
            f"• Узнавать, насколько хорошо тебя знают\n"
            f"• Получать милые дипломы за результаты\n"
            f"• Выполнять задания и получать бонусы\n"
            f"• Соревноваться в рейтинге\n\n"
            f"💖 *Поехали!* 👇")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    available = get_available_tests(user_id)
    
    if available <= 0:
        await update.message.reply_text(
            f"{WOW_EMOJIS['error']} У тебя закончились тесты!\n\n"
            "🎁 Получи бонус или пригласи подругу!\n"
            "💎 Или загляни в магазин за премиумом\n"
            "📋 Выполняй задания - они дают тесты!",
            reply_markup=get_main_keyboard()
        )
        return
    
    context.user_data['create_test'] = {
        'step': 'title',
        'questions_data': []
    }
    logger.info(f"Создана новая сессия создания теста для {user_id}")
    
    await update.message.reply_text(
        f"{WOW_EMOJIS['test']} *СОЗДАЕМ ТЕСТ!* {WOW_EMOJIS['test']}\n\n"
        f"📦 *Доступно тестов:* {available}\n\n"
        "🌸 Придумай красивое название (например: «Насколько хорошо ты меня знаешь?»):\n\n"
        "❌ Отмена - чтобы выйти",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'create_test' in context.user_data:
        logger.info(f"Отмена создания теста пользователем {update.effective_user.id}")
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
        logger.info(f"Сохранено название теста: {data['title']}")
        
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
            
            logger.info(f"Начинаем создание вопросов. Всего: {count}")
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
    
    await query.message.edit_text(
        f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{question_text}\n\n"
        f"❓ Что делать с этим вопросом?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_question_keyboard()
    )

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
    
    await query.message.reply_text(
        f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n"
        f"❓ {data['current_question_text']}\n\n"
        f"✏️ Напишите *вариант ответа №1*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

async def select_question_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    logger.info(f"=== select_question_group вызвана ===")
    logger.info(f"Callback data: {query.data}")
    
    try:
        group = query.data.split("_")[1]
        logger.info(f"Выбрана группа: {group}")
    except IndexError:
        logger.error(f"Ошибка: неверный формат callback_data: {query.data}")
        await query.message.reply_text("Ошибка выбора группы")
        return
    
    data = context.user_data.get('create_test')
    
    if not data:
        logger.error("Нет сессии создания теста! Создаем новую...")
        data = {
            'step': 'group',
            'questions_data': []
        }
        context.user_data['create_test'] = data
    else:
        logger.info(f"Найдена сессия создания теста. Step: {data.get('step')}, Title: {data.get('title', 'не задан')}")
    
    data['group'] = group
    data['step'] = 'waiting_question_count'
    
    user_id = query.from_user.id
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    
    group_name = PREMIUM_QUESTION_GROUPS.get(group, FREE_QUESTION_GROUPS.get(group))
    if not group_name:
        group_name = "Вопросы"
    
    logger.info(f"Переход к вводу количества вопросов для группы {group_name}")
    
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
    
    logger.info(f"Сохранен вопрос {data['current_q']}/{data['total_q']}")
    
    await query.message.reply_text(
        f"✅ *Вопрос {data['current_q']}/{data['total_q']} сохранен!*",
        parse_mode=ParseMode.MARKDOWN
    )
    
    if data['current_q'] < data['total_q']:
        await show_next_question(query, context)
    else:
        await finish_creation_from_callback(query, context, query.from_user.id)

async def show_next_question(query, context):
    data = context.user_data.get('create_test')
    if not data:
        await query.message.reply_text("Ошибка: сессия создания теста потеряна")
        return
    
    current_idx = data.get('current_question_index', 0)
    questions = data.get('group_questions', [])
    
    if current_idx >= len(questions):
        current_idx = 0
        data['current_question_index'] = 0
    
    question_text = questions[current_idx]
    data['current_question_text'] = question_text
    logger.info(f"Показываем вопрос {data['current_q'] + 1}/{data['total_q']}: {question_text[:50]}")
    
    await query.message.reply_text(
        f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{question_text}\n\n"
        f"❓ Что делать с этим вопросом?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_question_keyboard()
    )

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
        save_test(user_id, test_id)
        
        text = (f"{WOW_EMOJIS['success']} *ТЕСТ СОЗДАН!* {WOW_EMOJIS['success']}\n\n"
                f"📝 *Название:* {data['title']}\n"
                f"🔢 *Вопросов:* {data['total_q']}\n\n"
                f"✨ *Что дальше?*\n"
                f"• Отправь тест подруге\n"
                f"• Получи милый диплом\n"
                f"• Набирай очки\n"
                f"• Выполняй задания\n\n"
                f"👇 *Подтверди отправку, чтобы списать тест*")
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, 
                                      reply_markup=get_share_confirm_keyboard(test_id))
    else:
        await update.message.reply_text(f"{WOW_EMOJIS['error']} Ошибка создания теста", 
                                       reply_markup=get_main_keyboard())
    
    del context.user_data['create_test']
    logger.info(f"Тест {test_id} создан пользователем {user_id}")

async def finish_creation_from_callback(query, context, user_id):
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
        query.from_user.first_name,
        query.from_user.username,
        data['title'],
        questions,
        options,
        correct_answers,
        None, None
    )
    
    if test_id:
        save_test(user_id, test_id)
        
        text = (f"{WOW_EMOJIS['success']} *ТЕСТ СОЗДАН!* {WOW_EMOJIS['success']}\n\n"
                f"📝 *Название:* {data['title']}\n"
                f"🔢 *Вопросов:* {data['total_q']}\n\n"
                f"✨ *Что дальше?*\n"
                f"• Отправь тест подруге\n"
                f"• Получи милый диплом\n"
                f"• Набирай очки\n"
                f"• Выполняй задания\n\n"
                f"👇 *Подтверди отправку, чтобы списать тест*")
        
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, 
                                      reply_markup=get_share_confirm_keyboard(test_id))
    else:
        await query.message.reply_text(f"{WOW_EMOJIS['error']} Ошибка создания теста", 
                                       reply_markup=get_main_keyboard())
    
    del context.user_data['create_test']
    logger.info(f"Тест {test_id} создан пользователем {user_id}")

# === НОВЫЕ ХЕНДЛЕРЫ ДЛЯ МЕХАНИК УДЕРЖАНИЯ ===
async def daily_tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать ежедневные задания"""
    user_id = update.effective_user.id
    tasks = get_daily_tasks(user_id)
    
    text = (f"{WOW_EMOJIS['task']} *ЕЖЕДНЕВНЫЕ ЗАДАНИЯ* {WOW_EMOJIS['task']}\n\n"
            f"Выполняй задания и получай очки! 📈\n\n")
    
    completed_count = 0
    for task in tasks:
        status = "✅" if task['completed'] else "⬜"
        text += f"{status} *{task['name']}* +{task['points']} ⭐\n"
        text += f"   _{task['description']}_\n\n"
        if task['completed']:
            completed_count += 1
    
    text += f"\n📊 *Выполнено:* {completed_count}/{len(tasks)}\n"
    
    if completed_count == len(tasks):
        text += f"\n🎉 *МОЛОДЕЦ!* Все задания выполнены! Завтра будут новые! 🌟"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def achievements_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать достижения пользователя"""
    user_id = update.effective_user.id
    achievements = get_achievements(user_id)
    
    text = (f"{WOW_EMOJIS['achievement']} *МОИ ДОСТИЖЕНИЯ* {WOW_EMOJIS['achievement']}\n\n")
    
    achievement_names = {
        'first_test': '🎯 Первый тест',
        'first_invite': '👭 Первое приглашение',
        'streak_7': '🔥 7 дней подряд',
        'streak_14': '⭐ 14 дней подряд',
        'streak_30': '💎 30 дней подряд',
        'streak_100': '👑 100 дней подряд',
        'level_500': '📚 Уровень ЗНАТОК',
        'level_1500': '💎 Уровень ЭКСПЕРТ',
        'level_3500': '👑 Уровень МАСТЕР',
        'level_7000': '🌟 Уровень ГУРУ',
        'level_15000': '👸 Уровень ЛЕГЕНДА'
    }
    
    if not achievements:
        text += "У тебя пока нет достижений.\nВыполняй задания и получай награды! 🌟"
    else:
        for ach in achievements:
            name = achievement_names.get(ach['achievement_type'], ach['achievement_type'])
            text += f"🏆 {name}\n"
            text += f"   📅 {ach['achieved_at'][:10]}\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def rating_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать рейтинг пользователей"""
    user_id = update.effective_user.id
    top_users = get_top_users(20)
    user = get_user(user_id)
    
    text = (f"{WOW_EMOJIS['level']} *РЕЙТИНГ ПОДРУГ* {WOW_EMOJIS['level']}\n\n")
    
    for i, u in enumerate(top_users, 1):
        medal = ""
        if i == 1:
            medal = "👑"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = "📌"
        
        name = u['first_name'] or f"ID {u['user_id']}"
        text += f"{medal} {i}. *{name}* — {u['total_points']} ⭐\n"
    
    if user:
        # Найти место пользователя
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) + 1 FROM users WHERE total_points > ?', (user['total_points'],))
        place = c.fetchone()[0]
        conn.close()
        
        text += f"\n📊 *Твое место:* {place}\n"
        text += f"⭐ *Твои очки:* {user['total_points']}\n"
        text += f"🎯 *До следующего уровня:* {get_next_level_points(user['total_points'])} очков"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

def get_next_level_points(current_points):
    for level in LEVELS:
        if level['min_score'] > current_points:
            return level['min_score'] - current_points
    return 0

async def premium_shop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать премиум-магазин"""
    query = update.callback_query
    await query.answer()
    
    text = (f"{WOW_EMOJIS['shop']} *ПРЕМИУМ-МАГАЗИН* {WOW_EMOJIS['shop']}\n\n"
            f"💎 *Эксклюзивные предметы только для премиум!*\n\n"
            f"🖼️ *Рамки для дипломов* — сделают твой диплом уникальным\n"
            f"🎬 *Анимированные дипломы* — впечатли подругу\n"
            f"⭐ *VIP-значок* — выдели свой профиль\n"
            f"✨ *Золотой никнейм* — покажи свой статус\n\n"
            f"👇 *Выбери предмет для покупки:*")
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_premium_shop_keyboard())

async def buy_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка предмета из премиум-магазина"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    has_premium = is_premium(user_id)
    
    if not has_premium:
        await query.message.reply_text(
            f"{WOW_EMOJIS['error']} *Только для премиум!*\n\n"
            f"💎 Оформи подписку, чтобы покупать эксклюзивные предметы!",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        item_key = query.data.split("_")[2]
    except:
        await query.message.reply_text("Ошибка выбора предмета")
        return
    
    if item_key not in PREMIUM_SHOP_ITEMS:
        await query.message.reply_text("Предмет не найден")
        return
    
    item = PREMIUM_SHOP_ITEMS[item_key]
    
    # Здесь должна быть интеграция с платежной системой
    # Пока просто подтверждаем покупку
    text = (f"{item['icon']} *{item['name']}* — {item['price']} ₽\n\n"
            f"✨ *Отличный выбор!*\n\n"
            f"💰 Для оплаты напишите @LavaTopBot\n\n"
            f"💎 После оплаты предмет будет активирован автоматически!")
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def promocode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Активация промокода"""
    user_id = update.effective_user.id
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            f"🎁 *Активация промокода*\n\n"
            f"Использование: `/promocode КОД`\n\n"
            f"Получить промокоды можно в наших соцсетях и у блогеров!",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    code = context.args[0].upper()
    success, message = apply_promocode(user_id, code)
    
    if success:
        await update.message.reply_text(f"✅ {message}", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"❌ {message}", parse_mode=ParseMode.MARKDOWN)

# === ОСТАЛЬНЫЕ ХЕНДЛЕРЫ ===
async def my_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    saved_tests_list = get_saved_tests(user_id)
    has_premium = is_premium(user_id)
    max_saved = SAVED_TESTS_PREMIUM if has_premium else SAVED_TESTS_FREE
    saved_count = len(saved_tests_list)
    
    if not saved_tests_list:
        await update.message.reply_text(
            f"{WOW_EMOJIS['test']} *Мои тесты*\n\nУ тебя пока нет сохраненных тестов.\nСохраняй тесты, которые тебе нравятся!\n\n⭐ *Как сохранить тест?*\nПросто нажми кнопку «Сохранить» под любым тестом!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    text = f"{WOW_EMOJIS['crown']} *СОХРАНЕННЫЕ ТЕСТЫ* {WOW_EMOJIS['crown']}\n\n"
    text += f"📦 *Сохранено:* {saved_count}/{max_saved}\n\n"
    
    for test in saved_tests_list:
        text += f"📝 *{test['title']}*\n   👤 Автор: {test['creator_name']}\n\n"
    
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
        await query.message.reply_text(
            f"{WOW_EMOJIS['error']} *Лимит сохранения!*\n\n"
            f"Ты можешь сохранить только {max_saved} тестов.\n"
            f"💎 Премиум позволяет сохранить до {SAVED_TESTS_PREMIUM} тестов!",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if save_test(user_id, test_id):
        await query.message.reply_text(
            f"{WOW_EMOJIS['success']} *Тест сохранен!*\n\n"
            f"Ты всегда можешь найти его в разделе «Мои тесты»",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await query.message.reply_text(
            f"{WOW_EMOJIS['error']} *Тест уже сохранен!*",
            parse_mode=ParseMode.MARKDOWN
        )

async def unsave_test_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        test_id = int(query.data.split("_")[2])
    except:
        await query.message.reply_text("Ошибка")
        return
    
    user_id = query.from_user.id
    
    if unsave_test(user_id, test_id):
        await query.message.reply_text(
            f"✅ *Тест удален из сохраненных!*",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await query.message.reply_text(
            f"❌ *Ошибка при удалении*",
            parse_mode=ParseMode.MARKDOWN
        )

async def test_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    text = f"📝 *{test['title']}*\n\n"
    text += f"👤 Автор: {test['creator_name']}\n"
    text += f"📅 Создан: {test['created_at'][:10]}\n"
    text += f"❤️ Лайков: {test['likes']} | 📤 Прохождений: {test['shares']}\n\n"
    text += "*Вопросы:*\n"
    
    for i, q in enumerate(test['questions'], 1):
        text += f"{i}. {q}\n"
        for j, opt in enumerate(test['options'][i-1], 1):
            mark = "✅" if test['correct_answers'][i-1] == j-1 else "➖"
            text += f"   {mark} {j}. {opt}\n"
        text += "\n"
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def share_saved_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    user_id = query.from_user.id
    
    if use_test(user_id, test_id):
        text = (f"{WOW_EMOJIS['success']} *Тест готов к отправке!*\n\n"
                f"📝 {test['title']}\n\n"
                f"Поделись им с подругой через кнопку ниже 👇")
        
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=get_share_confirm_keyboard(test_id))
        # Добавляем задание
        complete_daily_task(user_id, 'send_test')
    else:
        await query.message.reply_text(
            f"{WOW_EMOJIS['error']} Не удалось отправить тест.\n\n"
            f"Возможные причины:\n"
            f"• У тебя закончились тесты\n"
            f"• Ты уже отправляла этот тест этой подруге\n\n"
            f"🎁 Получи бонус или пригласи подругу!",
            reply_markup=get_main_keyboard()
        )

async def top_friends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
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
            reply_markup=get_top_friends_keyboard(has_premium)
        )
        return
    
    text = f"{WOW_EMOJIS['top']} *ТВОЙ ТОП ПОДРУГ* {WOW_EMOJIS['top']}\n\n"
    
    for i, friend in enumerate(rows, 1):
        name = friend['friend_name'] or 'Подруга'
        username = f"(@{friend['friend_username']})" if friend['friend_username'] else ''
        avg = friend['avg_score']
        
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = "💕"
        
        text += f"{medal} *{name}* {username}\n"
        text += f"   📊 Средний балл: {avg:.1f}%\n"
        text += f"   📝 Тестов пройдено: {friend['tests_count']}\n"
        text += "\n"
    
    if not has_premium:
        text += "\n💎 *Купи премиум, чтобы видеть детальные ответы каждой подруги и полную статистику!*"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, 
                                   reply_markup=get_top_friends_keyboard(has_premium))

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
    saved_count = get_saved_tests_count(user_id)
    max_saved = SAVED_TESTS_PREMIUM if has_premium else SAVED_TESTS_FREE
    
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM attempts WHERE friend_id = ?', (user_id,))
        tests_passed = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) + 1 FROM users WHERE total_points > ?', (points,))
        rating = c.fetchone()[0]
        
        tests_stats = get_attempts_stats(user_id)
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
    
    next_level_points = get_next_level_points(points)
    
    text = (f"{WOW_EMOJIS['stats']} *ТВОЯ СТАТИСТИКА* {WOW_EMOJIS['stats']}\n\n"
            f"👤 *Имя:* {user.get('first_name', 'Подруга')}\n"
            f"🏆 *Ранг:* {rank['name']}\n"
            f"⭐ *Очки:* {points}\n"
            f"📊 *Место в рейтинге:* {rating}\n"
            f"🔥 *Серия дней:* {streak}\n"
            f"🎯 *До следующего ранга:* {next_level_points} очков\n\n"
            f"📝 *Создано тестов:* {created}\n"
            f"🎯 *Пройдено тестов:* {tests_passed}\n"
            f"👭 *Приглашено подруг:* {referrals}\n"
            f"📦 *Сохранено тестов:* {saved_count}/{max_saved}\n\n"
            f"📦 *Тестов доступно:* {tests_left}\n"
            f"🔢 *Максимум вопросов:* {max_q}{unlimited_text}")
    
    if has_premium:
        text += f"\n\n🎨 *Твой диплом:* {DIPLOMS.get(user.get('selected_diplom', 'free'), DIPLOMS['free'])['name']}\n"
        text += f"🖼️ *Твоя рамка:* {PREMIUM_SHOP_ITEMS.get(user.get('selected_frame', 'none'), {}).get('name', 'Нет')}\n"
        text += f"⭐ *VIP-значок:* {'Да' if user.get('selected_badge') else 'Нет'}\n"
        text += f"✨ *Золотой никнейм:* {'Да' if user.get('gold_nickname') else 'Нет'}"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = get_daily_bonus(user_id)
    
    if result[0] is None:
        streak = result[1]
        next_reward = ""
        for s in STREAK_REWARDS:
            if s > streak:
                next_reward = f"\n\n🎯 *Следующая награда через {s - streak} дней!*"
                break
        
        await update.message.reply_text(
            f"{WOW_EMOJIS['daily']} 🎁 *БОНУС*\n\n"
            f"Ты уже получала бонус сегодня!\n"
            f"🔥 *Серия:* {streak} дней{next_reward}\n"
            f"⏰ Возвращайся завтра!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    bonus, streak = result
    
    text = (f"{WOW_EMOJIS['daily']} 🎁 *БОНУС ПОЛУЧЕН!* {WOW_EMOJIS['daily']}\n\n"
            f"✨ *+{bonus} очков!*\n"
            f"🔥 *Серия:* {streak} дней\n\n")
    
    if streak in STREAK_REWARDS:
        reward = STREAK_REWARDS[streak]
        text += f"🎉 *ОСОБАЯ НАГРАДА!*\n"
        if reward['points'] > 0:
            text += f"⭐ +{reward['points']} очков\n"
        if reward['tests'] > 0:
            text += f"📦 +{reward['tests']} тестов\n"
        if reward['premium_days'] > 0:
            text += f"💎 +{reward['premium_days']} дней премиума\n"
        text += "\n"
    
    text += f"💫 *Завтра будет новая награда! Приходи снова!*"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    code = user.get('referral_code', str(update.effective_user.id))
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    referrals = user.get('referral_count', 0)
    
    text = (f"{WOW_EMOJIS['money']} *ПРИГЛАСИ ПОДРУГУ* {WOW_EMOJIS['money']}\n\n"
            f"🌸 *Приглашай подруг и получай бонусы!* 🌸\n\n"
            f"🎁 *За каждую приглашенную подругу ты получаешь +1 тест!*\n"
            f"💕 *Чем больше подруг, тем больше тестов!*\n"
            f"🏆 *Топ приглашающих получают эксклюзивные награды!*\n\n"
            f"🔗 *Твоя пригласительная ссылка:* \n{link}\n\n"
            f"👭 *Приглашено подруг:* {referrals}\n\n"
            f"💡 *Как это работает:*\n"
            f"1. Отправь ссылку подруге\n"
            f"2. Она переходит и начинает использовать бота\n"
            f"3. Ты получаешь +1 тест (и так за каждую!)\n\n"
            f"✨ *Вместе веселее! Делитесь тестами и узнавайте друг друга лучше!* ✨")
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(), disable_web_page_preview=False)

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        message = update.callback_query.message
    else:
        user_id = update.effective_user.id
        message = update.message
    
    if not message:
        return
    
    user = get_user(user_id)
    if not user:
        await message.reply_text("❌ Ошибка. Попробуйте позже.", reply_markup=get_main_keyboard())
        return
    
    points = user.get('total_points', 0)
    rank = get_rank(points)
    has_premium = is_premium(user_id)
    max_q = MAX_QUESTIONS_PREMIUM if has_premium else MAX_QUESTIONS_FREE
    max_saved = SAVED_TESTS_PREMIUM if has_premium else SAVED_TESTS_FREE
    saved_count = get_saved_tests_count(user_id)
    
    text = (f"{WOW_EMOJIS['shop']} *ПРЕМИУМ ПОДПИСКА* {WOW_EMOJIS['shop']}\n\n"
            f"👑 *Твой ранг:* {rank['name']}\n"
            f"⭐ *Очки:* {points}\n"
            f"🔢 *Сейчас вопросов в тесте:* до {max_q}\n"
            f"📦 *Сохранено тестов:* {saved_count}/{max_saved}\n\n"
            f"💎 *ПРЕИМУЩЕСТВА ПРЕМИУМ:*\n\n"
            f"✅ *До 10 вопросов в тесте* (вместо 5)\n"
            f"✅ *10 групп вопросов* (вместо 4)\n"
            f"✅ *До 10 сохраненных тестов* (вместо 3)\n"
            f"✅ *Полная статистика по тестам*\n"
            f"   • Кто проходил твои тесты\n"
            f"   • Детальные ответы каждой подруги\n"
            f"   • Средний балл каждого теста\n"
            f"✅ *5 красивых дипломов на выбор*\n"
            f"✅ *Эксклюзивные рамки и значки*\n"
            f"✅ *Золотой никнейм в профиле*\n"
            f"✅ *Неограниченное количество тестов*\n\n"
            f"🎁 *СТОИМОСТЬ ПРЕМИУМ:*\n\n"
            f"• 30 дней — 299 ₽\n"
            f"• 3 месяца — 699 ₽\n"
            f"• ГОД — 1999 ₽\n\n"
            f"💡 *СОВЕТ:* Если ты создаешь больше 10 тестов в месяц — премиум для тебя!\n\n"
            f"🛍️ *Также в магазине:* эксклюзивные рамки, анимированные дипломы и VIP-значки!")
    
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_shop_keyboard())

async def confirm_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        test_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.message.reply_text("Ошибка подтверждения")
        return
    
    user_id = query.from_user.id
    
    if use_test(user_id, test_id):
        text = (f"{WOW_EMOJIS['success']} *Тест отправлен!*\n\n"
                f"Поделитесь им с подругой через кнопку ниже 👇")
        
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=get_share_confirm_keyboard(test_id))
        # Добавляем задание
        complete_daily_task(user_id, 'send_test')
    else:
        await query.message.reply_text(
            f"{WOW_EMOJIS['error']} Не удалось списать тест.\n\n"
            f"Возможные причины:\n"
            f"• У тебя закончились тесты\n"
            f"• Ты уже отправляла этот тест этой подруге\n\n"
            f"🎁 Получи бонус или пригласи подругу!",
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
    await query.message.reply_text(
        "✨ Выбери *группу вопросов*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_question_groups_keyboard(user_id)
    )

async def open_shop_from_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
            "Каждую подругу можно проверить только один раз"
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
    user_id = user.id
    test_id = data['test_id']
    
    score = 0
    for i, ans in enumerate(answers):
        if i < len(correct_answers) and ans == correct_answers[i]:
            score += 100 / len(test['questions'])
    
    save_attempt(test_id, user_id, user.first_name, user.username, answers, score)
    add_points(user_id, int(score))
    
    creator_id = test['creator_id']
    selected_diplom = get_selected_diplom(creator_id)
    diplom = DIPLOMS.get(selected_diplom, DIPLOMS['free'])
    
    status = get_friendship_status(score)
    
    text = (f"{diplom['border']}\n"
            f"{diplom['icon']} *{diplom['name']}* {diplom['icon']}\n"
            f"{diplom['border']}\n\n"
            f"🏆 *ВРУЧАЕТСЯ:* {user.first_name or 'УЧАСТНИК'}\n"
            f"📝 *ТЕСТ:* «{test['title']}»\n"
            f"✨ *РЕЗУЛЬТАТ:* {score:.1f}%\n"
            f"{status}\n\n"
            f"{diplom['icon']} *ОСОБЫЕ ДОСТИЖЕНИЯ:*\n"
            f"💕 *Статус:* {status}\n"
            f"⭐ *Очков получено:* +{int(score)}\n"
            f"📅 *Дата:* {datetime.now().strftime('%d.%m.%Y')}\n\n"
            f"{diplom['text']}\n\n"
            f"{diplom['border']}\n"
            f"✨ *СПАСИБО ЗА ПРОХОЖДЕНИЕ!* ✨\n"
            f"{diplom['border']}")
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == f"{WOW_EMOJIS['test']} Создать тест":
        await create_test_start(update, context)
    elif text == f"{WOW_EMOJIS['crown']} Мои тесты":
        await my_tests(update, context)
    elif text == f"{WOW_EMOJIS['stats']} Моя статистика":
        await my_stats(update, context)
    elif text == f"{WOW_EMOJIS['daily']} Бонус":
        await daily_bonus(update, context)
    elif text == f"{WOW_EMOJIS['task']} Задания":
        await daily_tasks_handler(update, context)
    elif text == f"{WOW_EMOJIS['achievement']} Достижения":
        await achievements_handler(update, context)
    elif text == f"{WOW_EMOJIS['money']} Пригласить подруг":
        await invite(update, context)
    elif text == f"{WOW_EMOJIS['shop']} Магазин":
        await shop(update, context)
    elif text == f"{WOW_EMOJIS['top']} Топ подруг":
        await top_friends(update, context)
    elif text == f"{WOW_EMOJIS['level']} Рейтинг":
        await rating_handler(update, context)
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
    elif data.startswith("save_test_"):
        await save_test_handler(update, context)
    elif data.startswith("unsave_test_"):
        await unsave_test_handler(update, context)
    elif data.startswith("details_"):
        await test_details(update, context)
    elif data.startswith("share_saved_"):
        await share_saved_test(update, context)
    elif data.startswith("answer_"):
        await take_test_answer(update, context)
    elif data == "open_shop":
        await open_shop_from_premium(update, context)
    elif data == "premium_shop":
        await premium_shop_handler(update, context)
    elif data.startswith("buy_item_"):
        await buy_item_handler(update, context)
    elif data.startswith("buy_"):
        item = data[4:]
        await query.message.reply_text(
            f"💎 *Покупка:* {item}\n\n"
            f"✨ Для оформления подписки напишите @LavaTopBot\n\n"
            f"💰 После оплаты премиум активируется автоматически!\n\n"
            f"Спасибо за выбор!", 
            parse_mode=ParseMode.MARKDOWN
        )
    elif data == "shop":
        await shop(update, context)
    else:
        logger.warning(f"Неизвестный callback: {data}")
    
    await query.answer()

# === АДМИН КОМАНДЫ ===
async def admin_set_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к этой команде!")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "📖 *Использование:*\n"
            "/setpremium @username - выдать премиум на 30 дней\n"
            "/setpremium @username 90 - выдать на 90 дней\n"
            "/setpremium @username 365 - выдать на год\n"
            "/removepremium @username - снять премиум\n"
            "/checkpremium @username - проверить статус\n"
            "/addtests @username 5 - добавить тесты\n"
            "/addpoints @username 100 - добавить очки\n"
            "/createpromo tests 5 - создать промокод на 5 тестов",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        action = context.args[0]
        
        if action.startswith('@'):
            username = action[1:]
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT user_id FROM users WHERE username = ?', (username,))
            row = c.fetchone()
            conn.close()
            if not row:
                await update.message.reply_text(f"❌ Пользователь @{username} не найден!")
                return
            target_id = row['user_id']
        elif action.isdigit():
            target_id = int(action)
        else:
            if action == 'setpremium':
                await update.message.reply_text("❌ Укажите пользователя: /setpremium @username")
                return
            elif action == 'removepremium':
                await update.message.reply_text("❌ Укажите пользователя: /removepremium @username")
                return
            elif action == 'checkpremium':
                await update.message.reply_text("❌ Укажите пользователя: /checkpremium @username")
                return
            elif action == 'addtests' or action == 'addpoints':
                await update.message.reply_text(f"❌ Укажите пользователя: /{action} @username количество")
                return
            else:
                await update.message.reply_text(f"❌ Неизвестная команда: {action}")
                return
        
        if action == 'setpremium':
            days = 30
            if len(context.args) > 1 and context.args[1].isdigit():
                days = int(context.args[1])
            unlimited_until = (datetime.now() + timedelta(days=days)).isoformat()
            conn = get_db()
            c = conn.cursor()
            c.execute('UPDATE users SET unlimited_until = ? WHERE user_id = ?', (unlimited_until, target_id))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ Пользователю выдан премиум на {days} дней!")
            
        elif action == 'removepremium':
            conn = get_db()
            c = conn.cursor()
            c.execute('UPDATE users SET unlimited_until = NULL WHERE user_id = ?', (target_id,))
            conn.commit()
            conn.close()
            await update.message.reply_text("✅ Премиум удален!")
            
        elif action == 'checkpremium':
            user = get_user(target_id)
            if user and user.get('unlimited_until'):
                until = datetime.fromisoformat(user['unlimited_until'])
                if until > datetime.now():
                    await update.message.reply_text(f"✅ Пользователь имеет премиум до {until.strftime('%d.%m.%Y')}")
                else:
                    await update.message.reply_text("❌ Премиум истек")
            else:
                await update.message.reply_text("❌ У пользователя нет премиум подписки")
        
        elif action == 'addtests':
            if len(context.args) < 2 or not context.args[1].isdigit():
                await update.message.reply_text("❌ Укажите количество: /addtests @username 5")
                return
            count = int(context.args[1])
            add_tests(target_id, count)
            await update.message.reply_text(f"✅ Добавлено {count} тестов пользователю!")
            
        elif action == 'addpoints':
            if len(context.args) < 2 or not context.args[1].isdigit():
                await update.message.reply_text("❌ Укажите количество: /addpoints @username 100")
                return
            count = int(context.args[1])
            add_points(target_id, count)
            await update.message.reply_text(f"✅ Добавлено {count} очков пользователю!")
            
        elif action == 'createpromo':
            if len(context.args) < 3:
                await update.message.reply_text("❌ Использование: /createpromo tests 5\nИли: /createpromo points 100\nИли: /createpromo premium 30")
                return
            reward_type = context.args[1]
            reward_value = int(context.args[2])
            code = f"{reward_type.upper()}{random.randint(10000, 99999)}"
            expires_at = (datetime.now() + timedelta(days=30)).isoformat()
            conn = get_db()
            c = conn.cursor()
            c.execute('INSERT INTO promocodes (code, reward_type, reward_value, expires_at) VALUES (?, ?, ?, ?)',
                     (code, reward_type, reward_value, expires_at))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ Создан промокод: `{code}`\nНаграда: {reward_value} {reward_type}\nДействителен 30 дней", parse_mode=ParseMode.MARKDOWN)
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setpremium", admin_set_premium))
    app.add_handler(CommandHandler("removepremium", admin_set_premium))
    app.add_handler(CommandHandler("checkpremium", admin_set_premium))
    app.add_handler(CommandHandler("addtests", admin_set_premium))
    app.add_handler(CommandHandler("addpoints", admin_set_premium))
    app.add_handler(CommandHandler("createpromo", admin_set_premium))
    app.add_handler(CommandHandler("promocode", promocode_handler))
    
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['test']} Создать тест$"), create_test_start))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['crown']} Мои тесты$"), my_tests))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['stats']} Моя статистика$"), my_stats))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['daily']} Бонус$"), daily_bonus))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['task']} Задания$"), daily_tasks_handler))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['achievement']} Достижения$"), achievements_handler))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['money']} Пригласить подруг$"), invite))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['shop']} Магазин$"), shop))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['top']} Топ подруг$"), top_friends))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['level']} Рейтинг$"), rating_handler))
    
    app.add_handler(MessageHandler(filters.Regex("^➕ Добавить вариант$"), add_option))
    app.add_handler(MessageHandler(filters.Regex("^✅ Готово$"), finish_options))
    app.add_handler(MessageHandler(filters.Regex(f"^{WOW_EMOJIS['back']} Назад$"), back_to_questions))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Назад к вопросам$"), back_to_questions))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.Regex("^❌ Отмена$"), cancel_creation))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🚀 Бот успешно запущен с новыми механиками удержания!")
    app.run_polling()

if __name__ == "__main__":
    main()
