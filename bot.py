python3
# -*- coding: utf-8 -*-
"""
PodrugaTestBot — бот для тестов между подругами
Версия: 11.0 — ПОЛНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ
Исправления:
- Платежи YooKassa с авто-проверкой (polling)
- Починена механика списания тестов
- Безопасный парсинг имён через attempt_id
- Кнопки оплаты обрабатываются первыми
- query.answer() в начале callback_handler
- Защита от зависания callback-обработчика
- Детальное логирование платежей
"""

import logging
import json
import sqlite3
import random
import os
import asyncio
import hashlib
import io
import time
import math
import platform
from datetime import datetime, timedelta
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import yookassa
from yookassa import Payment, Configuration
from yookassa.exceptions import ApiError
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

SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "1337862")
SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
Configuration.account_id = SHOP_ID
Configuration.secret_key = SECRET_KEY

logger.info(f"💳 YooKassa: shop_id={SHOP_ID}, ключ={'live_***' if SECRET_KEY.startswith('live_') else 'test_***' if SECRET_KEY.startswith('test_') else 'НЕ НАСТРОЕН'}")

# Словарь для хранения соответствия payment_id -> user_data
payment_registry = {}

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil не установлен. Статистика сервера будет недоступна.")

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
                    try:
                        await update.callback_query.answer(error_msg, show_alert=True)
                    except:
                        pass
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
        c.execute("UPDATE media_tracking SET is_valid = 0 WHERE views_count > 0 AND last_viewed_at < datetime('now', '-7 days')")
        c.execute('UPDATE media_tracking SET is_valid = 0 WHERE test_id IS NOT NULL AND test_id NOT IN (SELECT id FROM tests)')
        conn.commit()
        conn.close()
        return {'cleaned_inactive': 0, 'cleaned_viewed': 0, 'cleaned_orphaned': 0, 'total_cleaned': 0}

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
                     (broadcast_id, user['user_id'], 'pending'))
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
        c.execute('''SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
            SUM(CASE WHEN status = 'read' THEN 1 ELSE 0 END) as read,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked
            FROM broadcast_messages 
            WHERE broadcast_id = ?''', (broadcast_id,))
        
        detail_stats = dict(c.fetchone())
        stats.update(detail_stats)
        total = detail_stats['total'] or 1
        stats['delivery_rate'] = round((detail_stats['delivered'] or 0) / total * 100, 1)
        stats['read_rate'] = round((detail_stats['read'] or 0) / total * 100, 1)
        stats['block_rate'] = round((detail_stats['blocked'] or 0) / total * 100, 1)
        stats['fail_rate'] = round((detail_stats['failed'] or 0) / total * 100, 1)
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
    },
    'love_test': {
        'name': '💘 Про любовь',
        'questions': [
            "💕 Кто мой краш сейчас?", "😍 Какой тип парней мне нравится?",
            "💋 Был ли у меня первый поцелуй?", "💌 Писала ли я любовные записки?",
            "🌹 Какое моё идеальное свидание?", "💔 Как я переживаю отказы?",
            "💍 Хочу ли я замуж?", "👀 На что я обращаю внимание в первую очередь?",
            "🎭 Ревнивая ли я?", "💬 Обсуждаю ли я парней с подругами?"
        ]
    },
    'secrets': {
        'name': '🤫 Секреты',
        'questions': [
            "🤐 Мой самый большой секрет?", "😴 Что я делаю когда никто не видит?",
            "🍪 Что я ем по ночам?", "📱 Что я скрываю в телефоне?",
            "😢 Из-за чего я плакала последний раз?", "🎤 Какую песню я пою в душе?",
            "👻 Чего я боюсь больше всего?", "💭 О чём я думаю перед сном?",
            "🪄 Какое моё тайное желание?", "📝 Веду ли я личный дневник?"
        ]
    },
    'school_life': {
        'name': '📚 Школьная жизнь',
        'questions': [
            "📖 Мой любимый предмет?", "😫 Какой урок я ненавижу?",
            "👩‍🏫 Любимая учительница?", "👯 С кем я сижу за партой?",
            "🍔 Что я ем в столовой?", "📱 Что я делаю на скучных уроках?",
            "🏆 Моя лучшая оценка?", "📝 Списываю ли я домашку?",
            "🎓 Куда хочу поступать?", "🌟 Моё главное достижение в школе?"
        ]
    },
    'future': {
        'name': '🔮 Будущее',
        'questions': [
            "🎯 Кем я хочу стать?", "🏠 Где я хочу жить?",
            "💼 Какую работу я выберу?", "✈️ В какой стране хочу побывать?",
            "👶 Сколько у меня будет детей?", "🐶 Какое животное хочу завести?",
            "🚗 Какую машину хочу?", "💎 Что для меня успех?",
            "🌟 Главная цель на жизнь?", "💖 Что сделает меня счастливой?"
        ]
    },
    'would_you_rather': {
        'name': '🎭 Что выберешь?',
        'questions': [
            "🏝️ Пляж или горы?", "🍕 Пицца или суши?",
            "🎬 Кино или сериал?", "☕ Кофе или чай?",
            "📱 iPhone или Android?", "👗 Платье или джинсы?",
            "🎵 Поп или рок?", "📚 Книга или фильм?",
            "🌅 Рассвет или закат?", "💃 Клуб или домашняя вечеринка?"
        ]
    },
    'friendship_advice': {
        'name': '💖 Совет подругам',
        'questions': [
            "💕 Что для меня настоящая дружба?", "🤝 Как я поддерживаю подруг?",
            "💬 Что я ценю в людях больше всего?", "😤 Что меня бесит в дружбе?",
            "🎁 Люблю ли я дарить подарки?", "📱 Часто ли я отвечаю на сообщения?",
            "🌟 Что для меня идеальная подруга?", "💔 Как я переживаю ссоры?",
            "🦋 Прощаю ли я обиды?", "💖 Что я готова сделать ради подруги?"
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
        "😴 В какое время я обычно ложусь спать?", "💖 Что я ценю в нашей дружбе больше всего?",
        "🤝 Как я познакомилась со своим лучшим другом?", "💭 О чём я мечтаю когда думаю о друзьях?",
        "🎵 Какая песня напоминает мне о нашей дружбе?", "📱 Какой стикер я использую чаще всего в чате с тобой?",
        "🌟 Кто мой пример для подражания?", "💕 Что я никогда не прощу подруге?"
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
        "💎 Верю ли я в любовь с первого взгляда?", "👻 Кто мой тайный краш из класса?",
        "😢 Из-за чего я могу расплакаться при парне?", "🎬 Какой любовный фильм я пересматриваю?",
        "💕 Ревную ли я?", "🌟 Верю ли я в родственные души?", "💘 Что для меня важнее: внешность или характер?"
    ],
    'style': [
        "👗 Мой любимый стиль одежды?", "🎀 Любимый цвет в одежде?", "👟 Кроссовки или каблуки?",
        "🛍️ Мой любимый бренд одежды?", "👖 Джинсы или платья?", "🧥 Какую верхнюю одежду я ношу чаще?",
        "💍 Люблю ли я аксессуары?", "👜 Какая у меня сумка?", "💇‍♀️ Как я обычно укладываю волосы?",
        "💅 Делаю ли я маникюр?", "👓 Ношу ли я очки или линзы?", "🎒 Что всегда в моей сумке?",
        "👚 Какой мой любимый топ?", "🧢 Ношу ли я кепки?", "💄 Крашусь ли я каждый день?",
        "👠 Какая обувь у меня самая любимая?", "📸 В какой одежде я чаще фоткаюсь?",
        "🎨 Какие цвета преобладают в моём гардеробе?", "🪞 Сколько времени я собираюсь на выход?",
        "✨ Что я никогда не надену?", "👗 Платье или спортивный костюм?",
        "💍 Люблю ли я бижутерию?", "🛍️ Как часто я покупаю новую одежду?",
        "👠 Моя самая дорогая пара обуви?", "🎀 Какой аксессуар я ношу каждый день?", "💄 Моя любимая косметика?"
    ],
    'beauty': [
        "💄 Моя любимая помада?", "🧴 Какой уход за кожей я использую?", "💅 Какой маникюр я люблю?",
        "👁️ Крашу ли я ресницы тушью?", "💇‍♀️ Как часто я стригусь?", "🎨 Крашу ли я волосы?",
        "🧖‍♀️ Делаю ли я маски для лица?", "🪞 Моё любимое зеркало?", "🌸 Мои любимые духи?",
        "💦 Умываюсь ли я пенкой или гелем?", "🧼 Как часто я принимаю ванну?",
        "💤 Делаю ли я ночной уход?", "☀️ Пользуюсь ли я SPF?", "💋 Блеск или матовая помада?",
        "👩‍🎤 Какой макияж я делаю на вечеринку?", "🧴 Какой у меня тип кожи?",
        "💆‍♀️ Делаю ли я массаж лица?", "🦷 Как часто я чищу зубы?",
        "🧴 Моё любимое масло для тела?", "✨ Что для меня главное в уходе за собой?",
        "💅 Делаю ли я педикюр?", "💇‍♀️ Какой цвет волос я хочу попробовать?",
        "🧖‍♀️ Хожу ли я к косметологу?", "🌸 Какие духи я ношу зимой и летом?",
        "💤 Что я делаю перед сном для красоты?", "🪞 Сколько зеркал у меня дома?"
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
        "💬 В каких чатах я сижу?", "📲 Как часто я меняю аватарку?",
        "📱 Какой у меня рингтон?", "🎵 Что у меня в плейлисте?",
        "💬 С кем я переписываюсь больше всего?", "📸 Сколько у меня подписчиков?",
        "🦄 Какие фильтры я использую чаще всего?", "🎬 Смотрю ли я стримы?"
    ],
    'school': [
        "📖 Мой любимый предмет?", "😫 Самый ненавистный урок?", "📱 Что я делаю на скучных уроках?",
        "👯 С кем я сижу за партой?", "🤫 Как я списываю?", "🍔 Что я ем в столовой?",
        "👩‍🏫 Моя любимая учительница?", "👻 Кого я боюсь в школе?", "🏆 Моя лучшая оценка?",
        "🎒 Что всегда в моём рюкзаке?", "📚 Читаю ли я книги вне программы?",
        "✏️ Какими ручками я пишу?", "📅 Какой день недели самый тяжёлый?",
        "🏃‍♀️ Люблю ли я физкультуру?", "🎨 Какой предмет хочу добавить в расписание?",
        "📝 Делаю ли я домашку сразу?", "🤝 С кем я делаю проекты?", "🎓 Хочу ли я в университет?",
        "📊 Переживаю ли я из-за оценок?", "🌟 Моё главное школьное достижение?",
        "👯 Кто моя школьная bestie?", "🍔 Что я покупаю в школьном буфете?",
        "📱 Прячу ли я телефон на уроках?", "🎒 Ношу ли я с собой косметичку в школу?",
        "🌟 Какой предмет я бы убрала из расписания?", "👩‍🏫 Как я называю учителей за их спиной?"
    ],
    'dreams': [
        "✈️ Куда я мечтаю поехать?", "🌟 Моя самая заветная мечта?", "🚗 Какую машину я хочу?",
        "☀️ Мой идеальный день?", "🛍️ Что я хочу купить прямо сейчас?", "📝 Что у меня в вишлисте?",
        "🏠 Где я хочу жить?", "💎 О чём я мечтаю каждый день?", "🎓 Кем я вижу себя через 5 лет?",
        "💍 Какой я представляю свою свадьбу?", "🐶 Хочу ли я завести питомца?",
        "🎤 Хочу ли я стать знаменитой?", "📸 О чём я мечтаю, глядя на фото?",
        "🌈 В какой стране хочу побывать больше всего?", "🎬 Какой фильм я хочу, чтобы сняли про меня?",
        "💼 Какую работу я хочу?", "🏝️ Остров или горы?", "🛫 Что первое я сделаю, когда разбогатею?",
        "💖 Сколько детей я хочу?", "✨ Какое желание я загадаю на падающую звезду?",
        "🌟 Если бы я могла исполнить 3 желания?", "💎 Что для меня важнее денег?",
        "🎤 Хочу ли я выступать на сцене?", "✈️ В какой стране я хочу встретить старость?",
        "🐶 Какое экзотическое животное я хочу?", "🏠 Квартира или дом?"
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
        "🎶 Какая группа у меня в топ-3?", "🌟 Какой концепт я люблю больше всего?",
        "💜 Кто мой ультимативный биас?", "🎤 Какая группа заставила меня полюбить k-pop?",
        "💃 Какие танцы я учу по утрам?", "📺 Какое k-pop шоу я пересматриваю?",
        "🌟 Если бы я могла встретить одного айдола?", "🎵 Какая песня заставляет меня плакать?"
    ],
    'food': [
        "🍕 Моё любимое блюдо?", "😖 Что я ненавижу есть?", "👩‍🍳 Что я умею готовить?",
        "☕ Что я заказываю в кафе?", "🍰 Какие сладости я люблю?", "🍳 Что я ем на завтрак?",
        "🏠 Моё любимое кафе?", "🚫 Какую еду я никогда не буду есть?", "🍜 Лапша или картошка?",
        "🥤 Мой любимый напиток?", "🍦 Какое мороженое я выбираю?", "🍫 Шоколад или чипсы?",
        "🥗 Ем ли я салаты?", "🍔 Фастфуд или домашняя еда?", "🧋 Люблю ли я баббл ти?",
        "🍣 Ем ли я суши?", "🌮 Люблю ли я мексиканскую еду?", "🍩 Какие пончики я люблю?",
        "🧀 Добавляю ли я сыр везде?", "🍇 Какой фрукт мой любимый?",
        "🍳 Что я готовлю лучше всего?", "☕ Сладкий кофе или горький?",
        "🍕 С ананасами или без?", "🍣 Люблю ли я острое?",
        "🍩 Что я ем когда грустно?", "🍦 Ванильное или шоколадное?"
    ],
    'humor': [
        "🏃‍♀️ Что я делаю, когда опаздываю?", "🤪 Моя самая странная привычка?",
        "💃 Как я танцую, когда никто не видит?", "🍪 Что я ем ночью?", "👀 Как я вру?",
        "😱 Что делаю при виде паука?", "🐌 Мой смешной страх?", "💬 Моя коронная фраза?",
        "🛌 В какой позе я сплю?", "🎤 Моя песня в караоке?", "😂 Над каким мемом я смеялась последним?",
        "📸 Моё самое смешное фото?", "🎭 Какое лицо я корчу на селфи?", "🤣 Как я смеюсь?",
        "🪄 Что бы я сделала, если бы стала невидимкой?", "🎁 Самый странный подарок, который я получала?",
        "💇‍♀️ Моя самая неудачная стрижка?", "👗 Что я надела не по погоде?",
        "📱 Что я случайно лайкнула?", "😅 Попадала ли я в неловкие ситуации?",
        "😂 Какая шутка меня всегда смешит?", "📸 Самое глупое фото в моём телефоне?",
        "🎭 Как я пародирую учителей?", "💃 Что я делаю когда думаю что никто не смотрит?",
        "🤪 Моя вредная привычка?", "😱 Что я делаю когда пугаюсь?"
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
            f"🌟 {name} — твой идеальный мэтч в дружбе! Вы созданы друг для друга! 💖",
            f"💫 Вы с {name} — две половинки одного целого. Такая дружба случается раз в жизни! Берегите друг друга! 🦋",
            f"🔥 {name} не просто подруга — она твоя soulmate! Вы читаете мысли друг друга. Это волшебно! ✨",
            f"👯‍♀️ Вы с {name} как две капли воды! Понимаете друг друга без слов. Настоящая дружба! 💕",
        ]
    elif score >= 70:
        predictions = [
            f"💎 {name} очень хорошо тебя знает! Вы близкие подруги, и ваша дружба крепнет с каждым днём 🌸",
            f"✨ {name} понимает тебя почти во всём. Ещё немного — и вы станете лучшими подругами! 💕",
            f"🌟 Вы с {name} на одной волне! Узнавайте друг друга ещё глубже, впереди много интересного! 🎵",
            f"🌸 {name} — настоящая подруга! Она знает твои привычки, вкусы и секреты. Цени это! 💫",
            f"🎯 {name} отлично тебя знает! Вы прошли через многое вместе. Дружба становится только крепче! 💪",
            f"🦋 С {name} легко и просто! Она понимает тебя с полуслова. Продолжайте в том же духе! ✨",
        ]
    elif score >= 50:
        predictions = [
            f"🌸 {name} знает тебя неплохо, но есть куда расти! Проводите больше времени вместе, это сближает 💫",
            f"🌱 Ваша дружба с {name} только расцветает! Делитесь секретами, мечтами и любимыми треками 🎧",
            f"💫 {name} уже многое о тебе знает. Ещё немного — и вы станете ближе! Устройте совместную прогулку 🌈",
            f"📖 Вы с {name} на правильном пути! Узнавайте друг друга постепенно. Впереди много интересного! 💕",
            f"🎵 {name} знает о тебе главное. Расскажи ей больше о своих мечтах — это сближает! ✨",
            f"🌺 {name} уже твоя подруга! Поделись с ней своими любимыми фильмами и музыкой. Узнайте друг друга глубже! 💖",
        ]
    elif score >= 30:
        predictions = [
            f"🦋 {name} только начинает тебя узнавать. Это отличный повод пообщаться побольше! Расскажи о себе 💬",
            f"🌱 Вы с {name} на пути к настоящей дружбе. Не останавливайтесь! Впереди столько всего интересного ✨",
            f"📖 {name} знает о тебе основы. Пригласи её на кофе или созвон — это сближает! 💕",
            f"🌸 Вы с {name} только начинаете дружить. Это самое волшебное время! Узнавайте друг друга 💫",
            f"🎯 {name} уже кое-что знает о тебе. Покажи ей свои любимые места и увлечения! ✨",
            f"🦋 {name} интересуется тобой! Расскажи о своих хобби и мечтах. Дружба только зарождается! 💖",
        ]
    else:
        predictions = [
            f"🦋 {name} пока плохо тебя знает. Но это только начало! Каждая великая дружба начинается с первого шага ✨",
            f"🌱 {name} ещё предстоит узнать тебя получше. Поделись своими увлечениями и любимыми фильмами 🎬",
            f"💫 Ваша дружба с {name} только зарождается. Впереди много смеха, секретов и совместных фото! 📸",
            f"🌸 Вы с {name} только знакомитесь. Будь открытой и искренней — это лучший способ подружиться! 💕",
            f"🎵 {name} пока мало о тебе знает. Но это поправимо! Пригласи её погулять или на чай ☕",
            f"🦋 {name} — новый человек в твоей жизни. Дай ей шанс узнать тебя настоящую! Впереди много хорошего 💖",
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
    try: c.execute('ALTER TABLE tests ADD COLUMN greeting_type TEXT')
    except: pass
    try: c.execute('ALTER TABLE tests ADD COLUMN greeting_file_id TEXT')
    except: pass
    try: c.execute('ALTER TABLE tests ADD COLUMN answer_comments TEXT')
    except: pass
    try: c.execute('ALTER TABLE tests ADD COLUMN question_photos TEXT')
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
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payment_id TEXT UNIQUE,
        user_id INTEGER,
        days INTEGER,
        amount TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()
    logger.info("✅ База данных готова")

init_db()

# === ФУНКЦИИ БД ===
def get_user(user_id):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone(); conn.close()
    return dict(row) if row else None

def create_user(user_id, username=None, first_name=None):
    conn = get_db(); c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)', (user_id, username, first_name))
    conn.commit(); conn.close()

def is_premium(user_id):
    user = get_user(user_id)
    if not user or not user.get('premium_until'): return False
    try: return datetime.fromisoformat(user['premium_until']) > datetime.now()
    except: return False

def get_available_tests_count(user_id):
    user = get_user(user_id)
    if not user: return FREE_TESTS_LIMIT
    if is_premium(user_id): return -1
    used = user.get('tests_created', 0)
    return max(0, FREE_TESTS_LIMIT - used)

def can_create_test(user_id):
    if is_premium(user_id): return True
    return get_available_tests_count(user_id) > 0

def get_user_tests(user_id):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT id, title, created_at FROM tests WHERE creator_id = ? ORDER BY created_at DESC LIMIT 10', (user_id,))
    tests = []
    for row in c.fetchall():
        test = dict(row)
        c.execute('SELECT COUNT(*) FROM attempts WHERE test_id = ?', (test['id'],))
        test['attempts'] = c.fetchone()[0]
        tests.append(test)
    conn.close(); return tests

def get_test_by_id(test_id):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT * FROM tests WHERE id = ?', (test_id,))
    row = c.fetchone()
    if row:
        test = dict(row)
        test['questions'] = json.loads(test['questions'])
        test['options'] = json.loads(test['options'])
        test['correct_answers'] = json.loads(test['correct_answers'])
        conn.close(); return test
    conn.close(); return None

def create_test(creator_id, creator_name, title, questions, options, correct_answers, greeting_type=None, greeting_file_id=None, comments=None, photos=None):
    conn = get_db(); c = conn.cursor()
    c.execute('''INSERT INTO tests (creator_id, creator_name, title, questions, options, correct_answers, greeting_type, greeting_file_id, answer_comments, question_photos)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (creator_id, creator_name, title, json.dumps(questions), json.dumps(options), 
               json.dumps(correct_answers), greeting_type, greeting_file_id, json.dumps(comments or {}), json.dumps(photos or {})))
    test_id = c.lastrowid
    c.execute('UPDATE users SET tests_created = tests_created + 1 WHERE user_id = ?', (creator_id,))
    c.execute('SELECT id FROM tests WHERE creator_id = ? ORDER BY created_at DESC LIMIT -1 OFFSET 10', (creator_id,))
    for old_test in c.fetchall():
        c.execute('DELETE FROM attempts WHERE test_id = ?', (old_test['id'],))
        c.execute('DELETE FROM tests WHERE id = ?', (old_test['id'],))
    conn.commit(); conn.close()
    return test_id

def delete_test(user_id, test_id):
    conn = get_db(); c = conn.cursor()
    c.execute('DELETE FROM tests WHERE id = ? AND creator_id = ?', (test_id, user_id))
    c.execute('DELETE FROM attempts WHERE test_id = ?', (test_id,))
    conn.commit(); conn.close()
    return True

def save_attempt(test_id, friend_id, friend_name, answers, score):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT id FROM attempts WHERE test_id = ? AND friend_id = ?', (test_id, friend_id))
    if c.fetchone():
        c.execute('UPDATE attempts SET friend_name = ?, answers = ?, score = ?, completed_at = CURRENT_TIMESTAMP WHERE test_id = ? AND friend_id = ?',
                  (friend_name, json.dumps(answers), score, test_id, friend_id))
    else:
        c.execute('INSERT INTO attempts (test_id, friend_id, friend_name, answers, score) VALUES (?, ?, ?, ?, ?)',
                  (test_id, friend_id, friend_name, json.dumps(answers), score))
    conn.commit(); conn.close()

def get_test_attempts(test_id):
    conn = get_db(); c = conn.cursor()
    c.execute('SELECT friend_name, score, answers FROM attempts WHERE test_id = ? ORDER BY completed_at DESC', (test_id,))
    attempts = [dict(row) for row in c.fetchall()]
    for a in attempts: a['answers'] = json.loads(a['answers'])
    conn.close(); return attempts

def give_premium(user_id, days=30):
    conn = get_db(); c = conn.cursor()
    until = (datetime.now() + timedelta(days=days)).isoformat()
    c.execute('UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?', (until, user_id))
    conn.commit(); conn.close()

def add_tests_to_user(user_id, count):
    conn = get_db(); c = conn.cursor()
    c.execute('UPDATE users SET tests_created = MAX(0, tests_created - ?) WHERE user_id = ?', (count, user_id))
    conn.commit(); conn.close()

def save_payment(payment_id, user_id, days, amount):
    conn = get_db(); c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO payments (payment_id, user_id, days, amount, status) VALUES (?, ?, ?, ?, ?)',
              (payment_id, user_id, days, amount, 'pending'))
    conn.commit(); conn.close()

def mark_payment_success(payment_id):
    conn = get_db(); c = conn.cursor()
    c.execute('UPDATE payments SET status = ? WHERE payment_id = ? AND status = ?', ('success', payment_id, 'pending'))
    updated = c.rowcount > 0
    if updated:
        c.execute('SELECT user_id, days FROM payments WHERE payment_id = ?', (payment_id,))
        row = c.fetchone()
        if row:
            give_premium(row['user_id'], row['days'])
            logger.info(f"✅ Премиум выдан пользователю {row['user_id']} на {row['days']} дней")
    conn.commit(); conn.close()
    return updated

# === ФОНОВАЯ ПРОВЕРКА ПЛАТЕЖЕЙ ===
async def payment_checker(context: ContextTypes.DEFAULT_TYPE):
    """Периодически проверяет статус незавершённых платежей"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT payment_id, user_id, days FROM payments WHERE status = 'pending' AND created_at > datetime('now', '-1 hour')")
        pending = c.fetchall()
        conn.close()
        
        for p in pending:
            try:
                payment = Payment.find_one(p['payment_id'])
                if payment.status == 'succeeded':
                    if mark_payment_success(p['payment_id']):
                        try:
                            word = decline_word(p['days'], "день", "дня", "дней")
                            await context.bot.send_message(
                                chat_id=p['user_id'],
                                text=f"🎉✨ *ПЛАТЁЖ ПОДТВЕРЖДЁН!* ✨🎉\n\n💳 Оплата прошла успешно!\n💎 Премиум активирован на *{p['days']} {word}*!\n\n🌸 Спасибо за покупку! Наслаждайся безлимитными тестами 💕",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        except Exception as e:
                            logger.error(f"Не удалось уведомить пользователя {p['user_id']}: {e}")
                elif payment.status == 'canceled':
                    conn = get_db(); c = conn.cursor()
                    c.execute('UPDATE payments SET status = ? WHERE payment_id = ?', ('canceled', p['payment_id']))
                    conn.commit(); conn.close()
            except Exception as e:
                logger.error(f"Ошибка проверки платежа {p['payment_id']}: {e}")
            await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Ошибка в payment_checker: {e}")

# === ГЕНЕРАЦИЯ ДИПЛОМА ===
async def generate_friendship_analysis(user_name, creator_name, test_title, score, status, prediction, categories_stats):
    clean_status = status.replace(' 👑','').replace(' 💎','').replace(' 🌸','').replace(' 🌱','').replace(' 🦋','')
    
    W, H = 1080, 1920
    image = Image.new('RGB', (W, H), '#0A0A14')
    draw = ImageDraw.Draw(image)
    
    for y in range(H):
        ratio = y / H
        r = int(10 + 8 * ratio)
        g = int(10 + 3 * ratio)
        b = int(20 + 25 * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    for i in range(6):
        color = (int(255 - i*30), int(107 + i*20), int(157 + i*15))
        draw.rectangle([(0, i*3), (W, i*3+3)], fill=color)
        draw.rectangle([(0, H-i*3-3), (W, H-i*3)], fill=(int(168 - i*20), int(85 + i*15), int(247 - i*10)))
    
    draw.rectangle([(0, 0), (5, H)], fill='#FF6B9D')
    
    try:
        font_hero = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 110)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 68)
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_subtitle = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 36)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 34)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 28)
    except:
        font_hero = font_name = font_title = font_subtitle = font_text = font_body = font_small = ImageFont.load_default()
    
    PINK = '#FF6B9D'; PURPLE = '#C084FC'; GOLD = '#FFD700'; WHITE = '#FFFFFF'
    GRAY = '#9CA3AF'; LIGHT_GRAY = '#6B7280'
    GREEN = '#4ADE80'; BLUE = '#60A5FA'; ORANGE = '#FBBF24'; RED = '#F87171'
    
    y = 100
    draw.text((W//2, y), "ПОДРУГА ТЕСТ", fill=PINK, font=font_small, anchor="mt")
    y += 40
    draw.text((W//2, y), "ОФИЦИАЛЬНЫЙ СЕРТИФИКАТ", fill=GRAY, font=font_small, anchor="mt")
    
    y += 70
    for i in range(5):
        x_offset = W//2 - 80 + i*40
        size = 4 + i*2
        draw.ellipse([(x_offset-size, y-size), (x_offset+size, y+size)], fill=PINK if i<3 else PURPLE)
    
    y += 60
    draw.text((W//2, y), user_name.upper(), fill=WHITE, font=font_hero, anchor="mt")
    
    bbox = draw.textbbox((0,0), user_name.upper(), font=font_hero)
    name_w = bbox[2] - bbox[0]
    y += 80
    draw.rounded_rectangle([(W//2-name_w//2-20, y), (W//2+name_w//2+20, y+4)], radius=2, fill=PINK)
    
    y += 50
    draw.text((W//2, y), f"знает", fill=GRAY, font=font_body, anchor="mt")
    y += 45
    draw.text((W//2, y), creator_name, fill=WHITE, font=font_title, anchor="mt")
    y += 50
    draw.text((W//2, y), f"на", fill=GRAY, font=font_body, anchor="mt")
    
    y += 60
    score_text = f"{score:.0f}%"
    
    if score >= 90: color = GREEN
    elif score >= 70: color = BLUE
    elif score >= 50: color = ORANGE
    else: color = RED
    
    for offset in range(12, 0, -2):
        alpha = hex(20 + offset*3)[2:].zfill(2)
        draw.text((W//2+1, y+1), score_text, fill=color+alpha, font=font_hero, anchor="mt")
    
    draw.text((W//2+3, y+3), score_text, fill='#00000040', font=font_hero, anchor="mt")
    draw.text((W//2, y), score_text, fill=color, font=font_hero, anchor="mt")
    
    y += 110
    draw.text((W//2, y), f"«{clean_status}»", fill=GOLD, font=font_subtitle, anchor="mt")
    
    y += 70
    for i in range(3):
        x = W//2 - 30 + i*30
        draw.ellipse([(x-3, y-3), (x+3, y+3)], fill=PINK if i==1 else PURPLE)
    
    y += 60
    if categories_stats:
        draw.text((80, y), "📊 ПО КАТЕГОРИЯМ", fill=WHITE, font=font_subtitle)
        y += 55
        
        for cat, stats in list(categories_stats.items())[:5]:
            cat_score = stats['correct'] * 100 / stats['total'] if stats['total'] > 0 else 0
            
            draw.text((80, y), cat, fill=WHITE, font=font_body)
            
            bar_w = 480
            bar_x = W - bar_w - 80
            bar_h = 30
            bar_y = y - 2
            
            draw.rounded_rectangle([bar_x, bar_y, bar_x+bar_w, bar_y+bar_h], radius=15, fill='#1A1A30')
            draw.rounded_rectangle([bar_x, bar_y, bar_x+bar_w, bar_y+bar_h], radius=15, fill=None, outline='#2A2A45', width=1)
            
            fill_w = int(bar_w * cat_score / 100)
            if fill_w > 0:
                bc = GREEN if cat_score >= 70 else ORANGE if cat_score >= 50 else RED
                draw.rounded_rectangle([bar_x, bar_y, bar_x+fill_w, bar_y+bar_h], radius=15, fill=bc)
            
            pct_text = f"{cat_score:.0f}%"
            if fill_w > 60:
                draw.text((bar_x+fill_w-55, y), pct_text, fill='#0A0A14', font=font_small)
            else:
                draw.text((bar_x+bar_w+15, y), pct_text, fill=GRAY, font=font_small)
            
            y += 65
    
    y += 50
    for i in range(3):
        x = W//2 - 30 + i*30
        draw.ellipse([(x-3, y-3), (x+3, y+3)], fill=PURPLE if i==1 else PINK)
    
    y += 40
    draw.text((80, y), "🔮 ПРЕДСКАЗАНИЕ", fill=WHITE, font=font_subtitle)
    y += 50
    
    words = prediction.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        if draw.textbbox((0,0), ' '.join(current), font=font_body)[2] > W - 200:
            current.pop()
            lines.append(' '.join(current))
            current = [w]
    if current:
        lines.append(' '.join(current))
    
    for line in lines:
        draw.text((80, y), line, fill=GRAY, font=font_body)
        y += 45
    
    y = max(y + 80, H - 250)
    
    for i in range(6):
        color = (int(168 - i*20), int(85 + i*15), int(247 - i*10))
        draw.rectangle([(0, H-200+i*3), (W, H-200+i*3+3)], fill=color)
    
    y = H - 160
    draw.text((W//2, y), "podrugatestbot", fill=PINK, font=font_small, anchor="mt")
    y += 35
    draw.text((W//2, y), f"Выдано {datetime.now().strftime('%d.%m.%Y')}", fill=LIGHT_GRAY, font=font_small, anchor="mt")
    
    cert_id = hashlib.md5(f"{user_name}{test_title}{datetime.now()}".encode()).hexdigest()[:8].upper()
    draw.text((W-100, 60), f"#{cert_id}", fill=LIGHT_GRAY, font=font_small, anchor="rt")
    
    stars_count = 5 if score >= 90 else 4 if score >= 70 else 3 if score >= 50 else 2 if score >= 30 else 1
    y = 70
    for i in range(5):
        star_color = GOLD if i < stars_count else '#2A2A45'
        draw.text((W-100-120+i*50, y), "★", fill=star_color, font=font_subtitle)
    
    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG', quality=95)
    img_bytes.seek(0)
    return img_bytes

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
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Статистика"), KeyboardButton("🖥 Сервер")],
        [KeyboardButton("🎁 Подарить премиум"), KeyboardButton("🛡 Антиспам")],
        [KeyboardButton("➕ Начислить тесты"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("🎬 Медиа"), KeyboardButton("🔙 Назад")]
    ], resize_keyboard=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True)

def get_options_keyboard():
    return ReplyKeyboardMarkup([["➕ Добавить вариант", "✅ Готово", "🔙 Назад"]], resize_keyboard=True, one_time_keyboard=True)

def get_question_groups_keyboard():
    keyboard, row = [], []
    for key, name in QUESTION_GROUPS.items():
        row.append(InlineKeyboardButton(name, callback_data=f"group_{key}"))
        if len(row) == 2: keyboard.append(row); row = []
    if row: keyboard.append(row)
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
            switch_inline_query=f"💕 Привет! Пройди тест обо мне и узнай, насколько хорошо ты меня знаешь! 💕\n\n👉 https://t.me/{BOT_USERNAME}?start=test_{test_id}")]
    ])

def get_premium_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 15 дней — 99₽", callback_data="buy_15days")],
        [InlineKeyboardButton("💎 Месяц — 149₽", callback_data="buy_month")]
    ])

# === ОСНОВНЫЕ ХЕНДЛЕРЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; message = update.message
    if not get_user(user.id): create_user(user.id, user.username, user.first_name)
    if context.args and context.args[0].startswith("test_"):
        test_id = int(context.args[0].split("_")[1]); test = get_test_by_id(test_id)
        if test:
            creator = get_user(test['creator_id']); creator_name = creator.get('first_name', 'Подружка') if creator else 'Подружка'
            text = (f"🌸✨ ПРИВЕТ, {user.first_name}! ✨🌸\n\n"
                    f"💕 *{creator_name}* приглашает тебя пройти тест!\n\n"
                    f"📝 *{test['title']}*\n\n👇 Нажми на кнопку и начни!")
            try: await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_{test_id}")]]))
            except Exception as e: logger.warning(f"Не удалось отправить: {e}")
            return
    is_prem = is_premium(user.id)
    if is_prem:
        text = (f"💎✨ *ПРИВЕТ, {user.first_name}!* ✨💎\n\n"
                f"🌸 Добро пожаловать в мир тестов для лучших подруг! 💕\n\n"
                f"👑 *Твой статус:* ПРЕМИУМ\n♾️ Безлимитные тесты\n🎓 Золотые дипломы\n📊 Смотри ответы подруг\n\n"
                f"✨ *Создай тест о себе и узнай, кто знает тебя лучше всех!* 💕")
    else:
        available = get_available_tests_count(user.id); word = decline_word(available, "тест", "теста", "тестов")
        text = (f"🌸✨ *ПРИВЕТ, {user.first_name}!* ✨🌸\n\n"
                f"💕 Создай тест о себе и отправь подружкам!\nУзнайте насколько хорошо вы друг друга знаете 🎯\n\n"
                f"📊 *Осталось тестов:* {available} {word}\n\n"
                f"💎 *Premium* открывает:\n♾️ Безлимитные тесты\n🎓 Красивый золотой диплом\n📊 Ответы подруг\n\n"
                f"👇 *Выбирай действие в меню:*")
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user.id))

# === АДМИН-ПАНЕЛЬ ===
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: await update.message.reply_text("❌ У вас нет доступа!"); return
    await update.message.reply_text("🔧 *АДМИН-ПАНЕЛЬ* ✨\n\nВыбери действие в меню 👇", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    is_callback = query is not None
    
    user_id = query.from_user.id if is_callback else update.effective_user.id
    if user_id != ADMIN_ID: return
    
    conn = get_db(); c = conn.cursor()
    today = datetime.now().date().isoformat(); yesterday = (datetime.now()-timedelta(days=1)).date().isoformat()
    week_ago = (datetime.now()-timedelta(days=7)).date().isoformat(); month_ago = (datetime.now()-timedelta(days=30)).date().isoformat()
    c.execute('SELECT COUNT(*) FROM users'); total_users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE DATE(created_at)=?', (today,)); new_today = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE DATE(created_at)=?', (yesterday,)); new_yesterday = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE created_at>=?', (week_ago,)); new_week = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE created_at>=?', (month_ago,)); new_month = c.fetchone()[0]
    c.execute('''SELECT COUNT(DISTINCT user_id) FROM (SELECT user_id FROM users WHERE created_at>=?
        UNION SELECT creator_id FROM tests WHERE created_at>=? UNION SELECT friend_id FROM attempts WHERE completed_at>=?)''',
        (week_ago,)*3); active_7d = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE premium_until>?', (today,)); prem_active = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL'); prem_total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE premium_until>? AND premium_until<=?',
        (today, (datetime.now()+timedelta(days=7)).date().isoformat())); prem_exp = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE premium_until>? AND premium_until>?', (week_ago, today)); prem_new = c.fetchone()[0]
    conversion = round(prem_total/max(total_users,1)*100,1)
    c.execute('SELECT COUNT(*) FROM tests'); total_tests = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM tests WHERE DATE(created_at)=?', (today,)); tests_today = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM tests WHERE created_at>=?', (week_ago,)); tests_week = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM tests WHERE created_at>=?', (month_ago,)); tests_month = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM tests WHERE greeting_type IS NOT NULL'); tests_greet = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM tests WHERE question_photos IS NOT NULL AND question_photos!="{}"'); tests_photos = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM attempts'); total_att = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM attempts WHERE DATE(completed_at)=?', (today,)); att_today = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM attempts WHERE completed_at>=?', (month_ago,)); att_month = c.fetchone()[0]
    c.execute('SELECT AVG(score) FROM attempts'); avg_score = c.fetchone()[0] or 0
    c.execute('SELECT MAX(score) FROM attempts'); max_score = c.fetchone()[0] or 0
    c.execute('''SELECT u.first_name, COUNT(t.id) as cnt FROM users u LEFT JOIN tests t ON u.user_id=t.creator_id
        GROUP BY u.user_id ORDER BY cnt DESC LIMIT 3'''); top_cr = c.fetchall()
    c.execute('''SELECT friend_name, COUNT(*) as cnt FROM attempts GROUP BY friend_name ORDER BY cnt DESC LIMIT 3'''); top_pl = c.fetchall()
    c.execute('''SELECT CAST(strftime("%H",created_at) AS INTEGER) as hour, COUNT(*) as cnt FROM tests
        WHERE created_at>=? GROUP BY hour ORDER BY cnt DESC LIMIT 1''', (month_ago,)); peak_test = c.fetchone()
    c.execute('''SELECT CAST(strftime("%H",completed_at) AS INTEGER) as hour, COUNT(*) as cnt FROM attempts
        WHERE completed_at>=? GROUP BY hour ORDER BY cnt DESC LIMIT 1''', (month_ago,)); peak_att = c.fetchone()
    conn.close()
    trend = "📈" if new_today>=new_yesterday else "📉" if new_today<new_yesterday else "➡️"
    text = f"""📊✨ *СТАТИСТИКА БОТА* ✨📊
🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}

👥 *ПОЛЬЗОВАТЕЛИ*
├ 👑 Всего: *{total_users}*
├ 🆕 Сегодня: *+{new_today}* {trend}
├ 📈 За неделю: *+{new_week}*
├ 📅 За месяц: *+{new_month}*
└ 🟢 Активных (7д): *{active_7d}*

💎 *ПРЕМИУМ*
├ ✨ Активных: *{prem_active}*
├ 💰 Всего купили: *{prem_total}*
├ 🆕 Новых за неделю: *+{prem_new}*
├ ⚠️ Истекает (7д): *{prem_exp}*
└ 📊 Конверсия: *{conversion}%*

📝 *ТЕСТЫ*
├ 📋 Всего: *{total_tests}*
├ 🆕 Сегодня: *+{tests_today}*
├ 📈 За неделю: *+{tests_week}*
├ 📅 За месяц: *+{tests_month}*
├ 🎬 С поздравлениями: *{tests_greet}*
└ 📸 С фото: *{tests_photos}*

🎯 *ПРОХОЖДЕНИЯ*
├ 🎮 Всего: *{total_att}*
├ 🆕 Сегодня: *+{att_today}*
├ 📅 За месяц: *+{att_month}*
├ 🎯 Средний балл: *{avg_score:.1f}%*
└ 👑 Лучший балл: *{max_score:.0f}%*
"""
    if top_cr:
        text += "\n🏆 *ТОП СОЗДАТЕЛЕЙ*\n"
        for i, cr in enumerate(top_cr,1): text += f"├ {i}. {cr['first_name'] or 'Аноним'}: *{cr['cnt']}* тестов\n"
    if top_pl:
        text += "\n🎮 *ТОП ПРОХОЖДЕНИЙ*\n"
        for i, pl in enumerate(top_pl,1): text += f"├ {i}. {pl['friend_name']}: *{pl['cnt']}* раз\n"
    if peak_test or peak_att:
        text += "\n⏰ *ПИКОВЫЕ ЧАСЫ*\n"
        if peak_test: text += f"├ Создание: *{peak_test['hour']}:00* ({peak_test['cnt']} шт.)\n"
        if peak_att: text += f"└ Прохождение: *{peak_att['hour']}:00* ({peak_att['cnt']} шт.)\n"
    analysis = "🚀 Отличная конверсия!" if conversion>20 else "📈 Хорошая конверсия" if conversion>10 else "📊 Продолжай продвигать!"
    text += f"\n💡 *АНАЛИЗ:* {analysis}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="admin_refresh_stats")], [InlineKeyboardButton("📈 Воронка", callback_data="admin_funnel")], [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]])
    if is_callback:
        await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def admin_server_stats_compact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        try: await query.answer()
        except: pass
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id
    if user_id != ADMIN_ID: return
    stats = get_server_stats()
    if 'error' in stats:
        msg = f"❌ {stats['error']}"
        if query: await query.message.edit_text(msg, parse_mode=ParseMode.MARKDOWN)
        else: await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        return
    cpu_e = get_server_status_emoji(stats['cpu']['percent']); mem_e = get_server_status_emoji(stats['memory']['percent']); disk_e = get_server_status_emoji(stats['disk']['percent'], (70,90))
    text = f"""🖥 *СЕРВЕР*
⏱ Аптайм: *{stats['uptime']}*

💻 Система: `{stats['system']}`
🐍 Python: `{stats['python']}`
🔢 Ядер CPU: *{stats['cpu']['cores']}*

📊 CPU: {cpu_e} *{stats['cpu']['percent']:.1f}%*
├ RAM: {mem_e} *{stats['memory']['percent']:.1f}%* ({stats['memory']['used_gb']}/{stats['memory']['total_gb']} GB)
└ Диск: {disk_e} *{stats['disk']['percent']:.1f}%*

🤖 Бот: RAM *{stats['bot_process']['memory_mb']} MB* | CPU *{stats['bot_process']['cpu_percent']:.1f}%* | Потоков *{stats['bot_process']['threads']}*

💡 {'⚠️ Высокая нагрузка!' if stats['cpu']['percent']>80 else '✅ Стабильно'}"""
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="server_refresh")], [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]])
    if query: await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else: await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def admin_antispam_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(f"🛡️ *АНТИСПАМ*\n\n🚫 Заблокировано: *{len(antispam._blocked_users)}*\n⚠️ С предупреждениями: *{len(antispam._warnings)}*", parse_mode=ParseMode.MARKDOWN)

async def admin_media_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    stats = media_manager.get_media_stats(); total_size_mb = round(stats['total_size_bytes']/(1024**2),1)
    text = f"🎬 *МЕДИА*\n\n📁 Всего: *{stats['total_media']}* | Активных: *{stats['active_media']}* | 💾 *{total_size_mb} MB* | 👁 *{stats['total_views']}*\n\n"
    names = {'voice':'🎤 Голосовые','video':'🎥 Видео','photo':'📸 Фото'}
    for ft, ts in stats['by_type'].items(): text += f"{names.get(ft,ft)}: *{ts['count']}* ({round(ts['size_bytes']/(1024**2),2)} MB)\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🧹 Очистить", callback_data="media_force_cleanup")], [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

# === РАССЫЛКИ ===
async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data.pop('admin_action', None); context.user_data['creating_broadcast'] = True
    recent = broadcast_manager.get_recent_broadcasts(3)
    text = "📢 *РАССЫЛКА*\n\n" + ("".join([f"• #{b['id']}: {b['sent_count']}/{b['total_users']}\n" for b in recent])+"\n" if recent else "")
    text += "📝 Отправь сообщение для ВСЕХ.\n❌ *Отмена* — выйти"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup([["❌ Отмена", "📊 Статистика рассылок"]], resize_keyboard=True))

async def execute_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.user_data.get('creating_broadcast'): return
    msg = update.message; md = {'type':'text','text':msg.text,'file_id':None}
    if msg.photo: md = {'type':'photo','text':msg.caption or '','file_id':msg.photo[-1].file_id}
    elif msg.video: md = {'type':'video','text':msg.caption or '','file_id':msg.video.file_id}
    elif msg.animation: md = {'type':'animation','text':msg.caption or '','file_id':msg.animation.file_id}
    conn = get_db(); c = conn.cursor(); c.execute('SELECT user_id FROM users'); users = c.fetchall(); conn.close()
    total = len(users); bid = broadcast_manager.create_broadcast(update.effective_user.id, md, total)
    st = await update.message.reply_text(f"📤 *РАССЫЛКА #{bid}*\n├ Всего: *{total}*\n└ Прогресс: *0/{total}*", parse_mode=ParseMode.MARKDOWN)
    stats = {'sent':0,'failed':0,'blocked':0}
    for i, u in enumerate(users):
        try:
            if md['type']=='text': await context.bot.send_message(chat_id=u['user_id'], text=md['text'])
            elif md['type']=='photo': await context.bot.send_photo(chat_id=u['user_id'], photo=md['file_id'], caption=md['text'] or None)
            elif md['type']=='video': await context.bot.send_video(chat_id=u['user_id'], video=md['file_id'], caption=md['text'] or None)
            elif md['type']=='animation': await context.bot.send_animation(chat_id=u['user_id'], animation=md['file_id'], caption=md['text'] or None)
            stats['sent'] += 1; broadcast_manager.update_message_status(bid, u['user_id'], 'sent')
        except Exception as e:
            if "blocked" in str(e).lower() or "forbidden" in str(e).lower(): stats['blocked'] += 1; broadcast_manager.update_message_status(bid, u['user_id'], 'blocked')
            else: stats['failed'] += 1; broadcast_manager.update_message_status(bid, u['user_id'], 'failed')
        if (i+1)%20==0 or (i+1)==total:
            try: await st.edit_text(f"📤 *РАССЫЛКА #{bid}*\n├ Всего: *{total}*\n├ Отправлено: *{stats['sent']}* ✅\n├ Заблокировали: *{stats['blocked']}* 🚫\n├ Ошибки: *{stats['failed']}* ❌\n└ Прогресс: *{i+1}/{total}* ({(i+1)/total*100:.0f}%)", parse_mode=ParseMode.MARKDOWN)
            except: pass
            await asyncio.sleep(0.1)
    broadcast_manager.complete_broadcast(bid)
    fs = broadcast_manager.get_broadcast_stats(bid)
    await st.edit_text(f"✅ *РАССЫЛКА #{bid} ЗАВЕРШЕНА!*\n\n├ Всего: *{total}*\n├ Отправлено: *{stats['sent']}* ({stats['sent']/max(total,1)*100:.1f}%)\n├ Доставлено: *{fs.get('delivered_count',0)}* ({fs.get('delivery_rate',0)}%)\n├ Прочитано: *{fs.get('read_count',0)}* ({fs.get('read_rate',0)}%)\n├ Заблокировали: *{stats['blocked']}*\n└ Ошибки: *{stats['failed']}*", parse_mode=ParseMode.MARKDOWN)
    del context.user_data['creating_broadcast']; await update.message.reply_text("🔧 *Админ-панель:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

async def broadcast_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    broadcasts = broadcast_manager.get_recent_broadcasts(10)
    if not broadcasts: await update.message.reply_text("📊 *Нет истории*", parse_mode=ParseMode.MARKDOWN); return
    text = "📊 *СТАТИСТИКА РАССЫЛОК*\n\n"
    for b in broadcasts:
        t = b['total_users'] or 1; se = '✅' if b['status']=='completed' else '🔄'
        text += f"{se} *#{b['id']}* — {b['created_at'][:16]}\n├ 📤 {b['sent_count']}/{t} ({round(b['sent_count']/t*100,1)}%)\n├ 📬 {b['delivered_count']} ({round(b['delivered_count']/max(t,1)*100,1)}%)\n├ 👁 {b['read_count']}\n└ 🚫 {b['blocked_count']} | ❌ {b['failed_count']}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# === АДМИН ДЕЙСТВИЯ ===
async def admin_give_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data['admin_action'] = 'give_premium'
    await update.message.reply_text("🎁 *ПОДАРИТЬ ПРЕМИУМ*\n\nВыбери срок:", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("1 день", callback_data="give_premium_1"), InlineKeyboardButton("5 дней", callback_data="give_premium_5")], [InlineKeyboardButton("15 дней", callback_data="give_premium_15"), InlineKeyboardButton("30 дней", callback_data="give_premium_30")]]))

async def admin_add_tests_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data['admin_action'] = 'add_tests'
    await update.message.reply_text("➕ *НАЧИСЛИТЬ ТЕСТЫ*\n\nВведи username или ID и количество:\nНапример: @anna 5", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    action = context.user_data.get('admin_action')
    if not action: return
    text = update.message.text.strip()
    
    if text in ["❌ Отмена", "🔙 Назад"]:
        context.user_data.pop('admin_action', None)
        context.user_data.pop('premium_days', None)
        await update.message.reply_text("❌ Действие отменено", reply_markup=get_admin_keyboard())
        return
    
    if action == 'give_premium':
        target = text.lstrip('@'); days = context.user_data.get('premium_days',30)
        conn = get_db(); c = conn.cursor()
        c.execute('SELECT user_id, first_name FROM users WHERE user_id=?' if target.isdigit() else 'SELECT user_id, first_name FROM users WHERE username=?', (int(target) if target.isdigit() else target,))
        row = c.fetchone(); conn.close()
        if not row: await update.message.reply_text(f"❌ {target} не найден", reply_markup=get_admin_keyboard()); del context.user_data['admin_action']; return
        give_premium(row['user_id'], days); dw = decline_word(days,"день","дня","дней")
        await update.message.reply_text(f"✅ *{row['first_name'] or target}* — премиум на *{days} {dw}*! 🎉", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        try: await context.bot.send_message(chat_id=row['user_id'], text=f"🎉✨ Поздравляем! Вам подарен ПРЕМИУМ на {days} {dw}!")
        except: pass
        del context.user_data['admin_action']; context.user_data.pop('premium_days',None)
    elif action == 'add_tests':
        parts = text.split()
        if len(parts)<2: await update.message.reply_text("❌ Введи username и количество!", reply_markup=get_admin_keyboard()); return
        target = parts[0].lstrip('@')
        try: count = int(parts[1])
        except: await update.message.reply_text("❌ Число!"); return
        conn = get_db(); c = conn.cursor()
        c.execute('SELECT user_id, first_name FROM users WHERE user_id=?' if target.isdigit() else 'SELECT user_id, first_name FROM users WHERE username=?', (int(target) if target.isdigit() else target,))
        row = c.fetchone()
        if not row: conn.close(); await update.message.reply_text(f"❌ {target} не найден", reply_markup=get_admin_keyboard()); del context.user_data['admin_action']; return
        user_id = row['user_id']; user_name = row['first_name'] or target
        add_tests_to_user(user_id, count)
        available = get_available_tests_count(user_id); at = "♾️ безлимит" if available==-1 else str(available)
        tw = decline_word(count,"тест","теста","тестов")
        conn.close()
        await update.message.reply_text(f"✅ *{user_name}* начислено *{count}* {tw}!\n📊 Доступно: *{at}*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        try: await context.bot.send_message(chat_id=user_id, text=f"🎁 Вам начислено +{count} {tw}!")
        except: pass
        del context.user_data['admin_action']

# === СОЗДАНИЕ ТЕСТА ===
@rate_limit('create_test')
async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not can_create_test(user_id):
        await update.message.reply_text(
            f"💔 *Бесплатные тесты закончились!* 💔\n\n"
            f"🌸 Ты создала все {FREE_TESTS_LIMIT} бесплатных тестов.\n\n"
            f"💎 *Premium* откроет:\n♾️ Безлимитные тесты\n🎓 Красивый золотой диплом\n📊 Смотри ответы всех подруг\n\n"
            f"💰 *Всего 99₽* за 15 дней или *149₽* за месяц\n\n"
            f"👇 Нажми кнопку «💎 Премиум» в меню и продолжай создавать тесты без ограничений!",
            parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user_id))
        return
    context.user_data['creating_test'] = {'step':'title'}
    ti = "♾️ *Премиум — безлимитные тесты*" if is_premium(user_id) else f"📊 *Осталось тестов:* {get_available_tests_count(user_id)}"
    await update.message.reply_text(f"🌸 *СОЗДАЁМ ТЕСТ*\n\n{ti}\n\nПридумай красивое название:\nНапример: «Насколько хорошо ты меня знаешь?»\n\n❌ *Отмена* — чтобы выйти", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def handle_create_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data or data.get('waiting_comment'): return
    text = update.message.text.strip(); step = data.get('step')
    if step == 'title':
        if len(text)<3: await update.message.reply_text("⚠️ Длиннее 3 символов!"); return
        data['title'] = text; data['step'] = 'group'
        await update.message.reply_text("✨ Выбери тему:", reply_markup=get_question_groups_keyboard())
    elif step == 'questions_count':
        try:
            count = int(text)
            if count<2 or count>MAX_QUESTIONS: await update.message.reply_text(f"⚠️ От 2 до {MAX_QUESTIONS}!"); return
            data['total_q'] = count; data['current_q'] = 0; data['questions_data'] = []; data['comments'] = {}; data['photos'] = {}
            await update.message.reply_text("🎬✨ *ДОБАВЬ ПОЗДРАВЛЕНИЕ!* ✨🎬\n\nПодружка получит его после прохождения!", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎤 Голосовое", callback_data="greeting_voice"), InlineKeyboardButton("🎥 Видео", callback_data="greeting_video")], [InlineKeyboardButton("⏭️ Пропустить", callback_data="greeting_skip")]]))
            data['step'] = 'greeting'
        except ValueError: await update.message.reply_text("⚠️ Напиши число!")

# === ПРОХОЖДЕНИЕ ТЕСТА ===
@rate_limit('take_test')
async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: await query.answer()
    except: pass
    tid = int(query.data.replace("start_","")); test = get_test_by_id(tid); user = query.from_user
    if not test: await query.message.reply_text("💔 Тест не найден"); return
    
    if test['creator_id'] == user.id:
        await query.message.reply_text("🌸 *Это твой тест!*\n\nТы не можешь пройти свой собственный тест.\nОтправь его подругам! 💕", parse_mode=ParseMode.MARKDOWN)
        return
    
    conn = get_db(); c = conn.cursor(); c.execute('SELECT id FROM attempts WHERE test_id=? AND friend_id=?', (tid, user.id))
    if c.fetchone(): conn.close(); await query.message.reply_text("💔 *Ты уже проходила этот тест!*", parse_mode=ParseMode.MARKDOWN); return
    conn.close(); context.user_data['taking_test'] = {'test':test,'current':0,'answers':[]}
    await send_question(query, context)

async def send_question(query, context):
    data = context.user_data.get('taking_test'); test = data['test']; current = data['current']
    photos = json.loads(test['question_photos']) if test.get('question_photos') else {}
    kb = [[InlineKeyboardButton(opt[:40], callback_data=f"answer_{i}")] for i, opt in enumerate(test['options'][current])]
    qt = f"💭 *ВОПРОС {current+1} ИЗ {len(test['questions'])}*\n\n✨ {test['questions'][current]}\n\n_Выбери один вариант ответа:_ 🎯"
    if str(current) in photos: await query.message.reply_photo(photo=photos[str(current)], caption=qt, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))
    else: await query.message.reply_text(qt, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: await query.answer()
    except: pass
    aidx = int(query.data.replace("answer_","")); data = context.user_data.get('taking_test')
    if not data: return
    test = data['test']; current = data['current']
    ua = test['options'][current][aidx]; ci = test['correct_answers'][current]; ca = test['options'][current][ci]
    is_correct = aidx == ci; data['answers'].append(aidx)
    
    comments_raw = test.get('answer_comments')
    comments = json.loads(comments_raw) if comments_raw else {}
    comment = comments.get(str(current), None)
    
    if is_correct:
        correct_messages = [
            f"✅ *ПРАВИЛЬНО!* ✅\n\n✨ Ты ответила: *{ua}*\n\n💕 _И это абсолютно верно! Ты знаешь меня как свои пять пальцев!_",
            f"✅ *ТЫ УГАДАЛА!* ✅\n\n✨ Ты ответила: *{ua}*\n\n🌸 _Да-да! Именно так! Ты читаешь мои мысли!_",
            f"✅ *ИДЕАЛЬНЫЙ ОТВЕТ!* ✅\n\n✨ Ты ответила: *{ua}*\n\n💎 _Ты настоящая подруга! Всё знаешь обо мне!_",
            f"✅ *ТОЧНО!* ✅\n\n✨ Ты ответила: *{ua}*\n\n👑 _Так держать! Ты лучшая подруга на свете!_",
            f"✅ *ПРАВИЛЬНО НА 100%!* ✅\n\n✨ Ты ответила: *{ua}*\n\n🎉 _Ты знаешь меня лучше всех! Я в восторге!_",
            f"✅ *ДА! ЭТО ПРАВДА!* ✅\n\n✨ Ты ответила: *{ua}*\n\n💖 _Ты настоящая soulmate! Мы на одной волне!_",
        ]
        result_text = random.choice(correct_messages)
    else:
        wrong_messages = [
            f"❌ *ОЙ! НЕ УГАДАЛА* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *А правильно:* {ca}\n\n🌱 _Ничего! Ты узнаёшь меня всё лучше с каждым днём!_",
            f"❌ *МИМО!* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *На самом деле:* {ca}\n\n💪 _В следующий раз точно получится! Я в тебя верю!_",
            f"❌ *НЕ СОВСЕМ ТАК* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *Правильный ответ:* {ca}\n\n🌸 _Теперь ты знаешь обо мне чуть больше!_",
            f"❌ *ПОЧТИ!* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *А я бы ответила:* {ca}\n\n🎯 _Ещё немного и ты станешь экспертом по мне!_",
            f"❌ *НЕ УГАДАЛА* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *Правильно:* {ca}\n\n💭 _Это повод пообщаться подольше и узнать друг друга лучше!_",
            f"❌ *НЕТ, НО БЛИЗКО!* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *Верный ответ:* {ca}\n\n👑 _С каждым вопросом ты становишься ближе ко мне!_",
        ]
        result_text = random.choice(wrong_messages)
    
    if comment:
        result_text += f"\n\n💬 *Пояснение:*\n_{comment}_"
    
    await query.message.reply_text(result_text, parse_mode=ParseMode.MARKDOWN)
    data['current'] += 1
    if data['current'] < len(test['questions']): await send_question(query, context)
    else: await finish_test(query, context)

async def finish_test(query, context):
    data = context.user_data['taking_test']; test = data['test']; answers = data['answers']; correct = test['correct_answers']; user = query.from_user
    score = sum(1 for i in range(min(len(answers),len(correct))) if answers[i]==correct[i])*100/len(correct) if correct else 0
    save_attempt(test['id'], user.id, user.first_name, answers, score)
    status = get_friendship_status(score); prediction = get_friendship_prediction(score, user.first_name)
    try:
        friend_username = f" @{user.username}" if user.username else ""
        await context.bot.send_message(
            chat_id=test['creator_id'],
            text=f"🎉💖 *УРА! ТВОЙ ТЕСТ ПРОШЛИ!* 💖🎉\n\n"
                 f"👤 *{user.first_name}*{friend_username} прошла тест\n"
                 f"📝 «{test['title']}»\n"
                 f"🎯 *Результат:* {score:.0f}%\n"
                 f"🏆 *Статус:* {status}\n\n"
                 f"✨ *Зайди в «👑 Мои тесты»!*",
            parse_mode=ParseMode.MARKDOWN
        )
    except: pass
    categories_stats = {}
    for i, q in enumerate(test['questions']):
        cat = "Другое"
        for ck, cqs in QUESTIONS.items():
            if q in cqs: cat = QUESTION_GROUPS.get(ck,ck); break
        if cat not in categories_stats: categories_stats[cat] = {'correct':0,'total':0}
        categories_stats[cat]['total'] += 1
        if i<len(answers) and answers[i]==correct[i]: categories_stats[cat]['correct'] += 1
    analysis_image = await generate_friendship_analysis(user.first_name, test['creator_name'], test['title'], score, status, prediction, categories_stats)
    await query.message.reply_photo(analysis_image, caption=f"🎉✨ *ТЕСТ ПРОЙДЕН!* ✨🎉\n\n💕 *{user.first_name}*, ты супер!\n🔥 *Поделись с {test['creator_name']}!* 🔥", parse_mode=ParseMode.MARKDOWN)
    if test.get('greeting_file_id'):
        await asyncio.sleep(0.5)
        try:
            if test.get('greeting_type')=='voice': await query.message.reply_voice(test['greeting_file_id'], caption=f"🎬✨ СЮРПРИЗ ОТ {test['creator_name'].upper()}! ✨🎬", parse_mode=ParseMode.MARKDOWN)
            elif test.get('greeting_type')=='video': await query.message.reply_video(test['greeting_file_id'], caption=f"🎬✨ СЮРПРИЗ ОТ {test['creator_name'].upper()}! ✨🎬", parse_mode=ParseMode.MARKDOWN)
            media_manager.mark_as_viewed(test['greeting_file_id'], user.id, test['id'])
        except: pass
    await query.message.reply_text("✨ *Выбирай действие:* ✨", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user.id))
    del context.user_data['taking_test']

# === МОИ ТЕСТЫ ===
async def my_tests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id; tests = get_user_tests(user_id)
    if not tests:
        await update.message.reply_text("👑✨ *МОИ ТЕСТЫ* ✨👑\n\n🌸 *У тебя пока нет тестов!*\n\n💕 Создай первый тест и отправь подружкам!", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup([["🌸 Создать тест"]], resize_keyboard=True))
        return
    total_att = sum(t['attempts'] for t in tests)
    proh_word = decline_word(total_att, "прохождение", "прохождения", "прохождений")
    text = f"👑✨ *МОИ ТЕСТЫ* ✨👑\n\n📦 *{len(tests)}* {decline_word(len(tests),'тест','теста','тестов')} | 🎯 *{total_att}* {proh_word}\n"
    text += f"• • • • • • • • • • • •\n💡 *Хранятся последние 10 тестов*\nПри создании нового — самый старый удалится\n• • • • • • • • • • • •\n\n"
    kb = []
    for t in tests:
        w = decline_friend_word(t['attempts'])
        if t['attempts']>=5: st, em = "🔥 ПОПУЛЯРНЫЙ", "💖"
        elif t['attempts']>=2: st, em = "⭐ АКТИВНЫЙ", "🌸"
        else: st, em = "🆕 НОВЫЙ", "✨"
        text += f"{em} *{t['title'][:30]}*\n   👥 {t['attempts']} {w} | {st}\n   📅 {t['created_at'][:10]}\n\n"
        kb.append([InlineKeyboardButton(f"💕 {t['title'][:30]} | {t['attempts']} 👥", callback_data=f"mytest_{t['id']}")])
    text += "👇 *Выбери тест чтобы посмотреть:*"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

async def my_test_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: await query.answer()
    except: pass
    tid = int(query.data.replace("mytest_","")); test = get_test_by_id(tid)
    if not test: await query.message.reply_text("💔 Тест не найден", parse_mode=ParseMode.MARKDOWN); return
    attempts = get_test_attempts(tid); avg = sum(a['score'] for a in attempts)/len(attempts) if attempts else 0; mx = max(a['score'] for a in attempts) if attempts else 0
    status = "🔥 СУПЕР-ПОПУЛЯРНЫЙ!" if len(attempts)>=10 else "⭐ ПОПУЛЯРНЫЙ!" if len(attempts)>=5 else "🌸 НАБИРАЕТ ПОПУЛЯРНОСТЬ" if len(attempts)>=2 else "🆕 ЖДЁТ ПОДРУГ"
    pw = "прошла" if len(attempts)==1 else "прошли"
    text = f"✨ *{test['title']}* ✨\n\n{status}\n\n👥 *{len(attempts)}* {decline_friend_word(len(attempts))} {pw} тест\n🎯 Средний результат: *{avg:.0f}%*\n"
    if attempts: text += f"👑 Лучший результат: *{mx:.0f}%*\n"
    text += f"💭 Вопросов: *{len(test['questions'])}*\n"
    if test.get('greeting_file_id'): text += "🎬 Видео-поздравление: *есть* ✨\n"
    if test.get('question_photos') and test['question_photos']!='{}': text += f"📸 Фото: *{len(json.loads(test['question_photos']))}*\n"
    text += "\n💕 *Что хочешь сделать с тестом?*"
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_test_actions_keyboard(tid))

# === ПРЕМИУМ ===
async def premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_premium(user_id):
        user = get_user(user_id); expiry = datetime.fromisoformat(user['premium_until']).strftime('%d.%m.%Y')
        text = f"💎✨ *У ТЕБЯ ПРЕМИУМ!* ✨💎\n\n♾️ Безлимитные тесты\n🎓 Золотой диплом\n📊 Ответы подруг\n\n📅 *Действует до:* {expiry}\n\n💕 *Создавай тесты и проверяй подруг!*"
    else: text = "💎 *ПРЕМИУМ ПОДПИСКА*\n\n✨ *Что даёт:*\n♾️ Безлимитные тесты\n🎓 Золотой диплом\n📊 Ответы подруг\n\n💰 *Стоимость:*\n• 99₽ — 15 дней\n• 149₽ — месяц\n\n👇 *Выбери тариф:*"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_premium_keyboard() if not is_premium(user_id) else get_main_keyboard(user_id))

 async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    days, price = (15, 99) if query.data == "buy_15days" else (30, 149)
    user_id = query.from_user.id
    
    logger.info(f"💎 Начало создания платежа: days={days}, price={price}, user_id={user_id}")
    
    # Отправляем сообщение что платёж создаётся
    status_msg = await query.message.reply_text("⏳ *Создаём платёж...*", parse_mode=ParseMode.MARKDOWN)
    
    try:
        # Устанавливаем таймаут 30 секунд
        import sys
        logger.info(f"💎 Python version: {sys.version}")
        logger.info(f"💎 YooKassa version: {yookassa.__version__ if hasattr(yookassa, '__version__') else 'неизвестна'}")
        
        # Создаём платёж с обработкой ошибок
        logger.info(f"💎 Отправляю запрос к YooKassa API...")
        
        payment = Payment.create({
            "amount": {
                "value": f"{price}.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{BOT_USERNAME}"
            },
            "description": f"Premium на {days} дней для пользователя {user_id}",
            "metadata": {
                "user_id": user_id,
                "days": days
            },
            "capture": True
        })
        
        logger.info(f"✅ Платёж создан успешно!")
        logger.info(f"   Payment ID: {payment.id}")
        logger.info(f"   Статус: {payment.status}")
        logger.info(f"   Ссылка для оплаты: {payment.confirmation.confirmation_url}")
        
        # Удаляем сообщение "Создаём платёж..."
        await status_msg.delete()
        
        # Сохраняем платёж
        payment_registry[payment.id] = {
            'user_id': user_id,
            'days': days
        }
        save_payment(payment.id, user_id, days, f"{price}.00")
        
        # Создаём кнопку оплаты
        payment_url = payment.confirmation.confirmation_url
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💎 Оплатить {price}₽", url=payment_url)]
        ])
        
        await query.message.reply_text(
            f"💎 *Premium на {days} дней*\n\n"
            f"💰 Сумма: *{price}₽*\n\n"
            f"✨ Что ты получишь:\n♾️ Безлимитные тесты\n🎓 Красивый золотой диплом\n📊 Смотри ответы подруг\n\n"
            f"👇 *Нажми на кнопку ниже для оплаты:*\n\n"
            f"_После оплаты бот автоматически активирует премиум в течение 1 минуты_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
        logger.info(f"✅ Сообщение с кнопкой оплаты отправлено пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании платежа: {type(e).__name__}: {e}")
        logger.error(f"❌ Полный traceback:", exc_info=True)
        
        # Удаляем сообщение "Создаём платёж..."
        try:
            await status_msg.delete()
        except:
            pass
        
        error_text = str(e)
        logger.error(f"❌ Текст ошибки: {error_text}")
        
        # Проверяем разные типы ошибок
        if "ConnectionError" in type(e).__name__ or "Timeout" in type(e).__name__:
            user_msg = "😢 *Ошибка соединения с платёжной системой*\n\nПопробуй ещё раз через минуту."
        elif "401" in error_text or "403" in error_text:
            user_msg = ("😢 *Ошибка авторизации*\n\n"
                       "Проверьте правильность ключей YooKassa:\n"
                       f"• Shop ID: `{SHOP_ID}`\n"
                       "• Secret Key должен соответствовать shop_id")
        elif "test" in error_text.lower() and "live_" in SECRET_KEY:
            user_msg = ("😢 *Ошибка конфигурации*\n\n"
                       "Боевой ключ (live_) используется с неверным shop_id.\n"
                       "Проверьте настройки в личном кабинете YooKassa.")
        else:
            user_msg = f"😢 *Ошибка при создании платежа*\n\n`{error_text[:300]}`\n\nПопробуй ещё раз через минуту."
        
        await query.message.reply_text(user_msg, parse_mode=ParseMode.MARKDOWN)

# === ОБРАБОТЧИКИ КНОПОК ===
@flood_check
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text; user_id = update.effective_user.id
    if context.user_data.get('creating_broadcast'):
        if text=="❌ Отмена": del context.user_data['creating_broadcast']; await update.message.reply_text("❌ Отменено", reply_markup=get_admin_keyboard())
        elif text=="📊 Статистика рассылок": await broadcast_stats_handler(update, context)
        else: await execute_broadcast(update, context)
        return
    if context.user_data.get('admin_action'):
        if text in ["❌ Отмена", "🔙 Назад"]:
            context.user_data.pop('admin_action', None)
            context.user_data.pop('premium_days', None)
            await update.message.reply_text("❌ Действие отменено", reply_markup=get_admin_keyboard())
        else:
            await handle_admin_input(update, context)
        return
    
    if text=="🌸 Создать тест": await create_test_start(update, context)
    elif text=="👑 Мои тесты": await my_tests_handler(update, context)
    elif text=="💎 Премиум": await premium_handler(update, context)
    elif text=="🔧 Админ-панель" and user_id==ADMIN_ID: await admin_panel(update, context)
    elif text=="📊 Статистика" and user_id==ADMIN_ID: await admin_stats(update, context)
    elif text=="🖥 Сервер" and user_id==ADMIN_ID: await admin_server_stats_compact(update, context)
    elif text=="🛡 Антиспам" and user_id==ADMIN_ID: await admin_antispam_stats(update, context)
    elif text=="🎬 Медиа" and user_id==ADMIN_ID: await admin_media_stats(update, context)
    elif text=="🎁 Подарить премиум" and user_id==ADMIN_ID: await admin_give_premium_start(update, context)
    elif text=="➕ Начислить тесты" and user_id==ADMIN_ID: await admin_add_tests_start(update, context)
    elif text=="📢 Рассылка" and user_id==ADMIN_ID: await admin_broadcast_start(update, context)
    elif text=="❌ Отмена":
        if 'creating_test' in context.user_data: del context.user_data['creating_test']; await update.message.reply_text("❌ Создание отменено", reply_markup=get_main_keyboard(user_id))
        elif user_id==ADMIN_ID and context.user_data.get('admin_action'): del context.user_data['admin_action']; await admin_panel(update, context)
        else: await start(update, context)
    elif text=="🔙 Назад": await start(update, context)
    elif text=="➕ Добавить вариант":
        data = context.user_data.get('creating_test')
        if data and data.get('step')=='collecting_options':
            if len(data.get('current_options',[])) >= MAX_OPTIONS:
                await update.message.reply_text(f"⚠️ *Максимум {MAX_OPTIONS} вариантов!*\n\n🎯 Нажми «✅ Готово» чтобы продолжить.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
            else:
                data['waiting_for_option'] = True
                await update.message.reply_text(f"✏️ *Напиши вариант №{len(data['current_options'])+1}:*\n\n💡 Варианты должны быть разными и понятными", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())
    elif text=="✅ Готово":
        data = context.user_data.get('creating_test')
        if data and data.get('step')=='collecting_options':
            opts = data.get('current_options',[])
            if len(opts)<2: await update.message.reply_text("⚠️ *Минимум 2 варианта!*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard()); data['waiting_for_option'] = True; return
            kb = [[InlineKeyboardButton(f"{i+1}. {opt[:30]}", callback_data=f"correct_{i}")] for i, opt in enumerate(opts)]
            await update.message.reply_text(f"❓ *Вопрос:* {data['current_question']}\n\n👇 *Какой вариант ПРАВИЛЬНЫЙ?* 👇\n\nВыбери ответ который описывает ТЕБЯ:", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))
            data['waiting_for_option'] = False
    else:
        data = context.user_data.get('creating_test')
        if data:
            if data.get('waiting_comment'): await save_comment(update, context)
            elif data.get('waiting_custom_question'):
                t = text.strip()
                if len(t)<5: await update.message.reply_text("⚠️ Вопрос длиннее 5 символов!")
                elif len(t)>150: await update.message.reply_text("⚠️ Слишком длинный!")
                else:
                    data['current_question'] = t; data['waiting_custom_question'] = False; data['current_options'] = []; data['step'] = 'collecting_options'; data['waiting_for_option'] = True
                    await update.message.reply_text(f"✅ *Вопрос сохранён!*\n\n📝 *Твой вопрос:* {t}\n\n✏️ *Напиши вариант ответа №1:*\n\n💡 Варианты должны быть разными и понятными", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())
            elif data.get('step')=='collecting_options' and data.get('waiting_for_option'):
                option_text = text.strip()
                if len(option_text)>50: await update.message.reply_text("⚠️ *Слишком длинный вариант!*"); return
                if len(data.get('current_options', [])) >= MAX_OPTIONS:
                    await update.message.reply_text(f"⚠️ *Максимум {MAX_OPTIONS} вариантов!*\n\n🎯 Нажми «✅ Готово» чтобы продолжить.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
                    data['waiting_for_option'] = False
                    return
                data['current_options'].append(option_text)
                ol = "\n".join([f"{i+1}. {o}" for i, o in enumerate(data['current_options'])])
                if len(data['current_options']) >= MAX_OPTIONS:
                    data['waiting_for_option'] = False
                    await update.message.reply_text(f"✅ *Вариант {len(data['current_options'])} добавлен!*\n\n📋 *Твои варианты:*\n{ol}\n\n🎯 *Максимум!* Нажми «✅ Готово»", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
                else:
                    await update.message.reply_text(f"✅ *Вариант {len(data['current_options'])} добавлен!*\n\n📋 *Твои варианты:*\n{ol}\n\n✏️ *Введи ещё вариант или нажми кнопку:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
            else: await handle_create_test(update, context)

# === CALLBACK ОБРАБОТЧИК ===
@rate_limit('callback')
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # 🔔 ВСЕГДА сначала логируем и отвечаем на callback
    logger.info(f"🔔 Callback: '{data}' от user_id={query.from_user.id}")
    
    # ❗️ НЕМЕДЛЕННО подтверждаем получение callback
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Ошибка query.answer: {e}")
    
    try:
        # === ПОКУПКА ПРЕМИУМА (ПЕРВЫМИ!) ===
        if data == "buy_15days" or data == "buy_month":
            logger.info(f"💎 Запуск покупки премиума: {data}")
            await buy_premium(update, context)
            return
        
        # === ВЫБОР ГРУППЫ ВОПРОСОВ ===
        elif data.startswith("group_"):
            await select_question_group(update, context)
        
        # === ГОТОВЫЕ НАБОРЫ ===
        elif data == "show_presets":
            await show_presets(update, context)
        elif data.startswith("preset_"):
            await select_preset(update, context)
        elif data == "back_to_groups":
            await query.message.edit_text("✨ Выбери тему:", reply_markup=get_question_groups_keyboard())
        
        # === ВЫБОР ВОПРОСА ===
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
        
        # === ПРАВИЛЬНЫЙ ОТВЕТ / КОММЕНТАРИЙ ===
        elif data.startswith("correct_"):
            await select_correct(update, context)
        elif data.startswith("skip_comment_"):
            await skip_comment(update, context)
        
        # === ПРИВЕТСТВИЕ ===
        elif data.startswith("greeting_"):
            await greeting_choice(update, context)
        
        # === АДМИН: ВЫДАТЬ ПРЕМИУМ ===
        elif data.startswith("give_premium_"):
            days = int(data.replace("give_premium_", ""))
            context.user_data['premium_days'] = days
            await query.message.edit_text(f"🎁 *ПРЕМИУМ НА {days} {decline_word(days,'ДЕНЬ','ДНЯ','ДНЕЙ')}*\n\nВведите username или ID (или нажмите ❌ Отмена):", parse_mode=ParseMode.MARKDOWN)
        
        # === ЗАПУСК ТЕСТА ===
        elif data.startswith("start_"):
            await start_test(update, context)
        
        # === ОТВЕТ НА ВОПРОС ===
        elif data.startswith("answer_"):
            await handle_answer(update, context)
        
        # === МОИ ТЕСТЫ ===
        elif data.startswith("mytest_"):
            await my_test_actions(update, context)
        
        # === ПРОСМОТР ТЕСТА ===
        elif data.startswith("view_"):
            tid = int(data.replace("view_", ""))
            test = get_test_by_id(tid)
            if test:
                text = f"👁✨ *ПРОСМОТР ТЕСТА* ✨👁\n\n📝 *{test['title']}*\n\n📋 *ТВОИ ВОПРОСЫ И ОТВЕТЫ:*\n\n"
                for i, q in enumerate(test['questions'], 1):
                    text += f"*{i}. {q}*\n"
                    for j, opt in enumerate(test['options'][i-1]):
                        text += f"   {'✅' if j==test['correct_answers'][i-1] else '➖'} {opt}\n"
                    text += "\n"
                text += "💡 *Подсказка:* Отправь тест подругам и узнай кто знает тебя лучше всех! 💕"
                await query.message.reply_text(text[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📤 Поделиться", callback_data=f"share_{tid}")], [InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_test_{tid}")]]))
        
        # === НАЗАД К ТЕСТУ ===
        elif data.startswith("back_to_test_"):
            tid = int(data.replace("back_to_test_", ""))
            test = get_test_by_id(tid)
            if test:
                attempts = get_test_attempts(tid)
                avg = sum(a['score'] for a in attempts)/len(attempts) if attempts else 0
                await query.message.edit_text(f"📝 *{test['title']}*\n\n👥 Прошли: {len(attempts)}\n🎯 Средний: {avg:.0f}%\n\n👇 Выбери действие:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_test_actions_keyboard(tid))
        
        # === ПОДЕЛИТЬСЯ ===
        elif data.startswith("share_"):
            tid = int(data.replace("share_", ""))
            await query.message.reply_text(f"📤✨ *ПОДЕЛИСЬ ТЕСТОМ!* ✨📤\n\n💕 Отправь тест подруге и узнай насколько хорошо она тебя знает!\n\n🎯 Чем больше подруг пройдут — тем интереснее битва за звание лучшей! 👑\n\n👇 *Нажми на кнопку:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(tid))
        
        # === ОТВЕТЫ ПОДРУГ ===
        elif data.startswith("answers_"):
            tid = int(data.replace("answers_", ""))
            if not is_premium(query.from_user.id):
                await query.answer("💎 Только для ПРЕМИУМ! ✨", show_alert=True)
                return
            test = get_test_by_id(tid); attempts = get_test_attempts(tid)
            if not attempts:
                await query.message.reply_text("📊✨ *ОТВЕТЫ ПОДРУГ* ✨📊\n\n👻 *Пока никто не прошёл тест!*\n\n💕 Отправь ссылку подружкам!", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💕 Отправить подруге", callback_data=f"share_{tid}")]]))
                return
            sa = sorted(attempts, key=lambda x: x['score'], reverse=True)
            text = f"📊✨ *ОТВЕТЫ ПОДРУГ* ✨📊\n\n📝 *{test['title']}*\n\n👥 *Твои подруги:*\n\n"
            for a in sa[:10]:
                s = a['score']
                em, hint = ('👑','Знает наизусть! 💕') if s>=90 else ('💎','Отлично знает! ✨') if s>=70 else ('🌸','Хорошо знает! 🌟') if s>=50 else ('🌱','Узнаёт лучше! 💫') if s>=30 else ('🦋','Знакомится! 🌈')
                text += f"{em} *{a['friend_name']}* — *{s:.0f}%*\n   💬 _{hint}_\n\n"
            text += "💡 *Нажми на подругу чтобы увидеть:*\n🔍 Все ответы\n📊 Детальную статистику\n🔮 Предсказание дружбы\n\n👇 *Выбери подругу:*"
            kb = []
            for a in sa[:10]:
                icon = '👑' if a['score']>=80 else '💎' if a['score']>=60 else '🌸'
                c = get_db().cursor()
                c.execute("SELECT id FROM attempts WHERE test_id=? AND friend_name=?", (tid, a['friend_name']))
                row = c.fetchone()
                attempt_id = row[0] if row else 0
                kb.append([InlineKeyboardButton(f"{icon} {a['friend_name'][:20]}: {a['score']:.0f}%", callback_data=f"friend_details_{attempt_id}")])
            kb.append([InlineKeyboardButton("📈 Общая статистика", callback_data=f"stats_friendship_{tid}"), InlineKeyboardButton("⚔️ Битва подруг", callback_data=f"battle_{tid}")])
            kb.append([InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_test_{tid}")])
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))
        
        # === ДЕТАЛИ ПОДРУГИ (по attempt_id) ===
        elif data.startswith("friend_details_"):
            attempt_id = int(data.replace("friend_details_", ""))
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT * FROM attempts WHERE id = ?', (attempt_id,))
            attempt_row = c.fetchone()
            if not attempt_row:
                conn.close()
                await query.answer("❌ Попытка не найдена", show_alert=True)
                return
            attempt = dict(attempt_row)
            attempt['answers'] = json.loads(attempt['answers']) if attempt['answers'] else []
            tid = attempt['test_id']; fn = attempt['friend_name']
            conn.close()
            
            test = get_test_by_id(tid)
            if not test:
                await query.answer("❌ Тест не найден", show_alert=True)
                return
            
            score = attempt['score']; level, desc = get_detailed_stats(score); pred = get_friendship_prediction(score, fn)
            correct_count = sum(1 for i, ans in enumerate(attempt['answers']) if i<len(test['correct_answers']) and ans==test['correct_answers'][i])
            total_q = len(test['questions'])
            text = f"🔮✨ *ДЕТАЛЬНЫЙ АНАЛИЗ* ✨🔮\n\n👤 *{fn}*\n📝 Тест: *{test['title']}*\n\n🎯 *Результат:* {score:.0f}%\n🏆 *Уровень:* {level}\n📊 *{desc}*\n✅ Правильно: *{correct_count}* из *{total_q}*\n\n"
            if score>=90: text += "👑 *СЁСТРЫ НАВЕК!*\n💕 Вы как две половинки одного целого!\n_Твоя душа знает твою душу_ ✨\n\n"
            elif score>=70: text += "💎 *ЛУЧШИЕ ПОДРУГИ!*\n🌸 Вы понимаете друг друга почти без слов!\n_Цени эту дружбу — она особенная_ 💫\n\n"
            elif score>=50: text += "🌟 *ХОРОШИЕ ПОДРУГИ!*\n🌱 Вы на правильном пути!\n_Ещё немного и вы станете ближе_ 💕\n\n"
            else: text += "🦋 *ЗНАКОМЫЕ!*\n🌈 Впереди много интересного!\n_Узнавайте друг друга постепенно_ ✨\n\n"
            text += f"🔮 *ПРЕДСКАЗАНИЕ ДРУЖБЫ:*\n_{pred}_\n\n📋 *ВСЕ ОТВЕТЫ:*\n\n"
            comms = json.loads(test.get('answer_comments','{}')) if test.get('answer_comments') else {}
            for i, q in enumerate(test['questions']):
                text += f"*{i+1}. {q}*\n"
                if i<len(attempt['answers']):
                    uai = attempt['answers'][i]; ci = test['correct_answers'][i]; ic = uai==ci
                    if uai<len(test['options'][i]):
                        ua = test['options'][i][uai]; ca = test['options'][i][ci]
                        text += f"   ✅ *{ua}*\n" if ic else f"   ❌ Ответила: *{ua}*\n   ✅ Правильно: *{ca}*\n"
                    if str(i) in comms: text += f"   💬 _{comms[str(i)]}_\n"
                text += "\n"
            text += f"💕 *ИТОГ:* {fn} — {'твоя родственная душа! ✨' if score>=80 else 'отличная подруга! 💫' if score>=60 else 'вы только начинаете узнавать друг друга! 🌱'}"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ Битва", callback_data=f"battle_{tid}"), InlineKeyboardButton("📈 Статистика", callback_data=f"stats_friendship_{tid}")], [InlineKeyboardButton("🔙 К списку", callback_data=f"answers_{tid}")]])
            await query.message.reply_text(text[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        
        # === БИТВА ПОДРУГ ===
        elif data.startswith("battle_"):
            tid = int(data.replace("battle_", "")); test = get_test_by_id(tid); attempts = get_test_attempts(tid)
            if len(attempts)<2:
                await query.message.reply_text("⚔️✨ *БИТВА ПОДРУГ* ✨⚔️\n\n😢 *Недостаточно участниц!*\n\n👯‍♀️ Нужно минимум 2 подруги!\n\n📤 *Отправь тест ещё одной:*", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💕 Поделиться", callback_data=f"share_{tid}")]]))
                return
            sa = sorted(attempts, key=lambda x: x['score'], reverse=True)
            text = f"⚔️✨ *БИТВА ПОДРУГ* ✨⚔️\n\n📝 Тест: _{test['title']}_\n\n🏆 *ТУРНИРНАЯ ТАБЛИЦА*\n\n"
            medals = ["🥇","🥈","🥉"]; descs = ["Королева знаний", "Бриллиантовая подруга", "Золотая середина", "Прелестно", "Растёт"]
            for i, a in enumerate(sa[:5]):
                medal = medals[i] if i<3 else f"  {i+1}."; score = a['score']; status = get_friendship_status(score)
                bar = "💜"*int(score/10)+"🤍"*(10-int(score/10))
                text += f"\n{medal} *{a['friend_name']}*\n   {bar} *{score:.0f}%*\n   {status}\n   _{descs[i] if i<len(descs) else 'Продолжай узнавать'}_\n"
            text += f"\n━━━━━━━━━━━━━━━━━━━━━━\n⚡ *ПРОТИВОСТОЯНИЕ ЛИДЕРОВ*\n\n"
            if len(sa)>=2:
                first, second = sa[0], sa[1]; diff = first['score']-second['score']
                text += f"🥇 *{first['friend_name']}* vs 🥈 *{second['friend_name']}*\n📊 Разрыв: *{diff:.0f}%*\n\n"
                if diff>=30: text += f"👑 *ТОТАЛЬНОЕ ДОМИНИРОВАНИЕ!*\n_{first['friend_name']} знает тебя в разы лучше!_\n_Она не просто подруга — она СЕСТРА!_ 💕\n"
                elif diff>=15: text += f"💪 *УВЕРЕННОЕ ЛИДЕРСТВО!*\n_{first['friend_name']} впереди, но {second['friend_name']} ещё может наверстать!_\n_Устройте реванш через неделю!_ 🎯\n"
                elif diff>=5: text += f"⚡ *НАПРЯЖЁННАЯ БОРЬБА!*\n_Разрыв минимален! Всё решают детали!_\n_Интрига сохраняется..._ 👀\n"
                else: text += f"🎯 *ФОТОФИНИШ!*\n_Практически одинаковый результат!_\n_Обе подруги знают тебя отлично!_ 💕💕\n"
            conn = get_db(); c = conn.cursor()
            c.execute("SELECT id FROM attempts WHERE test_id=? AND friend_name=?", (tid, sa[0]['friend_name']))
            row = c.fetchone(); first_attempt_id = row[0] if row else 0
            conn.close()
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📈 Статистика", callback_data=f"stats_friendship_{tid}"), InlineKeyboardButton("📊 Ответы", callback_data=f"answers_{tid}")], [InlineKeyboardButton("👑 Детали победителя", callback_data=f"friend_details_{first_attempt_id}")], [InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_test_{tid}")]])
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        
        # === СТАТИСТИКА ДРУЖБЫ ===
        elif data.startswith("stats_friendship_"):
            tid = int(data.replace("stats_friendship_","")); test = get_test_by_id(tid); attempts = get_test_attempts(tid)
            if not attempts:
                await query.message.reply_text("📈✨ *СТАТИСТИКА ДРУЖБЫ* ✨📈\n\n😢 *Пока никто не прошёл!*\n\n🌸 Отправь ссылку подружкам!", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💕 Поделиться", callback_data=f"share_{tid}")]]))
                return
            sa = sorted(attempts, key=lambda x: x['score'], reverse=True); avg_score = sum(a['score'] for a in attempts)/len(attempts); max_score = max(a['score'] for a in attempts); min_score = min(a['score'] for a in attempts)
            conn = get_db(); c = conn.cursor(); usernames = {}
            for a in sa[:10]: c.execute('SELECT username FROM users WHERE first_name=?', (a['friend_name'],)); row = c.fetchone()
            if row and row['username']: usernames[a['friend_name']] = row['username']
            conn.close()
            text = f"💕✨ *СТАТИСТИКА ДРУЖБЫ* ✨💕\n\n📝 *{test['title']}*\n\n👥 *Твои подруги прошли тест:*\n\n"
            preds = ["💕 Родственная душа! ✨","🌸 Настоящая bestie! 💎","🌟 На одной волне 🎵","🌱 Узнавайте друг друга 💫","🤝 Впереди много интересного 🌈","🦋 Всё только начинается 💖"]
            for i, a in enumerate(sa[:10]):
                score = a['score']
                if score>=90: em, st, pr = '👑','ЭКСПЕРТ',preds[0]
                elif score>=80: em, st, pr = '💎','СУПЕР',preds[0]
                elif score>=70: em, st, pr = '💕','ЛУЧШАЯ ПОДРУГА',preds[1]
                elif score>=60: em, st, pr = '🌸','ХОРОШАЯ ПОДРУГА',preds[2]
                elif score>=50: em, st, pr = '🌟','ЗНАЕТ ТЕБЯ',preds[3]
                elif score>=40: em, st, pr = '🌱','УЗНАЁТ ТЕБЯ',preds[4]
                elif score>=30: em, st, pr = '🤝','ЗНАКОМАЯ',preds[5]
                else: em, st, pr = '🦋','НОВАЯ ЗНАКОМАЯ',preds[5]
                un = f" @{usernames[a['friend_name']]}" if a['friend_name'] in usernames else ""
                filled = int(score/10)
                if score>=90: bar = "💜"*filled+"🩶"*(10-filled)
                elif score>=70: bar = "💗"*filled+"🩶"*(10-filled)
                elif score>=50: bar = "💛"*filled+"🩶"*(10-filled)
                elif score>=30: bar = "🩵"*filled+"🩶"*(10-filled)
                else: bar = "🤍"*filled+"🩶"*(10-filled)
                text += f"{em} *{a['friend_name']}*{un}\n   {bar} *{score:.0f}%*\n   🏆 Уровень: *{st}*\n   💬 _{pr}_\n\n"
            pw = "прошла" if len(attempts)==1 else "прошли"
            text += f"\n📊 *ОБЩАЯ СТАТИСТИКА:*\n\n👥 Тест {pw}: *{len(attempts)}* {decline_friend_word(len(attempts))}\n📈 Средний результат: *{avg_score:.0f}%*\n👑 Лучший: *{max_score:.0f}%* — *{sa[0]['friend_name']}* 💕\n💔 Худший: *{min_score:.0f}%*\n\n"
            if len(sa)>=2:
                best, second = sa[0], sa[1]; diff = best['score']-second['score']
                text += f"⚡ *БИТВА ЛУЧШИХ ПОДРУГ:*\n🥇 *{best['friend_name']}* — {best['score']:.0f}%\n🥈 *{second['friend_name']}* — {second['score']:.0f}%\n\n"
                if diff>=20: text += f"👑 *{best['friend_name']}* знает НАМНОГО лучше!\nОна soulmate! Береги её 💕\n"
                elif diff>=10: text += f"💪 *{best['friend_name']}* лидирует!\n{second['friend_name']} дышит в спину 🔥\n"
                elif diff>=5: text += f"⚡ Напряжённая борьба!\nУстройте реванш 🎯\n"
                else: text += f"🎯 ОДИНАКОВЫЙ результат!\nОбе знают отлично! 💕💕\n"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ Битва", callback_data=f"battle_{tid}"), InlineKeyboardButton("📊 Ответы", callback_data=f"answers_{tid}")], [InlineKeyboardButton("🔮 Анализ", callback_data=f"friend_details_{get_db().execute('SELECT id FROM attempts WHERE test_id=? AND friend_name=?', (tid, sa[0]['friend_name'])).fetchone()[0]}")], [InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_test_{tid}")]])
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        
        # === УДАЛИТЬ ТЕСТ ===
        elif data.startswith("delete_"):
            tid = int(data.replace("delete_","")); delete_test(query.from_user.id, tid)
            await query.message.reply_text("🗑 Тест удалён! Создай новый 💕", reply_markup=get_main_keyboard(query.from_user.id))
        
        # === АДМИН КОМАНДЫ ===
        elif data=="admin_refresh_stats": await admin_stats(update, context)
        elif data=="admin_funnel":
            conn = get_db(); c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM users'); total = c.fetchone()[0]
            c.execute('SELECT COUNT(DISTINCT creator_id) FROM tests'); created = c.fetchone()[0]
            c.execute('SELECT COUNT(DISTINCT friend_id) FROM attempts'); passed = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE premium_until>datetime('now')"); premium = c.fetchone()[0]; conn.close()
            await query.message.edit_text(f"🔄 *ВОРОНКА КОНВЕРСИИ*\n\n👥 Всего: *{total}* (100%)\n📝 Создали тест: *{created}* ({round(created/max(total,1)*100,1)}%)\n🎮 Прошли тест: *{passed}* ({round(passed/max(total,1)*100,1)}%)\n💎 Премиум: *{premium}* ({round(premium/max(total,1)*100,1)}%)", parse_mode=ParseMode.MARKDOWN)
        elif data=="back_to_admin": await admin_panel(update, context)
        elif data=="server_refresh": await admin_server_stats_compact(update, context)
        elif data=="admin_media_stats": await admin_media_stats(update, context)
        elif data=="media_force_cleanup": media_manager.periodic_cleanup(); await query.answer("✅ Очищено"); await admin_media_stats(update, context)
        
        else:
            logger.warning(f"⚠️ Неизвестный callback: '{data}'")
    
    except Exception as e:
        logger.error(f"💥 Ошибка в callback_handler: {e}", exc_info=True)
        try:
            await query.message.reply_text("😢 *Произошла ошибка*\n\nПопробуй ещё раз или нажми /start", parse_mode=ParseMode.MARKDOWN)
        except:
            pass

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (все оригинальные тексты сохранены) ===
async def select_question_group(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    group = query.data.replace("group_",""); data = context.user_data.get('creating_test')
    if not data: return
    if group=='random':
        all_q = [q for g in QUESTION_GROUPS for q in QUESTIONS.get(g,[])]; random.shuffle(all_q)
        data['group_questions'] = all_q[:30]
    else: data['group_questions'] = QUESTIONS.get(group,[]).copy(); random.shuffle(data['group_questions'])
    data['step'] = 'questions_count'
    await query.message.reply_text(f"📊 Сколько вопросов?\n✏️ Напиши число от 2 до {MAX_QUESTIONS}:", reply_markup=get_cancel_keyboard())

async def show_presets(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    kb = [[InlineKeyboardButton(p['name'], callback_data=f"preset_{k}")] for k, p in PRESET_GROUPS.items()]
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_groups")])
    await query.message.edit_text("📦 *ГОТОВЫЕ НАБОРЫ*\n\n👇 Выбери:", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

async def select_preset(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    preset = PRESET_GROUPS.get(query.data.replace("preset_",""))
    if not preset: return
    data = context.user_data.get('creating_test')
    if not data: return
    data['group_questions'] = preset['questions']; data['step'] = 'questions_count'
    await query.message.reply_text(f"✅ *{preset['name']}*\n📊 Сколько вопросов?\n✏️ Напиши число:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def greeting_choice(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    choice = query.data.replace("greeting_",""); data = context.user_data.get('creating_test')
    if choice=="skip":
        data['step'] = 'selecting_question'; data['current_question_index'] = 0; data['greeting_type'] = None; data['greeting_file_id'] = None
        await query.message.reply_text("✨ *Приступаем к вопросам!*", parse_mode=ParseMode.MARKDOWN); await show_question_for_selection(query, context); return
    data['greeting_type'] = choice; data['waiting_greeting'] = True
    t = "🎤 Отправь голосовое (до 15 сек)" if choice=="voice" else "🎥 Отправь видео (до 15 сек)"
    await query.message.reply_text(t+"\n\n❌ *Отмена* — пропустить", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def save_greeting(update, context):
    data = context.user_data.get('creating_test')
    if not data or not data.get('waiting_greeting'): return
    uid = update.effective_user.id; gt = data['greeting_type']
    if gt=="voice":
        if not update.message.voice: return
        fid = update.message.voice.file_id; fs = update.message.voice.file_size or 0; dur = update.message.voice.duration or 0
    else:
        if not update.message.video: return
        fid = update.message.video.file_id; fs = update.message.video.file_size or 0; dur = update.message.video.duration or 0
    val = media_manager.validate_media(fid, gt, fs, dur)
    if not val['valid']: await update.message.reply_text(f"❌ {val['reason']}"); return
    data['greeting_file_id'] = fid; data['waiting_greeting'] = False; data['step'] = 'selecting_question'; data['current_question_index'] = 0
    data['_pending_media'] = {'file_id':fid,'file_type':gt,'file_size':fs,'duration':dur}
    await update.message.reply_text("✅ *Поздравление сохранено!*\n\n✨ *Приступаем к вопросам!* ✨", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(uid))
    await show_question_for_selection(update, context)

async def save_photo(update, context):
    data = context.user_data.get('creating_test')
    if not data or not data.get('waiting_photo') or not update.message.photo: return
    fid = update.message.photo[-1].file_id
    if 'photos' not in data: data['photos'] = {}
    data['photos'][str(data['current_q'])] = fid
    if '_pending_photos' not in data: data['_pending_photos'] = []
    data['_pending_photos'].append({'file_id':fid})
    data['waiting_photo'] = False; data['step'] = 'collecting_options'; data['current_options'] = []; data['waiting_for_option'] = True
    await update.message.reply_text("✅ *Фото добавлено!* 📸\n\n✏️ *Напиши вариант ответа №1:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def show_question_for_selection(update, context):
    data = context.user_data.get('creating_test')
    if not data: return
    qs = data.get('group_questions',[]); data['current_question_index'] = data.get('current_question_index',0)
    qt = qs[data['current_question_index']]; data['current_question'] = qt
    text = f"📝 *Вопрос {data['current_q']+1}/{data['total_q']}*\n\n{qt}"
    if hasattr(update,'message'): await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_choice_keyboard())
    else: await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_choice_keyboard())

async def next_question_callback(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    data = context.user_data.get('creating_test')
    if not data: return
    qs = data.get('group_questions',[]); idx = (data.get('current_question_index',0)+1)%len(qs)
    data['current_question_index'] = idx; data['current_question'] = qs[idx]
    await query.message.edit_text(f"📝 *Вопрос {data['current_q']+1}/{data['total_q']}*\n\n{qs[idx]}", parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_choice_keyboard())

async def random_question_callback(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    data = context.user_data.get('creating_test')
    if not data: return
    all_q = [q for g in QUESTION_GROUPS for q in QUESTIONS.get(g,[])]; random.shuffle(all_q)
    data['group_questions'] = all_q[:30]; data['current_question_index'] = 0; data['current_question'] = all_q[0]
    await query.message.edit_text(f"📝 *Вопрос {data['current_q']+1}/{data['total_q']}*\n\n{all_q[0]}", parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_choice_keyboard())

async def select_this_question(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    data = context.user_data.get('creating_test')
    if not data: return
    data['current_options'] = []; data['step'] = 'collecting_options'; data['waiting_for_option'] = True
    await query.message.reply_text(f"📝 *Вопрос:* {data['current_question']}\n\n✏️ *Напиши вариант ответа №1:*\n\n📏 *До 50 символов*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def add_photo_to_question(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    data = context.user_data.get('creating_test')
    if not data or not data.get('current_question'): return
    data['waiting_photo'] = True
    await query.message.reply_text("📸 *Отправь фото*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def custom_question(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    data = context.user_data.get('creating_test')
    if not data: return
    data['waiting_custom_question'] = True
    await query.message.reply_text("✏️ *Напиши свой вопрос:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def select_correct(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    ci = int(query.data.replace("correct_","")); data = context.user_data.get('creating_test')
    if not data: return
    await query.message.reply_text("💬 *Хочешь добавить комментарий?*\n\nНапиши или нажми «Пропустить»\n\n*Пример:* «Да, я обожаю этот цвет!»", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Пропустить", callback_data=f"skip_comment_{ci}")]]))
    data['waiting_comment'] = True; data['temp_correct_idx'] = ci

async def save_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data or not data.get('waiting_comment'): return
    ci = data['temp_correct_idx']
    comment_text = update.message.text.strip()
    if len(comment_text) > 100:
        await update.message.reply_text("⚠️ *Слишком длинный комментарий!*\n📏 Максимум 100 символов.\n\nНапиши короче или нажми «Пропустить»", parse_mode=ParseMode.MARKDOWN)
        return
    if 'comments' not in data: data['comments'] = {}
    data['comments'][str(data['current_q'])] = comment_text
    data['waiting_comment'] = False
    await continue_after_comment(update, context, ci)

async def skip_comment(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    data = context.user_data.get('creating_test')
    if not data: return
    ci = int(query.data.replace("skip_comment_","")); data['waiting_comment'] = False; await continue_after_comment(query, context, ci)

async def continue_after_comment(uoq, context, ci):
    data = context.user_data.get('creating_test')
    
    if data['current_q'] >= data['total_q']:
        await finish_test_creation(uoq, context)
        return
    
    data['questions_data'].append({'text':data['current_question'],'options':data['current_options'].copy(),'correct':ci})
    data['current_q'] += 1
    
    if data['current_q'] < data['total_q']:
        data['step'] = 'selecting_question'; data['current_question_index'] = (data.get('current_question_index',0)+1)%len(data.get('group_questions',[]))
        data['current_options'] = []; data['waiting_for_option'] = False; data['waiting_comment'] = False
        msg = f"✅ *Вопрос {data['current_q']} сохранён!*"
        if hasattr(uoq,'message'): await uoq.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        else: await uoq.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        await show_question_for_selection(uoq, context)
    else:
        await finish_test_creation(uoq, context)

async def finish_test_creation(uoq, context):
    data = context.user_data.get('creating_test')
    if not data: return
    
    qs = [q['text'] for q in data['questions_data']]
    opts = [q['options'] for q in data['questions_data']]
    corr = [q['correct'] for q in data['questions_data']]
    
    if hasattr(uoq, 'callback_query') and uoq.callback_query: user = uoq.callback_query.from_user
    elif hasattr(uoq, 'from_user'): user = uoq.from_user
    elif hasattr(uoq, 'effective_user'): user = uoq.effective_user
    else: return
    
    tid = create_test(user.id, user.first_name, data['title'], qs, opts, corr, data.get('greeting_type'), data.get('greeting_file_id'), data.get('comments',{}), data.get('photos',{}))
    pm = data.get('_pending_media')
    if pm: media_manager.track_media(pm['file_id'], pm['file_type'], user.id, tid, pm.get('file_size',0), pm.get('duration',0))
    for ph in data.get('_pending_photos',[]): media_manager.track_media(ph['file_id'], 'photo', user.id, tid)
    del context.user_data['creating_test']
    
    text = (f"🎉✨ *ТЕСТ ГОТОВ!* ✨🎉\n\n📝 *{data['title']}*\n• • • • • • • • • • • •\n💭 Вопросов: *{len(qs)}*\n")
    if data.get('greeting_file_id'): text += "🎬 Поздравление: *есть ✨*\n"
    if data.get('_pending_photos'): text += f"📸 Фото: *{len(data.get('_pending_photos',[]))}*\n"
    text += ("• • • • • • • • • • • •\n\n💖 *Отправь тест подружке и узнай\nкто знает тебя лучше всех!* 👑\n\n👇 Нажми на кнопку ниже чтобы поделиться:")
    if hasattr(uoq,'message'): await uoq.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(tid))
    else: await uoq.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(tid))
    await uoq.message.reply_text("🌸 Главное меню:", reply_markup=get_main_keyboard(user.id))

# === MAIN ===
def main():
    global bot_application
    app = Application.builder().token(TOKEN).build()
    bot_application = app
    
    # Фоновая проверка платежей каждые 60 секунд
    job_queue = app.job_queue
    job_queue.run_repeating(payment_checker, interval=60, first=10)
    
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
    
    logger.info("🚀✨ Бот запущен! Версия 11.0 (полная, все тексты оригинальные) ✨🚀")
    app.run_polling()

if __name__ == "__main__":
    main()
