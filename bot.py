#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PodrugaTestBot — бот для тестов между подругами
Версия: 9.5 — БЕЗ FLASK, ТОЛЬКО POLLING
"""

import logging
import json
import sqlite3
import random
import os
import asyncio
import hashlib
import io
import threading
import sys
import time
import platform
from datetime import datetime, timedelta
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import yookassa
from yookassa import Payment, Configuration
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from collections import defaultdict
from functools import wraps

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

# === НАСТРОЙКА ===
BOT_USERNAME = "PodrugaTestBot"
DB_NAME = 'bot_simple.db'
FREE_TESTS_LIMIT = 5
MAX_QUESTIONS = 10
MAX_OPTIONS = 4
ADMIN_ID = 710623393
BOT_START_TIME = time.time()

# ЮKassa настройки
SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "1337862")
SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
Configuration.account_id = SHOP_ID
Configuration.secret_key = SECRET_KEY

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# === PSUTIL ДЛЯ МОНИТОРИНГА ===
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil не установлен. Мониторинг сервера будет недоступен")

# === СКЛОНЕНИЕ СЛОВ ===
def decline_word(number, word1, word2, word3):
    if 11 <= number % 100 <= 19:
        return word3
    if number % 10 == 1:
        return word1
    if 2 <= number % 10 <= 4:
        return word2
    return word3

def decline_friend_word(number):
    if 11 <= number % 100 <= 19:
        return "подруг"
    if number % 10 == 1:
        return "подруга"
    if 2 <= number % 10 <= 4:
        return "подруги"
    return "подруг"

# === СЕРВЕРНАЯ СТАТИСТИКА ===
def get_server_stats() -> dict:
    """Сбор базовой статистики сервера"""
    if not PSUTIL_AVAILABLE:
        return {'error': 'psutil не установлен'}
    
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        
        memory = psutil.virtual_memory()
        memory_total_gb = round(memory.total / (1024**3), 1)
        memory_used_gb = round(memory.used / (1024**3), 1)
        memory_percent = memory.percent
        
        disk = psutil.disk_usage('/')
        disk_total_gb = round(disk.total / (1024**3), 1)
        disk_used_gb = round(disk.used / (1024**3), 1)
        disk_percent = disk.percent
        
        uptime_seconds = int(time.time() - BOT_START_TIME)
        days, rem = divmod(uptime_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{days}д {hours}ч {minutes}м" if days > 0 else f"{hours}ч {minutes}м {seconds}с"
        
        process = psutil.Process(os.getpid())
        bot_memory_mb = round(process.memory_info().rss / (1024**2), 1)
        bot_cpu = process.cpu_percent(interval=0.1)
        bot_threads = process.num_threads()
        
        system_info = f"{platform.system()} {platform.release()}"
        python_ver = platform.python_version()
        
        return {
            'timestamp': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
            'system': system_info,
            'python': python_ver,
            'uptime': uptime_str,
            'cpu': {'percent': cpu_percent, 'cores': cpu_count},
            'memory': {'total_gb': memory_total_gb, 'used_gb': memory_used_gb, 'percent': memory_percent},
            'disk': {'total_gb': disk_total_gb, 'used_gb': disk_used_gb, 'percent': disk_percent},
            'bot_process': {'memory_mb': bot_memory_mb, 'cpu_percent': bot_cpu, 'threads': bot_threads}
        }
    except Exception as e:
        return {'error': str(e)}

def get_server_status_emoji(percent: float, thresholds: tuple = (50, 80)) -> str:
    if percent < thresholds[0]:
        return '🟢'
    elif percent < thresholds[1]:
        return '🟡'
    else:
        return '🔴'

# === АНТИСПАМ СИСТЕМА ===
class AntiSpam:
    def __init__(self):
        self._actions = defaultdict(lambda: defaultdict(list))
        self._blocked_users = set()
        self._blocked_until = {}
        self._warnings = defaultdict(int)
        self._warning_timestamps = defaultdict(list)
        
        self.limits = {
            'message': {'max': 30, 'window': 60},
            'create_test': {'max': 3, 'window': 300},
            'take_test': {'max': 5, 'window': 60},
            'callback': {'max': 40, 'window': 60},
            'share': {'max': 10, 'window': 300},
        }
        
        self.max_warnings = 3
        self.warning_reset_time = 3600
        self.block_duration = 600
        
        logger.info("🛡️ Антиспам-система инициализирована")
    
    def check_rate_limit(self, user_id: int, action_type: str) -> tuple:
        if user_id in self._blocked_users:
            if time.time() < self._blocked_until.get(user_id, 0):
                remaining = int(self._blocked_until[user_id] - time.time())
                return False, f"🚫 Доступ заблокирован! Подожди {remaining} сек."
            else:
                self._blocked_users.discard(user_id)
                self._blocked_until.pop(user_id, None)
        
        if action_type not in self.limits:
            return True, ""
        
        limit_config = self.limits[action_type]
        max_actions = limit_config['max']
        window = limit_config['window']
        
        current_time = time.time()
        if user_id in self._actions and action_type in self._actions[user_id]:
            self._actions[user_id][action_type] = [
                t for t in self._actions[user_id][action_type]
                if current_time - t < window
            ]
        
        self._actions[user_id][action_type].append(current_time)
        action_count = len(self._actions[user_id][action_type])
        
        if action_count > max_actions:
            self._add_warning(user_id, f"Лимит {action_type}")
            return False, f"⚠️ Слишком много действий! Подожди немного."
        
        return True, ""
    
    def check_flood(self, user_id: int, text: str) -> bool:
        key = 'identical_messages'
        current_time = time.time()
        
        if user_id in self._actions and key in self._actions[user_id]:
            self._actions[user_id][key] = [
                (t, msg) for t, msg in self._actions[user_id][key]
                if current_time - t < 10
            ]
        
        identical_count = sum(1 for _, msg in self._actions.get(user_id, {}).get(key, []) if msg == text)
        
        if user_id not in self._actions:
            self._actions[user_id] = defaultdict(list)
        self._actions[user_id][key].append((current_time, text))
        
        if identical_count >= 3:
            self._add_warning(user_id, "Флуд одинаковыми сообщениями")
            return False
        return True
    
    def _add_warning(self, user_id: int, reason: str):
        current_time = time.time()
        self._warning_timestamps[user_id] = [
            t for t in self._warning_timestamps.get(user_id, [])
            if current_time - t < self.warning_reset_time
        ]
        self._warnings[user_id] += 1
        self._warning_timestamps[user_id].append(current_time)
        
        if len(self._warning_timestamps[user_id]) >= self.max_warnings:
            self._blocked_users.add(user_id)
            self._blocked_until[user_id] = time.time() + self.block_duration
            logger.warning(f"🚫 Пользователь {user_id} заблокирован на {self.block_duration}с")
    
    def unblock_user(self, user_id: int):
        self._blocked_users.discard(user_id)
        self._blocked_until.pop(user_id, None)
        self._warnings[user_id] = 0
        self._warning_timestamps[user_id] = []
    
    def periodic_cleanup(self):
        current_time = time.time()
        for user_id in list(self._actions.keys()):
            for action_type in list(self._actions[user_id].keys()):
                self._actions[user_id][action_type] = [
                    t for t in self._actions[user_id][action_type]
                    if (isinstance(t, tuple) and current_time - t[0] < 3600) or
                       (not isinstance(t, tuple) and current_time - t < 3600)
                ]
            if not any(self._actions[user_id].values()):
                del self._actions[user_id]

antispam = AntiSpam()

def rate_limit(action_type: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user_id = update.effective_user.id if hasattr(update, 'effective_user') else 0
            allowed, error_msg = antispam.check_rate_limit(user_id, action_type)
            if not allowed:
                if hasattr(update, 'message') and update.message:
                    await update.message.reply_text(error_msg)
                elif hasattr(update, 'callback_query') and update.callback_query:
                    await update.callback_query.answer(error_msg, show_alert=True)
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator

def flood_check(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        if hasattr(update, 'message') and update.message and update.message.text:
            user_id = update.effective_user.id
            if not antispam.check_flood(user_id, update.message.text):
                await update.message.reply_text("⚠️ Не флуди одинаковыми сообщениями!")
                return
        return await func(update, context, *args, **kwargs)
    return wrapper

# === МЕДИА МЕНЕДЖЕР ===
class MediaManager:
    def __init__(self, db_name: str = 'bot_simple.db'):
        self.db_name = db_name
        self.max_greeting_size_mb = 5
        self.max_greeting_duration_sec = 15
        self.max_total_media_per_user = 50
        self._init_db()
        logger.info("🎬 MediaManager инициализирован")
    
    def _get_db(self):
        conn = sqlite3.connect(self.db_name, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        conn = self._get_db()
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS media_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            file_type TEXT NOT NULL,
            test_id INTEGER,
            user_id INTEGER NOT NULL,
            file_size_bytes INTEGER,
            duration_seconds REAL,
            views_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_viewed_at TIMESTAMP,
            is_valid INTEGER DEFAULT 1
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS media_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            viewer_id INTEGER NOT NULL,
            test_id INTEGER,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        conn.commit()
        conn.close()
    
    def validate_media(self, file_id: str, file_type: str, file_size: int = 0, duration: float = 0) -> dict:
        if file_size > self.max_greeting_size_mb * 1024 * 1024:
            return {'valid': False, 'reason': f'Файл слишком большой (> {self.max_greeting_size_mb} MB)'}
        if file_type in ('voice', 'video') and duration > self.max_greeting_duration_sec:
            return {'valid': False, 'reason': f'Слишком длинное (> {self.max_greeting_duration_sec} сек)'}
        return {'valid': True, 'reason': 'ok'}
    
    def track_media(self, file_id: str, file_type: str, user_id: int, test_id: int = None, file_size: int = 0, duration: float = 0) -> bool:
        conn = self._get_db()
        c = conn.cursor()
        try:
            c.execute('INSERT INTO media_tracking (file_id, file_type, test_id, user_id, file_size_bytes, duration_seconds) VALUES (?, ?, ?, ?, ?, ?)',
                     (file_id, file_type, test_id, user_id, file_size, duration))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка отслеживания медиа: {e}")
            return False
        finally:
            conn.close()
    
    def mark_as_viewed(self, file_id: str, viewer_id: int, test_id: int = None):
        conn = self._get_db()
        c = conn.cursor()
        try:
            c.execute('UPDATE media_tracking SET views_count = views_count + 1, last_viewed_at = CURRENT_TIMESTAMP WHERE file_id = ?', (file_id,))
            c.execute('INSERT INTO media_views (file_id, viewer_id, test_id) VALUES (?, ?, ?)', (file_id, viewer_id, test_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Ошибка отметки просмотра: {e}")
        finally:
            conn.close()
    
    def get_media_stats(self, user_id: int = None) -> dict:
        conn = self._get_db()
        c = conn.cursor()
        stats = {'total_media': 0, 'active_media': 0, 'total_size_bytes': 0, 'total_views': 0, 'by_type': {}}
        
        c.execute('SELECT COUNT(*) FROM media_tracking')
        stats['total_media'] = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM media_tracking WHERE is_valid = 1')
        stats['active_media'] = c.fetchone()[0]
        
        c.execute('SELECT file_type, COUNT(*) as count, SUM(file_size_bytes) as size, SUM(views_count) as views FROM media_tracking GROUP BY file_type')
        for row in c.fetchall():
            stats['by_type'][row['file_type']] = {'count': row['count'], 'size_bytes': row['size'] or 0, 'views': row['views'] or 0}
            stats['total_size_bytes'] += (row['size'] or 0)
            stats['total_views'] += (row['views'] or 0)
        
        conn.close()
        return stats
    
    def periodic_cleanup(self) -> dict:
        conn = self._get_db()
        c = conn.cursor()
        
        c.execute("UPDATE media_tracking SET is_valid = 0 WHERE created_at < datetime('now', '-30 days') AND views_count = 0")
        cleaned_inactive = c.rowcount
        
        c.execute("UPDATE media_tracking SET is_valid = 0 WHERE views_count > 0 AND last_viewed_at < datetime('now', '-7 days')")
        cleaned_viewed = c.rowcount
        
        c.execute('UPDATE media_tracking SET is_valid = 0 WHERE test_id IS NOT NULL AND test_id NOT IN (SELECT id FROM tests)')
        cleaned_orphaned = c.rowcount
        
        conn.commit()
        conn.close()
        
        return {
            'cleaned_inactive': cleaned_inactive,
            'cleaned_viewed': cleaned_viewed,
            'cleaned_orphaned': cleaned_orphaned,
            'total_cleaned': cleaned_inactive + cleaned_viewed + cleaned_orphaned
        }

media_manager = MediaManager()

# === МЕНЕДЖЕР РАССЫЛОК ===
class BroadcastManager:
    def __init__(self, db_name: str = 'bot_simple.db'):
        self.db_name = db_name
    
    def _get_db(self):
        conn = sqlite3.connect(self.db_name, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_broadcast(self, admin_id: int, message_data: dict, total_users: int) -> int:
        conn = self._get_db()
        c = conn.cursor()
        
        c.execute('''INSERT INTO broadcasts (admin_id, message_text, message_type, file_id, total_users, status)
                     VALUES (?, ?, ?, ?, ?, 'sending')''',
                  (admin_id, message_data.get('text', ''), message_data.get('type', 'text'),
                   message_data.get('file_id'), total_users))
        
        broadcast_id = c.lastrowid
        
        c.execute('SELECT user_id FROM users')
        users = c.fetchall()
        for user in users:
            c.execute('INSERT INTO broadcast_messages (broadcast_id, user_id, status) VALUES (?, ?, ?)',
                     (broadcast_id, user['user_id'], 'sent'))
        
        conn.commit()
        conn.close()
        return broadcast_id
    
    def update_message_status(self, broadcast_id: int, user_id: int, status: str, message_id: int = None, error: str = None):
        conn = self._get_db()
        c = conn.cursor()
        update_fields = ['status = ?']
        params = [status]
        if message_id:
            update_fields.append('message_id = ?')
            params.append(message_id)
        if error:
            update_fields.append('error_text = ?')
            params.append(error)
        params.extend([broadcast_id, user_id])
        c.execute(f'UPDATE broadcast_messages SET {", ".join(update_fields)} WHERE broadcast_id = ? AND user_id = ?', params)
        conn.commit()
        conn.close()
    
    def update_broadcast_stats(self, broadcast_id: int):
        conn = self._get_db()
        c = conn.cursor()
        c.execute('''UPDATE broadcasts SET
            sent_count = (SELECT COUNT(*) FROM broadcast_messages WHERE broadcast_id = ? AND status IN ('sent', 'delivered', 'read')),
            delivered_count = (SELECT COUNT(*) FROM broadcast_messages WHERE broadcast_id = ? AND status IN ('delivered', 'read')),
            read_count = (SELECT COUNT(*) FROM broadcast_messages WHERE broadcast_id = ? AND status = 'read'),
            failed_count = (SELECT COUNT(*) FROM broadcast_messages WHERE broadcast_id = ? AND status = 'failed'),
            blocked_count = (SELECT COUNT(*) FROM broadcast_messages WHERE broadcast_id = ? AND status = 'blocked')
            WHERE id = ?''', (broadcast_id,) * 6)
        conn.commit()
        conn.close()
    
    def complete_broadcast(self, broadcast_id: int):
        conn = self._get_db()
        c = conn.cursor()
        c.execute('UPDATE broadcasts SET status = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?', ('completed', broadcast_id))
        conn.commit()
        conn.close()
    
    def get_broadcast_stats(self, broadcast_id: int) -> dict:
        conn = self._get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM broadcasts WHERE id = ?', (broadcast_id,))
        broadcast = c.fetchone()
        if not broadcast:
            conn.close()
            return None
        
        stats = dict(broadcast)
        c.execute('''SELECT COUNT(*) as total,
                     SUM(CASE WHEN status IN ('sent', 'delivered', 'read') THEN 1 ELSE 0 END) as sent,
                     SUM(CASE WHEN status IN ('delivered', 'read') THEN 1 ELSE 0 END) as delivered,
                     SUM(CASE WHEN status = 'read' THEN 1 ELSE 0 END) as read,
                     SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                     SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked
                     FROM broadcast_messages WHERE broadcast_id = ?''', (broadcast_id,))
        
        detail_stats = dict(c.fetchone())
        stats.update(detail_stats)
        
        total = detail_stats['total'] or 1
        stats['delivery_rate'] = round(detail_stats['delivered'] / total * 100, 1)
        stats['read_rate'] = round(detail_stats['read'] / total * 100, 1)
        stats['block_rate'] = round(detail_stats['blocked'] / total * 100, 1)
        stats['fail_rate'] = round(detail_stats['failed'] / total * 100, 1)
        
        conn.close()
        return stats
    
    def get_recent_broadcasts(self, limit: int = 5) -> list:
        conn = self._get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT ?', (limit,))
        broadcasts = [dict(row) for row in c.fetchall()]
        conn.close()
        return broadcasts

broadcast_manager = BroadcastManager()

# === ТЕМЫ ВОПРОСОВ ===
QUESTION_GROUPS = {
    'friendship': '👭 Дружба',
    'love': '💖 Любовь и краши',
    'style': '👗 Стиль и мода',
    'beauty': '💄 Бьюти и уход',
    'social': '📱 Соцсети и блогерство',
    'school': '📚 Школа и учёба',
    'dreams': '✨ Мечты и будущее',
    'kpop': '🎤 K-pop и айдолы',
    'food': '🍕 Еда и вкусняшки',
    'humor': '😂 Приколы и мемы'
}

PRESET_GROUPS = {
    'best_friend': {
        'name': '💕 Для лучшей подруги',
        'questions': [
            "✨ Как долго мы дружим?", "💕 Где мы познакомились?", "🎨 Мой любимый цвет?",
            "🤫 Мой секрет, который знаешь только ты?", "💬 Фраза, которую я часто говорю?",
            "😢 Из-за чего я могу заплакать?", "🌟 Моя заветная мечта?",
            "🎁 Что я дарила тебе на ДР?", "📸 Наше лучшее совместное фото?",
            "💖 Что я ценю в нашей дружбе больше всего?"
        ]
    },
    'new_friend': {
        'name': '👋 Для новой знакомой',
        'questions': [
            "🌸 Какое моё хобби?", "🎵 Мой любимый исполнитель?", "📺 Мой любимый сериал?",
            "🍕 Моя любимая еда?", "💃 Моё любимое занятие?", "📱 Как часто я сижу в телефоне?",
            "🐶 Есть ли у меня питомец?", "☕ Что я заказываю в кафе?",
            "🎬 Мой любимый фильм?", "👗 Какой стиль одежды я предпочитаю?"
        ]
    },
    'birthday': {
        'name': '🎂 Ко дню рождения',
        'questions': [
            "🎁 Что я хочу в подарок?", "🎂 Моё любимое блюдо на ДР?", "🌟 Моя заветная мечта?",
            "📅 Когда у меня День Рождения?", "🎉 Как я люблю праздновать?",
            "🍰 Какой торт я люблю?", "🎈 Что я делаю в свой ДР обычно?",
            "💐 Какие цветы мне нравятся?", "🎵 Под какую музыку я задуваю свечи?",
            "💖 Что для меня самый лучший подарок?"
        ]
    },
    'party': {
        'name': '🎉 Для вечеринки',
        'questions': [
            "💃 Как я танцую?", "🎤 Моя песня в караоке?", "🍹 Мой любимый напиток?",
            "👗 Что я надену на вечеринку?", "📸 Люблю ли я фоткаться?",
            "🎭 Какое лицо я корчу на селфи?", "🤣 Как я смеюсь?",
            "🪩 Люблю ли я танцевать до упаду?", "🎲 В какие игры я играю на вечеринках?",
            "✨ Что я делаю, когда все устали, а я нет?"
        ]
    }
}

QUESTIONS = {
    'friendship': [
        "✨ Как долго мы дружим?", "💕 Где мы познакомились?", "🎨 Мой любимый цвет?",
        "🌸 Какое моё хобби?", "📱 Как часто я тебе пишу?", "🎁 Что я дарила тебе на ДР?",
        "😤 Что меня бесит в людях?", "🌟 Моя заветная мечта?", "🎵 Мой любимый исполнитель?",
        "📺 Наш любимый сериал?", "🍕 Что мы всегда заказываем вместе?", "💃 Моё любимое занятие?",
        "😢 Из-за чего я могу заплакать?", "🤫 Мой секрет, который знаешь только ты?",
        "🎬 Фильм, который мы смотрели вместе?", "📸 Наше лучшее совместное фото?",
        "💬 Фраза, которую я часто говорю?", "🛍️ Где мы любим гулять?",
        "😴 В какое время я обычно ложусь спать?", "💖 Что я ценю в нашей дружбе больше всего?"
    ],
    'love': [
        "💘 Какой тип парней мне нравится?", "😳 Как я показываю симпатию?", "🌹 Моё идеальное свидание?",
        "💕 Что для меня важно в отношениях?", "👀 На что я обращаю внимание в первую очередь?",
        "💋 Первый поцелуй — это важно?", "📱 Мой краш из Тиктока?",
        "🎤 Любимый певец, в которого я влюблена?", "💍 Хочу ли я замуж?",
        "😍 Сколько у меня было крашей?", "💌 Писала ли я любовные записки?",
        "🤝 Дружба между парнем и девушкой возможна?", "💔 Как я переживаю расставания?",
        "🎭 Какой типаж парней из фильмов мне нравится?", "📝 Веду ли я дневник про любовь?",
        "😊 Что меня влюбляет в человека?", "🙄 Что меня раздражает в парнях?",
        "💬 Обсуждаю ли я крашей с подругами?", "🎁 Какой подарок от парня я хочу?",
        "💎 Верю ли я в любовь с первого взгляда?"
    ],
    'style': [
        "👗 Мой любимый стиль одежды?", "🎀 Любимый цвет в одежде?", "👟 Кроссовки или каблуки?",
        "🛍️ Мой любимый бренд одежды?", "👖 Джинсы или платья?", "🧥 Какую верхнюю одежду я ношу чаще?",
        "💍 Люблю ли я аксессуары?", "👜 Какая у меня сумка?", "💇‍♀️ Как я обычно укладываю волосы?",
        "💅 Делаю ли я маникюр?", "👓 Ношу ли я очки или линзы?", "🎒 Что всегда в моей сумке?",
        "👚 Какой мой любимый топ?", "🧢 Ношу ли я кепки?", "💄 Крашусь ли я каждый день?",
        "👠 Какая обувь у меня самая любимая?", "📸 В какой одежде я чаще фоткаюсь?",
        "🎨 Какие цвета преобладают в моём гардеробе?", "🪞 Сколько времени я собираюсь на выход?",
        "✨ Что я никогда не надену?"
    ],
    'beauty': [
        "💄 Моя любимая помада?", "🧴 Какой уход за кожей я использую?", "💅 Какой маникюр я люблю?",
        "👁️ Крашу ли я ресницы тушью?", "💇‍♀️ Как часто я стригусь?", "🎨 Крашу ли я волосы?",
        "🧖‍♀️ Делаю ли я маски для лица?", "🪞 Моё любимое зеркало?", "🌸 Мои любимые духи?",
        "💦 Умываюсь ли я пенкой или гелем?", "🧼 Как часто я принимаю ванну?",
        "💤 Делаю ли я ночной уход?", "☀️ Пользуюсь ли я SPF?", "💋 Блеск или матовая помада?",
        "👩‍🎤 Какой макияж я делаю на вечеринку?", "🧴 Какой у меня тип кожи?",
        "💆‍♀️ Делаю ли я массаж лица?", "🦷 Как часто я чищу зубы?",
        "🧴 Моё любимое масло для тела?", "✨ Что для меня главное в уходе за собой?"
    ],
    'social': [
        "📱 Моя любимая соцсеть?", "📸 Что я пощу в сторис?", "❤️ Сколько лайков я обычно набираю?",
        "🦄 Мой любимый фильтр?", "👯 С кем я снимаю контент?", "📺 Какого блогера я смотрю?",
        "🎵 Мой любимый звук из Тиктока?", "🔒 У меня приватный или открытый аккаунт?",
        "💬 Сколько времени я сижу в Телеграме?", "📊 Слежу ли я за статистикой?",
        "🎬 Снимаю ли я Reels?", "📝 Пишу ли я посты или только сторис?",
        "🤳 Делаю ли я селфи каждый день?", "📱 Сколько приложений у меня на телефоне?",
        "🔋 На сколько процентов у меня обычно зарядка?", "🎮 Играю ли я в мобильные игры?",
        "📹 Смотрю ли я YouTube?", "🎤 Записываю ли я голосовые сообщения?",
        "💬 В каких чатах я сижу?", "📲 Как часто я меняю аватарку?"
    ],
    'school': [
        "📖 Мой любимый предмет?", "😫 Самый ненавистный урок?", "📱 Что я делаю на скучных уроках?",
        "👯 С кем я сижу за партой?", "🤫 Как я списываю?", "🍔 Что я ем в столовой?",
        "👩‍🏫 Моя любимая учительница?", "👻 Кого я боюсь в школе?", "🏆 Моя лучшая оценка?",
        "🎒 Что всегда в моём рюкзаке?", "📚 Читаю ли я книги вне программы?",
        "✏️ Какими ручками я пишу?", "📅 Какой день недели самый тяжёлый?",
        "🏃‍♀️ Люблю ли я физкультуру?", "🎨 Какой предмет хочу добавить в расписание?",
        "📝 Делаю ли я домашку сразу?", "🤝 С кем я делаю проекты?", "🎓 Хочу ли я в университет?",
        "📊 Переживаю ли я из-за оценок?", "🌟 Моё главное школьное достижение?"
    ],
    'dreams': [
        "✈️ Куда я мечтаю поехать?", "🌟 Моя самая заветная мечта?", "🚗 Какую машину я хочу?",
        "☀️ Мой идеальный день?", "🛍️ Что я хочу купить прямо сейчас?", "📝 Что у меня в вишлисте?",
        "🏠 Где я хочу жить?", "💎 О чём я мечтаю каждый день?", "🎓 Кем я вижу себя через 5 лет?",
        "💍 Какой я представляю свою свадьбу?", "🐶 Хочу ли я завести питомца?",
        "🎤 Хочу ли я стать знаменитой?", "📸 О чём я мечтаю, глядя на фото?",
        "🌈 В какой стране хочу побывать больше всего?", "🎬 Какой фильм я хочу, чтобы сняли про меня?",
        "💼 Какую работу я хочу?", "🏝️ Остров или горы?", "🛫 Что первое я сделаю, когда разбогатею?",
        "💖 Сколько детей я хочу?", "✨ Какое желание я загадаю на падающую звезду?"
    ],
    'kpop': [
        "🎤 Моя любимая k-pop группа?", "💕 Мой биас?", "🎧 Какой трек сейчас на повторе?",
        "💜 На каком концерте я была/мечтаю побывать?", "⭐ С кем из айдолов хочу встретиться?",
        "💃 Какой танец я выучила?", "🫶 Кто мой вайб?", "🎁 Какой мерч я хочу?",
        "📺 Моё любимое k-pop шоу?", "🌙 Какой юнит или соло я люблю?",
        "🎵 Первая k-pop песня, которую я услышала?", "💿 Сколько у меня альбомов?",
        "📱 Какое фото айдола у меня на заставке?", "🎤 Пою ли я k-pop в караоке?",
        "🪭 Коллекционирую ли я фотокарты?", "💬 С кем я обсуждаю k-pop?",
        "🎬 Смотрю ли я дорамы с айдолами?", "💘 Кто мой bias wrecker?",
        "🎶 Какая группа у меня в топ-3?", "🌟 Какой концепт я люблю больше всего?"
    ],
    'food': [
        "🍕 Моё любимое блюдо?", "😖 Что я ненавижу есть?", "👩‍🍳 Что я умею готовить?",
        "☕ Что я заказываю в кафе?", "🍰 Какие сладости я люблю?", "🍳 Что я ем на завтрак?",
        "🏠 Моё любимое кафе?", "🚫 Какую еду я никогда не буду есть?", "🍜 Лапша или картошка?",
        "🥤 Мой любимый напиток?", "🍦 Какое мороженое я выбираю?", "🍫 Шоколад или чипсы?",
        "🥗 Ем ли я салаты?", "🍔 Фастфуд или домашняя еда?", "🧋 Люблю ли я баббл ти?",
        "🍣 Ем ли я суши?", "🌮 Люблю ли я мексиканскую еду?", "🍩 Какие пончики я люблю?",
        "🧀 Добавляю ли я сыр везде?", "🍇 Какой фрукт мой любимый?"
    ],
    'humor': [
        "🏃‍♀️ Что я делаю, когда опаздываю?", "🤪 Моя самая странная привычка?",
        "💃 Как я танцую, когда никто не видит?", "🍪 Что я ем ночью?", "👀 Как я вру?",
        "😱 Что делаю при виде паука?", "🐌 Мой смешной страх?", "💬 Моя коронная фраза?",
        "🛌 В какой позе я сплю?", "🎤 Моя песня в караоке?", "😂 Над каким мемом я смеялась последним?",
        "📸 Моё самое смешное фото?", "🎭 Какое лицо я корчу на селфи?", "🤣 Как я смеюсь?",
        "🪄 Что бы я сделала, если бы стала невидимкой?", "🎁 Самый странный подарок, который я получала?",
        "💇‍♀️ Моя самая неудачная стрижка?", "👗 Что я надела не по погоде?",
        "📱 Что я случайно лайкнула?", "😅 Попадала ли я в неловкие ситуации?"
    ]
}

# === СТАТУСЫ ДРУЖБЫ ===
def get_friendship_status(score):
    if score >= 90: return "СЁСТРЫ НАВЕК! 👑"
    if score >= 70: return "ЛУЧШИЕ ПОДРУГИ! 💎"
    if score >= 50: return "ХОРОШИЕ ПОДРУЖКИ! 🌸"
    if score >= 30: return "ПРИЯТЕЛЬНИЦЫ! 🌱"
    return "ЗНАКОМЫЕ! 🦋"

def get_friendship_prediction(score, name):
    if score >= 90:
        predictions = [
            f"💕 {name} — твоя родственная душа! Вы понимаете друг друга с полуслова. Береги эту дружбу, она особенная! ✨",
            f"👑 {name} знает тебя лучше всех! Вы как сёстры — такие друзья встречаются раз в жизни. Цени её! 💎",
            f"🌟 {name} — твой идеальный мэтч в дружбе! Вы созданы друг для друга! 💖"
        ]
    elif score >= 70:
        predictions = [
            f"💎 {name} очень хорошо тебя знает! Вы близкие подруги, и ваша дружба крепнет с каждым днём 🌸",
            f"✨ {name} понимает тебя почти во всём. Ещё немного — и вы станете лучшими подругами! 💕",
            f"🌟 Вы с {name} на одной волне! Узнавайте друг друга ещё глубже, впереди много интересного! 🎵"
        ]
    elif score >= 50:
        predictions = [
            f"🌸 {name} знает тебя неплохо, но есть куда расти! Проводите больше времени вместе, это сближает 💫",
            f"🌱 Ваша дружба с {name} только расцветает! Делитесь секретами, мечтами и любимыми треками 🎧",
            f"💫 {name} уже многое о тебе знает. Ещё немного — и вы станете ближе! Устройте совместную прогулку 🌈"
        ]
    elif score >= 30:
        predictions = [
            f"🦋 {name} только начинает тебя узнавать. Это отличный повод пообщаться побольше! Расскажи о себе 💬",
            f"🌱 Вы с {name} на пути к настоящей дружбе. Не останавливайтесь! Впереди столько всего интересного ✨",
            f"📖 {name} знает о тебе основы. Пригласи её на кофе или созвон — это сближает! 💕"
        ]
    else:
        predictions = [
            f"🦋 {name} пока плохо тебя знает. Но это только начало! Каждая великая дружба начинается с первого шага ✨",
            f"🌱 {name} ещё предстоит узнать тебя получше. Поделись своими увлечениями и любимыми фильмами 🎬",
            f"💫 Ваша дружба с {name} только зарождается. Впереди много смеха, секретов и совместных фото! 📸"
        ]
    return random.choice(predictions)

def get_detailed_stats(score):
    if score >= 90: return "ЭКСПЕРТ 👑", "Знает тебя наизусть! Вы родственные души"
    elif score >= 70: return "ПРОФИ 💎", "Отлично тебя знает! Настоящая подруга"
    elif score >= 50: return "ЗНАЕТ 🌸", "Хорошо тебя знает, но есть куда расти"
    elif score >= 30: return "УЧИТСЯ 🌱", "Только узнаёт тебя. Гуляйте чаще!"
    else: return "НОВИЧОК 🦋", "Почти не знает. Расскажи о себе больше!"

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
        is_premium INTEGER DEFAULT 0,
        premium_until TEXT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id INTEGER,
        creator_name TEXT,
        title TEXT,
        questions TEXT,
        options TEXT,
        correct_answers TEXT,
        greeting_type TEXT,
        greeting_file_id TEXT,
        answer_comments TEXT,
        question_photos TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    try:
        c.execute('ALTER TABLE tests ADD COLUMN greeting_type TEXT')
    except: pass
    try:
        c.execute('ALTER TABLE tests ADD COLUMN greeting_file_id TEXT')
    except: pass
    try:
        c.execute('ALTER TABLE tests ADD COLUMN answer_comments TEXT')
    except: pass
    try:
        c.execute('ALTER TABLE tests ADD COLUMN question_photos TEXT')
    except: pass
    
    c.execute('''CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_id INTEGER,
        friend_id INTEGER,
        friend_name TEXT,
        answers TEXT,
        score REAL,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(test_id, friend_id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS broadcasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        message_text TEXT,
        message_type TEXT,
        file_id TEXT,
        total_users INTEGER,
        sent_count INTEGER DEFAULT 0,
        delivered_count INTEGER DEFAULT 0,
        read_count INTEGER DEFAULT 0,
        failed_count INTEGER DEFAULT 0,
        blocked_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'sending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS broadcast_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        broadcast_id INTEGER,
        user_id INTEGER,
        status TEXT DEFAULT 'pending',
        message_id INTEGER,
        error_text TEXT,
        FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id)
    )''')
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных готова")

init_db()

# === ФУНКЦИИ БД ===
def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(user_id, username=None, first_name=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
              (user_id, username, first_name))
    conn.commit()
    conn.close()

def is_premium(user_id):
    user = get_user(user_id)
    if not user or not user.get('premium_until'):
        return False
    try:
        return datetime.fromisoformat(user['premium_until']) > datetime.now()
    except:
        return False

def get_available_tests_count(user_id):
    user = get_user(user_id)
    if not user:
        return FREE_TESTS_LIMIT
    if is_premium(user_id):
        return -1
    tests_created = user.get('tests_created', 0)
    available = FREE_TESTS_LIMIT - tests_created
    return max(0, available)

def can_create_test(user_id):
    if is_premium(user_id):
        return True
    available = get_available_tests_count(user_id)
    return available > 0

def get_user_tests(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, title, created_at FROM tests WHERE creator_id = ? ORDER BY created_at DESC LIMIT 10', (user_id,))
    tests = []
    for row in c.fetchall():
        test = dict(row)
        c.execute('SELECT COUNT(*) FROM attempts WHERE test_id = ?', (test['id'],))
        test['attempts'] = c.fetchone()[0]
        tests.append(test)
    conn.close()
    return tests

def get_test_by_id(test_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM tests WHERE id = ?', (test_id,))
    row = c.fetchone()
    if row:
        test = dict(row)
        test['questions'] = json.loads(test['questions'])
        test['options'] = json.loads(test['options'])
        test['correct_answers'] = json.loads(test['correct_answers'])
        conn.close()
        return test
    conn.close()
    return None

def create_test(creator_id, creator_name, title, questions, options, correct_answers, greeting_type=None, greeting_file_id=None, comments=None, photos=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO tests (creator_id, creator_name, title, questions, options, correct_answers, greeting_type, greeting_file_id, answer_comments, question_photos)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (creator_id, creator_name, title, json.dumps(questions), json.dumps(options), 
               json.dumps(correct_answers), greeting_type, greeting_file_id, json.dumps(comments or {}), json.dumps(photos or {})))
    test_id = c.lastrowid
    c.execute('UPDATE users SET tests_created = tests_created + 1 WHERE user_id = ?', (creator_id,))
    c.execute('SELECT id FROM tests WHERE creator_id = ? ORDER BY created_at DESC LIMIT -1 OFFSET 10', (creator_id,))
    old_tests = c.fetchall()
    for old_test in old_tests:
        c.execute('DELETE FROM attempts WHERE test_id = ?', (old_test['id'],))
        c.execute('DELETE FROM tests WHERE id = ?', (old_test['id'],))
    conn.commit()
    conn.close()
    return test_id

def delete_test(user_id, test_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM tests WHERE id = ? AND creator_id = ?', (test_id, user_id))
    c.execute('DELETE FROM attempts WHERE test_id = ?', (test_id,))
    conn.commit()
    conn.close()
    return True

def save_attempt(test_id, friend_id, friend_name, answers, score):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM attempts WHERE test_id = ? AND friend_id = ?', (test_id, friend_id))
    existing = c.fetchone()
    if existing:
        c.execute('UPDATE attempts SET friend_name = ?, answers = ?, score = ?, completed_at = CURRENT_TIMESTAMP WHERE test_id = ? AND friend_id = ?',
                  (friend_name, json.dumps(answers), score, test_id, friend_id))
    else:
        c.execute('INSERT INTO attempts (test_id, friend_id, friend_name, answers, score) VALUES (?, ?, ?, ?, ?)',
                  (test_id, friend_id, friend_name, json.dumps(answers), score))
    conn.commit()
    conn.close()

def get_test_attempts(test_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT friend_name, score, answers FROM attempts WHERE test_id = ? ORDER BY completed_at DESC', (test_id,))
    attempts = [dict(row) for row in c.fetchall()]
    for a in attempts:
        a['answers'] = json.loads(a['answers'])
    conn.close()
    return attempts

def give_premium(user_id, days=30):
    conn = get_db()
    c = conn.cursor()
    until = (datetime.now() + timedelta(days=days)).isoformat()
    c.execute('UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?', (until, user_id))
    conn.commit()
    conn.close()
    return True

def add_tests_to_user(user_id, count):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT tests_created FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    if row:
        current = row['tests_created']
        new_value = max(0, current - count)
        c.execute('UPDATE users SET tests_created = ? WHERE user_id = ?', (new_value, user_id))
    conn.commit()
    conn.close()
    return True

# === ДИПЛОМ-АНАЛИЗ ===
async def generate_friendship_analysis(user_name, creator_name, test_title, score, status, prediction, categories_stats):
    width, height = 1600, 1300
    image = Image.new('RGB', (width, height), '#1A0B2E')
    draw = ImageDraw.Draw(image)
    
    for y in range(height):
        ratio = y / height
        r = int(26 + (45 - 26) * ratio)
        g = int(11 + (25 - 11) * ratio)
        b = int(46 + (80 - 46) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        font_heading = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 34)
        font_score = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 150)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 28)
        font_prediction = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf", 32)
    except:
        font_title = ImageFont.load_default()
        font_heading = ImageFont.load_default()
        font_text = ImageFont.load_default()
        font_score = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_prediction = ImageFont.load_default()
    
    gold = '#FFD700'
    pink = '#FF6B9D'
    purple = '#A855F7'
    white = '#FFFFFF'
    light_gray = '#E2E8F0'
    gray = '#94A3B8'
    
    draw.ellipse([width-500, -300, width+300, 500], fill='#FF6B9D20', outline='#FF6B9D40', width=4)
    draw.ellipse([-350, height-500, 300, height+300], fill='#A855F740', outline='#A855F760', width=4)
    
    draw.rectangle([25, 25, width-25, height-25], outline=gold, width=5)
    draw.rectangle([40, 40, width-40, height-40], outline=pink, width=3)
    draw.rectangle([50, 50, width-50, height-50], outline=purple, width=1)
    
    title = "АНАЛИЗ ДРУЖБЫ"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    title_width = bbox[2] - bbox[0]
    draw.text((width//2 - title_width//2, 60), title, fill=gold, font=font_title)
    
    draw.rectangle([width//4, 145, width*3//4, 150], fill=pink)
    
    y = 210
    text1 = f"{user_name} знает {creator_name} на:"
    bbox = draw.textbbox((0, 0), text1, font=font_heading)
    text1_width = bbox[2] - bbox[0]
    draw.text((width//2 - text1_width//2, y), text1, fill=white, font=font_heading)
    
    y = 300
    score_text = f"{score:.0f}%"
    bbox = draw.textbbox((0, 0), score_text, font=font_score)
    score_width = bbox[2] - bbox[0]
    
    if score >= 70: score_color = '#10B981'
    elif score >= 50: score_color = '#F59E0B'
    else: score_color = '#EF4444'
    
    draw.text((width//2 - score_width//2 + 6, y + 6), score_text, fill='#00000050', font=font_score)
    draw.text((width//2 - score_width//2, y), score_text, fill=score_color, font=font_score)
    
    y = 460
    subtitle = "ОБЩИЙ РЕЗУЛЬТАТ"
    draw.text((width//2 - 200, y), subtitle, fill=gray, font=font_small)
    
    y = 570
    draw.text((80, y), "ПО КАТЕГОРИЯМ:", fill=light_gray, font=font_heading)
    
    y += 70
    if categories_stats:
        for cat, stats in list(categories_stats.items())[:5]:
            cat_score = stats['correct'] * 100 / stats['total'] if stats['total'] > 0 else 0
            draw.text((100, y), cat, fill=gray, font=font_text)
            
            bar_width = 550
            bar_x = 500
            bar_y = y + 8
            
            draw.rounded_rectangle([bar_x, bar_y, bar_x+bar_width, bar_y+28], radius=14, fill='#2D1B4E', outline=pink+'40', width=2)
            fill_width = int(bar_width * cat_score / 100)
            if fill_width > 0:
                bar_color = '#10B981' if cat_score >= 70 else '#F59E0B' if cat_score >= 50 else '#EF4444'
                draw.rounded_rectangle([bar_x, bar_y, bar_x+fill_width, bar_y+28], radius=14, fill=bar_color)
            
            percent_text = f"{cat_score:.0f}%"
            draw.text((bar_x + bar_width + 20, y), percent_text, fill=white, font=font_text)
            y += 75
    
    y += 60
    draw.text((80, y), "ВЕРДИКТ:", fill=light_gray, font=font_heading)
    y += 60
    draw.text((100, y), status, fill=gold, font=font_text)
    
    y += 90
    draw.text((80, y), "ПРЕДСКАЗАНИЕ:", fill=light_gray, font=font_heading)
    y += 65
    
    words = prediction.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        test_line = ' '.join(current_line)
        bbox = draw.textbbox((0, 0), test_line, font=font_prediction)
        if bbox[2] - bbox[0] > width - 250:
            current_line.pop()
            lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    
    for line in lines:
        draw.text((100, y), line, fill=gray, font=font_prediction)
        y += 45
    
    footer_y = height - 80
    date_text = datetime.now().strftime("%d.%m.%Y")
    draw.text((50, footer_y), date_text, fill=gray, font=font_small)
    
    cert_id = hashlib.md5(f"{user_name}{test_title}{datetime.now()}".encode()).hexdigest()[:8].upper()
    cert_text = f"ID: {cert_id}"
    draw.text((width-200, footer_y), cert_text, fill=gray, font=font_small)
    
    stars = ["★", "★", "★", "★"]
    positions = [(40, 40), (width-80, 40), (40, height-80), (width-80, height-80)]
    for i, (x, y_pos) in enumerate(positions):
        draw.text((x, y_pos), stars[i], fill=gold, font=font_title)
    
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG', quality=95)
    img_byte_arr.seek(0)
    return img_byte_arr

# === КЛАВИАТУРЫ ===
def get_main_keyboard(user_id=None):
    keyboard = [
        [KeyboardButton("🌸 Создать тест")],
        [KeyboardButton("👑 Мои тесты"), KeyboardButton("💎 Премиум")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("🔧 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("📊 Статистика"), KeyboardButton("🖥 Сервер")],
        [KeyboardButton("🎁 Подарить премиум"), KeyboardButton("🛡 Антиспам")],
        [KeyboardButton("➕ Начислить тесты"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("🎬 Медиа"), KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True)

def get_options_keyboard():
    return ReplyKeyboardMarkup([["➕ Добавить вариант", "✅ Готово", "🔙 Назад"]], resize_keyboard=True, one_time_keyboard=True)

def get_question_groups_keyboard():
    keyboard = []
    row = []
    for key, name in QUESTION_GROUPS.items():
        row.append(InlineKeyboardButton(name, callback_data=f"group_{key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🎲 Случайные вопросы", callback_data="group_random")])
    keyboard.append([InlineKeyboardButton("📦 ГОТОВЫЕ НАБОРЫ", callback_data="show_presets")])
    return InlineKeyboardMarkup(keyboard)

def get_question_choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Другой вопрос", callback_data="next_question"),
         InlineKeyboardButton("🎲 Случайный", callback_data="random_question")],
        [InlineKeyboardButton("✅ Этот вопрос", callback_data="select_question")],
        [InlineKeyboardButton("📸 Добавить фото", callback_data="add_photo"),
         InlineKeyboardButton("✏️ Свой вопрос", callback_data="custom_question")]
    ])

def get_test_actions_keyboard(test_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁 Посмотреть", callback_data=f"view_{test_id}"),
         InlineKeyboardButton("📤 Поделиться", callback_data=f"share_{test_id}")],
        [InlineKeyboardButton("📊 Ответы подруг", callback_data=f"answers_{test_id}"),
         InlineKeyboardButton("⚔️ Битва подруг", callback_data=f"battle_{test_id}")],
        [InlineKeyboardButton("📈 Статистика", callback_data=f"stats_friendship_{test_id}"),
         InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{test_id}")]
    ])

def get_share_keyboard(test_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👭 Поделиться с подругой", 
            switch_inline_query=f"💕 Пройди тест обо мне! 👉 https://t.me/{BOT_USERNAME}?start=test_{test_id}")]
    ])

def get_premium_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 15 дней — 99₽", callback_data="buy_15days")],
        [InlineKeyboardButton("💎 Месяц — 149₽", callback_data="buy_month")]
    ])

# === ОСНОВНЫЕ ХЕНДЛЕРЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    
    if not get_user(user.id):
        create_user(user.id, user.username, user.first_name)
    
    if context.args and context.args[0].startswith("test_"):
        test_id = int(context.args[0].split("_")[1])
        test = get_test_by_id(test_id)
        if test:
            creator = get_user(test['creator_id'])
            creator_name = creator.get('first_name', 'Подружка') if creator else 'Подружка'
            
            text = (f"🌸✨ ПРИВЕТ, {user.first_name}! ✨🌸\n\n"
                    f"💕 *{creator_name}* приглашает тебя пройти тест!\n\n"
                    f"📝 *{test['title']}*\n\n"
                    f"👇 Нажми на кнопку и начни!")
            
            try:
                await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_{test_id}")
                ]]))
            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение: {e}")
            return
    
    user_data = get_user(user.id)
    tests_created = user_data.get('tests_created', 0)
    is_prem = is_premium(user.id)
    
    if is_prem:
        text = (f"💎✨ *ПРИВЕТ, {user.first_name}!* ✨💎\n\n"
                f"🌸 Добро пожаловать в мир тестов для лучших подруг! 💕\n\n"
                f"👑 *Твой статус:* ПРЕМИУМ\n"
                f"♾️ Безлимитные тесты\n"
                f"🎓 Золотые дипломы\n"
                f"📊 Смотри ответы подруг\n\n"
                f"✨ *Создай тест о себе и узнай, кто знает тебя лучше всех!* 💕")
    else:
        available = get_available_tests_count(user.id)
        word = decline_word(available, "тест", "теста", "тестов")
        tests_info = f"📊 *Осталось:* {available} {word}" if available > 0 else "⚠️ *Лимит исчерпан!*"
        text = (f"🌸✨ *ПРИВЕТ, {user.first_name}!* ✨🌸\n\n"
                f"💕 Создай тест о себе и отправь подружкам!\n"
                f"Узнайте насколько хорошо вы друг друга знаете 🎯\n\n"
                f"🎁 *Бесплатно:* {FREE_TESTS_LIMIT} тестов\n"
                f"{tests_info}\n\n"
                f"💎 *Premium* открывает:\n"
                f"♾️ Безлимитные тесты\n"
                f"🎓 Красивый золотой диплом\n"
                f"📊 Ответы подруг\n\n"
                f"👇 *Выбирай действие в меню:*")
    
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user.id))

# === АДМИН-ПАНЕЛЬ ===
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа!")
        return
    await update.message.reply_text("🔧 *АДМИН-ПАНЕЛЬ* ✨\n\nВыбери действие в меню 👇", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    conn = get_db()
    c = conn.cursor()
    
    today = datetime.now().date().isoformat()
    week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
    month_ago = (datetime.now() - timedelta(days=30)).date().isoformat()
    
    c.execute('SELECT COUNT(*) FROM users')
    total_users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?', (today,))
    new_today = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE created_at >= ?', (week_ago,))
    new_week = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE created_at >= ?', (month_ago,))
    new_month = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM users WHERE premium_until > ?', (today,))
    premium_active = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL')
    premium_total = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM tests')
    total_tests = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM tests WHERE created_at >= ?', (month_ago,))
    tests_month = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM attempts')
    total_attempts = c.fetchone()[0]
    c.execute('SELECT AVG(score) FROM attempts')
    avg_score = c.fetchone()[0] or 0
    
    conn.close()
    
    text = f"""
📊✨ *СТАТИСТИКА БОТА* ✨📊
🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━

👥 *ПОЛЬЗОВАТЕЛИ*
├ 👑 Всего: *{total_users}*
├ 🆕 Сегодня: *+{new_today}*
├ 📈 За неделю: *+{new_week}*
└ 📅 За месяц: *+{new_month}*

💎 *ПРЕМИУМ*
├ ✨ Активных: *{premium_active}*
├ 💰 Всего купили: *{premium_total}*
└ 📊 Конверсия: *{round(premium_total/max(total_users,1)*100, 1)}%*

📝 *ТЕСТЫ*
├ 📋 Всего создано: *{total_tests}*
└ 📅 За месяц: *+{tests_month}*

🎯 *ПРОХОЖДЕНИЯ*
├ 🎮 Всего: *{total_attempts}*
└ 🎯 Средний балл: *{avg_score:.1f}%*

💡 *АНАЛИЗ:* {'🚀 Бот активно растёт!' if new_week > 100 else '📈 Стабильный рост. Продолжай продвигать!'}
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_refresh_stats")],
        [InlineKeyboardButton("📈 Воронка", callback_data="admin_funnel")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ])
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def admin_server_stats_compact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    stats = get_server_stats()
    
    if 'error' in stats:
        await update.message.reply_text(f"❌ *Ошибка:* {stats['error']}", parse_mode=ParseMode.MARKDOWN)
        return
    
    cpu_emoji = get_server_status_emoji(stats['cpu']['percent'])
    mem_emoji = get_server_status_emoji(stats['memory']['percent'])
    disk_emoji = get_server_status_emoji(stats['disk']['percent'], (70, 90))
    
    text = f"""
🖥 *СЕРВЕР*
⏱ Аптайм: *{stats['uptime']}*

💻 Система: `{stats['system']}`
🐍 Python: `{stats['python']}`
🔢 Ядер CPU: *{stats['cpu']['cores']}*

📊 Нагрузка:
├ CPU: {cpu_emoji} *{stats['cpu']['percent']:.1f}%*
├ RAM: {mem_emoji} *{stats['memory']['percent']:.1f}%*
│   └ {stats['memory']['used_gb']}/{stats['memory']['total_gb']} GB
└ Диск: {disk_emoji} *{stats['disk']['percent']:.1f}%*

🤖 Бот:
├ RAM: *{stats['bot_process']['memory_mb']} MB*
├ CPU: *{stats['bot_process']['cpu_percent']:.1f}%*
└ Потоков: *{stats['bot_process']['threads']}*

💡 {'⚠️ Высокая нагрузка!' if stats['cpu']['percent'] > 80 else '✅ Стабильно'}
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="server_refresh")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ])
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def admin_antispam_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    text = f"🛡️ *АНТИСПАМ*\n\n🚫 Заблокировано: *{len(antispam._blocked_users)}*\n⚠️ С предупреждениями: *{len(antispam._warnings)}*"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def admin_media_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    stats = media_manager.get_media_stats()
    total_size_mb = round(stats['total_size_bytes'] / (1024**2), 1)
    
    text = f"""
🎬 *МЕДИА*

📁 Всего: *{stats['total_media']}* | Активных: *{stats['active_media']}*
💾 Размер: *{total_size_mb} MB*
👁 Просмотров: *{stats['total_views']}*

📊 По типам:
"""
    type_names = {'voice': '🎤 Голосовые', 'video': '🎥 Видео', 'photo': '📸 Фото'}
    for file_type, type_stats in stats['by_type'].items():
        type_name = type_names.get(file_type, file_type)
        size_mb = round(type_stats['size_bytes'] / (1024**2), 2)
        text += f"├ {type_name}: *{type_stats['count']}* ({size_mb} MB)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧹 Очистить", callback_data="media_force_cleanup")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ])
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

# === РАССЫЛКИ ===
async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    if 'admin_action' in context.user_data:
        del context.user_data['admin_action']
    
    context.user_data['creating_broadcast'] = True
    
    recent = broadcast_manager.get_recent_broadcasts(3)
    text = "📢 *РАССЫЛКА*\n\n"
    
    if recent:
        text += "*Последние:*\n"
        for b in recent:
            text += f"• #{b['id']}: отправлено {b['sent_count']}/{b['total_users']}\n"
        text += "\n"
    
    text += "📝 Отправь сообщение для ВСЕХ пользователей.\n❌ *Отмена* — выйти"
    
    keyboard = ReplyKeyboardMarkup([["❌ Отмена", "📊 Статистика рассылок"]], resize_keyboard=True)
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def execute_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID or not context.user_data.get('creating_broadcast'):
        return
    
    message = update.message
    
    message_data = {'type': 'text', 'text': None, 'file_id': None}
    
    if message.text:
        message_data['type'] = 'text'
        message_data['text'] = message.text
    elif message.photo:
        message_data['type'] = 'photo'
        message_data['file_id'] = message.photo[-1].file_id
        message_data['text'] = message.caption or ''
    elif message.video:
        message_data['type'] = 'video'
        message_data['file_id'] = message.video.file_id
        message_data['text'] = message.caption or ''
    elif message.animation:
        message_data['type'] = 'animation'
        message_data['file_id'] = message.animation.file_id
        message_data['text'] = message.caption or ''
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id FROM users')
    users = c.fetchall()
    conn.close()
    
    total_users = len(users)
    broadcast_id = broadcast_manager.create_broadcast(user_id, message_data, total_users)
    
    status_msg = await update.message.reply_text(
        f"📤 *РАССЫЛКА #{broadcast_id}*\n├ Всего: *{total_users}*\n└ Прогресс: *0/{total_users}* (0%)",
        parse_mode=ParseMode.MARKDOWN
    )
    
    stats = {'sent': 0, 'failed': 0, 'blocked': 0}
    
    for i, user in enumerate(users):
        try:
            if message_data['type'] == 'text':
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=message_data['text'],
                    parse_mode=ParseMode.MARKDOWN if message.entities else None
                )
            elif message_data['type'] == 'photo':
                await context.bot.send_photo(
                    chat_id=user['user_id'],
                    photo=message_data['file_id'],
                    caption=message_data['text'] or None
                )
            elif message_data['type'] == 'video':
                await context.bot.send_video(
                    chat_id=user['user_id'],
                    video=message_data['file_id'],
                    caption=message_data['text'] or None
                )
            elif message_data['type'] == 'animation':
                await context.bot.send_animation(
                    chat_id=user['user_id'],
                    animation=message_data['file_id'],
                    caption=message_data['text'] or None
                )
            
            stats['sent'] += 1
            broadcast_manager.update_message_status(broadcast_id, user['user_id'], 'sent')
            
        except Exception as e:
            error_str = str(e)
            if "blocked" in error_str.lower() or "forbidden" in error_str.lower():
                stats['blocked'] += 1
                broadcast_manager.update_message_status(broadcast_id, user['user_id'], 'blocked', error=error_str)
            else:
                stats['failed'] += 1
                broadcast_manager.update_message_status(broadcast_id, user['user_id'], 'failed', error=error_str)
        
        if (i + 1) % 20 == 0 or (i + 1) == total_users:
            percent = (i + 1) / total_users * 100
            try:
                await status_msg.edit_text(
                    f"📤 *РАССЫЛКА #{broadcast_id}*\n"
                    f"├ Всего: *{total_users}*\n"
                    f"├ Отправлено: *{stats['sent']}* ✅\n"
                    f"├ Заблокировали: *{stats['blocked']}* 🚫\n"
                    f"├ Ошибки: *{stats['failed']}* ❌\n"
                    f"└ Прогресс: *{i+1}/{total_users}* ({percent:.0f}%)",
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass
            await asyncio.sleep(0.1)
    
    broadcast_manager.complete_broadcast(broadcast_id)
    final_stats = broadcast_manager.get_broadcast_stats(broadcast_id)
    
    percent = stats['sent'] / total_users * 100 if total_users > 0 else 0
    
    final_text = (
        f"✅ *РАССЫЛКА #{broadcast_id} ЗАВЕРШЕНА!*\n\n"
        f"├ Всего: *{total_users}*\n"
        f"├ Отправлено: *{stats['sent']}* ({percent:.1f}%)\n"
        f"├ Доставлено: *{final_stats.get('delivered_count', 0)}* ({final_stats.get('delivery_rate', 0)}%)\n"
        f"├ Прочитано: *{final_stats.get('read_count', 0)}* ({final_stats.get('read_rate', 0)}%)\n"
        f"├ Заблокировали: *{stats['blocked']}* ({final_stats.get('block_rate', 0)}%)\n"
        f"└ Ошибки: *{stats['failed']}* ({final_stats.get('fail_rate', 0)}%)"
    )
    
    await status_msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
    del context.user_data['creating_broadcast']
    await update.message.reply_text("🔧 *Админ-панель:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

async def broadcast_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    broadcasts = broadcast_manager.get_recent_broadcasts(10)
    
    if not broadcasts:
        await update.message.reply_text("📊 *Нет истории рассылок*", parse_mode=ParseMode.MARKDOWN)
        return
    
    text = "📊 *СТАТИСТИКА РАССЫЛОК*\n\n"
    
    for b in broadcasts:
        total = b['total_users'] or 1
        status_emoji = {'completed': '✅', 'cancelled': '❌'}.get(b['status'], '🔄')
        text += (
            f"{status_emoji} *#{b['id']}* — {b['created_at'][:16]}\n"
            f"├ 📤 Отправлено: *{b['sent_count']}/{total}* ({round(b['sent_count']/total*100, 1)}%)\n"
            f"├ 📬 Доставлено: *{b['delivered_count']}* ({round(b['delivered_count']/max(total,1)*100, 1)}%)\n"
            f"├ 👁 Прочитано: *{b['read_count']}* ({round(b['read_count']/max(total,1)*100, 1)}%)\n"
            f"├ 🚫 Заблокировали: *{b['blocked_count']}*\n"
            f"└ ❌ Ошибки: *{b['failed_count']}*\n\n"
        )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# === АДМИН ДЕЙСТВИЯ ===
async def admin_give_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 день", callback_data="give_premium_1"),
         InlineKeyboardButton("5 дней", callback_data="give_premium_5")],
        [InlineKeyboardButton("15 дней", callback_data="give_premium_15"),
         InlineKeyboardButton("30 дней", callback_data="give_premium_30")]
    ])
    
    await update.message.reply_text("🎁 *ПОДАРИТЬ ПРЕМИУМ*\n\nВыбери срок:", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    context.user_data['admin_action'] = 'give_premium'

async def admin_add_tests_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    context.user_data['admin_action'] = 'add_tests'
    await update.message.reply_text(
        "➕ *НАЧИСЛИТЬ ТЕСТЫ*\n\nВведите username или ID и количество:\nНапример: @anna 5",
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
    )

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    action = context.user_data.get('admin_action')
    if not action:
        return
    
    text = update.message.text.strip()
    
    if action == 'give_premium':
        target = text.lstrip('@')
        days = context.user_data.get('premium_days', 30)
        
        conn = get_db()
        c = conn.cursor()
        if target.isdigit():
            c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(target),))
        else:
            c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            await update.message.reply_text(f"❌ Пользователь {target} не найден", reply_markup=get_admin_keyboard())
            del context.user_data['admin_action']
            return
        
        give_premium(row['user_id'], days)
        day_word = decline_word(days, "день", "дня", "дней")
        await update.message.reply_text(f"✅ *{row['first_name'] or target}* получил премиум на *{days} {day_word}*! 🎉", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        try:
            await context.bot.send_message(chat_id=row['user_id'], text=f"🎉✨ Поздравляем! Вам подарен ПРЕМИУМ на {days} {day_word}!", parse_mode=ParseMode.MARKDOWN)
        except:
            pass
        del context.user_data['admin_action']
        if 'premium_days' in context.user_data:
            del context.user_data['premium_days']
    
    elif action == 'add_tests':
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Введите username и количество!", reply_markup=get_admin_keyboard())
            return
        
        target = parts[0].lstrip('@')
        try:
            count = int(parts[1])
        except:
            await update.message.reply_text("❌ Количество должно быть числом!", reply_markup=get_admin_keyboard())
            return
        
        conn = get_db()
        c = conn.cursor()
        if target.isdigit():
            c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(target),))
        else:
            c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (target,))
        row = c.fetchone()
        
        if not row:
            conn.close()
            await update.message.reply_text(f"❌ Пользователь {target} не найден", reply_markup=get_admin_keyboard())
            del context.user_data['admin_action']
            return
        
        add_tests_to_user(row['user_id'], count)
        available = get_available_tests_count(row['user_id'])
        
        await update.message.reply_text(
            f"✅ *{row['first_name'] or target}* начислено *{count}* тестов!\n📊 Доступно: *{available}*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard()
        )
        try:
            await context.bot.send_message(chat_id=row['user_id'], text=f"🎁 Вам начислено +{count} тестов!")
        except:
            pass
        conn.close()
        del context.user_data['admin_action']

# === СОЗДАНИЕ ТЕСТА ===
@rate_limit('create_test')
async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not can_create_test(user_id):
        await update.message.reply_text(
            "💔 *Лимит бесплатных тестов!*\n\n💎 *Купи Премиум* для безлимита!",
            parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user_id)
        )
        return
    
    context.user_data['creating_test'] = {'step': 'title'}
    
    is_prem = is_premium(user_id)
    tests_info = "♾️ *Премиум — безлимит*" if is_prem else f"📊 *Осталось:* {get_available_tests_count(user_id)}"
    
    await update.message.reply_text(
        f"🌸 *СОЗДАЁМ ТЕСТ*\n\n{tests_info}\n\nПридумай название:\n❌ *Отмена* — выйти",
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
    )

async def handle_create_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data or data.get('waiting_comment'):
        return
    
    text = update.message.text.strip()
    step = data.get('step')
    
    if step == 'title':
        if len(text) < 3:
            await update.message.reply_text("⚠️ Название должно быть длиннее 3 символов!")
            return
        data['title'] = text
        data['step'] = 'group'
        await update.message.reply_text("✨ Выбери тему:", reply_markup=get_question_groups_keyboard())
    
    elif step == 'questions_count':
        try:
            count = int(text)
            if count < 2 or count > MAX_QUESTIONS:
                await update.message.reply_text(f"⚠️ От 2 до {MAX_QUESTIONS} вопросов!")
                return
            data['total_q'] = count
            data['current_q'] = 0
            data['questions_data'] = []
            data['comments'] = {}
            data['photos'] = {}
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎤 Голосовое", callback_data="greeting_voice"),
                 InlineKeyboardButton("🎥 Видео", callback_data="greeting_video")],
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="greeting_skip")]
            ])
            await update.message.reply_text(
                "🎬✨ *ДОБАВЬ ПОЗДРАВЛЕНИЕ!* ✨🎬\n\nПодружка получит его после прохождения!",
                parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
            )
            data['step'] = 'greeting'
        except ValueError:
            await update.message.reply_text("⚠️ Напиши число!")

# === ПРОХОЖДЕНИЕ ТЕСТА ===
@rate_limit('take_test')
async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    test_id = int(query.data.replace("start_", ""))
    test = get_test_by_id(test_id)
    user = query.from_user
    
    if not test:
        await query.message.reply_text("💔 Тест не найден")
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM attempts WHERE test_id = ? AND friend_id = ?', (test_id, user.id))
    already_attempted = c.fetchone()
    conn.close()
    
    if already_attempted:
        await query.message.reply_text("💔 *Ты уже проходила этот тест!*", parse_mode=ParseMode.MARKDOWN)
        return
    
    context.user_data['taking_test'] = {'test': test, 'current': 0, 'answers': []}
    await send_question(query, context)

async def send_question(query, context):
    data = context.user_data.get('taking_test')
    test = data['test']
    current = data['current']
    
    photos_raw = test.get('question_photos')
    photos = json.loads(photos_raw) if photos_raw else {}
    
    keyboard = []
    for i, opt in enumerate(test['options'][current]):
        keyboard.append([InlineKeyboardButton(opt[:40], callback_data=f"answer_{i}")])
    
    if str(current) in photos:
        await query.message.reply_photo(
            photo=photos[str(current)],
            caption=f"❓ *Вопрос {current + 1}/{len(test['questions'])}*\n\n{test['questions'][current]}",
            parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        text = f"❓ *Вопрос {current + 1}/{len(test['questions'])}*\n\n{test['questions'][current]}"
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    answer_idx = int(query.data.replace("answer_", ""))
    data = context.user_data.get('taking_test')
    if not data:
        return
    
    test = data['test']
    current = data['current']
    user_answer = test['options'][current][answer_idx]
    correct_idx = test['correct_answers'][current]
    correct_answer = test['options'][current][correct_idx]
    is_correct = answer_idx == correct_idx
    
    data['answers'].append(answer_idx)
    
    if is_correct:
        result_text = f"✅ *ПРАВИЛЬНО!*\n\nТвой ответ: *{user_answer}*"
    else:
        result_text = f"❌ *НЕПРАВИЛЬНО*\n\nТвой ответ: *{user_answer}*\n✅ *Правильно:* {correct_answer}"
    
    await query.message.reply_text(result_text, parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(1)
    
    data['current'] += 1
    
    if data['current'] < len(test['questions']):
        await send_question(query, context)
    else:
        await finish_test(query, context)

async def finish_test(query, context):
    data = context.user_data['taking_test']
    test = data['test']
    answers = data['answers']
    correct = test['correct_answers']
    user = query.from_user
    
    min_len = min(len(answers), len(correct))
    score = sum(1 for i in range(min_len) if answers[i] == correct[i]) * 100 / len(correct) if correct else 0
    save_attempt(test['id'], user.id, user.first_name, answers, score)
    status = get_friendship_status(score)
    prediction = get_friendship_prediction(score, user.first_name)
    
    try:
        creator_id = test['creator_id']
        await context.bot.send_message(
            chat_id=creator_id,
            text=f"🎉💖 *УРА! ТВОЙ ТЕСТ ПРОШЛИ!* 💖🎉\n\n👤 *{user.first_name}* только что прошла твой тест\n📝 «{test['title']}»\n🎯 *Результат:* {score:.0f}%\n🏆 *Статус:* {status}\n\n✨ *Зайди в «👑 Мои тесты» чтобы посмотреть ответы!* ✨",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass
    
    categories_stats = {}
    for i, q in enumerate(test['questions']):
        category = "Другое"
        for cat, cat_questions in QUESTIONS.items():
            if q in cat_questions:
                category = QUESTION_GROUPS.get(cat, cat)
                break
        if category not in categories_stats:
            categories_stats[category] = {'correct': 0, 'total': 0}
        categories_stats[category]['total'] += 1
        if i < len(answers) and answers[i] == correct[i]:
            categories_stats[category]['correct'] += 1
    
    analysis_image = await generate_friendship_analysis(user.first_name, test['creator_name'], test['title'], score, status, prediction, categories_stats)
    
    caption = f"🎉✨ *ТЕСТ ПРОЙДЕН!* ✨🎉\n\n💕 *{user.first_name}*, ты просто супер!\n🔥 *Поделись этим анализом с {test['creator_name']}!* 🔥"
    
    await query.message.reply_photo(analysis_image, caption=caption, parse_mode=ParseMode.MARKDOWN)
    
    if test.get('greeting_file_id'):
        await asyncio.sleep(0.5)
        try:
            if test.get('greeting_type') == 'voice':
                await query.message.reply_voice(test['greeting_file_id'], caption=f"🎬✨ СЮРПРИЗ ОТ {test['creator_name'].upper()}! ✨🎬\n💕 Она приготовила для тебя особенное послание...", parse_mode=ParseMode.MARKDOWN)
            elif test.get('greeting_type') == 'video':
                await query.message.reply_video(test['greeting_file_id'], caption=f"🎬✨ СЮРПРИЗ ОТ {test['creator_name'].upper()}! ✨🎬\n💕 Она приготовила для тебя особенное послание...", parse_mode=ParseMode.MARKDOWN)
            media_manager.mark_as_viewed(test['greeting_file_id'], user.id, test['id'])
        except Exception as e:
            logger.error(f"Ошибка отправки поздравления: {e}")
    
    await query.message.reply_text("✨ *Выбирай действие:* ✨", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user.id))
    del context.user_data['taking_test']

# === МОИ ТЕСТЫ ===
async def my_tests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tests = get_user_tests(user_id)
    
    if not tests:
        await update.message.reply_text(
            "👑✨ *МОИ ТЕСТЫ* ✨👑\n\n"
            "🌸 *У тебя пока нет тестов!*\n\n"
            "💕 Создай свой первый тест о себе\n"
            "и отправь подружкам! Пусть узнают\n"
            "насколько хорошо они тебя знают 🎯\n\n"
            "👇 *Нажми кнопку ниже чтобы создать:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardMarkup([["🌸 Создать тест"]], resize_keyboard=True)
        )
        return
    
    text = f"👑✨ *МОИ ТЕСТЫ* ✨👑\n\n📦 *Создано тестов:* {len(tests)}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    for i, t in enumerate(tests, 1):
        word = decline_friend_word(t['attempts'])
        status = "🔥 ПОПУЛЯРНЫЙ" if t['attempts'] >= 5 else "⭐ АКТИВНЫЙ" if t['attempts'] >= 2 else "🆕 НОВЫЙ"
        text += f"{i}. 📝 *{t['title'][:30]}*\n   👥 Прошли: *{t['attempts']}* {word}\n   📊 Статус: {status}\n   📅 Создан: {t['created_at'][:10]}\n\n"
        keyboard.append([InlineKeyboardButton(f"📝 {t['title'][:30]} ({t['attempts']} 👥)", callback_data=f"mytest_{t['id']}")])
    
    text += "👇 *Выбери тест чтобы посмотреть:*"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def my_test_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    test_id = int(query.data.replace("mytest_", ""))
    test = get_test_by_id(test_id)
    if not test:
        await query.message.reply_text("💔 *Тест не найден*\n\nВозможно он был удалён или истёк срок хранения", parse_mode=ParseMode.MARKDOWN)
        return
    attempts = get_test_attempts(test_id)
    avg_score = sum(a['score'] for a in attempts) / len(attempts) if attempts else 0
    max_score = max(a['score'] for a in attempts) if attempts else 0
    
    status = "🔥 СУПЕР-ПОПУЛЯРНЫЙ!" if len(attempts) >= 10 else "⭐ ПОПУЛЯРНЫЙ!" if len(attempts) >= 5 else "🌸 НАБИРАЕТ ПОПУЛЯРНОСТЬ" if len(attempts) >= 2 else "🆕 ЖДЁТ ПОДРУГ"
    
    text = f"📝 *{test['title']}*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"📊 *СТАТУС ТЕСТА:* {status}\n\n"
    text += f"👥 Прошли: {len(attempts)} {decline_friend_word(len(attempts))}\n"
    text += f"🎯 Средний результат: {avg_score:.0f}%\n"
    if attempts:
        text += f"👑 Лучший результат: {max_score:.0f}%\n"
    text += f"❓ Вопросов в тесте: {len(test['questions'])}\n"
    if test.get('greeting_file_id'):
        text += "🎬 Поздравление: ЕСТЬ ✨\n"
    if test.get('question_photos') and test['question_photos'] != '{}':
        photos_count = len(json.loads(test['question_photos']))
        text += f"📸 Фото в тесте: {photos_count}\n"
    text += "\n👇 *Что хочешь сделать с тестом?*"
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_test_actions_keyboard(test_id))

# === ПРЕМИУМ ===
async def premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_prem = is_premium(user_id)
    
    if is_prem:
        user = get_user(user_id)
        expiry = datetime.fromisoformat(user['premium_until']).strftime('%d.%m.%Y')
        text = (f"💎✨ *У ТЕБЯ ПРЕМИУМ!* ✨💎\n\n"
                f"♾️ Безлимитные тесты\n"
                f"🎓 Красивый золотой диплом\n"
                f"📊 Смотреть ответы подруг\n\n"
                f"📅 *Действует до:* {expiry}\n\n"
                f"💕 *Создавай тесты и проверяй подруг!*")
    else:
        text = ("💎 *ПРЕМИУМ ПОДПИСКА*\n\n"
                "✨ *Что даёт:*\n"
                "♾️ Безлимитные тесты\n"
                "🎓 Красивый золотой диплом\n"
                "📊 Смотреть ответы подруг\n\n"
                "💰 *Стоимость:*\n"
                "• 99₽ — 15 дней\n"
                "• 149₽ — месяц\n\n"
                "👇 *Выбери тариф и открой все возможности:*")
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_premium_keyboard() if not is_prem else get_main_keyboard(user_id))

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "buy_15days":
        days = 15
        price_rub = 99
    else:
        days = 30
        price_rub = 149
    
    payment = Payment.create({
        "amount": {"value": f"{price_rub}.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": f"https://t.me/{BOT_USERNAME}"},
        "description": f"Premium на {days} дней",
        "metadata": {"user_id": query.from_user.id, "days": days},
        "capture": True
    })
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"💎 Оплатить {price_rub}₽", url=payment.confirmation.confirmation_url)]])
    
    await query.message.reply_text(
        f"💎 *Premium на {days} дней*\n\n"
        f"💰 *{price_rub}₽*\n"
        f"✨ Безлимитные тесты\n"
        f"🎓 Золотой диплом\n"
        f"📊 Ответы подруг\n\n"
        f"👇 *Нажми на кнопку для оплаты:*",
        parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
    )

# === ОБРАБОТЧИКИ КНОПОК ===
@flood_check
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if context.user_data.get('creating_broadcast'):
        if text == "❌ Отмена":
            del context.user_data['creating_broadcast']
            await update.message.reply_text("❌ Рассылка отменена", reply_markup=get_admin_keyboard())
            return
        elif text == "📊 Статистика рассылок":
            await broadcast_stats_handler(update, context)
            return
        else:
            await execute_broadcast(update, context)
            return
    
    if context.user_data.get('admin_action'):
        await handle_admin_input(update, context)
        return
    
    if text == "🌸 Создать тест":
        await create_test_start(update, context)
    elif text == "👑 Мои тесты":
        await my_tests_handler(update, context)
    elif text == "💎 Премиум":
        await premium_handler(update, context)
    elif text == "🔧 Админ-панель" and user_id == ADMIN_ID:
        await admin_panel(update, context)
    elif text == "📊 Статистика" and user_id == ADMIN_ID:
        await admin_stats(update, context)
    elif text == "🖥 Сервер" and user_id == ADMIN_ID:
        await admin_server_stats_compact(update, context)
    elif text == "🛡 Антиспам" and user_id == ADMIN_ID:
        await admin_antispam_stats(update, context)
    elif text == "🎬 Медиа" and user_id == ADMIN_ID:
        await admin_media_stats(update, context)
    elif text == "🎁 Подарить премиум" and user_id == ADMIN_ID:
        await admin_give_premium_start(update, context)
    elif text == "➕ Начислить тесты" and user_id == ADMIN_ID:
        await admin_add_tests_start(update, context)
    elif text == "📢 Рассылка" and user_id == ADMIN_ID:
        await admin_broadcast_start(update, context)
    elif text == "❌ Отмена":
        if 'creating_test' in context.user_data:
            del context.user_data['creating_test']
            await update.message.reply_text("❌ Создание отменено", reply_markup=get_main_keyboard(user_id))
        elif user_id == ADMIN_ID and context.user_data.get('admin_action'):
            del context.user_data['admin_action']
            await admin_panel(update, context)
        else:
            await start(update, context)
    elif text == "🔙 Назад":
        await start(update, context)
    elif text == "➕ Добавить вариант":
        data = context.user_data.get('creating_test')
        if data and data.get('step') == 'collecting_options' and len(data.get('current_options', [])) < MAX_OPTIONS:
            data['waiting_for_option'] = True
            await update.message.reply_text(f"✏️ *Напиши вариант №{len(data['current_options']) + 1}:*\n\n💡 *Совет:* Варианты должны быть разными и понятными", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())
    elif text == "✅ Готово":
        data = context.user_data.get('creating_test')
        if data and data.get('step') == 'collecting_options':
            options = data.get('current_options', [])
            if len(options) < 2:
                await update.message.reply_text("⚠️ *Минимум 2 варианта!* Добавь ещё один вариант ответа", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
                data['waiting_for_option'] = True
                return
            keyboard = []
            for i, opt in enumerate(options):
                keyboard.append([InlineKeyboardButton(f"{i+1}. {opt[:30]}", callback_data=f"correct_{i}")])
            await update.message.reply_text(f"❓ *Вопрос:* {data['current_question']}\n\n👇 *Какой вариант ПРАВИЛЬНЫЙ?* 👇\n\nВыбери тот ответ, который описывает ТЕБЯ:", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
            data['waiting_for_option'] = False
    else:
        data = context.user_data.get('creating_test')
        if data:
            if data.get('waiting_comment'):
                await save_comment(update, context)
            elif data.get('waiting_custom_question'):
                text = update.message.text.strip()
                if len(text) < 5:
                    await update.message.reply_text("⚠️ Вопрос должен быть длиннее 5 символов!")
                elif len(text) > 150:
                    await update.message.reply_text("⚠️ Вопрос слишком длинный! До 150 символов.")
                else:
                    data['current_question'] = text
                    data['waiting_custom_question'] = False
                    data['current_options'] = []
                    data['step'] = 'collecting_options'
                    data['waiting_for_option'] = True
                    await update.message.reply_text(f"✅ *Вопрос сохранён!*\n\n📝 *Твой вопрос:* {text}\n\n✏️ *Напиши вариант ответа №1:*\n\n💡 *Совет:* Варианты должны быть разными и понятными", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())
            elif data.get('step') == 'collecting_options' and data.get('waiting_for_option'):
                await handle_create_test(update, context)
            elif data.get('step') == 'collecting_options' and not data.get('waiting_for_option'):
                option_text = text.strip()
                if len(option_text) > 50:
                    await update.message.reply_text("⚠️ *Слишком длинный вариант!* До 50 символов.")
                    return
                data['current_options'].append(option_text)
                options_list = "\n".join([f"{i+1}. {o}" for i, o in enumerate(data['current_options'])])
                if len(data['current_options']) >= MAX_OPTIONS:
                    await update.message.reply_text(f"✅ *Вариант {len(data['current_options'])} добавлен!*\n\n📋 *Твои варианты:*\n{options_list}\n\n🎯 *Достигнут максимум!* Нажми «✅ Готово» чтобы продолжить.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
                else:
                    await update.message.reply_text(f"✅ *Вариант {len(data['current_options'])} добавлен!*\n\n📋 *Твои варианты:*\n{options_list}\n\n➕ *Можешь добавить ещё или нажать «Готово»*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
            else:
                await handle_create_test(update, context)

# === CALLBACK ОБРАБОТЧИК ===
@rate_limit('callback')
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("group_"):
        await select_question_group(update, context)
    elif data == "show_presets":
        await show_presets(update, context)
    elif data.startswith("preset_"):
        await select_preset(update, context)
    elif data == "back_to_groups":
        await query.message.edit_text("✨ Выбери тему:", reply_markup=get_question_groups_keyboard())
    elif data == "next_question":
        await next_question_callback(update, context)
    elif data == "random_question":
        await random_question_callback(update, context)
    elif data == "select_question":
        await select_this_question(update, context)
    elif data == "add_photo":
        await add_photo_to_question(update, context)
    elif data == "custom_question":
        await custom_question(update, context)
    elif data.startswith("correct_"):
        await select_correct(update, context)
    elif data.startswith("skip_comment_"):
        await skip_comment(update, context)
    elif data.startswith("greeting_"):
        await greeting_choice(update, context)
    elif data.startswith("give_premium_"):
        days = int(data.replace("give_premium_", ""))
        context.user_data['premium_days'] = days
        await query.message.edit_text(f"🎁 *ПРЕМИУМ НА {days} {decline_word(days, 'ДЕНЬ', 'ДНЯ', 'ДНЕЙ')}*\n\nВведите username или ID:", parse_mode=ParseMode.MARKDOWN)
        await query.message.reply_text("Ожидаю ввод...", reply_markup=get_cancel_keyboard())
    elif data.startswith("start_"):
        await start_test(update, context)
    elif data.startswith("answer_"):
        await handle_answer(update, context)
    elif data.startswith("mytest_"):
        await my_test_actions(update, context)
    elif data.startswith("view_"):
        test_id = int(data.replace("view_", ""))
        test = get_test_by_id(test_id)
        if test:
            text = f"👁✨ *ПРОСМОТР ТЕСТА* ✨👁\n\n📝 *{test['title']}*\n━━━━━━━━━━━━━━━━━━━━━━\n\n📋 *ТВОИ ВОПРОСЫ И ОТВЕТЫ:*\n\n"
            for i, q in enumerate(test['questions'], 1):
                text += f"*{i}. {q}*\n"
                for j, opt in enumerate(test['options'][i-1]):
                    prefix = "✅" if j == test['correct_answers'][i-1] else "➖"
                    text += f"   {prefix} {opt}\n"
                text += "\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━\n💡 *Подсказка:* Отправь тест подругам\nи узнай кто знает тебя лучше всех! 💕"
            await query.message.reply_text(text[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📤 Поделиться", callback_data=f"share_{test_id}")], [InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_test_{test_id}")]]))
    elif data.startswith("back_to_test_"):
        test_id = int(data.replace("back_to_test_", ""))
        test = get_test_by_id(test_id)
        if test:
            attempts = get_test_attempts(test_id)
            avg_score = sum(a['score'] for a in attempts) / len(attempts) if attempts else 0
            text = f"📝 *{test['title']}*\n\n👥 Прошли: {len(attempts)}\n🎯 Средний: {avg_score:.0f}%\n\n👇 Выбери действие:"
            await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_test_actions_keyboard(test_id))
    elif data.startswith("share_"):
        test_id = int(data.replace("share_", ""))
        user_id = query.from_user.id
        
        if not is_premium(user_id):
            conn = get_db()
            c = conn.cursor()
            c.execute('UPDATE users SET tests_created = tests_created + 1 WHERE user_id = ?', (user_id,))
            conn.commit()
            user_data = get_user(user_id)
            remaining = FREE_TESTS_LIMIT - user_data.get('tests_created', 0)
            conn.close()
            
            if remaining >= 0:
                word = decline_word(remaining, "тест", "теста", "тестов")
                spent_info = f"\n\n📦 *Списан 1 тест*\n📊 *Осталось:* {remaining} {word}"
            else:
                spent_info = f"\n\n📦 *Списан 1 тест*\n⚠️ *Лимит превышен!* Купи Премиум"
        else:
            spent_info = "\n\n💎 *Премиум — безлимитные отправки!* ♾️"
        
        await query.message.reply_text(
            f"📤✨ *ПОДЕЛИСЬ ТЕСТОМ!* ✨📤\n\n"
            f"💕 Отправь тест подруге и узнай\n"
            f"насколько хорошо она тебя знает!\n\n"
            f"🎯 Чем больше подруг пройдут тест —\n"
            f"тем интереснее будет битва за звание\n"
            f"самой лучшей подруги! 👑"
            f"{spent_info}\n\n"
            f"👇 *Нажми на кнопку ниже:*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(test_id)
        )
    elif data.startswith("answers_"):
        test_id = int(data.replace("answers_", ""))
        if not is_premium(query.from_user.id):
            await query.answer("💎 Только для ПРЕМИУМ! Открой все секреты подруг ✨", show_alert=True)
            return
        
        test = get_test_by_id(test_id)
        attempts = get_test_attempts(test_id)
        
        if not attempts:
            await query.message.reply_text(
                "📊✨ *ОТВЕТЫ ПОДРУГ* ✨📊\n\n"
                "👻 *Пока никто не прошёл тест!*\n\n"
                "💕 Отправь ссылку подружкам и узнай\n"
                "все их секретные ответы! 🔍\n\n"
                "📤 *Поделись тестом прямо сейчас* 👇",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💕 Отправить подруге", callback_data=f"share_{test_id}")
                ]])
            )
            return
        
        sorted_attempts = sorted(attempts, key=lambda x: x['score'], reverse=True)
        
        text = f"📊✨ *ОТВЕТЫ ПОДРУГ* ✨📊\n\n📝 *{test['title']}*\n━━━━━━━━━━━━━━━━━━━━━━\n\n👥 *Твои подруги прошли тест:*\n\n"
        
        for a in sorted_attempts[:10]:
            score = a['score']
            if score >= 90: emoji, hint = '👑', 'Знает тебя наизусть! 💕'
            elif score >= 70: emoji, hint = '💎', 'Отлично знает тебя! ✨'
            elif score >= 50: emoji, hint = '🌸', 'Хорошо знает тебя! 🌟'
            elif score >= 30: emoji, hint = '🌱', 'Узнаёт тебя лучше! 💫'
            else: emoji, hint = '🦋', 'Только знакомится! 🌈'
            text += f"{emoji} *{a['friend_name']}* — *{score:.0f}%*\n   💬 _{hint}_\n\n"
        
        text += f"━━━━━━━━━━━━━━━━━━━━━━\n\n💡 *Нажми на подругу чтобы увидеть:*\n🔍 Все её ответы на вопросы\n📊 Детальную статистику\n🔮 Предсказание дружбы\n\n👇 *Выбери подругу:*"
        
        keyboard = []
        for a in sorted_attempts[:10]:
            score = a['score']
            icon = '👑' if score >= 80 else '💎' if score >= 60 else '🌸'
            keyboard.append([InlineKeyboardButton(f"{icon} {a['friend_name'][:20]}: {score:.0f}%", callback_data=f"friend_details_{test_id}_{a['friend_name']}")])
        
        keyboard.append([InlineKeyboardButton("📈 Общая статистика", callback_data=f"stats_friendship_{test_id}"), InlineKeyboardButton("⚔️ Битва подруг", callback_data=f"battle_{test_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_test_{test_id}")])
        
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("friend_details_"):
        parts = data.split("_", 2)
        test_id = int(parts[2].split("_")[0])
        friend_name = "_".join(parts[2].split("_")[1:]) if "_" in parts[2].split("_", 1)[-1] else parts[2].split("_")[-1]
        
        test = get_test_by_id(test_id)
        attempts = get_test_attempts(test_id)
        attempt = next((a for a in attempts if a['friend_name'] == friend_name), None)
        
        if not attempt:
            await query.answer("❌ Ответы не найдены", show_alert=True)
            return
        
        score = attempt['score']
        level, description = get_detailed_stats(score)
        prediction = get_friendship_prediction(score, friend_name)
        correct_count = sum(1 for i, ans in enumerate(attempt['answers']) if i < len(test['correct_answers']) and ans == test['correct_answers'][i])
        total_q = len(test['questions'])
        
        text = f"🔮✨ *ДЕТАЛЬНЫЙ АНАЛИЗ* ✨🔮\n\n👤 *{friend_name}*\n📝 Тест: *{test['title']}*\n━━━━━━━━━━━━━━━━━━━━━━\n\n🎯 *Результат:* {score:.0f}%\n🏆 *Уровень:* {level}\n📊 *{description}*\n✅ Правильно: *{correct_count}* из *{total_q}*\n\n"
        
        if score >= 90:
            text += "👑 *СЁСТРЫ НАВЕК!*\n💕 Вы как две половинки одного целого!\n_Твоя душа знает твою душу_ ✨\n\n"
        elif score >= 70:
            text += "💎 *ЛУЧШИЕ ПОДРУГИ!*\n🌸 Вы понимаете друг друга почти без слов!\n_Цени эту дружбу — она особенная_ 💫\n\n"
        elif score >= 50:
            text += "🌟 *ХОРОШИЕ ПОДРУГИ!*\n🌱 Вы на правильном пути!\n_Ещё немного и вы станете ближе_ 💕\n\n"
        else:
            text += "🦋 *ЗНАКОМЫЕ!*\n🌈 Впереди много интересного!\n_Узнавайте друг друга постепенно_ ✨\n\n"
        
        text += f"🔮 *ПРЕДСКАЗАНИЕ ДРУЖБЫ:*\n_{prediction}_\n\n━━━━━━━━━━━━━━━━━━━━━━\n📋 *ВСЕ ОТВЕТЫ:*\n\n"
        
        comments = json.loads(test.get('answer_comments', '{}')) if test.get('answer_comments') else {}
        
        for i, q in enumerate(test['questions']):
            text += f"*{i+1}. {q}*\n"
            if i < len(attempt['answers']):
                user_ans_idx = attempt['answers'][i]
                correct_idx = test['correct_answers'][i]
                is_correct = user_ans_idx == correct_idx
                if user_ans_idx < len(test['options'][i]):
                    user_ans = test['options'][i][user_ans_idx]
                    correct_ans = test['options'][i][correct_idx]
                    if is_correct:
                        text += f"   ✅ *{user_ans}*\n"
                    else:
                        text += f"   ❌ Ответила: *{user_ans}*\n   ✅ Правильно: *{correct_ans}*\n"
                if str(i) in comments:
                    text += f"   💬 _{comments[str(i)]}_\n"
            text += "\n"
        
        if score >= 80:
            text += f"💕 *ИТОГ:* {friend_name} — твоя родственная душа!\n_Вы созданы друг для друга! Берегите эту дружбу!_ ✨"
        elif score >= 60:
            text += f"🌸 *ИТОГ:* {friend_name} — отличная подруга!\n_Продолжайте узнавать друг друга и становиться ближе!_ 💫"
        else:
            text += f"🌱 *ИТОГ:* Вы только начинаете узнавать друг друга!\n_Проводите больше времени вместе — это сближает!_ 💕"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔️ Битва подруг", callback_data=f"battle_{test_id}"), InlineKeyboardButton("📈 Статистика", callback_data=f"stats_friendship_{test_id}")],
            [InlineKeyboardButton("🔙 К списку подруг", callback_data=f"answers_{test_id}")]
        ])
        
        await query.message.reply_text(text[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    elif data.startswith("battle_"):
        test_id = int(data.replace("battle_", ""))
        test = get_test_by_id(test_id)
        attempts = get_test_attempts(test_id)
        
        if len(attempts) < 2:
            await query.message.reply_text(
                "⚔️✨ *БИТВА ПОДРУГ* ✨⚔️\n\n"
                "😢 *Недостаточно участниц!*\n\n"
                "👯‍♀️ Нужно минимум 2 подруги чтобы устроить\n"
                "эпичное сражение за звание лучшей! 👑\n\n"
                "📤 *Отправь тест ещё одной подруге:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💕 Поделиться", callback_data=f"share_{test_id}")
                ]])
            )
            return
        
        sorted_attempts = sorted(attempts, key=lambda x: x['score'], reverse=True)
        
        text = f"⚔️✨ *БИТВА ПОДРУГ* ✨⚔️\n\n📝 *{test['title']}*\n━━━━━━━━━━━━━━━━━━━━━━\n\n🏆 *ТУРНИРНАЯ ТАБЛИЦА:*\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        descriptions = [
            "👑 *Королева знаний!* Знает тебя лучше всех!",
            "💎 *Бриллиантовая подруга!* Почти идеально!",
            "🌟 *Золотая середина!* Отличный результат!",
            "🌸 *Прелестно!* Старается изо всех сил!",
            "🌱 *Растёт!* Становится ближе с каждым днём!"
        ]
        
        for i, a in enumerate(sorted_attempts[:5]):
            medal = medals[i] if i < 3 else f"  {i+1}."
            score = a['score']
            status = get_friendship_status(score)
            bar = "💜" * int(score / 10) + "🤍" * (10 - int(score / 10))
            
            text += f"{medal} *{a['friend_name']}*\n   [{bar}] *{score:.0f}%*\n   🏆 Статус: *{status}*\n   {descriptions[i] if i < len(descriptions) else '💫 Продолжай узнавать!'}\n\n"
        
        text += "━━━━━━━━━━━━━━━━━━━━━━\n\n⚡ *ПРОТИВОСТОЯНИЕ ЛИДЕРОВ:*\n\n"
        
        if len(sorted_attempts) >= 2:
            first, second = sorted_attempts[0], sorted_attempts[1]
            diff = first['score'] - second['score']
            
            text += f"🥇 *{first['friend_name']}* vs 🥈 *{second['friend_name']}*\n📊 Разрыв: *{diff:.0f}%*\n\n"
            
            if diff >= 30:
                text += f"👑 *ТОТАЛЬНОЕ ДОМИНИРОВАНИЕ!*\n{first['friend_name']} знает тебя в разы лучше!\nОна не просто подруга — она СЕСТРА! 💕\n_Вы понимаете друг друга без слов_ ✨\n"
            elif diff >= 15:
                text += f"💪 *УВЕРЕННОЕ ЛИДЕРСТВО!*\n{first['friend_name']} впереди, но {second['friend_name']}\nещё может наверстать! 🔥\n_Устройте реванш через неделю!_ 🎯\n"
            elif diff >= 5:
                text += f"⚡ *НАПРЯЖЁННАЯ БОРЬБА!*\nРазрыв минимален! Всё решают детали!\nКто знает твой любимый цвет? А песню? 🎵\n_Интрига сохраняется..._ 👀\n"
            else:
                text += f"🎯 *ФОТОФИНИШ!*\nПрактически ОДИНАКОВЫЙ результат!\nОбе подруги знают тебя на отлично! 💕💕\n_Ты окружена замечательными людьми!_ ✨\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Статистика", callback_data=f"stats_friendship_{test_id}"), InlineKeyboardButton("📊 Ответы", callback_data=f"answers_{test_id}")],
            [InlineKeyboardButton("👑 Детали победителя", callback_data=f"friend_details_{test_id}_{first['friend_name']}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_test_{test_id}")]
        ])
        
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    elif data.startswith("stats_friendship_"):
        test_id = int(data.replace("stats_friendship_", ""))
        test = get_test_by_id(test_id)
        attempts = get_test_attempts(test_id)
        
        if not attempts:
            await query.message.reply_text(
                "📈✨ *СТАТИСТИКА ДРУЖБЫ* ✨📈\n\n"
                "😢 *Пока никто не прошёл тест!*\n\n"
                "🌸 Отправь ссылку подружкам и узнай,\n"
                "кто знает тебя лучше всех! 💕",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💕 Поделиться с подругами", callback_data=f"share_{test_id}")
                ]])
            )
            return
        
        sorted_attempts = sorted(attempts, key=lambda x: x['score'], reverse=True)
        avg_score = sum(a['score'] for a in attempts) / len(attempts)
        max_score = max(a['score'] for a in attempts)
        min_score = min(a['score'] for a in attempts)
        
        text = f"📈✨ *СТАТИСТИКА ДРУЖБЫ* ✨📈\n\n📝 *{test['title']}*\n━━━━━━━━━━━━━━━━━━━━━━\n\n👥 *Твои подруги прошли тест:*\n\n"
        
        predictions = [
            "💕 Она твоя родственная душа! ✨",
            "🌸 Настоящая bestie! Цени эту дружбу 💎",
            "🌟 Отличная подруга! Вы на одной волне 🎵",
            "🌱 Хорошая знакомая! Узнавайте друг друга 💫",
            "🤝 Приятельница! Впереди много интересного 🌈",
            "🦋 Новая знакомая! Всё только начинается 💖"
        ]
        
        for i, a in enumerate(sorted_attempts[:10]):
            score = a['score']
            bar = "█" * int(score / 10) + "░" * (10 - int(score / 10))
            
            if score >= 90: emoji, status, pred = '👑', 'ЭКСПЕРТ', predictions[0]
            elif score >= 80: emoji, status, pred = '💎', 'СУПЕР', predictions[0]
            elif score >= 70: emoji, status, pred = '💕', 'ЛУЧШАЯ ПОДРУГА', predictions[1]
            elif score >= 60: emoji, status, pred = '🌸', 'ХОРОШАЯ ПОДРУГА', predictions[2]
            elif score >= 50: emoji, status, pred = '🌟', 'ЗНАЕТ ТЕБЯ', predictions[3]
            elif score >= 40: emoji, status, pred = '🌱', 'УЗНАЁТ ТЕБЯ', predictions[4]
            elif score >= 30: emoji, status, pred = '🤝', 'ЗНАКОМАЯ', predictions[5]
            else: emoji, status, pred = '🦋', 'НОВАЯ ЗНАКОМАЯ', predictions[5]
            
            text += f"{emoji} *{a['friend_name']}*\n   [{bar}] *{score:.0f}%*\n   🏆 Уровень: *{status}*\n   💬 _{pred}_\n\n"
        
        text += f"━━━━━━━━━━━━━━━━━━━━━━\n\n📊 *ОБЩАЯ СТАТИСТИКА:*\n\n"
        text += f"👥 Прошли тест: *{len(attempts)}* {decline_friend_word(len(attempts))}\n"
        text += f"📈 Средний результат: *{avg_score:.0f}%*\n"
        text += f"👑 Лучший результат: *{max_score:.0f}%* — *{sorted_attempts[0]['friend_name']}* 💕\n"
        text += f"💔 Худший результат: *{min_score:.0f}%*\n\n"
        
        if len(attempts) >= 2:
            best, second = sorted_attempts[0], sorted_attempts[1]
            diff = best['score'] - second['score']
            
            text += f"⚡ *БИТВА ЛУЧШИХ ПОДРУГ:*\n"
            text += f"🥇 *{best['friend_name']}* — {best['score']:.0f}%\n"
            text += f"🥈 *{second['friend_name']}* — {second['score']:.0f}%\n\n"
            
            if diff >= 20:
                text += f"👑 *{best['friend_name']}* знает тебя НАМНОГО лучше!\nОна настоящая soulmate! Береги её 💕\n"
            elif diff >= 10:
                text += f"💪 *{best['friend_name']}* уверенно лидирует!\nНо {second['friend_name']} дышит в спину 🔥\n"
            elif diff >= 5:
                text += f"⚡ Напряжённая борьба!\nРазрыв минимален! Устройте реванш 🎯\n"
            else:
                text += f"🎯 Практически ОДИНАКОВЫЙ результат!\nОбе подруги знают тебя отлично! 💕💕\n"
        
        if avg_score >= 80:
            text += f"\n💕 *Вау! Тебя ОТЛИЧНО знают!*\nТы открытая и искренняя душа компании!\nПодруги тебя обожают и понимают с полуслова ✨\n\n🌟 *Совет:* Ты rare find! Продолжай сиять!\n"
        elif avg_score >= 60:
            text += f"\n🌸 *Тебя ХОРОШО знают!*\nТы интересная и загадочная личность.\nПодруги тянутся к тебе и хотят узнать лучше 💫\n\n💡 *Совет:* Расскажи о своих мечтах — это сближает!\n"
        elif avg_score >= 40:
            text += f"\n🌱 *Тебя УЗНАЮТ всё лучше!*\nТы как захватывающая книга — интересно,\nно ещё не всё прочитано 📖\n\n💡 *Совет:* Устройте совместную прогулку или созвон!\n"
        else:
            text += f"\n🦋 *Вы только НАЧИНАЕТЕ дружить!*\nЭто самое волшебное время — первые секреты,\nпервые шутки и первые совместные фото 📸\n\n💡 *Совет:* Поделись своими любимыми треками!\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔️ Битва подруг", callback_data=f"battle_{test_id}"), InlineKeyboardButton("📊 Ответы", callback_data=f"answers_{test_id}")],
            [InlineKeyboardButton("🔮 Детальный анализ", callback_data=f"friend_details_{test_id}_{sorted_attempts[0]['friend_name']}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_test_{test_id}")]
        ])
        
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    elif data.startswith("delete_"):
        test_id = int(data.replace("delete_", ""))
        delete_test(query.from_user.id, test_id)
        await query.message.reply_text("🗑 Тест удалён! Создай новый и проверь подруг снова 💕", reply_markup=get_main_keyboard(query.from_user.id))
    elif data in ["buy_15days", "buy_month"]:
        await buy_premium(update, context)
    elif data == "admin_refresh_stats":
        await admin_stats(update, context)
    elif data == "admin_funnel":
        await admin_funnel(update, context)
    elif data == "back_to_admin":
        query = update.callback_query
        await query.answer()
        await admin_panel(update, context)
    elif data == "server_refresh":
        await admin_server_stats_compact(update, context)
    elif data == "admin_media_stats":
        await admin_media_stats(update, context)
    elif data == "media_force_cleanup":
        result = media_manager.periodic_cleanup()
        await query.answer(f"✅ Очищено {result['total_cleaned']} записей")
        await admin_media_stats(update, context)
    
    await query.answer()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
async def select_question_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    group = query.data.replace("group_", "")
    data = context.user_data.get('creating_test')
    if not data:
        return
    if group == 'random':
        all_questions = []
        for g in QUESTION_GROUPS.keys():
            all_questions.extend(QUESTIONS.get(g, []))
        random.shuffle(all_questions)
        data['group_questions'] = all_questions[:30]
    else:
        data['group_questions'] = QUESTIONS.get(group, []).copy()
        random.shuffle(data['group_questions'])
    data['step'] = 'questions_count'
    await query.message.reply_text(f"📊 Сколько вопросов?\n✏️ Напиши число от 2 до {MAX_QUESTIONS}:", reply_markup=get_cancel_keyboard())

async def show_presets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, preset in PRESET_GROUPS.items():
        keyboard.append([InlineKeyboardButton(preset['name'], callback_data=f"preset_{key}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_groups")])
    await query.message.edit_text("📦 *ГОТОВЫЕ НАБОРЫ*\n\n👇 Выбери:", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def select_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    preset_key = query.data.replace("preset_", "")
    preset = PRESET_GROUPS.get(preset_key)
    if not preset:
        return
    data = context.user_data.get('creating_test')
    if not data:
        return
    data['group_questions'] = preset['questions']
    data['step'] = 'questions_count'
    await query.message.reply_text(f"✅ *{preset['name']}*\n📊 Сколько вопросов?\n✏️ Напиши число:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def greeting_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.replace("greeting_", "")
    data = context.user_data.get('creating_test')
    if choice == "skip":
        data['step'] = 'selecting_question'
        data['current_question_index'] = 0
        data['greeting_type'] = None
        data['greeting_file_id'] = None
        await query.message.reply_text("✨ *Приступаем к вопросам!*", parse_mode=ParseMode.MARKDOWN)
        await show_question_for_selection(query, context)
        return
    data['greeting_type'] = choice
    data['waiting_greeting'] = True
    text = "🎤 Отправь голосовое (до 15 сек)" if choice == "voice" else "🎥 Отправь видео (до 15 сек)"
    await query.message.reply_text(text + "\n\n❌ *Отмена* — пропустить", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def save_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data or not data.get('waiting_greeting'):
        return
    
    user_id = update.effective_user.id
    greeting_type = data['greeting_type']
    
    if greeting_type == "voice":
        if not update.message.voice:
            return
        file_id = update.message.voice.file_id
        file_size = update.message.voice.file_size or 0
        duration = update.message.voice.duration or 0
    else:
        if not update.message.video:
            return
        file_id = update.message.video.file_id
        file_size = update.message.video.file_size or 0
        duration = update.message.video.duration or 0
    
    validation = media_manager.validate_media(file_id, greeting_type, file_size, duration)
    if not validation['valid']:
        await update.message.reply_text(f"❌ {validation['reason']}")
        return
    
    data['greeting_file_id'] = file_id
    data['waiting_greeting'] = False
    data['step'] = 'selecting_question'
    data['current_question_index'] = 0
    data['_pending_media'] = {'file_id': file_id, 'file_type': greeting_type, 'file_size': file_size, 'duration': duration}
    
    await update.message.reply_text(f"✅ *Поздравление сохранено!* ({file_size/1024:.0f} KB, {duration:.0f} сек)\n\n✨ *Приступаем к вопросам!* ✨", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user_id))
    await show_question_for_selection(update, context)

async def save_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data or not data.get('waiting_photo'):
        return
    
    if not update.message.photo:
        return
    
    photo_file_id = update.message.photo[-1].file_id
    
    if 'photos' not in data:
        data['photos'] = {}
    data['photos'][str(data['current_q'])] = photo_file_id
    
    if '_pending_photos' not in data:
        data['_pending_photos'] = []
    data['_pending_photos'].append({'file_id': photo_file_id})
    
    data['waiting_photo'] = False
    data['step'] = 'collecting_options'
    data['current_options'] = []
    data['waiting_for_option'] = True
    
    await update.message.reply_text("✅ *Фото добавлено!* 📸\n\n✏️ *Напиши вариант ответа №1:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def show_question_for_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data:
        return
    questions = data.get('group_questions', [])
    data['current_question_index'] = data.get('current_question_index', 0)
    question_text = questions[data['current_question_index']]
    data['current_question'] = question_text
    text = f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{question_text}"
    
    if hasattr(update, 'message'):
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_choice_keyboard())
    else:
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_choice_keyboard())

async def next_question_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('creating_test')
    if not data:
        return
    questions = data.get('group_questions', [])
    current_idx = (data.get('current_question_index', 0) + 1) % len(questions)
    data['current_question_index'] = current_idx
    data['current_question'] = questions[current_idx]
    text = f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{questions[current_idx]}"
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_choice_keyboard())

async def random_question_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('creating_test')
    if not data:
        return
    all_questions = []
    for g in QUESTION_GROUPS.keys():
        all_questions.extend(QUESTIONS.get(g, []))
    random.shuffle(all_questions)
    data['group_questions'] = all_questions[:30]
    data['current_question_index'] = 0
    data['current_question'] = all_questions[0]
    text = f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{all_questions[0]}"
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_choice_keyboard())

async def select_this_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('creating_test')
    if not data:
        return
    data['current_options'] = []
    data['step'] = 'collecting_options'
    data['waiting_for_option'] = True
    await query.message.reply_text(f"📝 *Вопрос:* {data['current_question']}\n\n✏️ *Напиши вариант ответа №1:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def add_photo_to_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('creating_test')
    if not data or not data.get('current_question'):
        return
    data['waiting_photo'] = True
    await query.message.reply_text("📸 *Отправь фото*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def custom_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('creating_test')
    if not data:
        return
    data['waiting_custom_question'] = True
    await query.message.reply_text("✏️ *Напиши свой вопрос:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def select_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    correct_idx = int(query.data.replace("correct_", ""))
    data = context.user_data.get('creating_test')
    if not data:
        return
    await query.message.reply_text(
        "💬 *Хочешь добавить комментарий к правильному ответу?*\n\nНапиши комментарий или нажми «Пропустить»\n\n*Пример:* «Да, я обожаю этот цвет!»",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Пропустить", callback_data=f"skip_comment_{correct_idx}")]])
    )
    data['waiting_comment'] = True
    data['temp_correct_idx'] = correct_idx

async def save_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data or not data.get('waiting_comment'):
        return
    text = update.message.text.strip()
    correct_idx = data['temp_correct_idx']
    if 'comments' not in data:
        data['comments'] = {}
    data['comments'][str(data['current_q'])] = text
    data['waiting_comment'] = False
    await continue_after_comment(update, context, correct_idx)

async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('creating_test')
    if not data:
        return
    correct_idx = int(query.data.replace("skip_comment_", ""))
    data['waiting_comment'] = False
    await continue_after_comment(query, context, correct_idx)

async def continue_after_comment(update_or_query, context, correct_idx):
    data = context.user_data.get('creating_test')
    
    data['questions_data'].append({
        'text': data['current_question'],
        'options': data['current_options'].copy(),
        'correct': correct_idx
    })
    data['current_q'] += 1
    
    if data['current_q'] < data['total_q']:
        data['step'] = 'selecting_question'
        data['current_question_index'] = (data.get('current_question_index', 0) + 1) % len(data.get('group_questions', []))
        data['current_options'] = []
        data['waiting_for_option'] = False
        data['waiting_comment'] = False
        
        msg = f"✅ *Вопрос {data['current_q']} сохранён!*"
        if hasattr(update_or_query, 'message'):
            await update_or_query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        else:
            await update_or_query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        await show_question_for_selection(update_or_query, context)
    else:
        questions = [q['text'] for q in data['questions_data']]
        options = [q['options'] for q in data['questions_data']]
        correct = [q['correct'] for q in data['questions_data']]
        
        if hasattr(update_or_query, 'from_user'):
            user = update_or_query.from_user
        elif hasattr(update_or_query, 'callback_query') and update_or_query.callback_query:
            user = update_or_query.callback_query.from_user
        else:
            user = update_or_query.effective_user if hasattr(update_or_query, 'effective_user') else None
        
        if not user:
            return
        
        test_id = create_test(user.id, user.first_name, data['title'], questions, options, correct,
                              data.get('greeting_type'), data.get('greeting_file_id'),
                              data.get('comments', {}), data.get('photos', {}))
        
        pending_media = data.get('_pending_media')
        if pending_media:
            media_manager.track_media(
                file_id=pending_media['file_id'], file_type=pending_media['file_type'],
                user_id=user.id, test_id=test_id,
                file_size=pending_media.get('file_size', 0), duration=pending_media.get('duration', 0)
            )
        
        for photo in data.get('_pending_photos', []):
            media_manager.track_media(file_id=photo['file_id'], file_type='photo', user_id=user.id, test_id=test_id)
        
        del context.user_data['creating_test']
        
        text = f"🎉✨ *ТЕСТ ГОТОВ!* ✨🎉\n\n📝 *{data['title']}*\n🔢 Вопросов: {len(questions)}"
        
        if hasattr(update_or_query, 'message'):
            await update_or_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(test_id))
        else:
            await update_or_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(test_id))
        await update_or_query.message.reply_text("🌸 Главное меню:", reply_markup=get_main_keyboard(user.id))

async def admin_funnel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM users')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(DISTINCT creator_id) FROM tests')
    created = c.fetchone()[0]
    c.execute('SELECT COUNT(DISTINCT friend_id) FROM attempts')
    passed = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE premium_until > datetime('now')")
    premium = c.fetchone()[0]
    conn.close()
    
    text = f"""
🔄 *ВОРОНКА КОНВЕРСИИ*

👥 Всего: *{total}* (100%)
📝 Создали тест: *{created}* ({round(created/max(total,1)*100, 1)}%)
🎮 Прошли тест: *{passed}* ({round(passed/max(total,1)*100, 1)}%)
💎 Премиум: *{premium}* ({round(premium/max(total,1)*100, 1)}%)
"""
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)

# === ПЕРИОДИЧЕСКИЕ ЗАДАЧИ ===
async def cleanup_media_job(context: ContextTypes.DEFAULT_TYPE):
    result = media_manager.periodic_cleanup()
    logger.info(f"🧹 Очистка медиа: {result['total_cleaned']} записей")

async def cleanup_antispam_job(context: ContextTypes.DEFAULT_TYPE):
    antispam.periodic_cleanup()
    logger.info("🧹 Очистка антиспама выполнена")

# === MAIN ===
def main():
    global bot_application
    
    app = Application.builder().token(TOKEN).build()
    bot_application = app
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^🌸 Создать тест$"), create_test_start))
    app.add_handler(MessageHandler(filters.Regex("^👑 Мои тесты$"), my_tests_handler))
    app.add_handler(MessageHandler(filters.Regex("^💎 Премиум$"), premium_handler))
    app.add_handler(MessageHandler(filters.Regex("^🔧 Админ-панель$"), admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^📊 Статистика$"), admin_stats))
    app.add_handler(MessageHandler(filters.Regex("^🖥 Сервер$"), admin_server_stats_compact))
    app.add_handler(MessageHandler(filters.Regex("^🛡 Антиспам$"), admin_antispam_stats))
    app.add_handler(MessageHandler(filters.Regex("^🎬 Медиа$"), admin_media_stats))
    app.add_handler(MessageHandler(filters.Regex("^🎁 Подарить премиум$"), admin_give_premium_start))
    app.add_handler(MessageHandler(filters.Regex("^➕ Начислить тесты$"), admin_add_tests_start))
    app.add_handler(MessageHandler(filters.Regex("^📢 Рассылка$"), admin_broadcast_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.VOICE, save_greeting))
    app.add_handler(MessageHandler(filters.VIDEO, save_greeting))
    app.add_handler(MessageHandler(filters.PHOTO, save_photo))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    app.job_queue.run_repeating(cleanup_media_job, interval=3600, first=600)
    app.job_queue.run_repeating(cleanup_antispam_job, interval=3600, first=300)
    
    logger.info("🚀✨ Бот запущен! Версия 9.5 (без Flask) ✨🚀")
    
    app.run_polling()

if __name__ == "__main__":
    main()
