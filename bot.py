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
from datetime import datetime, timedelta, time as datetime_time
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import yookassa
from yookassa import Payment, Configuration
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
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
    'humor': '😂 Приколы и мемы',
    'anime': '🎌 Аниме и манга',
    'music': '🎧 Музыка и плейлисты',
    'pets': '🐾 Питомцы и животные',
    'sport': '💪 Спорт и фитнес'
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
        "💕 Что я ценю в нашей дружбе больше всего?",
        "🦋 Когда мы стали не разлей вода?",
        "🎵 Какая песня про нашу дружбу?",
        "📸 Наша самая смешная совместная фотка?",
        "😭 Из-за чего я могу расплакаться при тебе?",
        "🤫 Мой секрет, который знаешь только ты?",
        "🌟 Что я загадала бы на падающую звезду?",
        "💬 Фраза, которую я говорю чаще всего?",
        "🛍️ Где мы любим шопиться вместе?",
        "🍿 Что мы всегда смотрим вдвоём?",
        "💝 Что я делаю когда скучаю по тебе?",
        "👯‍♀️ Наша общая мечта?",
        "🎁 Какой подарок от тебя я храню?",
        "💌 Моё любимое воспоминание с тобой?",
        "🤝 Что я никогда не прощу подруге?",
        "💎 Почему наша дружба особенная?",
        "📱 Какой стикер я шлю тебе чаще всего?",
        "🌈 Какого цвета наша дружба?",
        "🦄 Кто из нас главная фантазёрка?",
        "💖 Что ты чувствуешь думая обо мне?",
        "🎯 Наше общее хобби?",
        "🌸 Чему я у тебя научилась?",
        "🔥 Наша самая безумная выходка?",
        "💫 Если бы мы поменялись жизнями на день?",
        "👑 Кто из нас принцесса а кто королева?",
        "🎭 Кого из нас я играю в школьном театре?",
        "😴 Кто из нас больше любит поспать?",
        "📞 В какое время ночи я могу тебе позвонить?",
        "🎪 На какой фестиваль мы поедем вместе?",
        "🍕 Какую пиццу мы закажем на ночевку?",
        "💅 Кто кому делает маникюр?",
        "🎤 Наша песня в караоке?",
        "📖 Какую книгу я тебе посоветовала?",
        "🧋 Кто пьёт бабл ти а кто кофе?",
        "🛴 На чём мы катаемся по району?",
        "💄 Кто у кого ворует косметику?",
        "🎬 Какой фильм мы пересматриваем каждый год?",
        "👗 Кто у кого одалживает платья?",
        "🌟 Если бы наша дружба была сериалом, как бы он назывался?",
        "💕 Без чего наша дружба невозможна?",
    ],
    'love': [
        "💘 Кто мой тайный краш сейчас?",
        "😍 Какой типаж парней мне нравится?",
        "💋 Как я представляю идеальный первый поцелуй?",
        "🌹 Какое свидание я запомнила навсегда?",
        "💌 Кому я писала любовные записки?",
        "💔 Как я переживаю расставания?",
        "💍 Какую свадьбу я хочу?",
        "👀 На что я смотрю в первую очередь у парня?",
        "🎭 Ревнивая ли я по шкале от 1 до 10?",
        "💬 Обсуждаю ли я парней с подругами?",
        "🎬 Какой любовный фильм я пересматриваю?",
        "💕 Что важнее: внешность или чувство юмора?",
        "😳 Как я веду себя когда влюблена?",
        "📱 Кто мой краш из тиктока?",
        "💎 Верю ли я в любовь с первого взгляда?",
        "🦋 Что заставляет моё сердце биться чаще?",
        "💭 О ком я думаю перед сном?",
        "🎵 Какая песня о любви описывает меня?",
        "💝 Что для меня идеальные отношения?",
        "😢 Из-за какого парня я плакала?",
        "🌟 Кто мой идеальный мужчина из фильма?",
        "💌 Получала ли я валентинки?",
        "👻 Кто мой бывший, о котором я молчу?",
        "💖 Как я привлекаю внимание краша?",
        "🎯 Как я понимаю что это ОН?",
        "🔥 Сколько раз я влюблялась?",
        "💭 Что я пишу в дневнике о любви?",
        "🎁 Какой подарок от парня я мечтаю получить?",
        "📝 Писала ли я стихи о любви?",
        "🤳 Отправляла ли я свои фото крашу?",
        "💬 Как я флиртую?",
        "😬 Что меня смущает на свидании?",
        "🎭 Играла ли я в любовь понарошку?",
        "💕 Кто был мой первый краш в детском саду?",
        "🌟 На какого актёра я западаю?",
        "💔 Что я делаю чтобы забыть бывшего?",
        "🦄 Верю ли я в родственные души?",
        "👑 Какой парень достоин меня по мнению подруг?",
        "💌 Что я ответила на первое признание в любви?",
        "🌈 Каким будет моё свидание мечты через 10 лет?",
    ],
    'style': [
        "👗 Мой стиль в трёх эмодзи?",
        "🎀 Какой цвет царит в моём шкафу?",
        "👟 Кроссовки или каблуки — что выберу?",
        "🛍️ Без какого бренда я не могу?",
        "👖 Джинсы или платья — что чаще на мне?",
        "💍 Моё отношение к аксессуарам?",
        "👜 Что всегда можно найти в моей сумке?",
        "💇‍♀️ Как часто я экспериментирую с причёской?",
        "💅 Какой маникюр я выберу на выпускной?",
        "👓 Очки для зрения или просто стиль?",
        "👠 Моя самая дорогая пара обуви?",
        "🕶️ Без какого аксессуара я не выхожу?",
        "👚 Моя любимая футболка с каким принтом?",
        "🧢 Ношу ли я кепки?",
        "💄 Крашусь ли я каждый день?",
        "🪞 Сколько минут я крашусь утром?",
        "🎨 Какой цвет мне категорически не идёт?",
        "👗 Платье или спортивный костюм на прогулку?",
        "🛍️ Как часто я покупаю новую одежду?",
        "💍 Люблю ли я бижутерию или только золото?",
        "👠 Каблуки какой высоты я ношу?",
        "📸 В чём я фоткаюсь чаще всего?",
        "🎀 Романтик, кэжуал или спорт шик?",
        "👗 Что я надену на первое свидание?",
        "💎 Какой аксессуар для меня важнее всего?",
        "🌈 Какой цвет я никогда не надену?",
        "🧥 Моё любимое пальто или куртка?",
        "👖 Скинни, мом джинс или багги?",
        "🎒 С какой сумкой я хожу в школу?",
        "💄 Какой макияж я делаю за 5 минут?",
        "👠 Туфли на шпильке или балетки?",
        "🧣 Люблю ли я шарфы и платки?",
        "💍 Сколько колец я ношу?",
        "🕶️ Солнцезащитные очки — стиль или необходимость?",
        "👗 Моё самое любимое платье?",
        "💇‍♀️ Какой цвет волос я мечтаю попробовать?",
        "👛 Клатч или шоппер?",
        "💎 Жемчуг или стразы?",
        "🎨 Макияж в стиле нюд или смоки айс?",
        "👚 Что я сплю в пижаме или футболке?",
    ],
    'beauty': [
        "💄 Моя любимая помада — какой оттенок?",
        "🧴 Какой уход за кожей у меня?",
        "💅 Гелевый маникюр или обычный лак?",
        "👁️ Тушь для ресниц — какой бренд?",
        "💇‍♀️ Как часто я стригу кончики?",
        "🎨 Крашу ли я волосы в яркие цвета?",
        "🧖‍♀️ Делаю ли я маски для лица?",
        "🌸 Мои любимые духи?",
        "💦 Пенка или гель для умывания?",
        "🧼 Ванна с пеной или душ?",
        "💤 Ночной крем — использую ли?",
        "☀️ Защита SPF каждый день?",
        "💋 Блеск или матовая помада?",
        "👩‍🎤 Макияж на вечеринку за сколько минут?",
        "🧴 Тип моей кожи?",
        "💆‍♀️ Делаю ли я массаж лица гуаша?",
        "🦷 Отбеливаю ли я зубы?",
        "🧴 Моё любимое масло для тела?",
        "💅 Делаю ли я педикюр сама или в салоне?",
        "💇‍♀️ Каре или длинные волосы?",
        "🧖‍♀️ Хожу ли я к косметологу?",
        "🌸 Духи на зиму и лето — разные?",
        "💤 Патчи под глаза перед сном?",
        "🪞 Сколько зеркал у меня дома?",
        "💄 Какой продукт из косметики закончится первым?",
        "🌟 Что главное в уходе за собой?",
        "💋 Сколько у меня помад?",
        "👁️ Накладные ресницы — да или нет?",
        "🎨 Тени для век — какой оттенок любимый?",
        "💅 Ногти — длинные или короткие?",
        "🧴 Сыворотка для лица — использую ли?",
        "💄 Тональный крем или BB крем?",
        "👁️ Стрелки на глазах каждый день?",
        "💇‍♀️ Фен или естественная сушка?",
        "🧖‍♀️ Пилинг для лица — как часто?",
        "🌸 Моя любимая маска для лица?",
        "💤 Шелковая наволочка для волос?",
        "💅 Какой формы мои ногти?",
        "👄 Бальзам для губ — всегда в кармане?",
        "🌟 Какой бьюти-секрет я знаю?",
    ],
    'social': [
        "📱 Моя любимая соцсеть?",
        "📸 Что я пощу в сторис чаще всего?",
        "❤️ Сколько лайков я набираю в среднем?",
        "🦄 Какой фильтр я использую чаще всего?",
        "👯 С кем я снимаю совместный контент?",
        "📺 Какой блогер меня вдохновляет?",
        "🎵 Какой трек сейчас в моём тиктоке?",
        "🔒 Приватный или открытый аккаунт?",
        "💬 Сколько часов я сижу в телеграме?",
        "📊 Слежу ли я за статистикой?",
        "🎬 Снимаю ли я рилсы?",
        "📝 Посты или только сторис?",
        "🤳 Сколько селфи я делаю в день?",
        "📱 Сколько приложений на моём телефоне?",
        "🔋 На сколько % у меня обычно зарядка?",
        "🎮 Играю ли я в мобильные игры?",
        "📹 Смотрю ли я ютуб перед сном?",
        "🎤 Записываю ли я голосовые?",
        "💬 В каких чатах я самая активная?",
        "📲 Как часто я меняю аватарку?",
        "📱 Какой рингтон на моём телефоне?",
        "🎵 Что у меня в плейлисте прямо сейчас?",
        "💬 Кому я пишу чаще всего?",
        "📸 Сколько у меня подписчиков?",
        "🦄 Какой эффект в сторис я люблю?",
        "🎬 Смотрю ли я стримы?",
        "📱 iPhone или Android?",
        "💬 Люблю ли я голосовые или текстовые?",
        "📸 Делаю ли я фото еды для соцсетей?",
        "🦋 Какое у меня bio в инстаграме?",
        "🎵 Какой плейлист я слушаю в дороге?",
        "💬 В каком часе я отвечаю быстрее всего?",
        "📱 Какое приложение я открываю первым утром?",
        "🦄 Какой фильтр я никогда не использую?",
        "📸 Снимаю ли я закаты?",
        "💬 Отправляю ли я мемы каждый день?",
        "🎬 Подписана ли я на каналы в телеграме?",
        "🦋 Сколько у меня сохранённых постов?",
        "📱 Что на моём экране блокировки?",
        "💬 Какой стикерпак у меня самый любимый?",
    ],
    'school': [
        "📖 Любимый предмет — какой и почему?",
        "😫 Какой урок я ненавижу всей душой?",
        "📱 Что я делаю на скучных уроках?",
        "👯 С кем я сижу за партой?",
        "🤫 Как я списываю домашку?",
        "🍔 Что я покупаю в столовой?",
        "👩‍🏫 Моя любимая учительница?",
        "👻 Кого из учителей я боюсь?",
        "🏆 Моя лучшая оценка в четверти?",
        "🎒 Что всегда можно найти в моём рюкзаке?",
        "📚 Читаю ли я книги по школьной программе?",
        "✏️ Гелевая ручка или карандаш?",
        "📅 Самый тяжёлый день недели?",
        "🏃‍♀️ Люблю ли я физкультуру?",
        "🎨 Какой урок я бы добавила в расписание?",
        "📝 Делаю ли я домашку сразу после школы?",
        "🤝 С кем я всегда делаю проекты?",
        "🎓 Куда я хочу поступать?",
        "📊 Сильно ли я переживаю из-за оценок?",
        "🌟 Моё главное школьное достижение?",
        "👯 Кто моя школьная bestie?",
        "📱 Прячу ли я телефон под партой?",
        "🎒 Ношу ли я косметичку в школу?",
        "🌟 Какой предмет я бы отменила?",
        "👩‍🏫 Прозвища учителей — какие?",
        "💄 Крашусь ли я перед школой?",
        "📖 Сколько времени я трачу на домашку?",
        "🍎 Что я ем на перемене?",
        "🎒 Тяжёлый ли у меня рюкзак?",
        "📱 Слушаю ли я музыку на уроках?",
        "👯 Сколько у меня подруг в классе?",
        "📝 Пишу ли я шпаргалки?",
        "🎨 Люблю ли я рисовать в тетрадях?",
        "🏆 Участвовала ли я в олимпиадах?",
        "📚 Моя любимая книга из школьной программы?",
        "🎭 Как я веду себя на контрольной?",
        "🍕 Что я заказываю в столовой на обед?",
        "👻 Прогуливала ли я уроки?",
        "🌟 За что меня хвалили учителя?",
        "💬 О чём я болтаю с подругами на переменах?",
    ],
    'dreams': [
        "✈️ В какую страну я мечтаю поехать?",
        "🌟 Моя самая заветная мечта?",
        "🚗 Машина моей мечты?",
        "☀️ Как выглядит мой идеальный день?",
        "🛍️ Что я хочу купить на первую зарплату?",
        "📝 Что возглавляет мой вишлист?",
        "🏠 Дом или квартира моей мечты?",
        "💎 О чём я мечтаю каждый день?",
        "🎓 Кем я буду через 5 лет?",
        "💍 Какой я вижу свою свадьбу?",
        "🐶 Какого питомца я хочу завести?",
        "🎤 Хочу ли я быть знаменитой?",
        "📸 О чём мечтаю глядя на звёзды?",
        "🌈 В какой стране хочу жить?",
        "🎬 Если бы про меня сняли фильм?",
        "💼 Работа моей мечты?",
        "🏝️ Отпуск на острове или в горах?",
        "🛫 Что я сделаю когда разбогатею?",
        "💖 Сколько у меня будет детей?",
        "✨ Какое желание загадаю золотой рыбке?",
        "🌟 Три желания которые я бы исполнила?",
        "💎 Что для меня дороже денег?",
        "🎤 Хочу ли я выступать на сцене?",
        "✈️ Где я встречу свою старость?",
        "🐶 Какое необычное животное я хочу?",
        "🏠 Сколько комнат в доме мечты?",
        "🌸 Какой сад я посажу у дома?",
        "📚 Напишу ли я книгу о своей жизни?",
        "🎨 Каким видом творчества я хочу заняться?",
        "🌍 Сколько стран я хочу посетить?",
        "💕 О какой семье я мечтаю?",
        "🚀 Полетела бы я в космос?",
        "🏰 В каком замке я хотела бы пожить?",
        "🎪 Какой бизнес я хочу открыть?",
        "🌟 Что я хочу изменить в мире?",
        "💫 Если бы я могла вернуться в прошлое?",
        "🦋 Какую суперспособность я хочу?",
        "💝 О каком подарке я мечтаю?",
        "🌈 Что я хочу успеть до 30 лет?",
        "👑 Какой титул я бы себе дала?",
    ],
    'kpop': [
        "🎤 Моя любимая к-поп группа?",
        "💕 Кто мой биас и почему?",
        "🎧 Какой трек играет на повторе?",
        "💜 Концерт мечты на который я хочу?",
        "⭐ С кем из айдолов я хочу селфи?",
        "💃 Какой танец я выучила первой?",
        "🫶 Кто мой вайб в к-попе?",
        "🎁 Какой мерч я хочу больше всего?",
        "📺 Моё любимое к-поп шоу?",
        "🌙 Соло или юнит — что я люблю больше?",
        "🎵 Какая песня заставила меня полюбить к-поп?",
        "💿 Сколько альбомов в моей коллекции?",
        "📱 Кто из айдолов на моей заставке?",
        "🎤 Пою ли я к-поп в караоке?",
        "🪭 Собираю ли я фотокарты?",
        "💬 С кем я фанатею вместе?",
        "🎬 Смотрю ли я дорамы с айдолами?",
        "💘 Кто мой bias wrecker?",
        "🎶 Топ-3 группы которые я слушаю?",
        "🌟 Какой концепт я люблю больше?",
        "💜 Кто мой ультимативный биас?",
        "🎤 С какой группы началась моя любовь к к-поп?",
        "💃 Какие танцы я учу по утрам?",
        "📺 Какое шоу я пересматриваю?",
        "🌟 Если бы я встретила одного айдола?",
        "🎵 Под какую песню я плачу?",
        "💜 Какой лайтстик у меня есть?",
        "🎤 Какое фан-имя у моей любимой группы?",
        "💕 Кто мой первый биас?",
        "🦋 Какая дорама с айдолом моя любимая?",
        "💿 Винил или CD — что я коллекционирую?",
        "🎵 Кавер на какую песню я хочу снять?",
        "🌟 Какой айдол вдохновляет меня больше всех?",
        "💜 Что я кричу на концерте?",
        "🎤 В какой группе я хотела бы быть участницей?",
        "🪭 Какое световое шоу я хочу увидеть?",
        "💕 Какой ship я поддерживаю?",
        "🎶 Какая песня поднимает мне настроение?",
        "🌟 Какой айдол по знаку зодиака мне подходит?",
        "💜 Сколько лет я уже в к-поп фандоме?",
    ],
    'food': [
        "🍕 Пицца — какой вкус мой любимый?",
        "😖 Что я никогда не положу в рот?",
        "👩‍🍳 Коронное блюдо которое я готовлю?",
        "☕ Мой заказ в кофейне?",
        "🍰 Торт или пирожное — что выберу?",
        "🍳 Что я ем на завтрак?",
        "🏠 Моё любимое кафе?",
        "🚫 Еда которую я ненавижу с детства?",
        "🍜 Рамен или паста — что вкуснее?",
        "🥤 Какой напиток я пью каждый день?",
        "🍦 Моё любимое мороженое?",
        "🍫 Молочный шоколад или горький?",
        "🥗 Ем ли я салаты и какие?",
        "🍔 Бургер или роллы на ужин?",
        "🧋 Люблю ли я бабл ти с тапиокой?",
        "🍣 Суши — какой ролл мой любимый?",
        "🌮 Тако или буррито — что выберу?",
        "🍩 Пончики с какой начинкой я люблю?",
        "🧀 Сыр — добавляю ли я его везде?",
        "🍇 Мои любимые фрукты и ягоды?",
        "🍳 Яичница или омлет по утрам?",
        "☕ Латте, капучино или раф?",
        "🍕 Ананасы на пицце — да или нет?",
        "🍣 Острое — люблю ли я васаби?",
        "🍩 Что я ем когда мне грустно?",
        "🍦 Ванильное или шоколадное мороженое?",
        "🥞 Блины или панкейки на завтрак?",
        "🍜 Какой суп я люблю больше всего?",
        "🧁 Капкейки сама пеку или покупаю?",
        "🍓 Клубника со сливками или шоколадом?",
        "🥑 Авокадо тосты — ем ли я такое?",
        "🍹 Мохито или лимонад летом?",
        "🍪 Печенье с молоком перед сном?",
        "🧇 Вафли с чем я люблю?",
        "🍿 Попкорн солёный или сладкий?",
        "🍰 Чизкейк или тирамису?",
        "🥤 Кола или спрайт?",
        "🍩 Сколько пончиков я могу съесть за раз?",
        "🍕 Тонкое тесто или пышное?",
        "🧋 Какой вкус бабл ти я заказываю?",
    ],
    'anime': [
        "🎌 Моё любимое аниме?",
        "🌸 Кто мой вайфу или хазбандо?",
        "🗡️ Какой аниме-персонаж похож на меня?",
        "🎬 Аниме или манга — что я предпочитаю?",
        "📺 Сколько аниме я смотрю в неделю?",
        "🍥 Любимый жанр аниме?",
        "🎭 Косплеила ли я кого-то?",
        "💫 Если бы я попала в аниме, в какое?",
        "🌙 Смотрю ли я аниме по ночам?",
        "📱 Какая аниме-песня у меня на звонке?",
        "🎨 Рисую ли я в аниме-стиле?",
        "⛩️ Хочу ли я поехать в Японию?",
        "🌸 Сакура или хризантема?",
        "🍜 Рамен или онигири?",
        "💕 Кто мой любимый аниме-парочка?",
        "👀 Какое аниме я пересматривала 5 раз?",
        "🎤 Пою ли я опенинги в душе?",
        "📚 Читаю ли я мангу на телефоне?",
        "🌟 Какой аниме-мир я хочу посетить?",
        "💔 Над каким аниме я плакала?",
        "🦊 Девушка-лисичка или девушка-кошка?",
        "⚔️ Сёнэн или сёдзё?",
        "🎌 Субтитры или озвучка?",
        "🏯 Какой аниме-фестиваль я хочу посетить?",
        "🌸 Какое аниме я советую всем?",
        "🗡️ Мой любимый аниме-злодей?",
        "💫 Суперспособность из аниме которую я хочу?",
        "🎬 Аниме-фильм который я жду?",
        "🌟 Кто мой аниме-краш?",
        "🍡 Моя любимая аниме-еда?",
        "📸 Делаю ли я аниме-аватарки?",
        "💕 OTP из аниме?",
        "🎭 Ходила ли я на аниме-фест?",
        "🌙 Аниме которое я смотрю перед сном?",
        "💬 С кем я обсуждаю аниме?",
        "🎌 Коллекционирую ли я аниме-фигурки?",
        "🌸 Смотрю ли я хентай? (шутка)",
        "🗡️ Какое аниме я бросила после 1 серии?",
        "💫 Если бы я могла жить в аниме-мире?",
        "🌟 Аниме которое изменило мою жизнь?"
    ],
    'music': [
        "🎧 Какой жанр музыки я слушаю?",
        "🎵 Моя любимая песня прямо сейчас?",
        "🎤 Любимый исполнитель или группа?",
        "🎸 Играю ли я на музыкальном инструменте?",
        "🎶 Что у меня в плейлисте на повторе?",
        "💿 Винил, CD или стриминг?",
        "🎧 В каких наушниках я хожу?",
        "🎼 Понимаю ли я ноты?",
        "🎤 Пою ли я в караоке?",
        "🎵 Песня которая напоминает мне о тебе?",
        "📻 Слушаю ли я радио?",
        "🎬 Саундтрек из какого фильма я люблю?",
        "🎧 Сколько часов в день я слушаю музыку?",
        "💃 Под какую музыку я танцую?",
        "🎵 Моя любимая песня на английском?",
        "🎤 Хочу ли я научиться петь?",
        "🎸 Акустика или электро?",
        "🎶 Какой трек я включу на вечеринке?",
        "🎧 Мои любимые наушники — какие?",
        "💔 Песня под которую я плакала?",
        "🌟 Концерт мечты на который я хочу?",
        "🎤 Подпеваю ли я в машине?",
        "🎵 Песня которая поднимает настроение?",
        "📱 Что у меня в Spotify Wrapped?",
        "🎼 Классика или попса?",
        "🎤 Кавер или оригинал — что лучше?",
        "🎧 Шумодав или музыка для учёбы?",
        "💿 Коллекционирую ли я альбомы?",
        "🎶 Какая песня ассоциируется с летом?",
        "🎵 Рэп или рок — что ближе?",
        "🌟 Артист которого я фанатею?",
        "🎤 Моя любимая песня из детства?",
        "🎧 Музыка для сна — слушаю ли?",
        "💕 Наша с тобой песня?",
        "🎵 Инди или мейнстрим?",
        "🎸 Была ли я на живом концерте?",
        "🎶 Песня которую я знаю наизусть?",
        "🌟 Если бы я была певицей, какой жанр?",
        "🎤 Что я пою когда никто не слышит?",
        "🎧 Поделилась бы я своим плейлистом?"
    ],
    'pets': [
        "🐶 Собака или кошка — кто мой фаворит?",
        "🐱 Как зовут моего питомца?",
        "🐾 Какое животное у меня есть?",
        "🦊 Какое экзотическое животное я хочу?",
        "🐰 Хомяк, кролик или шиншилла?",
        "🐍 Боюсь ли я змей и пауков?",
        "🐴 Хочу ли я научиться ездить верхом?",
        "🐠 Есть ли у меня аквариум?",
        "🦜 Говорящий попугай — хочу ли?",
        "🐕 Собака какой породы мне нравится?",
        "🐈 Чёрная кошка — к удаче или нет?",
        "🐾 Сколько питомцев я хочу когда вырасту?",
        "🦮 Гуляю ли я с собакой?",
        "🐱 Мой кот спит со мной?",
        "🐶 Кто главный в доме — я или пёс?",
        "🐾 Какое животное я боюсь?",
        "🦊 Лиса или енот — кто милее?",
        "🐰 Завела бы я кролика?",
        "🐍 Держала ли я змею в руках?",
        "🦄 Единороги существуют?",
        "🐕 Моя собака умеет давать лапу?",
        "🐈 Мой кот царапает мебель?",
        "🐾 Спасала ли я бездомных животных?",
        "🐶 Смотрю ли я видео с собаками?",
        "🐱 Кошачье кафе — ходила ли?",
        "🐴 Каталась ли я на лошади?",
        "🐠 Рыбки — скучно или красиво?",
        "🦜 Какое животное говорит лучше всех?",
        "🐕 Дрессирую ли я свою собаку?",
        "🐈 Сколько кошек — уже слишком много?",
        "🐾 Волонтёрила ли я в приюте?",
        "🐶 Какую кличку я дам своей собаке?",
        "🐱 Мой кот приносит мне мышей?",
        "🦊 Хочу ли я лису как в тиктоке?",
        "🐰 Что ест мой кролик на завтрак?",
        "🐍 Какое животное я бы никогда не завела?",
        "🐴 Люблю ли я смотреть скачки?",
        "🐕 Собака-поводырь — хочу ли такую?",
        "🐈 Кошки или собаки — кто умнее?",
        "🐾 Если бы я была животным, то каким?"
    ],
    'sport': [
        "💪 Занимаюсь ли я спортом?",
        "🏃‍♀️ Бег или йога — что я выберу?",
        "🧘‍♀️ Медитирую ли я по утрам?",
        "🏋️‍♀️ Хожу ли я в спортзал?",
        "🤸‍♀️ Гибкая ли я?",
        "🚴‍♀️ Катаюсь ли я на велосипеде?",
        "🏊‍♀️ Люблю ли я плавать?",
        "⛸️ Катаюсь ли я на коньках?",
        "🎾 Теннис или бадминтон?",
        "🏀 Играю ли я в командные виды спорта?",
        "🩰 Занималась ли я танцами?",
        "🤼‍♀️ Смотрю ли я спортивные соревнования?",
        "⚽ Футбол или волейбол?",
        "🏓 Настольный теннис — играю ли?",
        "🥊 Бокс или единоборства — моё?",
        "🧗‍♀️ Лазала ли я по скалам?",
        "🛼 Катаюсь ли я на роликах?",
        "🏌️‍♀️ Гольф — скучно или интересно?",
        "🏄‍♀️ Хочу ли я научиться сёрфить?",
        "⛷️ Горные лыжи или сноуборд?",
        "🤸‍♀️ Делаю ли я зарядку по утрам?",
        "🧘‍♀️ Какой вид йоги мне нравится?",
        "🏃‍♀️ Сколько километров я пробегу?",
        "💪 Качаю ли я пресс каждый день?",
        "🤾‍♀️ Гандбол — знаю ли я правила?",
        "🏹 Стрельба из лука — хочу ли попробовать?",
        "🎿 Беговые лыжи — люблю ли?",
        "🛹 Скейтборд или самокат?",
        "🏸 Бадминтон на пляже — играю ли?",
        "🥋 Карате или дзюдо — что выберу?",
        "🏊‍♀️ Плаваю ли я в бассейне зимой?",
        "🤸‍♀️ Растяжка — каждый день?",
        "🚴‍♀️ Велосипед или самокат?",
        "💪 Сколько раз я отжимаюсь?",
        "🏋️‍♀️ Тренируюсь ли я с тренером?",
        "🧗‍♀️ Боюсь ли я высоты на скалодроме?",
        "🛼 Падала ли я на роликах?",
        "🏄‍♀️ Серфинг на волнах или вейкборд?",
        "🤼‍♀️ Смотрела ли я рестлинг?",
        "💪 Спорт — это боль или удовольствие?"
    ],
    'anime': [
        "🎌 Моё любимое аниме?",
        "🌸 Кто мой вайфу или хазбандо?",
        "🗡️ Какой аниме-персонаж похож на меня?",
        "🎬 Аниме или манга — что я предпочитаю?",
        "📺 Сколько аниме я смотрю в неделю?",
        "🍥 Любимый жанр аниме?",
        "🎭 Косплеила ли я кого-то?",
        "💫 Если бы я попала в аниме, в какое?",
        "🌙 Смотрю ли я аниме по ночам?",
        "📱 Какая аниме-песня у меня на звонке?",
        "🎨 Рисую ли я в аниме-стиле?",
        "⛩️ Хочу ли я поехать в Японию?",
        "🌸 Сакура или хризантема?",
        "🍜 Рамен или онигири?",
        "💕 Кто мой любимый аниме-парочка?",
        "👀 Какое аниме я пересматривала 5 раз?",
        "🎤 Пою ли я опенинги в душе?",
        "📚 Читаю ли я мангу на телефоне?",
        "🌟 Какой аниме-мир я хочу посетить?",
        "💔 Над каким аниме я плакала?",
        "🦊 Девушка-лисичка или девушка-кошка?",
        "⚔️ Сёнэн или сёдзё?",
        "🎌 Субтитры или озвучка?",
        "🏯 Какой аниме-фестиваль я хочу посетить?",
        "🌸 Какое аниме я советую всем?",
        "🗡️ Мой любимый аниме-злодей?",
        "💫 Суперспособность из аниме которую я хочу?",
        "🎬 Аниме-фильм который я жду?",
        "🌟 Кто мой аниме-краш?",
        "🍡 Моя любимая аниме-еда?",
        "📸 Делаю ли я аниме-аватарки?",
        "💕 OTP из аниме?",
        "🎭 Ходила ли я на аниме-фест?",
        "🌙 Аниме которое я смотрю перед сном?",
        "💬 С кем я обсуждаю аниме?",
        "🎌 Коллекционирую ли я аниме-фигурки?",
        "🌸 Смотрю ли я хентай? (шутка)",
        "🗡️ Какое аниме я бросила после 1 серии?",
        "💫 Если бы я могла жить в аниме-мире?",
        "🌟 Аниме которое изменило мою жизнь?"
    ],
    'music': [
        "🎧 Какой жанр музыки я слушаю?",
        "🎵 Моя любимая песня прямо сейчас?",
        "🎤 Любимый исполнитель или группа?",
        "🎸 Играю ли я на музыкальном инструменте?",
        "🎶 Что у меня в плейлисте на повторе?",
        "💿 Винил, CD или стриминг?",
        "🎧 В каких наушниках я хожу?",
        "🎼 Понимаю ли я ноты?",
        "🎤 Пою ли я в караоке?",
        "🎵 Песня которая напоминает мне о тебе?",
        "📻 Слушаю ли я радио?",
        "🎬 Саундтрек из какого фильма я люблю?",
        "🎧 Сколько часов в день я слушаю музыку?",
        "💃 Под какую музыку я танцую?",
        "🎵 Моя любимая песня на английском?",
        "🎤 Хочу ли я научиться петь?",
        "🎸 Акустика или электро?",
        "🎶 Какой трек я включу на вечеринке?",
        "🎧 Мои любимые наушники — какие?",
        "💔 Песня под которую я плакала?",
        "🌟 Концерт мечты на который я хочу?",
        "🎤 Подпеваю ли я в машине?",
        "🎵 Песня которая поднимает настроение?",
        "📱 Что у меня в Spotify Wrapped?",
        "🎼 Классика или попса?",
        "🎤 Кавер или оригинал — что лучше?",
        "🎧 Шумодав или музыка для учёбы?",
        "💿 Коллекционирую ли я альбомы?",
        "🎶 Какая песня ассоциируется с летом?",
        "🎵 Рэп или рок — что ближе?",
        "🌟 Артист которого я фанатею?",
        "🎤 Моя любимая песня из детства?",
        "🎧 Музыка для сна — слушаю ли?",
        "💕 Наша с тобой песня?",
        "🎵 Инди или мейнстрим?",
        "🎸 Была ли я на живом концерте?",
        "🎶 Песня которую я знаю наизусть?",
        "🌟 Если бы я была певицей, какой жанр?",
        "🎤 Что я пою когда никто не слышит?",
        "🎧 Поделилась бы я своим плейлистом?"
    ],
    'pets': [
        "🐶 Собака или кошка — кто мой фаворит?",
        "🐱 Как зовут моего питомца?",
        "🐾 Какое животное у меня есть?",
        "🦊 Какое экзотическое животное я хочу?",
        "🐰 Хомяк, кролик или шиншилла?",
        "🐍 Боюсь ли я змей и пауков?",
        "🐴 Хочу ли я научиться ездить верхом?",
        "🐠 Есть ли у меня аквариум?",
        "🦜 Говорящий попугай — хочу ли?",
        "🐕 Собака какой породы мне нравится?",
        "🐈 Чёрная кошка — к удаче или нет?",
        "🐾 Сколько питомцев я хочу когда вырасту?",
        "🦮 Гуляю ли я с собакой?",
        "🐱 Мой кот спит со мной?",
        "🐶 Кто главный в доме — я или пёс?",
        "🐾 Какое животное я боюсь?",
        "🦊 Лиса или енот — кто милее?",
        "🐰 Завела бы я кролика?",
        "🐍 Держала ли я змею в руках?",
        "🦄 Единороги существуют?",
        "🐕 Моя собака умеет давать лапу?",
        "🐈 Мой кот царапает мебель?",
        "🐾 Спасала ли я бездомных животных?",
        "🐶 Смотрю ли я видео с собаками?",
        "🐱 Кошачье кафе — ходила ли?",
        "🐴 Каталась ли я на лошади?",
        "🐠 Рыбки — скучно или красиво?",
        "🦜 Какое животное говорит лучше всех?",
        "🐕 Дрессирую ли я свою собаку?",
        "🐈 Сколько кошек — уже слишком много?",
        "🐾 Волонтёрила ли я в приюте?",
        "🐶 Какую кличку я дам своей собаке?",
        "🐱 Мой кот приносит мне мышей?",
        "🦊 Хочу ли я лису как в тиктоке?",
        "🐰 Что ест мой кролик на завтрак?",
        "🐍 Какое животное я бы никогда не завела?",
        "🐴 Люблю ли я смотреть скачки?",
        "🐕 Собака-поводырь — хочу ли такую?",
        "🐈 Кошки или собаки — кто умнее?",
        "🐾 Если бы я была животным, то каким?"
    ],
    'sport': [
        "💪 Занимаюсь ли я спортом?",
        "🏃‍♀️ Бег или йога — что я выберу?",
        "🧘‍♀️ Медитирую ли я по утрам?",
        "🏋️‍♀️ Хожу ли я в спортзал?",
        "🤸‍♀️ Гибкая ли я?",
        "🚴‍♀️ Катаюсь ли я на велосипеде?",
        "🏊‍♀️ Люблю ли я плавать?",
        "⛸️ Катаюсь ли я на коньках?",
        "🎾 Теннис или бадминтон?",
        "🏀 Играю ли я в командные виды спорта?",
        "🩰 Занималась ли я танцами?",
        "🤼‍♀️ Смотрю ли я спортивные соревнования?",
        "⚽ Футбол или волейбол?",
        "🏓 Настольный теннис — играю ли?",
        "🥊 Бокс или единоборства — моё?",
        "🧗‍♀️ Лазала ли я по скалам?",
        "🛼 Катаюсь ли я на роликах?",
        "🏌️‍♀️ Гольф — скучно или интересно?",
        "🏄‍♀️ Хочу ли я научиться сёрфить?",
        "⛷️ Горные лыжи или сноуборд?",
        "🤸‍♀️ Делаю ли я зарядку по утрам?",
        "🧘‍♀️ Какой вид йоги мне нравится?",
        "🏃‍♀️ Сколько километров я пробегу?",
        "💪 Качаю ли я пресс каждый день?",
        "🤾‍♀️ Гандбол — знаю ли я правила?",
        "🏹 Стрельба из лука — хочу ли попробовать?",
        "🎿 Беговые лыжи — люблю ли?",
        "🛹 Скейтборд или самокат?",
        "🏸 Бадминтон на пляже — играю ли?",
        "🥋 Карате или дзюдо — что выберу?",
        "🏊‍♀️ Плаваю ли я в бассейне зимой?",
        "🤸‍♀️ Растяжка — каждый день?",
        "🚴‍♀️ Велосипед или самокат?",
        "💪 Сколько раз я отжимаюсь?",
        "🏋️‍♀️ Тренируюсь ли я с тренером?",
        "🧗‍♀️ Боюсь ли я высоты на скалодроме?",
        "🛼 Падала ли я на роликах?",
        "🏄‍♀️ Серфинг на волнах или вейкборд?",
        "🤼‍♀️ Смотрела ли я рестлинг?",
        "💪 Спорт — это боль или удовольствие?"
    ],
    'humor': [
        "😂 Над каким мемом я смеялась до слёз?",
        "🤪 Какая у меня самая странная привычка?",
        "💃 Как я танцую когда никто не видит?",
        "🍪 Что я ем по ночам втихаря?",
        "👀 Как я вру и краснею ли при этом?",
        "😱 Что я ору когда вижу паука?",
        "🐌 Какой у меня самый глупый страх?",
        "💬 Моя коронная фраза которая всех бесит?",
        "🛌 В какой позе я сплю?",
        "🎤 Что я пою в душе?",
        "📸 Моё самое позорное фото в телефоне?",
        "🎭 Какую рожицу я корчу на селфи?",
        "🤣 Какой у меня смех? Опиши звук!",
        "🪄 Что бы я сделала став невидимкой?",
        "🎁 Самый странный подарок который я получала?",
        "💇‍♀️ Моя самая неудачная стрижка?",
        "👗 Что я надела не по погоде?",
        "📱 Что я лайкнула случайно в 3 ночи?",
        "😅 Моя самая неловкая ситуация?",
        "🎭 Как я пародирую учителей?",
        "💃 Что я делаю думая что никто не видит?",
        "🤪 Вредная привычка от которой я не могу избавиться?",
        "😱 От какого звука я просыпаюсь?",
        "📸 Самое смешное детское фото?",
        "🎤 Какую песню я ору в машине?",
        "😂 Какая шутка меня всегда смешит?",
        "🦄 Если бы я была животным то каким?",
        "🤣 Я спотыкалась на ровном месте?",
        "😜 Что я делаю чтобы развеселить подруг?",
        "🎭 Мой талант который никто не оценил?",
        "💬 Что я бормочу во сне?",
        "🪞 Сколько времени я смотрю в зеркало?",
        "🤷‍♀️ Что я теряю чаще всего?",
        "📱 Моя самая тупая переписка?",
        "😬 Что я делала на спор?",
        "🎤 Мой любимый трек для танцев под душем?",
        "💄 Как я крашусь в темноте?",
        "🛒 Что я покупаю в супермаркете ночью?",
        "😂 Над чем я смеюсь когда нельзя?",
        "🤪 Если бы я вела свой блог, о чём бы он был?",
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
            f"💝 {name} — твой персональный ангел-хранитель! Такая дружба нерушима и вечна! 🌟",
            f"🎀 С {name} вы прошли огонь и воду! Ваша дружба — настоящий бриллиант! 💎"
        ]
    elif score >= 70:
        predictions = [
            f"💎 {name} очень хорошо тебя знает! Вы близкие подруги, и ваша дружба крепнет с каждым днём 🌸",
            f"✨ {name} понимает тебя почти во всём. Ещё немного — и вы станете лучшими подругами! 💕",
            f"🌟 Вы с {name} на одной волне! Узнавайте друг друга ещё глубже, впереди много интересного! 🎵",
            f"🌸 {name} — настоящая подруга! Она знает твои привычки, вкусы и секреты. Цени это! 💫",
            f"🎯 {name} отлично тебя знает! Вы прошли через многое вместе. Дружба становится только крепче! 💪",
            f"🦋 С {name} легко и просто! Она понимает тебя с полуслова. Продолжайте в том же духе! ✨",
            f"💖 {name} помнит все твои любимые вещи! Это признак настоящей подруги! 🌸",
            f"🌈 Вы с {name} как пазл — идеально подходите друг другу! Продолжайте дружить! 💕"
        ]
    elif score >= 50:
        predictions = [
            f"🌸 {name} знает тебя неплохо, но есть куда расти! Проводите больше времени вместе, это сближает 💫",
            f"🌱 Ваша дружба с {name} только расцветает! Делитесь секретами, мечтами и любимыми треками 🎧",
            f"💫 {name} уже многое о тебе знает. Ещё немного — и вы станете ближе! Устройте совместную прогулку 🌈",
            f"📖 Вы с {name} на правильном пути! Узнавайте друг друга постепенно. Впереди много интересного! 💕",
            f"🎵 {name} знает о тебе главное. Расскажи ей больше о своих мечтах — это сближает! ✨",
            f"🌺 {name} уже твоя подруга! Поделись с ней своими любимыми фильмами и музыкой. Узнайте друг друга глубже! 💖",
            f"🍿 Пригласи {name} на девчачий вечер с пиццей! Это лучший способ узнать друг друга! 🌸",
            f"📸 Сделайте с {name} совместное фото и поставьте на заставку! Дружба становится крепче! 💕"
        ]
    elif score >= 30:
        predictions = [
            f"🦋 {name} только начинает тебя узнавать. Это отличный повод пообщаться побольше! Расскажи о себе 💬",
            f"🌱 Вы с {name} на пути к настоящей дружбе. Не останавливайтесь! Впереди столько всего интересного ✨",
            f"📖 {name} знает о тебе основы. Пригласи её на кофе или созвон — это сближает! 💕",
            f"🌸 Вы с {name} только начинаете дружить. Это самое волшебное время! Узнавайте друг друга 💫",
            f"🎯 {name} уже кое-что знает о тебе. Покажи ей свои любимые места и увлечения! ✨",
            f"🦋 {name} интересуется тобой! Расскажи о своих хобби и мечтах. Дружба только зарождается! 💖",
            f"💌 Напиши {name} длинное голосовое сообщение! Это растопит лёд и сблизит вас! 🎤",
            f"🌈 Устройте с {name} совместный шопинг! Ничто так не сближает как выбор нарядов! 👗"
        ]
    else:
        predictions = [
            f"🦋 {name} пока плохо тебя знает. Но это только начало! Каждая великая дружба начинается с первого шага ✨",
            f"🌱 {name} ещё предстоит узнать тебя получше. Поделись своими увлечениями и любимыми фильмами 🎬",
            f"💫 Ваша дружба с {name} только зарождается. Впереди много смеха, секретов и совместных фото! 📸",
            f"🌸 Вы с {name} только знакомитесь. Будь открытой и искренней — это лучший способ подружиться! 💕",
            f"🎵 {name} пока мало о тебе знает. Но это поправимо! Пригласи её погулять или на чай ☕",
            f"🦋 {name} — новый человек в твоей жизни. Дай ей шанс узнать тебя настоящую! Впереди много хорошего 💖",
            f"🌷 Расскажи {name} свою любимую песню и спроси про её! Музыка объединяет сердца! 🎵",
            f"🍰 Приготовь вместе с {name} что-нибудь вкусненькое! Совместная готовка сближает! 👩‍🍳"
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
    try: c.execute('ALTER TABLE users ADD COLUMN zodiac_sign TEXT')
    except: pass
    try: c.execute('ALTER TABLE users ADD COLUMN age INTEGER')
    except: pass
    try: c.execute('ALTER TABLE users ADD COLUMN pending_test INTEGER')
    except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        tests_created INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        premium_until TEXT DEFAULT NULL,
        zodiac_sign TEXT DEFAULT NULL,
        age INTEGER DEFAULT NULL,
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
    # Удаляем самый непопулярный тест, если больше 10
    c.execute('''SELECT t.id, COUNT(a.id) as attempts_count FROM tests t 
                 LEFT JOIN attempts a ON t.id = a.test_id 
                 WHERE t.creator_id = ? 
                 GROUP BY t.id 
                 ORDER BY attempts_count ASC, t.created_at ASC''', (creator_id,))
    all_tests = c.fetchall()
    for old_test in all_tests[10:]:
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
    c.execute('UPDATE users SET tests_created = tests_created - ? WHERE user_id = ?', (count, user_id))
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
        [KeyboardButton("🌸"), KeyboardButton("👑"), KeyboardButton("🏆"), KeyboardButton("⭐"), KeyboardButton("💎")],
                [KeyboardButton("❓ Помощь")],
        
    ]
    if user_id == ADMIN_ID:
        
        keyboard.append([KeyboardButton("🔧 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Статистика"), KeyboardButton("🖥 Сервер")],
        [KeyboardButton("🎁 Подарить премиум"), KeyboardButton("🛡 Антиспам")],
        [KeyboardButton("➕ Начислить тесты"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("🔄 Сбросить тесты"), KeyboardButton("🎬 Медиа")],
        [KeyboardButton("🔙 Назад")]
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

def get_test_actions_keyboard(test_id, user_id=None):
    if user_id and is_premium(user_id):
        answers_icon = "📊"
        stats_icon = "📈"
    else:
        answers_icon = "🔒"
        stats_icon = "🔒"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁 Посмотреть", callback_data=f"view_{test_id}"),
         InlineKeyboardButton("📤 Поделиться", callback_data=f"share_{test_id}")],
        [InlineKeyboardButton(f"{answers_icon} Ответы подруг", callback_data=f"answers_{test_id}"),
         InlineKeyboardButton(f"{stats_icon} Статистика", callback_data=f"stats_friendship_{test_id}")],
        [InlineKeyboardButton("🗑 Удалить тест", callback_data=f"delete_{test_id}")]
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
    logger.info(f"START: user={user.id}, args={context.args}")
    if not get_user(user.id): create_user(user.id, user.username, user.first_name)
    else:
        # Обновляем имя если изменилось
        conn = get_db(); c = conn.cursor()
        c.execute('UPDATE users SET first_name = ?, username = ? WHERE user_id = ?', 
                  (user.first_name, user.username, user.id))
        conn.commit()
    
    # Сохраняем test_id из deep-link
    test_id = None
    if context.args and len(context.args) > 0 and context.args[0].startswith("test_"):
        test_id = int(context.args[0].split("_")[1])
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE users SET pending_test = ? WHERE user_id = ?', (test_id, user.id))
        conn.commit()
        logger.info(f"СОХРАНЁН pending_test={test_id}")
    
    user_data = get_user(user.id)
    zodiac = user_data.get('zodiac_sign') if user_data else None
    if not zodiac:
        await ask_profile_name(update, context)
        return
    
    # Показываем тест если есть отложенный
    pending = user_data.get('pending_test')
    if pending:
        test = get_test_by_id(pending)
        if test:
            conn = get_db(); c = conn.cursor()
            c.execute('UPDATE users SET pending_test = NULL WHERE user_id = ?', (user.id,))
            conn.commit()
            
            creator = get_user(test['creator_id'])
            creator_display = test['creator_name']
            if creator and creator.get('username'):
                creator_display += f" @{creator['username']}"
            
            q_count = len(test['questions'])
            q_word = decline_word(q_count, "вопрос", "вопроса", "вопросов")
            
            greeting_text = ""
            if test.get('greeting_file_id'):
                if test.get('greeting_type') == 'voice':
                    greeting_text = "\n🎤 Подружка записала для тебя *голосовое поздравление*!"
                elif test.get('greeting_type') == 'video':
                    greeting_text = "\n🎥 Подружка сняла для тебя *видео-поздравление*!"
            
            text = (f"🌸✨ *ПРИВЕТ, {user.first_name}!* ✨🌸\n\n"
                    f"💕 {creator_display} приглашает тебя пройти тест!\n\n"
                    f"📝 *{test['title']}*\n"
                    f"💭 {q_count} {q_word} о ней\n"
                    f"{greeting_text}\n"
                    f"🎓 Именной *диплом* ждёт тебя!\n\n"
                    f"👇 Нажми на кнопку и начни! 💖")
            try: await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_{test['id']}")]]))
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

🙎‍♀️ *ПОЛЬЗОВАТЕЛИ*
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
        text += "\n🏆 *ТОП-3 СОЗДАТЕЛЕЙ ТЕСТОВ*\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, cr in enumerate(top_cr,1): 
            text += f"{medals[i-1]} {cr['first_name'] or 'Аноним'} — *{cr['cnt']}* {decline_word(cr['cnt'], 'тест', 'теста', 'тестов')}\n"
    if top_pl:
        text += "\n🎮 *ТОП-3 АКТИВНЫХ ПОДРУГ*\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, pl in enumerate(top_pl,1): 
            text += f"{medals[i-1]} {pl['friend_name']} — *{pl['cnt']}* {decline_word(pl['cnt'], 'раз', 'раза', 'раз')}\n"
    if peak_test or peak_att:
        text += "\n⏰ *ПИКОВАЯ АКТИВНОСТЬ*\n"
        if peak_test: text += f"📝 Создание тестов: *{peak_test['hour']}:00* ({peak_test['cnt']} шт.)\n"
        if peak_att: text += f"🎮 Прохождение тестов: *{peak_att['hour']}:00* ({peak_att['cnt']} шт.)\n"
    if conversion > 20: analysis = "🚀 Отличная конверсия! Бот растёт!"
    elif conversion > 10: analysis = "📈 Хорошая конверсия. Продолжай в том же духе!"
    elif conversion > 5: analysis = "📊 Есть потенциал для роста. Увеличь продвижение!"
    else: analysis = "🌱 Начальный этап. Требуется активное продвижение!"
    text += f"\n• • • • • • • • • • • • • • • •\n💡 *ВЫВОД:* {analysis}"
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
    # Определяем статус нагрузки
    if stats['cpu']['percent'] > 80: load_status = "🔴 Критическая нагрузка!"
    elif stats['cpu']['percent'] > 60: load_status = "🟡 Повышенная нагрузка"
    elif stats['cpu']['percent'] > 30: load_status = "🟢 Умеренная нагрузка"
    else: load_status = "✅ Низкая нагрузка"
    
    if stats['memory']['percent'] > 90: mem_status = "🔴"
    elif stats['memory']['percent'] > 70: mem_status = "🟡"
    else: mem_status = "🟢"
    
    text = f"""🖥✨ *МОНИТОРИНГ СЕРВЕРА* ✨🖥
• • • • • • • • • • • • • • • •

⏱ *Аптайм:* {stats['uptime']}

🖥 *СИСТЕМА*
┌ ОС: `{stats['system']}`
├ Python: `{stats['python']}`
└ Ядер CPU: *{stats['cpu']['cores']}*

📊 *НАГРУЗКА*
┌ CPU: {cpu_e} *{stats['cpu']['percent']:.1f}%*
├ RAM: {mem_e} *{stats['memory']['percent']:.1f}%*
│   └ Использовано: {stats['memory']['used_gb']} GB из {stats['memory']['total_gb']} GB
└ Диск: {disk_e} *{stats['disk']['percent']:.1f}%*
    └ Занято: {stats['disk']['used_gb']} GB из {stats['disk']['total_gb']} GB

🤖 *ПРОЦЕСС БОТА*
┌ RAM: *{stats['bot_process']['memory_mb']} MB*
├ CPU: *{stats['bot_process']['cpu_percent']:.1f}%*
└ Потоков: *{stats['bot_process']['threads']}*

• • • • • • • • • • • • • • • •
💡 *Статус:* {load_status}"""
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="server_refresh")], [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]])
    if query: await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else: await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def admin_antispam_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    
    # Собираем детальную статистику
    total_warnings = len(antispam._warnings)
    blocked_now = len(antispam._blocked_users)
    warned_users = len(antispam._warning_timestamps)
    
    # Топ пользователей с предупреждениями
    top_warned = sorted(antispam._warnings.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Статистика по типам действий
    action_stats = {}
    for uid, actions in antispam._actions.items():
        for action_type, timestamps in actions.items():
            if action_type not in action_stats:
                action_stats[action_type] = 0
            action_stats[action_type] += len(timestamps)
    
    text = f"""🛡️✨ *АНТИСПАМ СИСТЕМА* ✨🛡️
• • • • • • • • • • • • • • • •

📊 *ОБЩАЯ СТАТИСТИКА*
┌ 🔒 Заблокировано сейчас: *{blocked_now}*
├ ⚠️ Всего предупреждений: *{total_warnings}*
└ 👤 Пользователей с варнами: *{warned_users}*

⏱ *ЛИМИТЫ ДЕЙСТВИЙ*
┌ 💬 Сообщений: *{antispam.limits['message']['max']}*/мин
├ 📝 Создание тестов: *{antispam.limits['create_test']['max']}*/5мин
├ 🎮 Прохождение тестов: *{antispam.limits['take_test']['max']}*/мин
├ 🔘 Callback-кнопок: *{antispam.limits['callback']['max']}*/мин
└ 📤 Поделиться: *{antispam.limits['share']['max']}*/5мин

⚙️ *НАСТРОЙКИ БЛОКИРОВКИ*
┌ Предупреждений до бана: *{antispam.max_warnings}*
├ Длительность бана: *{antispam.block_duration}с* ({antispam.block_duration//60} мин)
└ Сброс предупреждений: *{antispam.warning_reset_time}с* ({antispam.warning_reset_time//60} мин)
"""
    
    if top_warned:
        text += "\n⚠️ *ТОП НАРУШИТЕЛЕЙ*\n"
        for i, (uid, count) in enumerate(top_warned, 1):
            text += f"{i}. ID {uid}: *{count}* предупреждений\n"
    
    if blocked_now == 0 and total_warnings == 0:
        text += "\n✅ *Статус:* Всё чисто! Нарушений нет."
    elif blocked_now > 0:
        text += f"\n🔴 *Статус:* Есть активные блокировки!"
    else:
        text += f"\n🟡 *Статус:* Есть предупреждения, блокировок нет."
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_anti_refresh"),
         InlineKeyboardButton("🔓 Разбанить всех", callback_data="admin_unblock_all")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ])
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def admin_media_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    stats = media_manager.get_media_stats()
    total_size_mb = round(stats['total_size_bytes']/(1024**2), 1)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(DISTINCT test_id) FROM media_tracking WHERE test_id IS NOT NULL AND is_valid = 1')
    tests_with_media = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM media_tracking WHERE test_id IS NULL AND is_valid = 1')
    orphan_media = c.fetchone()[0]
    conn.close()
    
    text = f"""🎬✨ *МЕДИА ХРАНИЛИЩЕ* ✨🎬
• • • • • • • • • • • • • • • •

📊 *ОБЩАЯ СТАТИСТИКА*
┌ Всего файлов: *{stats['total_media']}*
├ Активных: *{stats['active_media']}*
├ Общий размер: *{total_size_mb} MB*
└ Просмотров: *{stats['total_views']}*

📁 *ПО ТИПАМ*
"""
    icons = {'voice':'🎤', 'video':'🎥', 'photo':'📸'}
    names = {'voice':'Голосовые', 'video':'Видео', 'photo':'Фото'}
    for ft, ts in stats['by_type'].items():
        size_mb = round(ts['size_bytes']/(1024**2), 2)
        text += f"{icons.get(ft,'📁')} {names.get(ft,ft)}: *{ts['count']}* шт ({size_mb} MB) | 👁 {ts['views']}\n"
    
    text += f"""
🧹 *ОЧИСТКА*
┌ Медиа в тестах: *{tests_with_media}* тестов
└ Осиротевших файлов: *{orphan_media}*

⚙️ *АВТООЧИСТКА*
┌ Без просмотров: *30 дней*
├ После просмотра: *7 дней*
└ Макс. размер: *{media_manager.max_greeting_size_mb} MB*
"""
    
    if stats['total_media'] > 50:
        text += "\n⚠️ Рекомендуется очистка!"
    else:
        text += "\n✅ Всё в порядке."
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧹 Очистить мусор", callback_data="media_force_cleanup")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ])
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

# === РАССЫЛКИ ===
async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data.pop('admin_action', None); context.user_data['creating_broadcast'] = True
    recent = broadcast_manager.get_recent_broadcasts(5)
    
    text = "📢✨ *РАССЫЛКА СООБЩЕНИЙ* ✨📢\n• • • • • • • • • • • • • • • •\n\n"
    
    if recent:
        text += "📋 *ПОСЛЕДНИЕ РАССЫЛКИ*\n"
        for b in recent:
            status_icon = "✅" if b['status'] == 'completed' else "🔄" if b['status'] == 'sending' else "❌"
            sent_pct = round(b['sent_count']/max(b['total_users'],1)*100, 1)
            text += f"{status_icon} *#{b['id']}* — {b['sent_count']}/{b['total_users']} ({sent_pct}%)\n"
            text += f"   📅 {b['created_at'][:16]}\n\n"
    
    text += "📝 *Отправь сообщение для ВСЕХ пользователей:*\n"
    text += "• Можно отправить *текст*\n"
    text += "• Можно отправить *фото* 📸\n"
    text += "• Можно отправить *видео* 🎥\n"
    text += "• Можно отправить *GIF* 🎬\n"
    text += "• Можно добавить *подпись* к медиа\n\n"
    text += "❌ *Отмена* — выйти из режима рассылки"
    
    await update.message.reply_text(
        text, 
        parse_mode=ParseMode.MARKDOWN, 
        reply_markup=ReplyKeyboardMarkup([["❌ Отмена", "📊 Статистика рассылок"]], resize_keyboard=True)
    )

async def execute_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.user_data.get('creating_broadcast'): return
    msg = update.message
    md = {'type':'text','text':msg.text or '','file_id':None}
    
    if msg.photo: 
        md = {'type':'photo','text':msg.caption or '','file_id':msg.photo[-1].file_id}
    elif msg.video: 
        md = {'type':'video','text':msg.caption or '','file_id':msg.video.file_id}
    elif msg.animation: 
        md = {'type':'animation','text':msg.caption or '','file_id':msg.animation.file_id}
    elif msg.voice:
        md = {'type':'voice','text':msg.caption or '','file_id':msg.voice.file_id}
    elif msg.video_note:
        md = {'type':'video_note','text':'','file_id':msg.video_note.file_id}
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
    broadcast_manager.update_broadcast_stats(bid)
    broadcast_manager.complete_broadcast(bid)
    fs = broadcast_manager.get_broadcast_stats(bid)
    await st.edit_text(f"✅ *РАССЫЛКА #{bid} ЗАВЕРШЕНА!*\n\n├ Всего: *{total}*\n├ Отправлено: *{stats['sent']}* ({stats['sent']/max(total,1)*100:.1f}%)\n├ Доставлено: *{fs.get('delivered_count',0)}* ({fs.get('delivery_rate',0)}%)\n├ Прочитано: *{fs.get('read_count',0)}* ({fs.get('read_rate',0)}%)\n├ Заблокировали: *{stats['blocked']}*\n└ Ошибки: *{stats['failed']}*", parse_mode=ParseMode.MARKDOWN)
    del context.user_data['creating_broadcast']; await update.message.reply_text("🔧 *Админ-панель:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

async def broadcast_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    broadcasts = broadcast_manager.get_recent_broadcasts(10)
    if not broadcasts: 
        await update.message.reply_text("📊✨ *СТАТИСТИКА РАССЫЛОК* ✨📊\n\n📭 *Нет истории рассылок*", parse_mode=ParseMode.MARKDOWN)
        return
    
    text = "📊✨ *СТАТИСТИКА РАССЫЛОК* ✨📊\n• • • • • • • • • • • • • • • •\n\n"
    
    total_sent = sum(b['sent_count'] for b in broadcasts)
    total_blocked = sum(b['blocked_count'] for b in broadcasts)
    total_failed = sum(b['failed_count'] for b in broadcasts)
    
    text += f"📋 *СВОДКА ПО {len(broadcasts)} РАССЫЛКАМ*\n"
    text += f"┌ Отправлено: *{total_sent}*\n"
    text += f"├ Заблокировано: *{total_blocked}*\n"
    text += f"└ Ошибок: *{total_failed}*\n\n"
    
    text += "📝 *ДЕТАЛИЗАЦИЯ:*\n\n"
    for b in broadcasts[:5]:
        t = b['total_users'] or 1
        status_icon = '✅' if b['status']=='completed' else '🔄'
        sent_pct = round(b['sent_count']/t*100, 1)
        del_pct = round(b['delivered_count']/max(t,1)*100, 1)
        
        text += f"{status_icon} *#{b['id']}* — {b['created_at'][:16]}\n"
        text += f"   📤 Отправлено: *{b['sent_count']}/{t}* ({sent_pct}%)\n"
        text += f"   📬 Доставлено: *{b['delivered_count']}* ({del_pct}%)\n"
        text += f"   👁 Прочитано: *{b['read_count']}*\n"
        text += f"   🚫 Блок: *{b['blocked_count']}* | ❌ Ошибки: *{b['failed_count']}*\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def admin_reset_tests_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data['admin_action'] = 'reset_tests'
    await update.message.reply_text(
        "🔄✨ *СБРОС ТЕСТОВ* ✨🔄\n\n"
        "Введи username или ID пользователя чтобы сбросить его тесты:\n"
        "Например: `@anna` или `710623393`\n\n"
        "⚠️ *Внимание:* Все созданные тесты пользователя будут удалены, а счётчик тестов обнулён!\n\n"
        "❌ *Отмена* — выйти",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

# === АДМИН ДЕЙСТВИЯ ===
async def admin_reset_tests_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data['admin_action'] = 'reset_tests'
    await update.message.reply_text(
        "🔄✨ *СБРОС ТЕСТОВ* ✨🔄\n\n"
        "Введи username или ID пользователя чтобы сбросить его тесты:\n"
        "Например: `@anna` или `710623393`\n\n"
        "⚠️ *Внимание:* Все созданные тесты пользователя будут удалены, а счётчик тестов обнулён!\n\n"
        "❌ *Отмена* — выйти",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )
async def admin_give_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data['admin_action'] = 'give_premium'
    await update.message.reply_text("🎁 *ПОДАРИТЬ ПРЕМИУМ*\n\nВыбери срок:", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("1 день", callback_data="give_premium_1"), InlineKeyboardButton("5 дней", callback_data="give_premium_5")], [InlineKeyboardButton("15 дней", callback_data="give_premium_15"), InlineKeyboardButton("30 дней", callback_data="give_premium_30")]]))

async def admin_add_tests_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    context.user_data['admin_action'] = 'add_tests'
    
    text = """➕✨ *НАЧИСЛЕНИЕ ТЕСТОВ* ✨➕
• • • • • • • • • • • • • • • •

🎯 *Выбери способ начисления:*

1️⃣ *Одному пользователю*
   Введи: `@username 5` или `ID 5`

2️⃣ *Всем пользователям*
   Введи: `all 3`

3️⃣ *Активным за 7 дней*
   Введи: `active7 5`

4️⃣ *Премиум-пользователям*
   Введи: `premium 10`

5️⃣ *Новичкам (до 7 дней)*
   Введи: `new 3`

6️⃣ *По дате регистрации*
   Введи: `date 2026-05-01 5`

💡 *Примеры:*
• `@anna 5` — начислит 5 тестов @anna
• `all 3` — всем по 3 теста
• `active7 5` — активным за неделю по 5
• `new 10` — новичкам по 10 тестов

❌ *Отмена* — выйти"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

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
        if len(parts) < 2: 
            await update.message.reply_text("❌ Укажи группу и количество!", reply_markup=get_admin_keyboard())
            return
        group = parts[0].lower()
        try: count = int(parts[-1])
        except: await update.message.reply_text("❌ Укажи число в конце!"); return
        
        conn = get_db(); c = conn.cursor()
        tw = decline_word(count, "тест", "теста", "тестов")
        
        if group == 'all':
            c.execute('SELECT user_id FROM users')
            users = c.fetchall()
            for u in users: add_tests_to_user(u['user_id'], count)
            conn.close()
            await update.message.reply_text(f"✅ *Всем* начислено по *{count}* {tw}!\n👥 *{len(users)}* чел.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        elif group == 'premium':
            c.execute("SELECT user_id FROM users WHERE premium_until > datetime('now')")
            users = c.fetchall()
            for u in users: add_tests_to_user(u['user_id'], count)
            conn.close()
            await update.message.reply_text(f"✅ *Премиум* начислено по *{count}* {tw}!\n👥 *{len(users)}* чел.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        elif group == 'active7':
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            c.execute("SELECT DISTINCT user_id FROM users WHERE created_at >= ? OR user_id IN (SELECT creator_id FROM tests WHERE created_at >= ?) OR user_id IN (SELECT friend_id FROM attempts WHERE completed_at >= ?)", (week_ago, week_ago, week_ago))
            users = c.fetchall()
            for u in users: add_tests_to_user(u['user_id'], count)
            conn.close()
            await update.message.reply_text(f"✅ *Активным 7д* начислено по *{count}* {tw}!\n👥 *{len(users)}* чел.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        elif group == 'new':
            week_ago = (datetime.now() - timedelta(days=7)).isoformat()
            c.execute("SELECT user_id FROM users WHERE created_at >= ?", (week_ago,))
            users = c.fetchall()
            for u in users: add_tests_to_user(u['user_id'], count)
            conn.close()
            await update.message.reply_text(f"✅ *Новичкам* начислено по *{count}* {tw}!\n👥 *{len(users)}* чел.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        else:
            target = parts[0].lstrip('@')
            c.execute('SELECT user_id, first_name FROM users WHERE user_id=?' if target.isdigit() else 'SELECT user_id, first_name FROM users WHERE username=?', (int(target) if target.isdigit() else target,))
            row = c.fetchone()
            if not row: conn.close(); await update.message.reply_text(f"❌ {target} не найден", reply_markup=get_admin_keyboard()); del context.user_data['admin_action']; return
            add_tests_to_user(row['user_id'], count)
            conn.close()
            await update.message.reply_text(f"✅ *{row['first_name'] or target}* +{count} {tw}!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
            try:
                await context.bot.send_message(
                    chat_id=row['user_id'],
                    text=f"🎁✨ *ПОДАРОК ДЛЯ ТЕБЯ!* ✨🎁\n\n"
                         f"💕 Администратор начислил тебе *{count}* {tw}!\n\n"
                         f"🌸 Создавай новые тесты о себе и отправляй подружкам!\n"
                         f"👯‍♀️ Узнайте кто знает тебя лучше всех!\n\n"
                         f"💖 *Твори и делись!*",
                    parse_mode=ParseMode.MARKDOWN
                )
            except: pass
        del context.user_data['admin_action']

    elif action == 'reset_tests':
        target = text.lstrip('@')
        conn = get_db(); c = conn.cursor()
        c.execute('SELECT user_id, first_name FROM users WHERE user_id=?' if target.isdigit() else 'SELECT user_id, first_name FROM users WHERE username=?', 
                 (int(target) if target.isdigit() else target,))
        row = c.fetchone()
        if not row: 
            conn.close()
            await update.message.reply_text(f"❌ {target} не найден", reply_markup=get_admin_keyboard())
            del context.user_data['admin_action']
            return
        
        user_id = row['user_id']; user_name = row['first_name'] or target
        
        # Удаляем все тесты пользователя
        c.execute('DELETE FROM tests WHERE creator_id = ?', (user_id,))
        deleted_tests = c.rowcount
        c.execute('DELETE FROM attempts WHERE test_id IN (SELECT id FROM tests WHERE creator_id = ?)', (user_id,))
        
        # Сбрасываем счётчик
        c.execute('UPDATE users SET tests_created = ? WHERE user_id = ?', (FREE_TESTS_LIMIT, user_id))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"🔄✨ *ТЕСТЫ СБРОШЕНЫ!* ✨🔄\n\n"
            f"👤 *{user_name}*\n"
            f"🗑 Удалено тестов: *{deleted_tests}*\n"
            f"📊 Доступно тестов: *0* (все использованы)",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
        del context.user_data['admin_action']

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
    await update.message.reply_text(f"🌸✨ *СОЗДАЁМ ТЕСТ* ✨🌸\n\n💕 Давай создадим что-то особенное!\n\n{ti}\n• • • ✨ • • •\n\n📝 Придумай красивое название:\nНапример: «Насколько хорошо ты меня знаешь?»\nИли: «Кто настоящая подруга?»\n\n❌ Отмена — чтобы выйти", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def handle_create_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data or data.get('waiting_comment'): return
    text = update.message.text.strip(); step = data.get('step')
    if step == 'title':
        if len(text)<3: await update.message.reply_text("⚠️ Длиннее 3 символов!"); return
        data['title'] = text; data['step'] = 'group'
        await update.message.reply_text(
        "✨ *Выбери тему:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_question_groups_keyboard()
    )
        await update.message.reply_text("_Нажми Отмена чтобы выйти_", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())
    elif step == 'questions_count':
        try:
            count = int(text)
            if count<2 or count>MAX_QUESTIONS: await update.message.reply_text(f"⚠️ От 2 до {MAX_QUESTIONS}!"); return
            data['total_q'] = count; data['current_q'] = 0; data['questions_data'] = []; data['comments'] = {}; data['photos'] = {}
            await update.message.reply_text("🎬 *ДОБАВЬ ПОЗДРАВЛЕНИЕ!* ✨\n\nПодружка получит его после прохождения! 💕", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎤 Голосовое", callback_data="greeting_voice"), InlineKeyboardButton("🎥 Видео", callback_data="greeting_video")], [InlineKeyboardButton("⏭️ Пропустить", callback_data="greeting_skip")]]))
            
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
            f"✅ *ДА! ЭТО ПРАВДА!* ✅\n\n✨ Ты ответила: *{ua}*\n\n💖 _Ты настоящая soulmate! Мы на одной волне!_"
        ]
        result_text = random.choice(correct_messages)
    else:
        wrong_messages = [
            f"❌ *ОЙ! НЕ УГАДАЛА* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *А правильно:* {ca}\n\n🌱 _Ничего! Ты узнаёшь меня всё лучше с каждым днём!_",
            f"❌ *МИМО!* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *На самом деле:* {ca}\n\n💪 _В следующий раз точно получится! Я в тебя верю!_",
            f"❌ *НЕ СОВСЕМ ТАК* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *Правильный ответ:* {ca}\n\n🌸 _Теперь ты знаешь обо мне чуть больше!_",
            f"❌ *ПОЧТИ!* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *А я бы ответила:* {ca}\n\n🎯 _Ещё немного и ты станешь экспертом по мне!_",
            f"❌ *НЕ УГАДАЛА* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *Правильно:* {ca}\n\n💭 _Это повод пообщаться подольше и узнать друг друга лучше!_",
            f"❌ *НЕТ, НО БЛИЗКО!* ❌\n\n💭 Ты ответила: *{ua}*\n✅ *Верный ответ:* {ca}\n\n👑 _С каждым вопросом ты становишься ближе ко мне!_"
        ]
        result_text = random.choice(wrong_messages)
    
    if comment:
        result_text += f"\n\n💬 *Пояснение:*\n_{comment}_"
    
    await query.message.reply_text(result_text, parse_mode=ParseMode.MARKDOWN)
    data['current'] += 1
    
    if data['current'] < len(test['questions']):
        # Пауза перед следующим вопросом
        await asyncio.sleep(4)
        await query.message.reply_text("✨ _Загружаем следующий вопрос..._ 💫", parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(1.5)
        await send_question(query, context)
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
    # Задержка перед результатом
    loading = await query.message.reply_text("🌸 _Подсчитываем результат..._ ✨", parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(4)
    await loading.delete()
    
    # Формируем красивый текст результата
    hearts = "💖" * int(score/10) + "🤍" * (10 - int(score/10))
    
    creator_display = test['creator_name']
    creator = get_user(test['creator_id'])
    if creator and creator.get('username'):
        creator_display += f" (@{creator['username']})"
    
    friend_result = f"🎉✨ *ТЕСТ ПРОЙДЕН!* ✨🎉\n\n"
    friend_result += f"💕 *{user.first_name}*, ты супер!\n"
    friend_result += f"{hearts} *{score:.0f}%*\n\n"
    friend_result += f"🏆 *{status}*\n"
    friend_result += f"💬 _{prediction[:150]}_\n\n"
    
    # Добавляем информацию о поздравлении в начало
    if test.get('greeting_file_id'):
        if test.get('greeting_type') == 'voice':
            friend_result = f"🎤 *{creator_display}* записала тебе голосовое поздравление!\n\n" + friend_result
        elif test.get('greeting_type') == 'video':
            friend_result = f"🎥 *{creator_display}* сняла тебе видео-поздравление!\n\n" + friend_result
    
    # Кнопка диплома
    diploma_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎓 Получить диплом", callback_data=f"get_diploma_{test['id']}_{score:.0f}")]
    ])
    
    # Отправляем всё в одном сообщении
    if test.get('greeting_file_id'):
        try:
            if test.get('greeting_type')=='voice': 
                await query.message.reply_voice(test['greeting_file_id'], caption=friend_result, parse_mode=ParseMode.MARKDOWN, reply_markup=diploma_kb)
            elif test.get('greeting_type')=='video': 
                await query.message.reply_video(test['greeting_file_id'], caption=friend_result, parse_mode=ParseMode.MARKDOWN, reply_markup=diploma_kb)
            media_manager.mark_as_viewed(test['greeting_file_id'], user.id, test['id'])
        except:
            await query.message.reply_text(friend_result, parse_mode=ParseMode.MARKDOWN, reply_markup=diploma_kb)
    else:
        await query.message.reply_text(friend_result, parse_mode=ParseMode.MARKDOWN, reply_markup=diploma_kb)
    
    await query.message.reply_text("✨ *Выбирай действие:* ✨", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user.id))
    
    # Сохраняем данные для диплома
    context.user_data['diploma_data'] = {
        'user_name': user.first_name,
        'creator_name': test['creator_name'],
        'test_title': test['title'],
        'score': score,
        'status': status,
        'prediction': prediction,
        'categories_stats': categories_stats
    }
    
    del context.user_data['taking_test']

async def show_all_tests(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    user_id = query.from_user.id
    tests = get_user_tests(user_id)
    if not tests:
        await query.message.reply_text("👑✨ *МОИ ТЕСТЫ* ✨👑\n\n🌸 *У тебя пока нет тестов!*", parse_mode=ParseMode.MARKDOWN)
        return
    
    total_att = sum(t['attempts'] for t in tests)
    proh_word = decline_word(total_att, "прохождение", "прохождения", "прохождений")
    text = f"👑✨ *МОИ ТЕСТЫ* ✨👑\n\n💕 *ВСЕ ТЕСТЫ* 💕\n• • • ✨ • • •\n\n🌸 Твои тесты ждут подруг! Чем больше пройдут — тем выше в ТОПе!\n\n"
    
    kb = []
    for t in tests:
        w = decline_friend_word(t['attempts'])
        if t['attempts']>=10: st, em = "🔥 СУПЕР-ПОПУЛЯРНЫЙ!", "🔥"
        elif t['attempts']>=5: st, em = "⭐ ПОПУЛЯРНЫЙ!", "⭐"
        elif t['attempts']>=2: st, em = "🌸 НАБИРАЕТ ПОПУЛЯРНОСТЬ", "🌸"
        else: st, em = "⏳ ЖДЁТ ПОДРУГ...", "⏳"
        text += f"{em} *{t['title'][:30]}*\n   🙎‍♀️ {t['attempts']} {w} • {st} • {t['created_at'][:10]}\n\n"
        kb.append([InlineKeyboardButton(f"💕 {t['title'][:25]} ({t['attempts']} 🙎‍♀️)", callback_data=f"mytest_{t['id']}")])
    
    kb.append([InlineKeyboardButton("🔙 Назад к ТОП-3", callback_data="back_to_my_tests")])
    text += "💕 *Выбери тест:*"
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

# Добавляем обработчик "назад к ТОП-3"
async def back_to_my_tests(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    user_id = query.from_user.id
    tests = get_user_tests(user_id)
    if not tests:
        await query.message.edit_text("👑✨ *МОИ ТЕСТЫ* ✨👑\n\n🌸 *У тебя пока нет тестов!*", parse_mode=ParseMode.MARKDOWN)
        return
    
    total_att = sum(t['attempts'] for t in tests)
    proh_word = decline_word(total_att, "прохождение", "прохождения", "прохождений")
    text = f"👑✨ *МОИ ТЕСТЫ* ✨👑\n\n💎 *Статус:* {'Премиум' if is_premium(user_id) else 'Начинающая'}\n\n📦 *{len(tests)}* {decline_word(len(tests),'тест','теста','тестов')} • 🎯 *{total_att}* {proh_word}\n• • • ✨ • • •\n\n"
    sorted_tests = sorted(tests, key=lambda x: x['attempts'], reverse=True)
    top3 = sorted_tests[:3]
    rest = sorted_tests[3:]
    
    if len(tests) >= 3:
        text += f"🔥 *ТОП-3 ТЕСТА*\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, t in enumerate(top3):
            w = decline_friend_word(t['attempts'])
            if t['attempts']>=10: st, icon = "🔥 СУПЕР-ПОПУЛЯРНЫЙ!", "🔥"
            elif t['attempts']>=5: st, icon = "⭐ ПОПУЛЯРНЫЙ!", "⭐"
            elif t['attempts']>=2: st, icon = "🌸 НАБИРАЕТ ПОПУЛЯРНОСТЬ", "🌸"
            else: st, icon = "⏳ ЖДЁТ ПОДРУГ...", "⏳"
            hearts = "💖" * min(t['attempts'], 5) + "🤍" * (5 - min(t['attempts'], 5))
            text += f"{medals[i]} *{t['title'][:30]}*\n"
            text += f"   ▌{st}\n"
            text += f"   ▌🙎‍♀️ {t['attempts']} {w} • 📅 {t['created_at'][:10]}\n"
            text += f"   ▌{hearts}\n\n"
        if rest:
            text += f"📋 *Остальные тесты ({len(tests)})*\n   👀 Смотри все тесты и узнай кто что знает...\n\n"
    else:
        for t in tests:
            w = decline_friend_word(t['attempts'])
            if t['attempts']>=10: st = "🔥 СУПЕР-ПОПУЛЯРНЫЙ!"
            elif t['attempts']>=5: st = "⭐ ПОПУЛЯРНЫЙ!"
            elif t['attempts']>=2: st = "🌸 НАБИРАЕТ ПОПУЛЯРНОСТЬ"
            else: st = "⏳ ЖДЁТ ПОДРУГ..."
            text += f"🌸 *{t['title'][:30]}*\n   🙎‍♀️ {t['attempts']} {w} • {st} • {t['created_at'][:10]}\n\n"
    
    text += "💕 *Выбери тест:*"
    kb = []
    if len(tests) >= 3:
        medals = ["🥇", "🥈", "🥉"]
        for i, t in enumerate(top3):
            kb.append([InlineKeyboardButton(f"{medals[i]} {t['title'][:25]} | {t['attempts']} 🙎‍♀️", callback_data=f"mytest_{t['id']}")])
        if rest:
            kb.append([InlineKeyboardButton(f"📋 Показать все тесты ({len(tests)})", callback_data="show_all_tests")])
    else:
        for t in tests:
            kb.append([InlineKeyboardButton(f"🙎‍♀️ {t['title'][:25]} | {t['attempts']} 🙎‍♀️", callback_data=f"mytest_{t['id']}")])
    kb.append([InlineKeyboardButton("🏆 МОИ БЕЙДЖИ", callback_data="my_badges")])
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

async def my_badges_handler(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    user_id = query.from_user.id
    tests = get_user_tests(user_id)
    total_att = sum(t['attempts'] for t in tests)
    is_prem = is_premium(user_id)
    
    # Считаем бейджи
    badges = []
    all_badges = {
        "💎 Премиум": "Оформи премиум-подписку",
        "🌟 Плодовитая": "Создай 10 тестов",
        "✨ Творческая": "Создай 5 тестов",
        "🔥 Популярная": "20 прохождений твоих тестов",
        "💕 Любимица": "10 прохождений твоих тестов",
        "👑 Идеальная подруга": "Кто-то прошёл тест на 90%+",
        "💖 Близкая подруга": "Кто-то прошёл тест на 70%+",
        "🌸 Новичок": "Создай свой первый тест",
        "🎯 Знаток подруг": "Пройди 5 тестов подруг",
        "🌈 Душа компании": "Твои тесты прошли 5 разных подруг"
    }
    
    if is_prem: badges.append(("💎 Премиум", all_badges["💎 Премиум"]))
    if len(tests) >= 10: badges.append(("🌟 Плодовитая", all_badges["🌟 Плодовитая"]))
    elif len(tests) >= 5: badges.append(("✨ Творческая", all_badges["✨ Творческая"]))
    if total_att >= 20: badges.append(("🔥 Популярная", all_badges["🔥 Популярная"]))
    elif total_att >= 10: badges.append(("💕 Любимица", all_badges["💕 Любимица"]))
    
    max_score = 0
    unique_friends = set()
    tests_passed = 0
    for t in tests:
        attempts = get_test_attempts(t['id'])
        for a in attempts:
            if a['score'] > max_score: max_score = a['score']
            unique_friends.add(a['friend_name'])
        tests_passed += len(attempts)
    
    if max_score >= 90: badges.append(("👑 Идеальная подруга", all_badges["👑 Идеальная подруга"]))
    elif max_score >= 70: badges.append(("💖 Близкая подруга", all_badges["💖 Близкая подруга"]))
    if tests_passed >= 5: badges.append(("🎯 Знаток подруг", all_badges["🎯 Знаток подруг"]))
    if len(unique_friends) >= 5: badges.append(("🌈 Душа компании", all_badges["🌈 Душа компании"]))
    if not badges: badges.append(("🌸 Новичок", all_badges["🌸 Новичок"]))
    
    text = f"🏆✨ *МОИ БЕЙДЖИ* ✨🏆\n\n"
    text += f"👤 *Статус:* {'💎 Премиум' if is_prem else '🌸 Начинающая'}\n"
    text += f"📦 Тестов: *{len(tests)}*\n"
    text += f"🎯 Прохождений: *{total_att}*\n"
    text += f"👑 Лучший результат: *{max_score:.0f}%*\n\n"
    text += "✨ *ТВОИ БЕЙДЖИ:* ✨\n\n"
    
    for b in badges:
        if b[0] in [x[0] for x in badges[:len(badges)]]:
            text += f"✅ {b[0]}\n   💬 {b[1]}\n\n"
    
    text += "💕 *Создавай тесты и получай новые бейджи!*"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Подробно о бейджах", callback_data="badges_info")],
        [InlineKeyboardButton("🔙 Назад к тестам", callback_data="back_to_my_tests")]
    ])
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)



async def my_tests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id; tests = get_user_tests(user_id)
    if not tests:
        await update.message.reply_text("👑✨ *МОИ ТЕСТЫ* ✨👑\n\n🌸 *У тебя пока нет тестов!*\n\n💕 Создай первый тест и отправь подружкам!", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup([["🌸 Создать тест"]], resize_keyboard=True))
        return
    total_att = sum(t['attempts'] for t in tests)
    proh_word = decline_word(total_att, "прохождение", "прохождения", "прохождений")
    text = f"👑✨ *МОИ ТЕСТЫ* ✨👑\n\n💎 *Статус:* {'Премиум' if is_premium(user_id) else 'Начинающая'}\n\n📦 *{len(tests)}* {decline_word(len(tests),'тест','теста','тестов')} • 🎯 *{total_att}* {proh_word}\n• • • ✨ • • •\n\n"
    sorted_tests = sorted(tests, key=lambda x: x['attempts'], reverse=True)
    top3 = sorted_tests[:3]
    rest = sorted_tests[3:]
    
    if len(tests) >= 3:
        text += f"🔥 *ТОП-3 ТЕСТА*\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, t in enumerate(top3):
            w = decline_friend_word(t['attempts'])
            if t['attempts']>=10: st, icon = "🔥 СУПЕР-ПОПУЛЯРНЫЙ!", "🔥"
            elif t['attempts']>=5: st, icon = "⭐ ПОПУЛЯРНЫЙ!", "⭐"
            elif t['attempts']>=2: st, icon = "🌸 НАБИРАЕТ ПОПУЛЯРНОСТЬ", "🌸"
            else: st, icon = "⏳ ЖДЁТ ПОДРУГ...", "⏳"
            hearts = "💖" * min(t['attempts'], 5) + "🤍" * (5 - min(t['attempts'], 5))
            text += f"{medals[i]} *{t['title'][:30]}*\n"
            text += f"   ▌{st}\n"
            text += f"   ▌🙎‍♀️ {t['attempts']} {w} • 📅 {t['created_at'][:10]}\n"
            text += f"   ▌{hearts}\n\n"
        if rest:
            text += f"📋 *Остальные тесты ({len(tests)})*\n   👀 Смотри все тесты и узнай кто что знает...\n\n"
    else:
        text += "📋 *ТВОИ ТЕСТЫ:*\n\n"
        for t in tests:
            w = decline_friend_word(t['attempts'])
            if t['attempts']>=10: st, icon, bg = "🔥 СУПЕР-ПОПУЛЯРНЫЙ!", "🔥", "bg_gold"
            elif t['attempts']>=5: st, icon, bg = "⭐ ПОПУЛЯРНЫЙ!", "⭐", "bg_pink"
            elif t['attempts']>=2: st, icon, bg = "🌸 НАБИРАЕТ ПОПУЛЯРНОСТЬ", "🌸", "bg_lavender"
            else: st, icon, bg = "⏳ ЖДЁТ ПОДРУГ...", "⏳", "bg_gray"
            
            hearts = "💖" * min(t['attempts'], 5) + "🤍" * (5 - min(t['attempts'], 5))
            
            text += f"┌─────────────────────┐\n"
            text += f"│  ✨ *{t['title'][:25]}*\n"
            text += f"│  {icon} _{st}_\n"
            text += f"│  🙎‍♀️ {t['attempts']} {w}\n"
            text += f"│  📅 {t['created_at'][:10]}\n"
            text += f"│  {hearts}\n"
            text += f"└─────────────────────┘\n\n"
    
    text += "💕 *Выбери тест:*"
    kb = []
    if len(tests) >= 3:
        for i, t in enumerate(top3):
            kb.append([InlineKeyboardButton(f"{medals[i]} {t['title'][:25]} | {t['attempts']} 🙎‍♀️", callback_data=f"mytest_{t['id']}")])
        if rest:
            kb.append([InlineKeyboardButton(f"📋 Показать все тесты ({len(tests)})", callback_data="show_all_tests")])
    else:
        for t in tests:
            kb.append([InlineKeyboardButton(f"🙎‍♀️ {t['title'][:25]} | {t['attempts']} 🙎‍♀️", callback_data=f"mytest_{t['id']}")])
    kb.append([InlineKeyboardButton("🏆 МОИ БЕЙДЖИ", callback_data="my_badges")])
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

async def my_test_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: await query.answer()
    except: pass
    tid = int(query.data.replace("mytest_","")); test = get_test_by_id(tid)
    if not test: await query.message.reply_text("💔 Тест не найден", parse_mode=ParseMode.MARKDOWN); return
    attempts = get_test_attempts(tid); avg = sum(a['score'] for a in attempts)/len(attempts) if attempts else 0; mx = max(a['score'] for a in attempts) if attempts else 0
    if len(attempts) >= 10: status = "🔥 СУПЕР-ПОПУЛЯРНЫЙ!"
    elif len(attempts) >= 5: status = "⭐ ПОПУЛЯРНЫЙ!"
    elif len(attempts) >= 2: status = "🌸 НАБИРАЕТ ПОПУЛЯРНОСТЬ"
    else: status = "⏳ ЖДЁТ ПОДРУГ..."
    pw = "прошла" if len(attempts)==1 else "прошли"
    text = f"💕 *{test['title']}* 💕\n\n{'✨' if len(attempts)==0 else '🌸'} {status}\n• • • ✨ • • •\n🙎‍♀️ *{len(attempts)}* {decline_friend_word(len(attempts))} {pw} тест\n🎯 Средний результат: *{avg:.0f}%*\n"
    if attempts: text += f"👑 Лучший результат: *{mx:.0f}%*\n"
    text += f"💭 Вопросов: *{len(test['questions'])}*\n"
    if test.get('greeting_file_id'): text += "🎬 Видео-поздравление: *есть* ✨\n"
    if test.get('question_photos') and test['question_photos']!='{}': text += f"📸 Фото: *{len(json.loads(test['question_photos']))}*\n"
    text += "\n• • • ✨ • • •\n💕 *Что хочешь сделать с тестом?* ✨"
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_test_actions_keyboard(tid, query.from_user.id))


async def badges_info_handler(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    text = f"📖✨ *ВСЕ БЕЙДЖИ* ✨📖\n\n"
    text += "🌸 *Как получать бейджи:*\n\n"
    text += "💎 *Премиум* — оформи премиум-подписку\n"
    text += "🌟 *Плодовитая* — создай 10 тестов\n"
    text += "✨ *Творческая* — создай 5 тестов\n"
    text += "🔥 *Популярная* — 20 прохождений твоих тестов\n"
    text += "💕 *Любимица* — 10 прохождений твоих тестов\n"
    text += "👑 *Идеальная подруга* — кто-то прошёл тест на 90%+\n"
    text += "💖 *Близкая подруга* — кто-то прошёл тест на 70%+\n"
    text += "🌸 *Новичок* — создай свой первый тест\n"
    text += "🎯 *Знаток подруг* — пройди 5 тестов подруг\n"
    text += "🌈 *Душа компании* — твои тесты прошли 5 разных подруг\n\n"
    text += "💕 *Создавай тесты, делись с подругами и собирай все бейджи!* ✨"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад к бейджам", callback_data="my_badges")]
    ])
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

# === ПРЕМИУМ ===
async def premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Определяем откуда пришёл запрос
    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
        msg = query.message
        try: await query.answer()
        except: pass
    elif hasattr(update, 'message') and update.message:
        user_id = update.effective_user.id
        msg = update.message
    else:
        user_id = update.effective_user.id
        msg = update.message
    
    if is_premium(user_id):
        user = get_user(user_id)
        expiry = datetime.fromisoformat(user['premium_until']).strftime('%d.%m.%Y')
        text = f"💎✨ *У ТЕБЯ ПРЕМИУМ!* ✨💎\n\n♾️ Безлимитные тесты\n🎓 Золотой диплом\n📊 Ответы подруг\n\n📅 *Действует до:* {expiry}\n\n💕 *Создавай тесты и проверяй подруг!*"
        if hasattr(update, 'callback_query') and update.callback_query:
            await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user_id))
        else:
            await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user_id))
    else:
        text = "💎 *ПРЕМИУМ ПОДПИСКА*\n\n✨ *Что даёт:*\n♾️ Безлимитные тесты\n🎓 Золотой диплом\n📊 Ответы подруг\n\n💰 *Стоимость:*\n• 99₽ — 15 дней\n• 149₽ — месяц\n\n👇 *Выбери тариф:*"
        if hasattr(update, 'callback_query') and update.callback_query:
            await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_premium_keyboard())
        else:
            await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_premium_keyboard())

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
        
        # Создаём платёж с обработкой ошибок
        
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
    # Проверка заполнения профиля
    if 'profile_setup' in context.user_data:
        if await handle_profile_setup(update, context):
            return
    
    # Всегда обрабатываем Отмену
    if text=="❌ Отмена":
        for key in ['creating_test', 'taking_test', 'waiting_for_option', 'waiting_comment', 'waiting_custom_question', 'waiting_photo', 'waiting_greeting']:
            if key in context.user_data:
                del context.user_data[key]
        if 'creating_test' in context.user_data:
            del context.user_data['creating_test']
        await update.message.reply_text("❌ Отменено", reply_markup=get_main_keyboard(user_id))
        return
    
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
    
    if text.startswith("🌸"): await create_test_start(update, context)
    elif text.startswith("👑"): await my_tests_handler(update, context)
    elif text.startswith("💎"): await premium_handler(update, context)
    elif text.startswith("❓"): await help_handler(update, context)
    elif text.startswith("🔧") and user_id==ADMIN_ID: await admin_panel(update, context)
    elif text=="📊 Статистика" and user_id==ADMIN_ID: await admin_stats(update, context)
    elif text=="🖥 Сервер" and user_id==ADMIN_ID: await admin_server_stats_compact(update, context)
    elif text=="🛡 Антиспам" and user_id==ADMIN_ID: await admin_antispam_stats(update, context)
    elif text=="🎬 Медиа" and user_id==ADMIN_ID: await admin_media_stats(update, context)
    elif text=="🎁 Подарить премиум" and user_id==ADMIN_ID: await admin_give_premium_start(update, context)
    elif text=="➕ Начислить тесты" and user_id==ADMIN_ID: await admin_add_tests_start(update, context)
    elif text=="📢 Рассылка" and user_id==ADMIN_ID: await admin_broadcast_start(update, context)
    elif text=="🔄 Сбросить тесты" and user_id==ADMIN_ID: await admin_reset_tests_start(update, context)
    elif text.startswith("🏆"): await show_friends_rating(update, context)
    elif text.startswith("⭐"): await show_zodiac_menu(update, context)
    elif text=="❌ Отмена":
        # Сбрасываем все состояния связанные с созданием теста
        if 'creating_test' in context.user_data: 
            del context.user_data['creating_test']
        if 'taking_test' in context.user_data:
            del context.user_data['taking_test']
        # Всегда работаем
        if user_id==ADMIN_ID and context.user_data.get('admin_action'): 
            del context.user_data['admin_action']; await admin_panel(update, context)
        else: 
            await update.message.reply_text("❌ Отменено", reply_markup=get_main_keyboard(user_id))
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
                logger.info(f"📝 Получен вариант: '{option_text}' для вопроса {data.get('current_question','?')[:30]}")
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
                    await update.message.reply_text(f"✅ *Вариант {len(data['current_options'])} добавлен!*\n\n📋 *Твои варианты:*\n{ol}\n\n✏️ _Введи ещё вариант или нажми кнопку:_", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
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
            await query.message.edit_text("✨ *Выбери тему:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_groups_keyboard())
        
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
        
        # === ПРОФИЛЬ ===
        elif data.startswith("age_"):
            if await handle_profile_age(update, context):
                return
        elif data.startswith("profile_zodiac_"):
            if await handle_profile_zodiac(update, context):
                return
        
        # === ЗОДИАК ===
        elif data == "zodiac_back":
            await show_zodiac_menu(update, context)
        elif data == "zodiac_pick_sign":
            await zodiac_pick_my_sign(update, context)
        elif data == "zodiac_pick_friend":
            await zodiac_pick_friend_sign(update, context)
        elif data == "zodiac_select":
            await zodiac_select_menu(update, context)
        elif data == "zodiac_daily":
            await zodiac_daily_horoscope(update, context)
        elif data == "zodiac_elements":
            await zodiac_elements(update, context)
        elif data == "zodiac_best_friend":
            await zodiac_best_friend(update, context)
        elif data == "zodiac_talismans":
            await zodiac_talismans(update, context)
        elif data == "zodiac_challenge":
            await zodiac_challenge(update, context)
        elif data.startswith("zodiac_match_"):
            await zodiac_match_handler(update, context)
        elif data.startswith("zodiac_setmy_"):
            sign = query.data.replace("zodiac_setmy_", "")
            # Сохраняем в БД
            conn = get_db()
            c = conn.cursor()
            c.execute('UPDATE users SET zodiac_sign = ? WHERE user_id = ?', (sign, query.from_user.id))
            conn.commit()
            conn.close()
            context.user_data['zodiac_sign'] = sign
            await query.answer(f"✅ Твой знак: {ZODIAC_SIGNS[sign]}", show_alert=True)
            await show_zodiac_menu(update, context)
        
        elif data.startswith("dq_answer_"):
            await daily_quiz_answer_handler(update, context)
        elif data == "dq_refresh":
            # Обновляем текущее сообщение вместо отправки нового
            query = update.callback_query
            try: await query.answer("✅ Результаты обновлены!")
            except: pass
            
            daily = context.bot_data.get('daily_question', {})
            if not daily:
                # Восстанавливаем вопрос дня если бот перезапускался
                today = datetime.now().day
                q_index = today % len(DAILY_QUESTIONS)
                question, options = DAILY_QUESTIONS[q_index]
                daily = {
                    'question': question,
                    'options': options,
                    'date': datetime.now().strftime('%d.%m.%Y'),
                    'answers': {}
                }
                context.bot_data['daily_question'] = daily
            
            answers = daily.get('answers', {})
            total = len(answers) if answers else 1
            options = daily.get('options', [])
            
            text = f"🌸✨ *ВОПРОС ДНЯ* ✨🌸\n\n📅 {daily.get('date', '')}\n\n💭 *{daily.get('question', '')}*\n\n"
            
            my_answer_idx = answers.get(str(query.from_user.id))
            if my_answer_idx is not None:
                text += f"✅ Твой выбор: *{options[my_answer_idx]}*\n\n"
            
            text += "📊 *Как ответили подруги:*\n\n"
            
            for i, opt in enumerate(options):
                count = sum(1 for v in answers.values() if v == i)
                pct = round(count / total * 100) if total > 0 else 0
                bar = "💖" * (pct // 10) + "🤍" * (10 - pct // 10)
                text += f"{bar} *{pct}%* — {opt}\n"
            
            text += f"\n👥 *Всего ответили:* {len(answers)} {decline_friend_word(len(answers))}\n\n_Обновлено: {datetime.now().strftime('%H:%M:%S')}_"
            
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Обновить результаты", callback_data="dq_refresh")
            ]])
            
            await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        
        # === ПОЛУЧИТЬ ДИПЛОМ ===
        elif data.startswith("get_diploma_"):
            parts = data.replace("get_diploma_", "").split("_")
            tid = int(parts[0])
            score = float(parts[1])
            diploma_data = context.user_data.get('diploma_data', {})
            if diploma_data:
                await query.message.reply_text("🎓 _Создаём твой диплом..._ 💫", parse_mode=ParseMode.MARKDOWN)
                analysis_image = await generate_friendship_analysis(
                    diploma_data['user_name'],
                    diploma_data['creator_name'],
                    diploma_data['test_title'],
                    diploma_data['score'],
                    diploma_data['status'],
                    diploma_data['prediction'],
                    diploma_data['categories_stats']
                )
                await query.message.reply_photo(analysis_image, caption="🎓✨ *ТВОЙ ДИПЛОМ!* ✨🎓\n\n💕 Сохрани его и поделись с подругами!", parse_mode=ParseMode.MARKDOWN)
            else:
                await query.answer("Диплом больше не доступен", show_alert=True)
        
        # === ЗАПУСК ТЕСТА ===
        elif data.startswith("start_"):
            await start_test(update, context)
        
        # === ОТВЕТ НА ВОПРОС ===
        elif data.startswith("answer_"):
            await handle_answer(update, context)
        
        # === ПОКАЗАТЬ ВСЕ ТЕСТЫ ===
        elif data == "show_all_tests":
            await show_all_tests(update, context)
        
        # === НАЗАД К МОИМ ТЕСТАМ ===
        elif data == "back_to_my_tests":
            await back_to_my_tests(update, context)
        
        # === МОИ ТЕСТЫ ===
        elif data == "show_all_tests":
            await show_all_tests(update, context)
        elif data == "back_to_my_tests":
            await back_to_my_tests(update, context)
        elif data == "my_badges":
            await my_badges_handler(update, context)
        elif data == "badges_info":
            await badges_info_handler(update, context)
        elif data == "go_premium":
            await premium_handler(update, context)
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
                pw = "прошла" if len(attempts)==1 else "прошли"
                if len(attempts) >= 10: icon, status = "🔥", "СУПЕР-ПОПУЛЯРНЫЙ!"
                elif len(attempts) >= 5: icon, status = "⭐", "ПОПУЛЯРНЫЙ!"
                elif len(attempts) >= 2: icon, status = "🌸", "НАБИРАЕТ ПОПУЛЯРНОСТЬ"
                else: icon, status = "⏳", "ЖДЁТ ПОДРУГ..."
                
                text = f"💕 *{test['title']}* 💕\n\n{icon} {status}\n• • • ✨ • • •\n🙎‍♀️ *{len(attempts)}* {decline_friend_word(len(attempts))} {pw} тест\n🎯 Средний результат: *{avg:.0f}%*\n"
                if attempts: text += f"👑 Лучший результат: *{max(a['score'] for a in attempts):.0f}%*\n"
                text += f"💭 Вопросов: *{len(test['questions'])}*\n"
                if test.get('greeting_file_id'): text += "🎬 Видео-поздравление: *есть* ✨\n"
                if test.get('question_photos') and test['question_photos']!='{}': text += f"📸 Фото: *{len(json.loads(test['question_photos']))}*\n"
                text += "\n• • • ✨ • • •\n💕 *Что хочешь сделать с тестом?* ✨"
                await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_test_actions_keyboard(tid, query.from_user.id))
        
        # === ПОДЕЛИТЬСЯ ===
        elif data.startswith("share_"):
            tid = int(data.replace("share_", ""))
            user_id = query.from_user.id
            if is_premium(user_id):
                share_text = f"📤✨ *ПОДЕЛИСЬ ТЕСТОМ!* ✨📤\n\n💕 Отправь тест подруге и узнай насколько хорошо она тебя знает!\n\n🎯 Чем больше подруг пройдут — тем интереснее битва за звание лучшей! 👑\n\n🔮 *Зодиак-челлендж:* когда подруга пройдёт тест — её знак зодиака добавится в твою коллекцию! Так ты соберёшь все 12 знаков!\n\n♾️ У тебя *Премиум* — безлимитные прохождения!\n\n👇 *Нажми на кнопку:*"
            else:
                available = get_available_tests_count(user_id)
                word = decline_word(available, "тест", "теста", "тестов")
                share_text = f"📤✨ *ПОДЕЛИСЬ ТЕСТОМ!* ✨📤\n\n💕 Отправь тест подруге и узнай насколько хорошо она тебя знает!\n\n🎯 Чем больше подруг пройдут — тем интереснее битва за звание лучшей! 👑\n\n🔮 *Зодиак-челлендж:* когда подруга пройдёт тест — её знак зодиака добавится в твою коллекцию! Так ты соберёшь все 12 знаков!\n\n⚠️ *Важно:* За каждое прохождение списывается 1 тест из твоего лимита.\n📊 Осталось: *{available}* {word}\n\n👇 *Нажми на кнопку:*"
            await query.message.reply_text(share_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(tid))
        
        # === ОТВЕТЫ ПОДРУГ ===
        elif data.startswith("answers_"):
            tid = int(data.replace("answers_", ""))
            if not is_premium(query.from_user.id):
                await query.answer("🔒 Ответы подруг доступны только с ПРЕМИУМ! 💎", show_alert=True)
                await query.message.reply_text(
                    "🔒✨ *ОТВЕТЫ ПОДРУГ* ✨🔒\n\n"
                    "💎 Эта функция доступна только с *премиум-подпиской*!\n\n"
                    "🌸 С премиумом ты сможешь:\n"
                    "👀 Смотреть ответы подруг\n"
                    "📊 Видеть статистику\n"
                    "🏆 Устраивать битвы подруг\n\n"
                    "💕 *Оформи премиум в главном меню!*",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("💎 Перейти в Премиум", callback_data="go_premium")
                    ]])
                )
                return
            test = get_test_by_id(tid); attempts = get_test_attempts(tid)
            if not attempts:
                await query.message.reply_text("💕✨ *ОТВЕТЫ ПОДРУГ* ✨💕\n\n👻 *Пока никто не прошёл тест!*\n\n💕 Отправь ссылку подружкам и узнай кто знает тебя лучше всех!", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💕 Отправить подруге", callback_data=f"share_{tid}")]]))
                return
            sa = sorted(attempts, key=lambda x: x['score'], reverse=True)
            text = f"💕✨ *ОТВЕТЫ ПОДРУГ* ✨💕\n\n📝 *{test['title']}*\n• • • ✨ • • •\n\n👯‍♀️ *Твои подруги прошли тест:*\n\n"
            for a in sa[:10]:
                s = a['score']
                if s>=90: em, hint = '👑','Знает меня наизусть! 💕'
                elif s>=70: em, hint = '💎','Отлично знает! ✨'
                elif s>=50: em, hint = '🌸','Хорошо знает! 🌟'
                elif s>=30: em, hint = '🌱','Узнаёт лучше! 💫'
                else: em, hint = '🦋','Только знакомится! 🌈'
                text += f"{em} *{a['friend_name']}* — *{s:.0f}%*\n   💬 _{hint}_\n\n"
            text += "💕 *Выбери подругу чтобы увидеть её ответы:*"
            kb = []
            for a in sa[:10]:
                icon = '👑' if a['score']>=80 else '💎' if a['score']>=60 else '🌸'
                c = get_db().cursor()
                c.execute("SELECT id FROM attempts WHERE test_id=? AND friend_name=?", (tid, a['friend_name']))
                row = c.fetchone()
                attempt_id = row[0] if row else 0
                kb.append([InlineKeyboardButton(f"{icon} {a['friend_name'][:20]} — {a['score']:.0f}%", callback_data=f"friend_details_{attempt_id}")])
            kb.append([InlineKeyboardButton("🔙 Назад к тесту", callback_data=f"back_to_test_{tid}")])
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
            
            # Получаем username
            friend_user = get_user(attempt['friend_id'])
            friend_display = fn
            if friend_user and friend_user.get('username'):
                friend_display = f"{fn} (@{friend_user['username']})"
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
                        if ic:
                            text += f"   ✅ _«{ua}»_\n"
                        else:
                            text += f"   ❌ Ответила: _«{ua}»_\n   ✅ Правильно: _«{ca}»_\n"
                    if str(i) in comms: text += f"   💬 _{comms[str(i)]}_\n"
                text += "\n"
            text += f"\n• • • ✨ • • •\n💕 *Итог:* {friend_display} и {'ты — родственные души! ✨' if score>=80 else 'вы отличные подруги! 💫' if score>=60 else 'вы только начинаете узнавать друг друга! 🌱'}"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 К списку подруг", callback_data=f"answers_{tid}")]])
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
            tid = int(data.replace("stats_friendship_",""))
            if not is_premium(query.from_user.id):
                await query.answer("🔒 Статистика доступна только с ПРЕМИУМ! 💎", show_alert=True)
                await query.message.reply_text(
                    "🔒✨ *СТАТИСТИКА ДРУЖБЫ* ✨🔒\n\n"
                    "💎 Эта функция доступна только с *премиум-подпиской*!\n\n"
                    "🌸 С премиумом ты сможешь:\n"
                    "📊 Видеть детальную статистику\n"
                    "👑 Узнать кто знает тебя лучше всех\n\n"
                    "💕 *Оформи премиум в главном меню!*",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("💎 Перейти в Премиум", callback_data="go_premium")
                    ]])
                )
                return
            test = get_test_by_id(tid); attempts = get_test_attempts(tid)
            if not attempts:
                await query.message.reply_text("📈✨ *СТАТИСТИКА ДРУЖБЫ* ✨📈\n\n😢 *Пока никто не прошёл!*\n\n🌸 Отправь ссылку подружкам!", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💕 Поделиться", callback_data=f"share_{tid}")]]))
                return
            sa = sorted(attempts, key=lambda x: x['score'], reverse=True); avg_score = sum(a['score'] for a in attempts)/len(attempts); max_score = max(a['score'] for a in attempts); min_score = min(a['score'] for a in attempts)
            conn = get_db(); c = conn.cursor(); usernames = {}
            for a in sa[:10]: 
                c.execute('SELECT username FROM users WHERE first_name=?', (a['friend_name'],))
                row = c.fetchone()
                if row and row['username']: usernames[a['friend_name']] = row['username']
            conn.close()
            
            text = f"💕✨ *СТАТИСТИКА ДРУЖБЫ* ✨💕\n\n📝 *{test['title']}*\n• • • ✨ • • •\n\n"
            text += f"👯‍♀️ *Твои подружки прошли тест:*\n\n"
            
            for a in sa[:10]:
                score = a['score']
                if score>=90: em, st, pr = '👑','ЭКСПЕРТ','Родственная душа! ✨'
                elif score>=80: em, st, pr = '💎','СУПЕР','Настоящая bestie! 💕'
                elif score>=70: em, st, pr = '💕','ЛУЧШАЯ ПОДРУГА','Цените друг друга 🌸'
                elif score>=60: em, st, pr = '🌸','ХОРОШАЯ ПОДРУГА','Вы на одной волне 💫'
                elif score>=50: em, st, pr = '🌟','ЗНАЕТ ТЕБЯ','Узнавайте друг друга 🌱'
                elif score>=30: em, st, pr = '🌱','УЗНАЁТ ТЕБЯ','Впереди много нового 💖'
                else: em, st, pr = '🦋','НОВАЯ ЗНАКОМАЯ','Всё только начинается 🦋'
                un = f" @{usernames[a['friend_name']]}" if a['friend_name'] in usernames else ""
                filled = int(score/10)
                if score>=90: bar = "💜"*filled+"🩶"*(10-filled)
                elif score>=70: bar = "💗"*filled+"🩶"*(10-filled)
                elif score>=50: bar = "💛"*filled+"🩶"*(10-filled)
                elif score>=30: bar = "🩵"*filled+"🩶"*(10-filled)
                else: bar = "🤍"*filled+"🩶"*(10-filled)
                text += f"{em} *{a['friend_name']}*{un}\n   {bar} *{score:.0f}%*\n   🏆 Уровень: *{st}*\n   💬 _{pr}_\n\n"
            
            pw = "прошла" if len(attempts)==1 else "прошли"
            text += f"• • • ✨ • • •\n\n📊 *ОБЩАЯ СТАТИСТИКА:*\n\n"
            text += f"🙎‍♀️ Тест {pw}: *{len(attempts)}* {decline_friend_word(len(attempts))}\n"
            text += f"📈 Средний результат: *{avg_score:.0f}%*\n"
            text += f"👑 Лучший: *{max_score:.0f}%* — *{sa[0]['friend_name']}* 💕\n"
            text += f"💔 Худший: *{min_score:.0f}%*\n\n"
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Ответы подруг", callback_data=f"answers_{tid}")],
                [InlineKeyboardButton("🔙 Назад к тесту", callback_data=f"back_to_test_{tid}")]
            ])
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

        elif data=="admin_funnel":
            conn = get_db(); c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM users'); total = c.fetchone()[0]
            c.execute('SELECT COUNT(DISTINCT creator_id) FROM tests'); created = c.fetchone()[0]
            c.execute('SELECT COUNT(DISTINCT friend_id) FROM attempts'); passed = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE premium_until>datetime('now')"); premium = c.fetchone()[0]; conn.close()
            await query.message.edit_text(f"🔄 *ВОРОНКА КОНВЕРСИИ*\n\n🙎‍♀️ Всего: *{total}* (100%)\n📝 Создали тест: *{created}* ({round(created/max(total,1)*100,1)}%)\n🎮 Прошли тест: *{passed}* ({round(passed/max(total,1)*100,1)}%)\n💎 Премиум: *{premium}* ({round(premium/max(total,1)*100,1)}%)", parse_mode=ParseMode.MARKDOWN)
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
    kb = []
    row = []
    for k, p in PRESET_GROUPS.items():
        row.append(InlineKeyboardButton(p["name"], callback_data=f"preset_{k}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
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
    await query.message.reply_text(f"✅ *{preset['name']}*\n📊 Сколько вопросов?\n✏️ Напиши число от 2 до 10:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def greeting_choice(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    choice = query.data.replace("greeting_",""); data = context.user_data.get('creating_test')
    if not data:
        await query.answer("Начни создание теста заново!", show_alert=True)
        return
    if choice=="skip":
        data['step'] = 'selecting_question'; data['current_question_index'] = 0; data['greeting_type'] = None; data['greeting_file_id'] = None
        msg = await query.message.reply_text("✨ _Готовим вопросы..._ 💫", parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(3)
        await msg.delete()
        await query.message.reply_text("✨ *Приступаем к вопросам!*", parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(1.5)
        await show_question_for_selection(query, context); return
    data['greeting_type'] = choice; data['waiting_greeting'] = True
    if choice=="voice":
        t = "🎤 *Отправь голосовое сообщение* (до 15 сек)\n\n💡 _Запиши приветствие для подруги — она услышит его после прохождения теста!_"
    else:
        t = "🎥 *Отправь видео* (до 15 сек)\n\n💡 _Сними видео-приветствие для подруги — она увидит его после прохождения теста!_"
    await query.message.reply_text(t + "\n\n⏭️ Нажми *«Пропустить»* если не хочешь добавлять поздравление", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="greeting_skip")]
    ]))

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
    await update.message.reply_text("✅ *Поздравление сохранено!*\n\n✨ Приступаем к вопросам! ✨", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(uid))
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
    await update.message.reply_text("✅ *Фото добавлено!* 📸\n\n✏️ Напиши вариант ответа №1:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def show_question_for_selection(update, context):
    data = context.user_data.get('creating_test')
    if not data: return
    qs = data.get('group_questions',[]); data['current_question_index'] = data.get('current_question_index',0)
    qt = qs[data['current_question_index']]; data['current_question'] = qt
    text = f"📝 *Вопрос {data['current_q']+1}/{data['total_q']}*\n\n{qt}"
    if hasattr(update,'message'): 
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_choice_keyboard())
        
    else: 
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_question_choice_keyboard())
        

async def next_question_callback(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    data = context.user_data.get('creating_test')
    if not data: 
        await query.answer("Начни создание теста заново!", show_alert=True)
        return
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
    await query.message.reply_text(f"📝 *Вопрос:* {data['current_question']}\n\n✏️ *Напиши вариант ответа №1:*\n\n📏 _До 50 символов_", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def add_photo_to_question(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    data = context.user_data.get('creating_test')
    if not data or not data.get('current_question'): return
    data['waiting_photo'] = True
    question_text = data.get('current_question', 'этому вопросу')
    await query.message.reply_text(f"📸 *Отправь фото к вопросу:*\n\n_{question_text}_", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def custom_question(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    data = context.user_data.get('creating_test')
    if not data: return
    data['waiting_custom_question'] = True
    await query.message.reply_text(
    "✏️✨ *Придумай свой вопрос!* ✨\n\n"
    "💡 _Напиши что хочешь узнать о себе от подруги._\n"
    "🌸 Например: «Какой мой любимый цвет?» или «Что я ем на завтрак?»\n\n"
    "📝 *Твой вопрос:*",
    parse_mode=ParseMode.MARKDOWN,
    reply_markup=get_cancel_keyboard()
)

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
    
    # Собираем вопросы
    questions_info = []
    for i, q in enumerate(qs):
        has_photo = " 📸" if str(i) in data.get('photos', {}) else ""
        # Если вопрос свой — добавляем эмодзи
        is_custom = True
        for cat_qs in QUESTIONS.values():
            if q in cat_qs:
                is_custom = False
                break
        prefix = "✏️ " if is_custom else ""
        questions_info.append(f"{i+1}. {prefix}{q}{has_photo}")
    
    questions_summary = "\n".join(questions_info)
    
    text = f"🎉✨ *ТЕСТ ГОТОВ!* ✨🎉\n\n📝 *{data['title']}*\n• • • • • • • • • • • •\n"
    text += f"💭 Вопросов: *{len(qs)}*\n"
    
    # Поздравление
    if data.get('greeting_file_id'):
        if data.get('greeting_type') == 'voice':
            text += "🎤 Голосовое поздравление: *есть* ✨\n"
        elif data.get('greeting_type') == 'video':
            text += "🎥 Видео-поздравление: *есть* ✨\n"
    else:
        text += "💬 Поздравление: *без поздравления*\n"
    
    if data.get('_pending_photos'):
        text += f"📸 Фото к вопросам: *{len(data.get('_pending_photos',[]))}*\n"
    
    text += f"• • • • • • • • • • • •\n\n"
    text += f"📋 *Твои вопросы:*\n{questions_summary}\n\n"
    text += "• • • • • • • • • • • •\n\n"
    text += "💖 *Отправь тест подружкам и узнай\nкто знает тебя лучше всех!* 👑\n\n👇 Нажми на кнопку ниже чтобы поделиться:"
    if hasattr(uoq,'message'): await uoq.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(tid))
    else: await uoq.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(tid))
    await uoq.message.reply_text("🌸 Главное меню:", reply_markup=get_main_keyboard(user.id))


ZODIAC_SIGNS = {
    "aries": "♈ Овен", "taurus": "♉ Телец", "gemini": "♊ Близнецы",
    "cancer": "♋ Рак", "leo": "♌ Лев", "virgo": "♍ Дева",
    "libra": "♎ Весы", "scorpio": "♏ Скорпион", "sagittarius": "♐ Стрелец",
    "capricorn": "♑ Козерог", "aquarius": "♒ Водолей", "pisces": "♓ Рыбы"
}

ZODIAC_COMPATIBILITY = {
    ("aries", "leo"): 95, ("aries", "sagittarius"): 92, ("aries", "gemini"): 88, ("aries", "aquarius"): 82, ("aries", "libra"): 70, ("aries", "aries"): 90,
    ("taurus", "virgo"): 95, ("taurus", "capricorn"): 93, ("taurus", "cancer"): 87, ("taurus", "pisces"): 82, ("taurus", "scorpio"): 78, ("taurus", "taurus"): 88,
    ("gemini", "libra"): 95, ("gemini", "aquarius"): 92, ("gemini", "aries"): 88, ("gemini", "leo"): 85, ("gemini", "sagittarius"): 80, ("gemini", "gemini"): 90,
    ("cancer", "scorpio"): 95, ("cancer", "pisces"): 93, ("cancer", "taurus"): 87, ("cancer", "virgo"): 84, ("cancer", "capricorn"): 75, ("cancer", "cancer"): 92,
    ("leo", "sagittarius"): 95, ("leo", "aries"): 95, ("leo", "libra"): 88, ("leo", "gemini"): 85, ("leo", "aquarius"): 78, ("leo", "leo"): 85,
    ("virgo", "taurus"): 95, ("virgo", "capricorn"): 92, ("virgo", "cancer"): 85, ("virgo", "scorpio"): 82, ("virgo", "pisces"): 72, ("virgo", "virgo"): 88,
    ("libra", "gemini"): 95, ("libra", "aquarius"): 90, ("libra", "leo"): 88, ("libra", "sagittarius"): 82, ("libra", "aries"): 70, ("libra", "libra"): 90,
    ("scorpio", "cancer"): 95, ("scorpio", "pisces"): 93, ("scorpio", "virgo"): 85, ("scorpio", "taurus"): 78, ("scorpio", "capricorn"): 80, ("scorpio", "scorpio"): 88,
    ("sagittarius", "aries"): 92, ("sagittarius", "leo"): 95, ("sagittarius", "libra"): 82, ("sagittarius", "aquarius"): 85, ("sagittarius", "gemini"): 80, ("sagittarius", "sagittarius"): 90,
    ("capricorn", "taurus"): 93, ("capricorn", "virgo"): 92, ("capricorn", "scorpio"): 85, ("capricorn", "cancer"): 75, ("capricorn", "pisces"): 70, ("capricorn", "capricorn"): 88,
    ("aquarius", "gemini"): 92, ("aquarius", "libra"): 90, ("aquarius", "sagittarius"): 85, ("aquarius", "aries"): 82, ("aquarius", "leo"): 78, ("aquarius", "aquarius"): 90,
    ("pisces", "cancer"): 93, ("pisces", "scorpio"): 93, ("pisces", "taurus"): 82, ("pisces", "virgo"): 72, ("pisces", "capricorn"): 70, ("pisces", "pisces"): 92,
    # Дополнительные комбинации
    ("leo", "capricorn"): 65, ("leo", "virgo"): 62, ("leo", "cancer"): 78, ("leo", "scorpio"): 75, ("leo", "pisces"): 82, ("leo", "taurus"): 72,
    ("aries", "cancer"): 68, ("aries", "virgo"): 60, ("aries", "scorpio"): 75, ("aries", "capricorn"): 65, ("aries", "taurus"): 70, ("aries", "pisces"): 72,
    ("taurus", "gemini"): 55, ("taurus", "leo"): 72, ("taurus", "libra"): 78, ("taurus", "aquarius"): 60, ("taurus", "sagittarius"): 58, ("taurus", "aries"): 70,
    ("gemini", "virgo"): 62, ("gemini", "scorpio"): 58, ("gemini", "cancer"): 72, ("gemini", "capricorn"): 55, ("gemini", "taurus"): 55, ("gemini", "pisces"): 65,
    ("cancer", "leo"): 78, ("cancer", "libra"): 68, ("cancer", "sagittarius"): 55, ("cancer", "aquarius"): 62, ("cancer", "gemini"): 72, ("cancer", "aries"): 68,
    ("virgo", "leo"): 62, ("virgo", "libra"): 72, ("virgo", "sagittarius"): 58, ("virgo", "aquarius"): 70, ("virgo", "gemini"): 62, ("virgo", "aries"): 60,
    ("libra", "cancer"): 68, ("libra", "virgo"): 72, ("libra", "scorpio"): 78, ("libra", "capricorn"): 75, ("libra", "taurus"): 78, ("libra", "pisces"): 72,
    ("scorpio", "leo"): 75, ("scorpio", "libra"): 78, ("scorpio", "sagittarius"): 68, ("scorpio", "aquarius"): 65, ("scorpio", "gemini"): 58, ("scorpio", "aries"): 75,
    ("sagittarius", "cancer"): 55, ("sagittarius", "virgo"): 58, ("sagittarius", "scorpio"): 68, ("sagittarius", "capricorn"): 72, ("sagittarius", "taurus"): 58, ("sagittarius", "pisces"): 70,
    ("capricorn", "leo"): 65, ("capricorn", "libra"): 75, ("capricorn", "sagittarius"): 72, ("capricorn", "aquarius"): 68, ("capricorn", "gemini"): 55, ("capricorn", "aries"): 65,
    ("aquarius", "cancer"): 62, ("aquarius", "virgo"): 70, ("aquarius", "scorpio"): 65, ("aquarius", "capricorn"): 68, ("aquarius", "taurus"): 60, ("aquarius", "pisces"): 75,
    ("pisces", "leo"): 82, ("pisces", "libra"): 72, ("pisces", "sagittarius"): 70, ("pisces", "aquarius"): 75, ("pisces", "gemini"): 65, ("pisces", "aries"): 72,
}

DAILY_QUESTIONS = [
    # Завтраки и еда
    ("🍳 Что я буду есть на завтрак?", ["🥞 Панкейки с сиропом", "🍳 Яичницу с тостом", "🥣 Кашу с ягодами", "🥑 Авокадо-тост", "🍌 Смузи боул"]),
    ("☕ Какой напиток я выберу утром?", ["☕ Латте с карамелью", "🍵 Зелёный чай", "🧋 Бабл ти", "🥤 Апельсиновый фреш", "☕ Капучино"]),
    ("🍕 Что я закажу на обед?", ["🍕 Пиццу с сыром", "🍣 Суши сет", "🍔 Бургер и картошку", "🥗 Цезарь с курицей", "🍜 Лапшу wok"]),
    ("🍰 Какой десерт я хочу прямо сейчас?", ["🍫 Шоколадный торт", "🍦 Мороженое с топингом", "🧁 Капкейк с кремом", "🍩 Пончик с глазурью", "🍓 Клубнику со сливками"]),
    
    # Школа и учёба
    ("📚 Как я готовлюсь к контрольной?", ["📝 Пишу шпаргалки", "📖 Учу всё подряд", "🤞 Надеюсь на удачу", "👯 Спрашиваю у подруги", "😴 Сплю — завтра разберусь"]),
    ("👩‍🏫 Какой урок я бы отменила?", ["📐 Математику", "🧪 Химию", "📖 Литературу", "🏃‍♀️ Физкультуру", "😫 Все!"]),
    ("📱 Что я делаю на скучном уроке?", ["📱 Сижу в телефоне", "💬 Переписываюсь", "😴 Сплю с открытыми глазами", "🎨 Рисую в тетради", "📝 Всё-таки слушаю"]),
    
    # Стиль и красота
    ("👗 Что я надену на свидание?", ["👗 Платье", "👖 Джинсы и топ", "💃 Юбку", "👟 Кэжуал", "🌸 Что-то новое куплю"]),
    ("💄 Какой макияж я сделаю сегодня?", ["💋 Нюдовый", "👁 Смоки айс", "✨ Сияющий", "🌸 Только тушь", "😴 Без макияжа"]),
    ("💅 Какой маникюр я выберу?", ["💅 Нюдовый", "🌸 Розовый", "❤️ Красный", "✨ С блёстками", "🦋 С дизайном"]),
    
    # Дружба и отношения
    ("👯 Что я ценю в подруге больше всего?", ["💕 Верность", "😂 Чувство юмора", "🤫 Умение хранить секреты", "🎉 С ней весело", "💖 Она меня понимает"]),
    ("💔 Как я переживаю ссору с подругой?", ["😢 Плачу", "💬 Пишу первой", "😤 Жду когда она напишет", "🍦 Ем мороженое", "💪 Иду мириться"]),
    ("💘 Что я сделаю если встречу краша?", ["😳 Покраснею", "💬 Попробую заговорить", "📱 Сделаю вид что в телефоне", "🏃‍♀️ Убегу", "💪 Подойду первая"]),
    
    # Настроение и планы
    ("🌸 Какой у меня вайб сегодня?", ["💕 Романтичный", "🔥 Боевой", "😴 Сонный", "🌟 Энергичный", "🦋 Мечтательный"]),
    ("🎯 Какая у меня цель на неделю?", ["📚 Хорошо учиться", "💪 Заняться спортом", "👯 Больше времени с подругами", "🛍️ Обновить гардероб", "😴 Выжить"]),
    ("🌙 Во сколько я лягу спать?", ["😴 До 22:00", "🌙 В 23:00", "🦉 После полуночи", "📱 Пока не сядет телефон", "☕ Вообще не спать"]),
    
    # Развлечения
    ("🎬 Что я буду смотреть вечером?", ["📺 Сериал", "🎥 Фильм", "📱 ТикТок", "🎮 Играть", "📚 Читать"]),
    ("🎵 Какой плейлист я включу?", ["🎤 K-pop", "💃 Русский поп", "🎸 Рок", "🎧 Lo-fi", "🌸 Инди"]),
    ("📸 Какое фото я выложу в сторис?", ["🤳 Селфи", "🌅 Закат", "🍽 Еду", "👯 С подругами", "🐶 Питомца"]),
    
    # Мечты и будущее
    ("✈️ Куда я мечтаю поехать?", ["🏖 На море", "🏔 В горы", "🏙 В большой город", "🌸 В Японию", "🌍 В кругосветку"]),
    ("🎓 Кем я хочу стать?", ["👩‍⚕️ Врачом", "👩‍💻 Программистом", "🎨 Дизайнером", "🎤 Звездой", "💼 Бизнес-леди"]),
    ("💎 Что для меня самое важное?", ["👨‍👩‍👧‍👦 Семья", "👯 Друзья", "💰 Деньги", "🌟 Слава", "💕 Любовь"]),
    
    # Приколы
    ("😂 Что меня рассмешит сегодня?", ["🤣 Смешной мем", "👯 Шутка подруги", "🐱 Видео с котами", "💬 Случайная фраза", "😜 Я и так смеюсь"]),
    ("🦄 Если бы у меня была суперсила?", ["🕊 Летать", "⏱ Останавливать время", "🧠 Читать мысли", "🫥 Быть невидимкой", "💪 Суперсила"]),
    ("👻 Что я делаю когда никто не видит?", ["💃 Танцую", "🎤 Пою в расчёску", "🤪 Кривляюсь у зеркала", "🍪 Ем вкусняшки", "😴 Сплю"]),
    ("🎭 Какое аниме я бы оживила?", ["🌸 Сёдзё", "⚔️ Сёнэн", "💕 Романтика", "😂 Комедию", "🌟 Фэнтези"]),
    ("🐱 Какое животное я бы завела?", ["🐶 Собаку", "🐱 Кошку", "🐹 Хомяка", "🐰 Кролика", "🦄 Единорога"]),
    ("🍕 С какой начинкой пицца — идеальна?", ["🧀 Сырная", "🍖 Пепперони", "🍍 Гавайская", "🍄 Грибная", "🌶 Острая"]),
    ("🎉 Как я отпраздную день рождения?", ["🎂 С семьёй", "👯 С подругами", "🏠 Дома", "🌟 В ресторане", "✈️ В путешествии"]),
    ("💬 Что я отвечу на признание в любви?", ["💕 Я тоже!", "😳 Промолчу", "😂 Посмеюсь", "🤔 Подумаю", "🏃‍♀️ Убегу"]),
    ("☕ Какой напиток я выберу утром?", ["☕ Латте с карамелью", "🍵 Зелёный чай", "🧋 Бабл ти", "🥤 Апельсиновый фреш", "☕ Капучино"]),
    ("👗 Что я надену сегодня в школу?", ["👖 Джинсы и футболку", "👗 Платье", "🩳 Юбку с топом", "👟 Спортивный костюм", "🌸 Романтичный образ"]),
    ("📱 Что я сделаю первым делом утром?", ["📱 Проверю соцсети", "🪞 Посмотрю в зеркало", "🎵 Включу музыку", "💬 Напишу подруге", "🧘‍♀️ Сделаю зарядку"]),
    ("🍕 Что я закажу на обед?", ["🍕 Пиццу с сыром", "🍣 Суши сет", "🍔 Бургер и картошку", "🥗 Цезарь с курицей", "🍜 Лапшу wok"]),
    ("🎵 Какой плейлист я включу сейчас?", ["🎤 K-pop хиты", "💃 Русский поп", "🎸 Альтернативный рок", "🎧 Lo-fi для учёбы", "🌸 Инди-поп"]),
    ("💄 Какой макияж я сделаю сегодня?", ["💋 Нюдовый на каждый день", "👁 Стрелки и тушь", "✨ Сияющий хайлайтер", "🌸 Только блеск для губ", "💅 Полный боевой раскрас"]),
    ("📺 Что я буду смотреть вечером?", ["🎬 Новый сериал", "📱 ТикТок до полуночи", "🎥 Любимый фильм", "📚 Почитаю книгу вместо", "💬 Буду болтать с подругами"]),
    ("🌸 Как я проведу выходные?", ["🛍️ Шопинг с подругами", "🏠 Домашний спа-день", "🎬 Киномарафон", "🌳 Прогулка в парке", "💃 Пойду на вечеринку"]),
    ("🍰 Какой десерт я хочу прямо сейчас?", ["🍫 Шоколадный торт", "🍦 Мороженое с топингом", "🧁 Капкейк с кремом", "🍩 Пончик с глазурью", "🍓 Клубнику со сливками"]),
    ("💇‍♀️ Какую причёску я сделаю?", ["💁‍♀️ Высокий хвост", "👩‍🦱 Распущенные волны", "💇‍♀️ Два пучка", "👧 Косичку", "🦋 Заколки-бабочки"]),
    ("📸 Какое фото я выложу в сторис?", ["🤳 Селфи с фильтром", "🌅 Закат", "🍽 Еду которую ем", "👯 С подругами", "🐶 Своего питомца"]),
    ("🎯 Какая у меня цель на сегодня?", ["📚 Сделать все уроки", "💪 Потренироваться", "💬 Помириться с подругой", "🛍️ Купить что-то новое", "😴 Просто выжить"]),
    ("💌 Что я отвечу на сообщение краша?", ["💕 С эмодзи сердечками", "😂 С мемом", "🤔 Что-то загадочное", "💬 Просто и мило", "👻 Ничего — пусть ждёт"]),
    ("🎨 Каким хобби я займусь сегодня?", ["🎨 Рисование", "🎸 Игра на гитаре", "📝 Вести дневник", "💃 Танцы под музыку", "🧶 Вязание/бисер"]),
    ("🌙 Во сколько я лягу спать?", ["😴 До 22:00 — я паинька", "🌙 В 23:00", "🦉 После полуночи", "📱 Пока не сядет телефон", "☕ Я вообще не сплю"]),
    ("🛍️ Что я куплю на следующей неделе?", ["👗 Новое платье", "💄 Косметику", "📱 Чехол на телефон", "🎁 Подарок подруге", "🌸 Канцелярию для школы"]),
    ("🎤 Какую песню я спою в душе?", ["🎵 Хит из ТикТока", "🎤 Любимую попсу", "💔 Грустный трек", "🌟 Из любимого мюзикла", "🤫 Я не пою в душе"]),
    ("👯 О чём я поговорю с подругой сегодня?", ["💕 О крашах", "📸 О новых фото", "😤 О том что бесит", "🌟 О планах на лето", "😂 Просто поржём"]),
    ("🌸 Какой у меня вайб сегодня?", ["💕 Романтичный", "🔥 Боевой", "😴 Сонный", "🌟 Энергичный", "🦋 Мечтательный"]),
    ("🍜 Что я приготовлю сама?", ["🍝 Пасту с сыром", "🥞 Блины", "🥗 Салат", "🍳 Омлет", "🍪 Печенье"]),
    ("📚 Что я почитаю перед сном?", ["📖 Фанфик", "📕 Книгу", "📱 Посты в соцсетях", "💌 Переписку с крашем", "😴 Ничего — сразу спать"]),
    ("🎬 Какой фильм я посмотрю с подругами?", ["💕 Ромком", "😂 Комедию", "👻 Ужастик", "🌟 Фэнтези", "🎭 Драму"]),
    ("💅 Какой маникюр я сделаю на этой неделе?", ["💅 Нюдовый", "🌸 Розовый с блёстками", "❤️ Красный", "🦋 С дизайном", "✨ Френч"]),
    ("🌤 Как я проведу летние каникулы?", ["🏖 На море", "🏕 В лагере", "🏠 Дома с друзьями", "✈️ В путешествии", "📱 В тиктоке"]),
    ("🎁 Что я хочу на день рождения?", ["📱 Новый телефон", "👗 Одежду", "💄 Косметику", "🎤 На концерт билет", "💕 Сюрприз от подруг"]),
    ("😤 Что меня сегодня бесит?", ["⏰ Рано вставать", "📚 Много домашки", "💔 Игнор от краша", "🌧 Плохая погода", "😴 Ничего — я zen"]),
    ("💪 Как я приведу себя в форму к лету?", ["🏃‍♀️ Бег по утрам", "🧘‍♀️ Йога", "💃 Танцы", "🥗 Правильное питание", "🤷‍♀️ И так сойдёт"]),
    ("👑 Кем я стану когда вырасту?", ["🎤 Звездой", "👩‍⚕️ Врачом", "👩‍💻 IT-специалистом", "🎨 Дизайнером", "💼 Бизнес-леди"]),
    ("🌸 Что сделает меня счастливой сегодня?", ["💕 Комплимент от подруги", "🍕 Вкусная еда", "📱 Лайки на фото", "🎵 Любимая песня", "🌟 Хорошая оценка"]),
]

async def show_friends_rating(update, context):
    user_id = update.effective_user.id
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT a.friend_name, a.friend_id, MAX(a.score) as best_score, t.title FROM attempts a JOIN tests t ON a.test_id = t.id WHERE t.creator_id = ? GROUP BY a.friend_name ORDER BY best_score DESC LIMIT 15", (user_id,))
    ratings = c.fetchall()
    conn.close()
    
    if not ratings:
        await update.message.reply_text("🏆✨ *РЕЙТИНГ ПОДРУГ* ✨🏆\n\n🌸 *Пока никто не прошёл твои тесты!*\n\n💕 Создай тест и отправь подругам!", parse_mode=ParseMode.MARKDOWN)
        return
    
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆✨ *ТВОЙ ТОП ПОДРУГ* ✨🏆\n\n"
    for i, (name, friend_id, score, title) in enumerate(ratings):
        icon = medals[i] if i < 3 else f"{i+1}."
        if score >= 90: level = "👑 Родная душа!"
        elif score >= 70: level = "💎 Лучшая подруга!"
        elif score >= 50: level = "🌸 Хорошая подруга!"
        elif score >= 30: level = "🌱 Приятельница!"
        else: level = "🦋 Знакомая!"
        hearts = "💖" * int(score/10) + "🤍" * (10 - int(score/10))
        
        # Получаем знак зодиака и username подруги
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT zodiac_sign, username FROM users WHERE user_id = ?', (friend_id,))
        row = c.fetchone()
        conn.close()
        zodiac_emoji = f" {ZODIAC_SIGNS[row['zodiac_sign']]}" if row and row['zodiac_sign'] else ""
        username_text = f" @{row['username']}" if row and row['username'] else ""
        
        text += f"{icon} *{name}*{username_text}{zodiac_emoji} — *{score:.0f}%*\n   {hearts}\n   {level}\n   📝 _{title}_\n\n"
    text += f"👥 *Всего подруг:* {len(ratings)}\n💕 *Лучшая:* {ratings[0][0]}!"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def show_zodiac_menu(update, context):
    """Меню знаков зодиака"""
    kb = [
        [InlineKeyboardButton("🔥 ЗОДИАК-ЧЕЛЛЕНДЖ 🔥", callback_data="zodiac_challenge")],
        [InlineKeyboardButton("⭐ Ежедневный гороскоп", callback_data="zodiac_daily")],
        [InlineKeyboardButton("💕 Проверить совместимость", callback_data="zodiac_select")],
        [InlineKeyboardButton("🌊 Совместимость по стихиям", callback_data="zodiac_elements")],
        [InlineKeyboardButton("👯‍♀️ Идеальная подруга", callback_data="zodiac_best_friend")],
        [InlineKeyboardButton("💎 Талисманы и цвета", callback_data="zodiac_talismans")],
    ]
    
    msg = update.message if hasattr(update, 'message') and update.message else update.callback_query.message
    
    # Показываем знак пользователя из БД
    uid = update.effective_user.id if hasattr(update, "effective_user") else update.callback_query.from_user.id
    db_user = get_user(uid)
    sign_key = db_user.get("zodiac_sign") if db_user else None
    text = "⭐✨ *ЗОДИАК-ЦЕНТР* ✨⭐\n"
    if sign_key and sign_key in ZODIAC_SIGNS:
        text += f"🌟 Твой знак: *{ZODIAC_SIGNS[sign_key]}*\n\n"
    else:
        text += "\n"
    text += "💫 Узнай всё о дружбе через звёзды!\n\n🌸 Выбери что хочешь узнать:"
    
    await msg.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def show_daily_quiz(update, context):
    today = datetime.now().day
    q_index = today % len(DAILY_QUESTIONS)
    question, options = DAILY_QUESTIONS[q_index]
    context.user_data["daily_quiz"] = {"question": question, "options": options}
    kb = [[InlineKeyboardButton(opt, callback_data=f"dq_answer_{i}")] for i, opt in enumerate(options)]
    await update.message.reply_text(f"🌸✨ *ВОПРОС ДНЯ* ✨🌸\n\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n💭 *{question}*\n\n👇 _Выбери свой вариант!_", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

async def zodiac_pick_my_sign(update, context):
    """Выбор своего знака (без выбора подруги)"""
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    kb = []
    signs = list(ZODIAC_SIGNS.items())
    for i in range(0, 12, 3):
        row = []
        for j in range(3):
            if i+j < 12:
                key, name = signs[i+j]
                row.append(InlineKeyboardButton(name, callback_data=f"zodiac_setmy_{key}"))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="zodiac_back")])
    
    # Показываем текущий знак из БД
    user = get_user(query.from_user.id)
    current_sign = user.get('zodiac_sign') if user else None
    current_text = f"🌟 Текущий знак: *{ZODIAC_SIGNS[current_sign]}*\n\n" if current_sign else ""
    
    await query.message.edit_text(
        f"⭐✨ *ВЫБЕРИ СВОЙ ЗНАК* ✨⭐\n\n{current_text}"
        "💫 Выбери *новый знак зодиака*!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def zodiac_pick_friend_sign(update, context):
    """Выбор знака подруги"""
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    kb = []
    signs = list(ZODIAC_SIGNS.items())
    for i in range(0, 12, 3):
        row = []
        for j in range(3):
            if i+j < 12:
                key, name = signs[i+j]
                row.append(InlineKeyboardButton(name, callback_data=f"zodiac_match_{key}"))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="zodiac_back")])
    
    user = get_user(query.from_user.id)
    db_user = get_user(query.from_user.id)
    my_sign = db_user.get("zodiac_sign") if db_user else "leo"
    await query.message.edit_text(
        f"⭐ Твой знак: *{ZODIAC_SIGNS.get(my_sign, 'Не выбран')}*\n\n"
        "💫 Теперь выбери *знак подруги*!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def zodiac_select_menu(update, context):
    """Меню выбора знака подруги"""
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    # Показываем текущий знак из БД
    user = get_user(query.from_user.id)
    my_sign = user.get('zodiac_sign') if user else None
    if not my_sign:
        # Если знак не выбран — просим выбрать свой
        kb = []
        signs = list(ZODIAC_SIGNS.items())
        for i in range(0, 12, 3):
            row = []
            for j in range(3):
                if i+j < 12:
                    key, name = signs[i+j]
                    row.append(InlineKeyboardButton(name, callback_data=f"zodiac_setmy_{key}"))
            kb.append(row)
        kb.append([InlineKeyboardButton("🔙 Назад", callback_data="zodiac_back")])
        await query.message.edit_text(
            "⭐✨ *СНАЧАЛА ВЫБЕРИ СВОЙ ЗНАК* ✨⭐\n\n"
            "💫 Выбери *свой знак зодиака*!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return
    
    # Сразу выбор знака подруги
    kb = []
    signs = list(ZODIAC_SIGNS.items())
    for i in range(0, 12, 3):
        row = []
        for j in range(3):
            if i+j < 12:
                key, name = signs[i+j]
                row.append(InlineKeyboardButton(name, callback_data=f"zodiac_match_{key}"))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="zodiac_back")])
    
    await query.message.edit_text(
        f"⭐✨ *СОВМЕСТИМОСТЬ* ✨⭐\n\n"
        f"🌟 Твой знак: *{ZODIAC_SIGNS[my_sign]}*\n\n"
        "💫 Теперь выбери *знак подруги*!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(kb)
    )


# DELETED_HANDLER


async def zodiac_match_handler(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    friend_sign = query.data.replace("zodiac_match_", "")
    user = get_user(query.from_user.id)
    my_sign = user.get('zodiac_sign') if user and user.get('zodiac_sign') else context.user_data.get("zodiac_sign", "leo")
    compat = 50
    for (a, b), val in ZODIAC_COMPATIBILITY.items():
        if (my_sign == a and friend_sign == b) or (my_sign == b and friend_sign == a):
            compat = val
            break
    hearts = "💖" * int(compat/10) + "🤍" * (10 - int(compat/10))
    
    if compat >= 95: desc = "🌟 *Идеальный союз!* Вы созданы друг для друга! Ваша дружба благословлена звёздами! Вместе вы способны покорить мир!"
    elif compat >= 90: desc = "💫 *Великолепная пара!* Космос говорит что вы родственные души. Доверяйте друг другу и делитесь секретами!"
    elif compat >= 85: desc = "✨ *Отличная совместимость!* Звёзды благоволят вашей дружбе. Вы понимаете друг друга без слов!"
    elif compat >= 80: desc = "💕 *Очень хорошая пара!* Ваши знаки гармонично сочетаются. Вместе вам никогда не скучно!"
    elif compat >= 75: desc = "🌸 *Хорошая совместимость!* Вы дополняете друг друга как инь и янь. Цените это!"
    elif compat >= 70: desc = "🌺 *Неплохая пара!* Есть небольшие разногласия, но вы умеете их преодолевать. Дружба стоит усилий!"
    elif compat >= 65: desc = "🌱 *Средняя совместимость.* Звёзды говорят — узнавайте друг друга глубже! У вас много общего там где вы не ожидаете!"
    elif compat >= 60: desc = "🦋 *Вы разные, но это интересно!* Противоположности притягиваются. Дайте друг другу шанс!"
    elif compat >= 50: desc = "🌈 *Непростой союз.* Но кто сказал что будет легко? Настоящая дружба строится на преодолении!"
    else: desc = "💫 *Загадочная связь.* Звёзды молчат, но это не значит что дружбы нет. Всё в ваших руках!"
    
    text = f"⭐✨ *КОСМИЧЕСКАЯ СОВМЕСТИМОСТЬ* ✨⭐\n\n"
    text += f"✨ Ты: *{ZODIAC_SIGNS[my_sign]}*\n"
    text += f"💕 Подруга: *{ZODIAC_SIGNS[friend_sign]}*\n\n"
    text += f"{hearts} *{compat}%*\n\n"
    text += f"{desc}\n\n"
    text += "💭 _Помни: настоящая дружба сильнее любых гороскопов! Пройди тест чтобы узнать реальную совместимость!_"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Проверить другие знаки", callback_data="zodiac_pick_friend")],
        [InlineKeyboardButton("🔙 Назад", callback_data="zodiac_back")]
    ])
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def daily_question_broadcast(context: ContextTypes.DEFAULT_TYPE):
    """Рассылает вопрос дня всем пользователям в 10:00"""
    today = datetime.now().day
    q_index = today % len(DAILY_QUESTIONS)
    question, options = DAILY_QUESTIONS[q_index]
    
    # Сохраняем вопрос дня в контексте бота
    context.bot_data['daily_question'] = {
        'question': question,
        'options': options,
        'date': datetime.now().strftime('%d.%m.%Y'),
        'answers': {}  # user_id: answer_idx
    }
    
    kb = [[InlineKeyboardButton(opt, callback_data=f"dq_answer_{i}")] for i, opt in enumerate(options)]
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id FROM users')
    users = c.fetchall()
    conn.close()
    
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(
                chat_id=u['user_id'],
                text=f"🌸✨ *ВОПРОС ДНЯ* ✨🌸\n\n📅 {datetime.now().strftime('%d.%m.%Y')}\n\n💭 *{question}*\n\n👇 _Выбери свой вариант и смотри как ответили подруги!_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(kb)
            )
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    logger.info(f"📢 Вопрос дня отправлен {sent} пользователям")

async def show_daily_results(update, context):
    """Показывает результаты вопроса дня"""
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    daily = context.bot_data.get('daily_question', {})
    if not daily:
        await query.message.reply_text("🌸 Сегодня ещё не было вопроса дня!")
        return
    
    answers = daily.get('answers', {})
    total = len(answers) if answers else 1
    options = daily.get('options', [])
    
    text = f"🌸✨ *РЕЗУЛЬТАТЫ ВОПРОСА ДНЯ* ✨🌸\n\n📅 {daily.get('date', '')}\n\n💭 *{daily.get('question', '')}*\n\n"
    
    for i, opt in enumerate(options):
        count = sum(1 for v in answers.values() if v == i)
        pct = round(count / total * 100)
        bar = "💖" * (pct // 10) + "🤍" * (10 - pct // 10)
        text += f"{bar} *{pct}%* — {opt}\n"
    
    my_answer_idx = answers.get(str(query.from_user.id))
    if my_answer_idx is not None:
        text += f"\n🌸 Твой выбор: *{options[my_answer_idx]}*"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Проверить другие знаки", callback_data="zodiac_pick_friend")],
        [InlineKeyboardButton("🔙 Назад", callback_data="zodiac_back")]
    ])
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def daily_quiz_answer_handler(update, context):
    query = update.callback_query
    try: await query.answer("✅ Ответ принят! Смотри результаты! 💕", show_alert=False)
    except: pass
    
    answer_idx = int(query.data.replace("dq_answer_", ""))
    user_id = str(query.from_user.id)
    
    daily = context.bot_data.get('daily_question', {})
    if not daily:
        # Создаём новый вопрос дня
        today = datetime.now().day
        q_index = today % len(DAILY_QUESTIONS)
        question, options = DAILY_QUESTIONS[q_index]
        daily = {
            'question': question,
            'options': options,
            'date': datetime.now().strftime('%d.%m.%Y'),
            'answers': {}
        }
        context.bot_data['daily_question'] = daily
    
    answers = daily.get('answers', {})
    answers[user_id] = answer_idx
    daily['answers'] = answers
    context.bot_data['daily_question'] = daily
    
    options = daily.get('options', [])
    chosen = options[answer_idx] if answer_idx < len(options) else ""
    
    # Показываем результаты
    total = len(answers) if answers else 1
    text = f"🌸✨ *ВОПРОС ДНЯ* ✨🌸\n\n📅 {daily.get('date', '')}\n\n💭 *{daily.get('question', '')}*\n\n"
    text += f"✅ Твой выбор: *{chosen}*\n\n"
    text += "📊 *Как ответили подруги:*\n\n"
    
    for i, opt in enumerate(options):
        count = sum(1 for v in answers.values() if v == i)
        pct = round(count / total * 100)
        bar = "💖" * (pct // 10) + "🤍" * (10 - pct // 10)
        text += f"{bar} *{pct}%* — {opt}\n"
    
    text += f"\n👥 *Всего ответили:* {len(answers)} {decline_friend_word(len(answers))}"
    
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Обновить результаты", callback_data="dq_refresh")
    ]])
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)



# ===== ГОРОСКОП ДРУЖБЫ НА СЕГОДНЯ =====
ZODIAC_DAILY_FULL = {  # 30 гороскопов для каждого знака
    "aries": [
        "🔥 Сегодня день активных действий! Позови подругу на прогулку — она будет в восторге. Возможен спонтанный шопинг!",
        "⚡ Энергия Марса с тобой! Отличный день для спорта с подругой. Устройте совместную пробежку!",
        "🌟 Звёзды говорят: будь смелее! Признайся подруге как она тебе дорога. Она ждёт этих слов!",
        "🎯 День для достижения целей! Напишите с подругой список желаний на лето.",
        "💪 Твоя сила сегодня — в честности. Скажи подруге правду, даже если это сложно.",
        "🌈 День сюрпризов! Сделай подруге неожиданный подарок — даже маленький, но от души.",
        "🔥 Овен в ударе! Сегодня ты можешь помирить любых подруг. Будь миротворцем!",
        "🌸 День нежности. Несмотря на твой огненный характер, сегодня будь мягче с близкими.",
        "🚀 Космическая энергия! Планируйте с подругой путешествие — звёзды обещают удачу.",
        "💎 День финансовых решений! Не трать всё сразу — отложи на подарок лучшей подруге.",
    ],
    "taurus": [
        "🌸 Телец, сегодня день уюта! Пригласи подругу на чай с вкусняшками. Домашние посиделки — лучшее!",
        "🍰 Венера балует тебя! Испеки что-то вместе с подругой. Совместная готовка сближает!",
        "💆‍♀️ День спа! Сделайте с подругой маски для лица и болтайте о своём.",
        "🌿 Природа зовёт! Прогулка в парке с подругой наполнит тебя энергией.",
        "💎 Сегодня день твоей стабильности. Подруга ценит тебя за надёжность. Покажи это!",
        "🎵 Музыкальный день! Составьте с подругой общий плейлист для прогулок.",
        "🌸 Телец, ты сегодня особенно привлекательна! Сходите с подругой за обновками.",
        "🍕 День вкусной еды! Закажите пиццу и смотрите любимый сериал вместе.",
        "💤 День отдыха. Не перегружай себя — просто побудь с подругой в тишине.",
        "🌟 Звёзды советуют: скажи подруге спасибо за то что она есть.",
    ],
    "gemini": [
        "🦋 Близнецы, сегодня Меркурий помогает общению! Напиши подруге первой — вы обсудите всё на свете!",
        "💬 День разговоров! Позвони подруге — у вас накопилось столько новостей!",
        "📚 Интеллектуальный день! Обсудите с подругой новую книгу или фильм.",
        "🎭 Твоя двойственность сегодня — суперсила! Помоги подруге увидеть ситуацию с другой стороны.",
        "🌈 День креатива! Придумайте с подругой новый челлендж или игру.",
        "🦋 Близнецы в ударе! Сегодня ты можешь развеселить кого угодно. Подруга будет в восторге!",
        "📱 Социальный день! Сделайте совместное фото и выложите в соцсети.",
        "🎤 Караоке-вечер! Пойте с подругой любимые песни — соседи потерпят!",
        "💕 День комплиментов! Скажи подруге 5 причин почему она лучшая.",
        "🌟 Звёзды говорят: поделись с подругой секретом — это укрепит дружбу.",
    ],
    "cancer": [
        "🌙 Рак, сегодня Луна делает тебя особенно чувствительной. Позвони подруге — она поймёт твоё настроение.",
        "💕 День заботы! Приготовь подруге что-то вкусное — твоя забота бесценна.",
        "🏠 Домашний день! Устройте с подругой вечер объятий и любимых фильмов.",
        "🌊 Твоя интуиция сегодня на высоте. Ты знаешь что нужно подруге — действуй!",
        "💌 Напиши подруге длинное сообщение о том как она важна для тебя.",
        "🌸 День воспоминаний! Посмотрите с подругой старые фото и посмейтесь.",
        "🦀 Рак, ты сегодня особенно сильна! Защити подругу если её кто-то обидел.",
        "💤 Уютный вечер! Наденьте пижамы и смотрите романтические комедии.",
        "🌙 Луна шепчет: не держи эмоции в себе. Поплачь с подругой — станет легче!",
        "💎 Сегодня твой день! Подруга ценит твою заботу — ответь ей тем же.",
    ],
    "leo": [
        "👑 Лев, сегодня твой день сиять! Организуй сюрприз для подруги — ты умеешь делать праздник!",
        "🌟 Звёзды на твоей стороне! Сделай комплимент подруге — ты поднимешь ей настроение на весь день!",
        "🎉 День веселья! Устройте с подругой мини-вечеринку — вы это заслужили!",
        "💃 Танцевальный вечер! Включите музыку и танцуйте как никто не видит.",
        "🔥 Львиная энергия! Поведи подругу в новое место — она будет в восторге от твоей инициативы.",
        "👑 Королевский день! Побалуйте себя с подругой — закажите что-то особенное.",
        "💕 День щедрости! Подари подруге что-то от души — не обязательно дорогое.",
        "🎭 Драматический день! Посмотрите с подругой новый фильм — эмоции гарантированы!",
        "🌟 Ты звезда! Подруга равняется на тебя — покажи пример доброты.",
        "🌈 День приключений! Выйдите из зоны комфорта вместе — это сближает!",
    ],
    "virgo": [
        "📝 Дева, сегодня день порядка! Помоги подруге с организацией — твой талант бесценен.",
        "🌸 День деталей! Ты замечаешь то что другие пропускают. Скажи подруге что-то важное.",
        "📚 Учебный день! Сделайте с подругой домашку вместе — так быстрее и веселее.",
        "💕 Твоя забота проявляется в мелочах. Подруга это ценит больше чем ты думаешь!",
        "🌿 День здоровья! Предложи подруге вместе заняться йогой или медитацией.",
        "💎 Твой перфекционизм сегодня уместен! Помоги подруге с выбором наряда.",
        "📝 Планируйте будущее! Составьте с подругой список целей на месяц.",
        "🌸 Дева, ты сегодня особенно мудра. Подруга придёт к тебе за советом — не откажи!",
        "🎨 Творческий день! Сделайте с подругой что-то руками — открытки, браслеты.",
        "💤 Не перетруждайся! Отложи дела и просто побудь с подругой.",
    ],
    "libra": [
        "⚖️ Весы, сегодня день гармонии! Помирись с подругой если были разногласия.",
        "🌸 День красоты! Сходите с подругой на маникюр или просто сделайте друг другу.",
        "💕 Твоя дипломатия сегодня на высоте! Помоги подругам найти общий язык.",
        "🎨 Эстетический день! Посетите с подругой выставку или красивое кафе.",
        "🌟 Звёзды говорят: не выбирай между подругами — у тебя хватит любви на всех!",
        "💃 День стиля! Примерьте с подругой новые образы и устройте фотосессию.",
        "🌈 Ты создаёшь гармонию вокруг себя. Подруги это чувствуют и тянутся к тебе.",
        "💎 День компромиссов! Найди общее решение которое устроит всех.",
        "🎵 Музыкальный день! Сходите с подругой на концерт или послушайте музыку дома.",
        "🌸 Весы, ты сегодня особенно обаятельна! Используй это для укрепления дружбы.",
    ],
    "scorpio": [
        "🦂 Скорпион, сегодня день страсти! Расскажи подруге о своих мечтах — она поддержит.",
        "💎 Твоя интуиция сегодня острее обычного. Ты знаешь что скрывает подруга — будь деликатна.",
        "🔥 День трансформации! Вместе с подругой начните что-то новое — спорт, хобби.",
        "🌙 Загадочный день! Твоя таинственность притягивает подруг как магнит.",
        "💕 День доверия! Откройся подруге — она не предаст.",
        "🦂 Ты сильная и страстная! Подруга восхищается твоей решительностью.",
        "🌟 Звёзды советуют: не ревнуй подругу к другим. Ты для неё особенная.",
        "🔮 Мистический день! Погадайте с подругой или почитайте гороскопы.",
        "💎 Твоя верность бесценна. Подруга знает что может на тебя положиться.",
        "🌊 Эмоциональный день! Не держи всё в себе — поделись с подругой.",
    ],
    "sagittarius": [
        "🏹 Стрелец, сегодня день приключений! Позови подругу в новое место — хоть в соседний район!",
        "✈️ Твоя жажда путешествий заразительна! Планируйте с подругой поездку.",
        "🔥 День оптимизма! Твой смех поднимет настроение любой подруге.",
        "🌟 Звёзды говорят: будь искренней! Подруги ценят твою прямоту.",
        "🎯 День целей! Запишите с подругой что хотите сделать вместе до конца года.",
        "💃 Активный день! Сходите на танцы, йогу или просто прогуляйтесь.",
        "🏹 Твоя свобода вдохновляет! Покажи подруге как быть независимой.",
        "🌈 День юмора! Твои шутки сегодня особенно смешные — веселитесь!",
        "📚 Философский день! Обсудите с подругой смысл жизни — это сближает.",
        "💕 Стрелец, ты сегодня особенно привлекательна для новых знакомств. Но не забывай старых подруг!",
    ],
    "capricorn": [
        "🏔 Козерог, сегодня день достижений! Помоги подруге с её целями — твой опыт бесценен.",
        "💎 Твоя надёжность — твой бренд! Подруга знает что на тебя можно положиться.",
        "📝 День планирования! Составьте с подругой расписание на неделю.",
        "🌟 Звёзды говорят: иногда нужно отдыхать! Устройте с подругой день без планов.",
        "🏔 Ты медленно но верно идёшь к цели. Подруга гордится тобой!",
        "💼 Карьерный день! Обсудите с подругой кем хотите стать в будущем.",
        "🌸 Козерог, сегодня будь мягче! Обними подругу и скажи что она важна.",
        "💎 День финансов! Научи подругу как копить и тратить с умом.",
        "🌿 Семейные ценности! Позвони подруге и спроси как у неё дела.",
        "🏔 Ты скала для своих подруг! Сегодня кто-то особенно нуждается в твоей поддержке.",
    ],
    "aquarius": [
        "⚡ Водолей, сегодня день идей! Придумайте с подругой что-то безумное и воплотите!",
        "🌟 Твоя уникальность — твоя суперсила! Подруги любят тебя за необычность.",
        "💡 Инновационный день! Покажи подруге новое приложение или игру.",
        "🌈 День свободы! Не ограничивай себя — делайте с подругой что хотите.",
        "⚡ Твой ум сегодня особенно остёр! Помоги подруге с креативной задачей.",
        "💕 День дружбы! Ты ценишь каждую подругу — скажи им об этом.",
        "🌟 Звёзды говорят: не отдаляйся от подруги. Ей нужно твоё внимание.",
        "🎨 Футуристический день! Обсудите с подругой будущее — ваше и мира.",
        "💎 Твоя оригинальность вдохновляет! Подруга хочет быть похожей на тебя.",
        "⚡ Электрический день! Ты заряжаешь всех вокруг — делись энергией с подругой!",
    ],
    "pisces": [
        "🌊 Рыбы, сегодня день творчества! Нарисуйте с подругой что-то или сделайте коллаж.",
        "💕 Твоя эмпатия сегодня на высоте. Подруга нуждается в твоей поддержке.",
        "🎵 Музыкальный день! Составьте с подругой плейлист для мечтаний.",
        "🌙 Загадочный день! Посмотрите с подругой фильм про любовь и поплачьте.",
        "💎 Твоя интуиция шепчет: позвони подруге. Она ждёт твоего звонка!",
        "🌸 День романтики! Помечтайте с подругой о прекрасном будущем.",
        "🌊 Рыбы, ты сегодня особенно чувствительна. Береги свои эмоции.",
        "💤 День отдыха! Устройте с подругой вечер без телефонов.",
        "🎨 Твой внутренний мир прекрасен! Поделись им с подругой.",
        "💕 Звёзды говорят: напиши подруге стих или песню — она будет тронута!",
    ],
}

ZODIAC_ELEMENTS = {
    "aries": "🔥 Огонь", "leo": "🔥 Огонь", "sagittarius": "🔥 Огонь",
    "taurus": "🌍 Земля", "virgo": "🌍 Земля", "capricorn": "🌍 Земля",
    "gemini": "💨 Воздух", "libra": "💨 Воздух", "aquarius": "💨 Воздух",
    "cancer": "🌊 Вода", "scorpio": "🌊 Вода", "pisces": "🌊 Вода",
}

ELEMENT_COMPATIBILITY = {
    ("🔥 Огонь", "💨 Воздух"): ("Искра!", "Огонь и Воздух создают ураган веселья! Вы самая энергичная пара подруг. Вместе вы способны зажечь любую вечеринку!", 90),
    ("🔥 Огонь", "🌍 Земля"): ("Тепло", "Огонь согревает Землю. Ты заряжаешь подругу энергией, а она даёт тебе стабильность. Отличный баланс!", 75),
    ("🔥 Огонь", "🌊 Вода"): ("Пар", "Огонь и Вода — это вызов! Но когда вы вместе — получается горячий чай. Главное не тушить друг друга.", 60),
    ("💨 Воздух", "🌊 Вода"): ("Волны", "Воздух создаёт волны на Воде. Вы вдохновляете друг друга на новые идеи и приключения!", 80),
    ("💨 Воздух", "🌍 Земля"): ("Пыльца", "Воздух разносит семена по Земле. Ты помогаешь подруге расти и развиваться!", 70),
    ("🌊 Вода", "🌍 Земля"): ("Плодородие", "Вода питает Землю. Ваша дружба глубокая и плодотворная. Вы растёте вместе!", 85),
}

# ===== ТАЛИСМАНЫ =====
ZODIAC_TALISMANS = {
    "aries": {"color": "🔥 Красный", "stone": "💎 Рубин", "flower": "🌹 Роза", "metal": "🥇 Золото"},
    "taurus": {"color": "🌸 Розовый", "stone": "💎 Изумруд", "flower": "🌷 Тюльпан", "metal": "🥈 Серебро"},
    "gemini": {"color": "💛 Жёлтый", "stone": "💎 Агат", "flower": "🌻 Подсолнух", "metal": "🥉 Бронза"},
    "cancer": {"color": "🤍 Белый", "stone": "💎 Лунный камень", "flower": "🌸 Лилия", "metal": "🥈 Серебро"},
    "leo": {"color": "🧡 Оранжевый", "stone": "💎 Янтарь", "flower": "🌺 Гибискус", "metal": "🥇 Золото"},
    "virgo": {"color": "💚 Зелёный", "stone": "💎 Яшма", "flower": "🌿 Лаванда", "metal": "🥈 Серебро"},
    "libra": {"color": "🩷 Пастельный", "stone": "💎 Опал", "flower": "💐 Пион", "metal": "🥇 Золото"},
    "scorpio": {"color": "🖤 Чёрный", "stone": "💎 Гранат", "flower": "🥀 Чёрная роза", "metal": "🥈 Серебро"},
    "sagittarius": {"color": "💜 Фиолетовый", "stone": "💎 Аметист", "flower": "🌼 Одуванчик", "metal": "🥉 Бронза"},
    "capricorn": {"color": "🤎 Коричневый", "stone": "💎 Оникс", "flower": "🌲 Эдельвейс", "metal": "🥈 Серебро"},
    "aquarius": {"color": "💙 Синий", "stone": "💎 Аквамарин", "flower": "🪷 Лотос", "metal": "🥇 Золото"},
    "pisces": {"color": "💗 Сиреневый", "stone": "💎 Жемчуг", "flower": "🪻 Сирень", "metal": "🥈 Серебро"},
}

# ===== ИДЕАЛЬНАЯ ПОДРУГА =====
ZODIAC_BEST_FRIENDS = {
    "aries": [("leo", 97, "Королевский союз!"), ("sagittarius", 94, "Огонь и пламя!"), ("gemini", 88, "Веселье без границ!")],
    "taurus": [("virgo", 95, "Идеальный баланс"), ("capricorn", 93, "Надёжный тыл"), ("cancer", 87, "Уют и тепло")],
    "gemini": [("libra", 95, "Интеллектуалки!"), ("aquarius", 92, "Мозговой штурм!"), ("aries", 85, "Энерджайзеры!")],
    "cancer": [("scorpio", 95, "Глубокая связь"), ("pisces", 93, "Родственные души"), ("taurus", 87, "Домашний уют")],
    "leo": [("sagittarius", 95, "Яркий тандем!"), ("aries", 95, "Две королевы!"), ("libra", 88, "Гармония и блеск")],
    "virgo": [("taurus", 95, "Настоящая опора"), ("capricorn", 92, "Общие цели"), ("cancer", 85, "Забота и нежность")],
    "libra": [("gemini", 95, "Родственные умы!"), ("aquarius", 90, "Креативный союз!"), ("leo", 88, "Стиль и грация")],
    "scorpio": [("cancer", 95, "Душевная глубина"), ("pisces", 93, "Мистическая связь"), ("virgo", 85, "Сила и точность")],
    "sagittarius": [("aries", 92, "Приключения!"), ("leo", 95, "Праздник жизни!"), ("libra", 85, "Лёгкость и драйв")],
    "capricorn": [("taurus", 93, "Верность навсегда"), ("virgo", 92, "Порядок и успех"), ("scorpio", 85, "Сила и стратегия")],
    "aquarius": [("gemini", 92, "Фейерверк идей!"), ("libra", 90, "Творческий дуэт!"), ("sagittarius", 85, "Свобода и драйв")],
    "pisces": [("cancer", 93, "Эмоциональная связь"), ("scorpio", 93, "Интуитивный союз"), ("taurus", 82, "Мечты и реальность")],
}

# ===== ЗОДИАК-ЧЕЛЛЕНДЖ =====
async def zodiac_challenge(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    user_id = query.from_user.id
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT a.friend_name FROM attempts a JOIN tests t ON a.test_id = t.id WHERE t.creator_id = ?", (user_id,))
    friends = c.fetchall()
    
    signs_found = set()
    
    for (name,) in friends:
        c.execute('SELECT zodiac_sign FROM users WHERE first_name = ?', (name,))
        row = c.fetchone()
        if row and row['zodiac_sign']:
            signs_found.add(row['zodiac_sign'])
    
    c.execute("SELECT DISTINCT u.zodiac_sign FROM users u JOIN tests t ON u.user_id = t.creator_id JOIN attempts a ON t.id = a.test_id WHERE a.friend_id = ? AND u.zodiac_sign IS NOT NULL", (user_id,))
    for (sign,) in c.fetchall():
        signs_found.add(sign)
    conn.close()
    
    text = "🔥✨ *ЗОДИАК-ЧЕЛЛЕНДЖ* ✨🔥\n\n"
    text += "👯‍♀️ *Собери все 12 знаков зодиака!*\n\n"
    text += "💡 *Как это работает:*\n"
    text += "• Отправь тест подруге — когда она пройдёт, её знак добавится в коллекцию\n"
    text += "• Пройди тест от подруги — её знак тоже засчитается!\n\n"
    text += "🌟 Собери все 12 и получи достижение *«Звёздный круг»*!\n\n"
    text += "📊 *Твой прогресс:*\n\n"
    
    elements_order = [
        ("🔥 Огонь", ["aries", "leo", "sagittarius"]),
        ("🌍 Земля", ["taurus", "virgo", "capricorn"]),
        ("💨 Воздух", ["gemini", "libra", "aquarius"]),
        ("🌊 Вода", ["cancer", "scorpio", "pisces"]),
    ]
    
    for element_name, element_signs in elements_order:
        text += f"*{element_name}:*\n"
        line = ""
        for key in element_signs:
            name = ZODIAC_SIGNS[key]
            if key in signs_found:
                line += f"✅ *{name}*  "
            else:
                line += f"⬜ {name}  "
        text += line + "\n\n"
    
    text += f"🌟 Найдено: *{len(signs_found)}* из 12 знаков\n\n"
    if len(signs_found) == 12:
        text += "🏆 _Поздравляем! Ты собрала все знаки зодиака! Ты — Королева Подруг!_ 👑✨"
    elif len(signs_found) >= 6:
        text += "💪 _Ты на полпути к звёздному кругу! Продолжай отправлять тесты подругам!_"
    else:
        text += "💕 _Отправляй тесты подругам и проходи их сама — собирай знаки в коллекцию!_"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Пригласить подругу", switch_inline_query=f"💕 Пройди тест обо мне и узнай нашу совместимость! 👉 https://t.me/{BOT_USERNAME}")],
        [InlineKeyboardButton("🔙 В Зодиак-центр", callback_data="zodiac_back")]
    ])
    
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)



async def zodiac_daily_horoscope(update, context):
    """Ежедневный гороскоп дружбы"""
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    # Берём знак из БД, если нет — из context, если нет — leo
    db_user = get_user(query.from_user.id)
    my_sign = db_user.get("zodiac_sign") if db_user else "leo"
    horoscope = ZODIAC_DAILY_FULL.get(my_sign, ZODIAC_DAILY_FULL["leo"])[datetime.now().day % 10]
    
    text = f"⭐✨ *ГОРОСКОП ДРУЖБЫ* ✨⭐\n\n📅 {datetime.now().strftime('%d.%m.%Y')}\n{ZODIAC_SIGNS.get(my_sign, 'Лев')}\n\n{horoscope}\n\n💫 _Завтра новый гороскоп! Заходи ещё!_"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💕 Проверить совместимость", callback_data="zodiac_pick_friend")],
        [InlineKeyboardButton("🔙 Назад", callback_data="zodiac_back")]
    ])
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def zodiac_elements(update, context):
    """Совместимость по стихиям"""
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    db_user = get_user(query.from_user.id)
    my_sign = db_user.get("zodiac_sign") if db_user else "leo"
    my_element = ZODIAC_ELEMENTS.get(my_sign, "🔥 Огонь")
    
    text = f"🌊✨ *СТИХИИ ДРУЖБЫ* ✨🔥\n\n"
    text += f"Твой знак: *{ZODIAC_SIGNS[my_sign]}*\n"
    text += f"Твоя стихия: *{my_element}*\n\n"
    text += "💫 *С кем ты совместима:*\n\n"
    
    for (e1, e2), (name, desc, compat) in ELEMENT_COMPATIBILITY.items():
        if e1 == my_element or e2 == my_element:
            other = e2 if e1 == my_element else e1
            text += f"{other}: *{compat}%* — {name}\n_{desc}_\n\n"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Найти идеальную подругу", callback_data="zodiac_best_friend")],
        [InlineKeyboardButton("🔙 Назад", callback_data="zodiac_back")]
    ])
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def zodiac_best_friend(update, context):
    """Идеальная подруга по знаку"""
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    db_user = get_user(query.from_user.id)
    my_sign = db_user.get("zodiac_sign") if db_user else "leo"
    best_friends = ZODIAC_BEST_FRIENDS.get(my_sign, [])
    
    text = f"👯‍♀️✨ *ИДЕАЛЬНАЯ ПОДРУГА* ✨👯‍♀️\n\n"
    text += f"Твой знак: *{ZODIAC_SIGNS[my_sign]}*\n\n"
    text += "💕 *Лучшая совместимость:*\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, (friend_sign, compat, desc) in enumerate(best_friends):
        text += f"{medals[i]} *{ZODIAC_SIGNS[friend_sign]}* — {compat}%\n   💬 _{desc}_\n\n"
    
    text += "🌟 _Найди подругу с идеальным знаком и проверьте свою дружбу тестом!_"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💕 Проверить совместимость", callback_data="zodiac_select")],
        [InlineKeyboardButton("💎 Талисманы", callback_data="zodiac_talismans")],
        [InlineKeyboardButton("🔙 Назад", callback_data="zodiac_back")]
    ])
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def zodiac_talismans(update, context):
    """Талисманы по знаку зодиака"""
    query = update.callback_query
    try: await query.answer()
    except: pass
    
    user = get_user(query.from_user.id)
    db_user = get_user(query.from_user.id)
    my_sign = db_user.get("zodiac_sign") if db_user else "leo"
    db_user = get_user(query.from_user.id); my_sign = db_user.get("zodiac_sign") if db_user else "leo"
    db_user = get_user(query.from_user.id); my_sign = db_user.get("zodiac_sign") if db_user else "leo"
    tal = ZODIAC_TALISMANS.get(my_sign, ZODIAC_TALISMANS['leo'])
    
    text = f"💎✨ *ТАЛИСМАНЫ* ✨💎\n\n"
    text += f"Для *{ZODIAC_SIGNS[my_sign]}*\n\n"
    text += f"🌸 *Цвет удачи:* {tal['color']}\n"
    text += f"💎 *Камень:* {tal['stone']} (защищает дружбу)\n"
    text += f"🌺 *Цветок:* {tal['flower']}\n"
    text += f"💍 *Металл:* {tal['metal']}\n\n"
    text += "💕 _Подари подруге талисман с её камнем — дружба станет крепче!_"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👯‍♀️ Идеальная подруга", callback_data="zodiac_best_friend")],
        [InlineKeyboardButton("🔙 Назад", callback_data="zodiac_back")]
    ])
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)



async def ask_profile_name(update, context):
    context.user_data["profile_setup"] = {"step": "name"}
    await update.message.reply_text(
        "🌸✨ *ПРИВЕТ, ПОДРУЖКА!* ✨🌸\n\n"
        "💕 Давай знакомиться! Расскажи немного о себе.\n\n"
        "👤 *Как тебя зовут?*\n"
        "_Напиши своё имя_",
        parse_mode=ParseMode.MARKDOWN
    )
















async def handle_profile_setup(update, context):
    if "profile_setup" not in context.user_data:
        return False
    profile = context.user_data["profile_setup"]
    text = update.message.text.strip()
    step = profile.get("step")
    if step == "name":
        if len(text) < 2 or len(text) > 30:
            await update.message.reply_text("Имя должно быть от 2 до 30 символов!")
            return True
        profile["name"] = text
        profile["step"] = "age"
        await update.message.reply_text(
            f"*{text}*, сколько тебе лет?\n\n_Напиши свой возраст (например: 14)_",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return True
    elif step == "age":
        try:
            age = int(text)
            if age < 5 or age > 99:
                await update.message.reply_text("Напиши реальный возраст!")
                return True
            profile["age"] = age
            profile["step"] = "zodiac"
            kb = []
            signs = list(ZODIAC_SIGNS.items())
            for i in range(0, 12, 3):
                row = []
                for j in range(3):
                    if i+j < 12:
                        key, name = signs[i+j]
                        row.append(InlineKeyboardButton(name, callback_data=f"profile_zodiac_{key}"))
                kb.append(row)
            await update.message.reply_text(
                f"*{age} лет* - супер!\n\nТеперь выбери свой знак зодиака:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return True
        except ValueError:
            await update.message.reply_text("Напиши число! Например: 14")
            return True
    return False


async def handle_profile_zodiac(update, context):
    query = update.callback_query
    try: await query.answer()
    except: pass
    if "profile_setup" not in context.user_data:
        return False
    profile = context.user_data["profile_setup"]
    zodiac = query.data.replace("profile_zodiac_", "")
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET first_name = ?, age = ?, zodiac_sign = ? WHERE user_id = ?",
              (profile["name"], profile["age"], zodiac, query.from_user.id))
    conn.commit()
    conn.close()
    context.user_data["zodiac_sign"] = zodiac
    del context.user_data["profile_setup"]
    user = query.from_user
    available = get_available_tests_count(user.id)
    word = decline_word(available, "тест", "теста", "тестов")
    text = (f"🌸✨ *{profile['name']}, ТВОЙ ПРОФИЛЬ ГОТОВ!* ✨🌸\n\n"
            f"🎂 *{profile['age']} лет* • ⭐ *{ZODIAC_SIGNS[zodiac]}*\n\n"
            f"📊 Тестов доступно: *{available} {word}*\n\n"
            f"💕 _Создай тест о себе и отправь подругам!_\n"
            f"👯‍♀️ _Узнайте кто знает тебя лучше всех!_")
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    await context.bot.send_message(chat_id=user.id, text="🌸", reply_markup=get_main_keyboard(user.id))
    
    # Проверяем есть ли отложенный тест
    db_user = get_user(user.id); pending_test_id = db_user.get('pending_test') if db_user else None
    if pending_test_id:
        await asyncio.sleep(5)
        await context.bot.send_message(
            chat_id=user.id,
            text="🌸 _Загружаем тест от твоей подруги..._ 💕",
            parse_mode=ParseMode.MARKDOWN
        )
        await asyncio.sleep(5)
        test = get_test_by_id(pending_test_id)
        if test:
            creator = get_user(test['creator_id'])
            creator_display = test['creator_name']
            if creator and creator.get('username'):
                creator_display += f" @{creator['username']}"
            
            q_count = len(test['questions'])
            q_word = decline_word(q_count, "вопрос", "вопроса", "вопросов")
            
            greeting_text = ""
            if test.get('greeting_file_id'):
                if test.get('greeting_type') == 'voice':
                    greeting_text = "\n🎤 Подружка записала для тебя *голосовое поздравление*!"
                elif test.get('greeting_type') == 'video':
                    greeting_text = "\n🎥 Подружка сняла для тебя *видео-поздравление*!"
            
            invite_text = (f"🌸✨ *ПРИВЕТ, {profile['name']}!* ✨🌸\n\n"
                    f"💕 {creator_display} приглашает тебя пройти тест!\n\n"
                    f"📝 *{test['title']}*\n"
                    f"💭 {q_count} {q_word} о ней\n"
                    f"{greeting_text}\n"
                    f"🎓 Именной *диплом* ждёт тебя!\n\n"
                    f"👇 Нажми на кнопку и начни! 💖")
            
            await context.bot.send_message(
                chat_id=user.id,
                text=invite_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_{pending_test_id}")]])
            )
        conn = get_db(); c = conn.cursor(); c.execute('UPDATE users SET pending_test = NULL WHERE user_id = ?', (user.id,)); conn.commit()
    
    return True



def generate_daily_horoscope(sign):
    today = datetime.now().strftime('%Y%m%d')
    random.seed(f"{sign}{today}")
    
    beginnings = [
        "🌟 Звёзды сегодня особенны для тебя!", "✨ Космическая энергия на твоей стороне!",
        "💫 День полный сюрпризов и открытий!", "🌸 Вселенная приготовила для тебя кое-что особенное!",
        "🦋 Сегодня твой день сиять!", "⭐ Планеты выстроились в твою пользу!",
        "🌈 Радужное настроение обеспечено!", "🔥 Энергия дня заряжает тебя!",
        "💎 Драгоценный день для дружбы!", "🎯 Твоя интуиция сегодня на высоте!",
    ]
    
    friendship_tips = [
        "💬 Напиши подруге первой — она ждёт твоего сообщения!",
        "💕 Сделай подруге комплимент — это поднимет настроение вам обеим!",
        "🌳 Позови подругу на прогулку — свежий воздух и разговоры творят чудеса!",
        "🎬 Устройте совместный просмотр фильма по видеосвязи!",
        "🤫 Поделись с подругой секретом — это укрепит вашу связь!",
        "😂 Отправь подруге смешной мем — смех объединяет!",
        "🍳 Приготовь что-то вкусное и угости подругу!",
        "📸 Сделайте совместное фото — сохраните момент!",
        "📖 Вспомните вашу самую смешную историю вместе!",
        "💖 Скажи подруге как она важна для тебя!",
        "🎨 Предложи подруге новое хобби на двоих!",
        "🎵 Обменяйтесь плейлистами — узнайте друг друга через музыку!",
        "✈️ Запланируйте совместную поездку или встречу!",
        "🎁 Подари подруге маленький сюрприз без повода!",
    ]
    
    warnings = [
        "⚠️ Осторожно: не принимай близко к сердцу чужие слова.",
        "⚠️ Звёзды советуют: избегай сплетен сегодня.",
        "⚠️ Не перегружай себя — отдохни с подругой.",
        "⚠️ Возможны мелкие недоразумения — не драматизируй!",
        "⚠️ Береги свои секреты — не всем можно доверять.",
        "⚠️ Не опаздывай на встречу с подругой!",
        "⚠️ Проверь зарядку телефона — важный звонок может быть сегодня!",
    ]
    
    activities = [
        "🎨 Творчество: порисуйте или сделайте что-то руками.",
        "🎵 Музыка: устройте танцы под любимые треки!",
        "📸 Фотосессия: найдите красивое место и поснимайтесь!",
        "🍳 Кулинария: приготовьте новое блюдо вместе!",
        "🎬 Кино: посмотрите фильм который давно откладывали.",
        "💄 Бьюти: сделайте друг другу макияж или маникюр.",
        "🛍️ Шопинг: пройдитесь по любимым магазинам.",
        "🌳 Природа: погуляйте в парке или лесу.",
        "☕ Кофе: сходите в новое кафе и попробуйте десерт.",
        "🎤 Караоке: пойте любимые песни от души!",
        "💌 Письма: напишите друг другу бумажные письма.",
    ]
    
    lucky = [
        "🍀 Цвет удачи сегодня: розовый!",
        "💎 Талисман дня: маленькое сердечко!",
        "🔢 Счастливое число: " + str(random.randint(1, 99)) + "!",
        "🌟 Удача ждёт тебя во второй половине дня!",
        "💕 Сегодня везёт на комплименты!",
        "🌙 Лучшее время для дружбы: вечер!",
    ]
    
    beginning = random.choice(beginnings)
    tip = random.choice(friendship_tips)
    warning = random.choice(warnings) if random.random() > 0.3 else ""
    activity = random.choice(activities)
    lucky_text = random.choice(lucky)
    
    horoscope = f"{beginning}\n\n💕 *Дружба:* {tip}\n"
    if warning:
        horoscope += f"\n{warning}\n"
    horoscope += f"\n🎯 *Совет дня:* {activity}\n\n{lucky_text}"
    
    return horoscope

ZODIAC_DAILY_FULL = {sign: [generate_daily_horoscope(sign) for _ in range(31)] for sign in ZODIAC_SIGNS}



async def help_handler(update, context):
    text = """🌸 *ПОДРУГА ТЕСТ — ПОМОЩЬ* ✨

🎯 Что это за бот?
Создавай тесты о себе и отправляй подругам! Узнайте кто знает тебя лучше всех!

📋 Кнопки меню:
🌸 — Создать тест о себе
👑 — Мои тесты и ответы подруг
🏆 — Рейтинг подруг кто лучше всех знает тебя
⭐ — Зодиак гороскопы и совместимость
💎 — Премиум безлимитные тесты

💡 Как создать тест:
1. Нажми 🌸
2. Придумай название
3. Выбери тему вопросов
4. Добавь варианты ответов
5. Отправь подругам!

🔮 Зодиак-челлендж:
Собирай знаки зодиака подруг! Отправляй тесты и проходи сама — собирай коллекцию из 12 знаков!

📊 Бесплатно: 5 тестов
💎 Премиум: безлимитно + ответы подруг + дипломы

💕 По вопросам: @SergeyMarko"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)



# === MAIN ===



def main():
    global bot_application
    app = Application.builder().token(TOKEN).build()
    bot_application = app
    
    # Фоновая проверка платежей каждые 60 секунд
    job_queue = app.job_queue
    job_queue.run_repeating(payment_checker, interval=60, first=10)
    # Ежедневный вопрос в 10:00 МСК
    job_queue.run_daily(daily_question_broadcast, time=datetime_time(hour=7, minute=0))
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^🌸"), create_test_start))
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

