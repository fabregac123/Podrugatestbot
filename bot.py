#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PodrugaTestBot — простой бот для тестов между подругами
Версия: 4.0 — ПОЛНЫЙ КОД СО ВСЕМИ ИСПРАВЛЕНИЯМИ
"""

import logging
import json
import sqlite3
import random
import os
import asyncio
import hashlib
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
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
DB_NAME = 'bot_simple.db'
FREE_TESTS_LIMIT = 3
MAX_QUESTIONS = 10
MAX_OPTIONS = 4
ADMIN_ID = 710623393

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# === СКЛОНЕНИЕ СЛОВ ===
def decline_word(number, word1, word2, word3):
    if 11 <= number % 100 <= 19:
        return word3
    if number % 10 == 1:
        return word1
    if 2 <= number % 10 <= 4:
        return word2
    return word3

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

# === ВОПРОСЫ ПО КАТЕГОРИЯМ (по 20 в каждой) ===
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
    if score >= 90: return "👯‍♀️ СЁСТРЫ НАВЕК! 💕"
    if score >= 70: return "💎 ЛУЧШИЕ ПОДРУГИ! 💎"
    if score >= 50: return "🌸 ХОРОШИЕ ПОДРУЖКИ! 🌸"
    if score >= 30: return "👋 ПРИЯТЕЛЬНИЦЫ! 👋"
    return "🤔 ПОКА ЗНАКОМЫЕ 🤔"

def get_friendship_prediction(score, name):
    """Генерирует персональное предсказание дружбы"""
    if score >= 90:
        predictions = [
            f"💕 {name} — твоя родственная душа! Вы понимаете друг друга с полуслова. Береги эту дружбу, она особенная!",
            f"👯‍♀️ {name} знает тебя лучше всех! Вы как сёстры — такие друзья встречаются раз в жизни.",
            f"🌟 {name} — твой идеальный мэтч в дружбе! Вы созданы друг для друга!"
        ]
    elif score >= 70:
        predictions = [
            f"💎 {name} очень хорошо тебя знает! Вы близкие подруги, и ваша дружба только крепнет.",
            f"🌸 {name} понимает тебя почти во всём. Ещё немного — и вы станете лучшими подругами!",
            f"✨ Вы с {name} на одной волне! Продолжайте узнавать друг друга ещё лучше."
        ]
    elif score >= 50:
        predictions = [
            f"👭 {name} знает тебя неплохо, но есть куда расти! Проводите больше времени вместе.",
            f"🌱 Ваша дружба с {name} только расцветает! Узнавайте друг друга глубже.",
            f"💫 {name} уже многое о тебе знает. Ещё немного — и вы станете ближе!"
        ]
    elif score >= 30:
        predictions = [
            f"👋 {name} только начинает тебя узнавать. Это отличный повод пообщаться побольше!",
            f"🤝 Вы с {name} на пути к настоящей дружбе. Не останавливайтесь!",
            f"🌿 {name} знает о тебе основы. Расскажи ей о себе побольше!"
        ]
    else:
        predictions = [
            f"🤔 {name} пока плохо тебя знает. Но это только начало вашей дружбы!",
            f"💭 {name} ещё предстоит узнать тебя получше. Устройте совместную прогулку!",
            f"🌙 Ваша дружба с {name} только зарождается. Впереди много интересного!"
        ]
    return random.choice(predictions)

def get_detailed_stats(score):
    """Возвращает детальную статистику"""
    if score >= 90:
        return "🌟 ЭКСПЕРТ", "Знает тебя наизусть!"
    elif score >= 70:
        return "💎 ПРОФИ", "Отлично тебя знает!"
    elif score >= 50:
        return "🌸 ЛЮБИТЕЛЬ", "Хорошо тебя знает"
    elif score >= 30:
        return "🌱 НОВИЧОК", "Только узнаёт тебя"
    else:
        return "🤔 НЕЗНАКОМКА", "Почти не знает тебя"

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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    try:
        c.execute('ALTER TABLE tests ADD COLUMN greeting_type TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE tests ADD COLUMN greeting_file_id TEXT')
    except:
        pass
    
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

def can_create_test(user_id):
    if is_premium(user_id):
        return True
    user = get_user(user_id)
    if not user:
        return True
    return user.get('tests_created', 0) < FREE_TESTS_LIMIT

def get_user_tests(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, title, created_at FROM tests WHERE creator_id = ? ORDER BY created_at DESC', (user_id,))
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

def create_test(creator_id, creator_name, title, questions, options, correct_answers, greeting_type=None, greeting_file_id=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO tests (creator_id, creator_name, title, questions, options, correct_answers, greeting_type, greeting_file_id)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (creator_id, creator_name, title, json.dumps(questions), json.dumps(options), 
               json.dumps(correct_answers), greeting_type, greeting_file_id))
    test_id = c.lastrowid
    c.execute('UPDATE users SET tests_created = tests_created + 1 WHERE user_id = ?', (creator_id,))
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
    c.execute('''INSERT INTO attempts (test_id, friend_id, friend_name, answers, score)
                 VALUES (?, ?, ?, ?, ?)''',
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

def get_all_users():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users')
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    return users

# === ДИПЛОМ ===
async def generate_diploma(user_name, test_title, score, status, is_premium_user):
    width, height = 1000, 700
    bg_color = '#0D1117' if is_premium_user else '#1A1A2E'
    image = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(image)
    
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        font_score = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 100)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except:
        font_title = ImageFont.load_default()
        font_name = ImageFont.load_default()
        font_score = ImageFont.load_default()
        font_text = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    primary = '#FFD700' if is_premium_user else '#E31B6D'
    text_white = '#FFFFFF'
    text_gray = '#B0B0B0'
    
    draw.rectangle([0, 0, width, 4], fill=primary)
    draw.rectangle([0, height-4, width, height], fill=primary)
    
    title = "💎 ПРЕМИУМ ДИПЛОМ 💎" if is_premium_user else "🌸 ДИПЛОМ ПОДРУЖКИ 🌸"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    title_width = bbox[2] - bbox[0]
    draw.text((width//2 - title_width//2, 50), title, fill=primary, font=font_title)
    
    icon = "👑" if is_premium_user else "📜"
    bbox = draw.textbbox((0, 0), icon, font=font_score)
    icon_width = bbox[2] - bbox[0]
    draw.text((width//2 - icon_width//2, 120), icon, fill=primary, font=font_score)
    
    name_display = user_name[:30]
    bbox = draw.textbbox((0, 0), name_display, font=font_name)
    name_width = bbox[2] - bbox[0]
    draw.text((width//2 - name_width//2, 220), name_display, fill=text_white, font=font_name)
    
    test_display = test_title[:40]
    bbox = draw.textbbox((0, 0), test_display, font=font_text)
    test_width = bbox[2] - bbox[0]
    draw.text((width//2 - test_width//2, 280), test_display, fill=text_gray, font=font_text)
    
    score_color = '#2EA043' if score >= 70 else '#FFA500' if score >= 50 else '#FF4444'
    score_text = f"{score:.0f}%"
    bbox = draw.textbbox((0, 0), score_text, font=font_score)
    score_width = bbox[2] - bbox[0]
    draw.text((width//2 - score_width//2, 350), score_text, fill=score_color, font=font_score)
    
    bbox = draw.textbbox((0, 0), status, font=font_text)
    status_width = bbox[2] - bbox[0]
    draw.text((width//2 - status_width//2, 470), status, fill=primary, font=font_text)
    
    congrats = "Поздравляем с прохождением теста!"
    bbox = draw.textbbox((0, 0), congrats, font=font_small)
    congrats_width = bbox[2] - bbox[0]
    draw.text((width//2 - congrats_width//2, 550), congrats, fill=text_gray, font=font_small)
    
    date_text = datetime.now().strftime("%d.%m.%Y")
    draw.text((50, height-40), date_text, fill=text_gray, font=font_small)
    
    cert_id = hashlib.md5(f"{user_name}{test_title}{datetime.now()}".encode()).hexdigest()[:8].upper()
    cert_text = f"ID: {cert_id}"
    bbox = draw.textbbox((0, 0), cert_text, font=font_small)
    cert_width = bbox[2] - bbox[0]
    draw.text((width-50-cert_width, height-40), cert_text, fill=text_gray, font=font_small)
    
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
        [KeyboardButton("📊 Статистика"), KeyboardButton("🎁 Подарить премиум")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True)

def get_options_keyboard():
    return ReplyKeyboardMarkup(
        [["➕ Добавить вариант", "✅ Готово", "🔙 Назад"]],
        resize_keyboard=True, 
        one_time_keyboard=True
    )

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
    return InlineKeyboardMarkup(keyboard)

def get_question_choice_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Другой вопрос", callback_data="next_question"),
         InlineKeyboardButton("🎲 Случайный", callback_data="random_question")],
        [InlineKeyboardButton("✅ Этот вопрос", callback_data="select_question")]
    ])

def get_test_actions_keyboard(test_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁 Посмотреть", callback_data=f"view_{test_id}"),
         InlineKeyboardButton("📤 Поделиться", callback_data=f"share_{test_id}")],
        [InlineKeyboardButton("📊 Ответы подруг", callback_data=f"answers_{test_id}"),
         InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{test_id}")]
    ])

def get_share_keyboard(test_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👭 Поделиться с подругой", 
            switch_inline_query=f"💕 Привет! Пройди тест обо мне и узнай, насколько хорошо ты меня знаешь! 💕\n\n👉 https://t.me/{BOT_USERNAME}?start=test_{test_id}")]
    ])

def get_premium_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Премиум на месяц — 199₽", callback_data="buy_month")],
        [InlineKeyboardButton("💎 Премиум на год — 1299₽", callback_data="buy_year")]
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
            text = (f"🌸✨ ПРИВЕТ, {user.first_name}! ✨🌸\n\n"
                    f"💕 {test['creator_name']} приглашает тебя пройти тест!\n\n"
                    f"📝 *{test['title']}*\n\n"
                    f"👇 Нажми на кнопку и начни!")
            await message.reply_text(
                text, 
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎮 Начать тест", callback_data=f"start_{test_id}")
                ]])
            )
            return
    
    user_data = get_user(user.id)
    tests_created = user_data.get('tests_created', 0)
    is_prem = is_premium(user.id)
    
    if is_prem:
        text = (f"🌸✨ *ПРИВЕТ, {user.first_name}!* ✨🌸\n\n"
                f"Создай тест о себе и отправь подружке!\n"
                f"Узнайте, насколько хорошо вы друг друга знаете 💕\n\n"
                f"💎 *Статус:* ПРЕМИУМ ✨\n"
                f"♾️ *Безлимитные тесты*\n"
                f"📊 *Создано:* {tests_created} тестов\n\n"
                f"Выбирай действие в меню 👇")
    else:
        text = (f"🌸✨ *ПРИВЕТ, {user.first_name}!* ✨🌸\n\n"
                f"Создай тест о себе и отправь подружке!\n"
                f"Узнайте, насколько хорошо вы друг друга знаете 💕\n\n"
                f"🎁 *Бесплатно:* {FREE_TESTS_LIMIT} теста\n"
                f"📊 *Создано:* {tests_created}/{FREE_TESTS_LIMIT}\n\n"
                f"💎 Хочешь безлимит и красивый диплом? Жми «💎 Премиум»\n\n"
                f"Выбирай действие в меню 👇")
    
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user.id))

# === АДМИН-ПАНЕЛЬ ===
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа!")
        return
    await update.message.reply_text("🔧 *АДМИН-ПАНЕЛЬ*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    users = get_all_users()
    total_users = len(users)
    premium_users = sum(1 for u in users if u.get('premium_until') and datetime.fromisoformat(u['premium_until']) > datetime.now())
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM tests')
    total_tests = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM attempts')
    total_attempts = c.fetchone()[0]
    c.execute('SELECT AVG(score) FROM attempts')
    avg_score = c.fetchone()[0] or 0
    conn.close()
    
    text = (f"📊 *СТАТИСТИКА БОТА*\n\n"
            f"👥 Пользователей: *{total_users}*\n"
            f"💎 Премиум активных: *{premium_users}*\n"
            f"📝 Тестов создано: *{total_tests}*\n"
            f"🎯 Пройдено тестов: *{total_attempts}*\n"
            f"📊 Средний результат: *{avg_score:.1f}%*\n\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y')}")
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

async def admin_give_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    context.user_data['admin_action'] = 'give_premium'
    await update.message.reply_text(
        "🎁 *ПОДАРИТЬ ПРЕМИУМ*\n\n"
        "Введите username или ID пользователя:\n"
        "Например: @anna или 123456789",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    action = context.user_data.get('admin_action')
    if action != 'give_premium':
        return
    
    text = update.message.text.strip().lstrip('@')
    
    conn = get_db()
    c = conn.cursor()
    if text.isdigit():
        c.execute('SELECT user_id, first_name FROM users WHERE user_id = ?', (int(text),))
    else:
        c.execute('SELECT user_id, first_name FROM users WHERE username = ?', (text,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await update.message.reply_text(f"❌ Пользователь {text} не найден", reply_markup=get_admin_keyboard())
        del context.user_data['admin_action']
        return
    
    target_user_id = row['user_id']
    target_name = row['first_name'] or text
    
    give_premium(target_user_id, 30)
    
    await update.message.reply_text(
        f"✅ *{target_name}* получил премиум на 30 дней! 🎉",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )
    
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎉✨ *ПОЗДРАВЛЯЕМ!* ✨🎉\n\n💎 Вам подарен *ПРЕМИУМ* на 30 дней!\n\n♾️ Безлимитные тесты\n🎓 Красивый диплом\n📊 Ответы подруг\n\n💖 Приятного использования!",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass
    
    del context.user_data['admin_action']

# === СОЗДАНИЕ ТЕСТА ===
async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not can_create_test(user_id):
        await update.message.reply_text(
            f"💔 *Лимит бесплатных тестов!* 💔\n\n"
            f"Ты создала {FREE_TESTS_LIMIT} теста.\n"
            f"💎 *Купи Премиум* для безлимита и красивых дипломов!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    context.user_data['creating_test'] = {'step': 'title'}
    await update.message.reply_text(
        "🌸 *СОЗДАЁМ ТЕСТ*\n\n"
        "Придумай красивое название:\n"
        "Например: «Насколько хорошо ты меня знаешь?»\n\n"
        "❌ *Отмена* — чтобы выйти",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

async def handle_create_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data:
        return
    
    text = update.message.text.strip()
    step = data.get('step')
    
    if step == 'title':
        if len(text) < 3:
            await update.message.reply_text("⚠️ Название должно быть длиннее 3 символов!")
            return
        data['title'] = text
        data['step'] = 'group'
        await update.message.reply_text("✨ Выбери тему для вопросов:", reply_markup=get_question_groups_keyboard())
    
    elif step == 'questions_count':
        try:
            count = int(text)
            if count < 2 or count > MAX_QUESTIONS:
                await update.message.reply_text(f"⚠️ От 2 до {MAX_QUESTIONS} вопросов!")
                return
            data['total_q'] = count
            data['current_q'] = 0
            data['questions_data'] = []
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎤 Голосовое", callback_data="greeting_voice"),
                 InlineKeyboardButton("🎥 Видео", callback_data="greeting_video")],
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="greeting_skip")]
            ])
            await update.message.reply_text(
                "🎬✨ *ДОБАВЬ ПОЗДРАВЛЕНИЕ!* ✨🎬\n\n"
                "Твоя подружка получит его после прохождения теста!\n\n"
                "👇 Выбери тип или пропусти:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            data['step'] = 'greeting'
            
        except ValueError:
            await update.message.reply_text("⚠️ Напиши число!")
    
    elif step == 'collecting_options':
        if data.get('waiting_for_option'):
            if len(text) > 50:
                await update.message.reply_text("⚠️ Слишком длинный вариант! До 50 символов.")
                return
            
            data['current_options'].append(text)
            data['waiting_for_option'] = False
            
            options_list = "\n".join([f"{i+1}. {o}" for i, o in enumerate(data['current_options'])])
            
            await update.message.reply_text(
                f"✅ *Вариант {len(data['current_options'])} добавлен!* ✅\n\n"
                f"📋 *Твои варианты:*\n{options_list}\n\n"
                f"➕ *Можешь добавить ещё или нажать «Готово»*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_options_keyboard()
            )

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
    await query.message.reply_text(
        f"📊 Сколько вопросов будет в тесте?\n🔹 От 2 до {MAX_QUESTIONS} вопросов\n\n✏️ Напиши число:",
        reply_markup=get_cancel_keyboard()
    )

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
        
        await query.message.reply_text("✨ *Отлично! Приступаем к вопросам!* ✨", parse_mode=ParseMode.MARKDOWN)
        await show_question_for_selection(query, context)
        return
    
    data['greeting_type'] = choice
    data['waiting_greeting'] = True
    
    if choice == "voice":
        text = "🎤 Отправь голосовое сообщение (до 15 секунд)\n\n❌ *Отмена* — чтобы пропустить"
    else:
        text = "🎥 Отправь видео (до 15 секунд)\n\n❌ *Отмена* — чтобы пропустить"
    
    await query.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

async def save_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data or not data.get('waiting_greeting'):
        return
    
    greeting_type = data['greeting_type']
    
    if greeting_type == "voice":
        if not update.message.voice:
            await update.message.reply_text("❌ Отправь голосовое сообщение!")
            return
        file_id = update.message.voice.file_id
    else:
        if not update.message.video:
            await update.message.reply_text("❌ Отправь видео!")
            return
        file_id = update.message.video.file_id
    
    data['greeting_file_id'] = file_id
    data['waiting_greeting'] = False
    data['step'] = 'selecting_question'
    data['current_question_index'] = 0
    
    await update.message.reply_text(
        "✅ *Поздравление сохранено!*\n\n"
        "✨ *Приступаем к вопросам!* ✨",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(update.effective_user.id)
    )
    
    await show_question_for_selection(update, context)

async def show_question_for_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data:
        return
    
    questions = data.get('group_questions', [])
    data['current_question_index'] = data.get('current_question_index', 0)
    question_text = questions[data['current_question_index']]
    data['current_question'] = question_text
    
    text = (f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n"
            f"{question_text}\n\n"
            f"👇 *Что делаем с этим вопросом?*")
    
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
    current_idx = data.get('current_question_index', 0)
    current_idx = (current_idx + 1) % len(questions)
    data['current_question_index'] = current_idx
    data['current_question'] = questions[current_idx]
    
    text = (f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n"
            f"{questions[current_idx]}\n\n"
            f"👇 *Что делаем с этим вопросом?*")
    
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
    
    text = (f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n"
            f"{all_questions[0]}\n\n"
            f"👇 *Что делаем с этим вопросом?*")
    
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
    
    await query.message.reply_text(
        f"📝 *Вопрос:* {data['current_question']}\n\n"
        f"✏️ *Напиши вариант ответа №1:*\n\n"
        f"💡 *Совет:* Варианты должны быть разными и понятными",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )

async def select_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    correct_idx = int(query.data.replace("correct_", ""))
    data = context.user_data.get('creating_test')
    if not data:
        return
    
    data['questions_data'].append({
        'text': data['current_question'],
        'options': data['current_options'].copy(),
        'correct': correct_idx
    })
    
    data['current_q'] += 1
    
    if data['current_q'] < data['total_q']:
        data['step'] = 'selecting_question'
        data['current_question_index'] = (data.get('current_question_index', 0) + 1) % len(data.get('group_questions', []))
        
        await query.message.reply_text(
            f"✅ *Вопрос {data['current_q']} сохранён!* ✅\n\n"
            f"➡️ *Переходим к следующему...*",
            parse_mode=ParseMode.MARKDOWN
        )
        await show_question_for_selection(query, context)
    else:
        questions = [q['text'] for q in data['questions_data']]
        options = [q['options'] for q in data['questions_data']]
        correct = [q['correct'] for q in data['questions_data']]
        
        test_id = create_test(
            query.from_user.id,
            query.from_user.first_name,
            data['title'],
            questions,
            options,
            correct,
            data.get('greeting_type'),
            data.get('greeting_file_id')
        )
        
        del context.user_data['creating_test']
        
        text = (f"🎉✨ *ТЕСТ ГОТОВ!* ✨🎉\n\n"
                f"📝 *{data['title']}*\n"
                f"🔢 Вопросов: {len(questions)}\n\n"
                f"💖 Отправь ссылку подружке!")
        
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_share_keyboard(test_id)
        )
        await query.message.reply_text("🌸 Главное меню:", reply_markup=get_main_keyboard(query.from_user.id))

# === МОИ ТЕСТЫ ===
async def my_tests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tests = get_user_tests(user_id)
    
    if not tests:
        await update.message.reply_text(
            "🌸 *У тебя пока нет тестов!*\n\n"
            "Создай свой первый тест через кнопку «🌸 Создать тест» 💕",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user_id)
        )
        return
    
    text = f"👑✨ *МОИ ТЕСТЫ* ✨👑\n\n"
    for t in tests:
        word = decline_word(t['attempts'], "подруга", "подруги", "подруг")
        text += f"📝 *{t['title'][:30]}*\n   👥 Прошли: {t['attempts']} {word}\n   📅 {t['created_at'][:10]}\n\n"
    
    text += "👇 Выбери тест для управления:"
    
    keyboard = []
    for t in tests[:10]:
        keyboard.append([InlineKeyboardButton(f"📝 {t['title'][:30]}", callback_data=f"mytest_{t['id']}")])
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def my_test_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.replace("mytest_", ""))
    test = get_test_by_id(test_id)
    
    if not test:
        await query.message.reply_text("💔 Тест не найден")
        return
    
    attempts = get_test_attempts(test_id)
    avg_score = sum(a['score'] for a in attempts) / len(attempts) if attempts else 0
    
    text = (f"📝 *{test['title']}*\n\n"
            f"👥 Прошли: {len(attempts)} подруг\n"
            f"🎯 Средний результат: {avg_score:.0f}%\n\n"
            f"👇 Выбери действие:")
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_test_actions_keyboard(test_id))

# === ПРОХОЖДЕНИЕ ТЕСТА ===
async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    test_id = int(query.data.replace("start_", ""))
    test = get_test_by_id(test_id)
    
    if not test:
        await query.message.reply_text("💔 Тест не найден")
        return
    
    context.user_data['taking_test'] = {'test': test, 'current': 0, 'answers': []}
    await send_question(query, context)

async def send_question(query, context):
    data = context.user_data.get('taking_test')
    test = data['test']
    current = data['current']
    
    text = f"❓ *Вопрос {current + 1}/{len(test['questions'])}*\n\n{test['questions'][current]}"
    
    keyboard = []
    for i, opt in enumerate(test['options'][current]):
        keyboard.append([InlineKeyboardButton(opt[:40], callback_data=f"answer_{i}")])
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    answer_idx = int(query.data.replace("answer_", ""))
    data = context.user_data.get('taking_test')
    if not data:
        return
    
    data['answers'].append(answer_idx)
    data['current'] += 1
    
    if data['current'] < len(data['test']['questions']):
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
    is_prem = is_premium(test['creator_id'])
    
    text = (f"🎉 *ТЕСТ ПРОЙДЕН!* 🎉\n\n"
            f"👤 *{user.first_name}*\n"
            f"📝 *{test['title']}*\n"
            f"🎯 *Результат:* {score:.0f}%\n"
            f"🏆 *{status}*")
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    if test.get('greeting_file_id'):
        try:
            caption = "🎬✨ *ПОЗДРАВЛЕНИЕ ОТ ПОДРУЖКИ* ✨🎬"
            if test.get('greeting_type') == 'voice':
                await query.message.reply_voice(test['greeting_file_id'], caption=caption, parse_mode=ParseMode.MARKDOWN)
            elif test.get('greeting_type') == 'video':
                await query.message.reply_video(test['greeting_file_id'], caption=caption, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Ошибка отправки поздравления: {e}")
    
    diploma = await generate_diploma(user.first_name, test['title'], score, status, is_prem)
    await query.message.reply_photo(diploma, caption="🎓 *ТВОЙ ДИПЛОМ!* 🎓", parse_mode=ParseMode.MARKDOWN)
    await query.message.reply_text("🌸 *Главное меню:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user.id))
    
    del context.user_data['taking_test']

# === ПРЕМИУМ ===
async def premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_prem = is_premium(user_id)
    
    if is_prem:
        user = get_user(user_id)
        expiry = datetime.fromisoformat(user['premium_until']).strftime('%d.%m.%Y')
        text = f"💎✨ *У ТЕБЯ ПРЕМИУМ!* ✨💎\n\n♾️ Безлимитные тесты\n🎓 Красивый диплом\n📊 Ответы подруг\n\n📅 Действует до: {expiry}"
    else:
        text = (f"💎 *ПРЕМИУМ ПОДПИСКА*\n\n✨ Что даёт:\n♾️ Безлимитные тесты\n🎓 Красивый золотой диплом\n📊 Смотреть ответы подруг\n\n"
                f"💰 Стоимость:\n• 199₽ — месяц\n• 1299₽ — год\n\n👇 Выбери тариф:")
    
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_premium_keyboard() if not is_prem else get_main_keyboard(user_id)
    )

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    is_month = query.data == "buy_month"
    price = "199₽" if is_month else "1299₽"
    await query.message.reply_text(
        f"💎 *ОПЛАТА ПРЕМИУМА*\n\nТариф: {'месяц' if is_month else 'год'}\nСумма: {price}\n\n"
        f"Для оплаты напишите: @LavaTopBot\nПосле оплаты сообщите админу: @SergeyMarko\n\n💖 Спасибо за поддержку!",
        parse_mode=ParseMode.MARKDOWN
    )

# === ОБРАБОТЧИКИ КНОПОК ===
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
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
    elif text == "🎁 Подарить премиум" and user_id == ADMIN_ID:
        await admin_give_premium_start(update, context)
    elif text == "❌ Отмена":
        if 'creating_test' in context.user_data:
            del context.user_data['creating_test']
            await update.message.reply_text("❌ Создание отменено", reply_markup=get_main_keyboard(user_id))
        elif context.user_data.get('admin_action'):
            del context.user_data['admin_action']
            await update.message.reply_text("❌ Отменено", reply_markup=get_admin_keyboard())
        else:
            await start(update, context)
    elif text == "🔙 Назад":
        data = context.user_data.get('creating_test')
        if data and data.get('step') == 'collecting_options':
            data['step'] = 'selecting_question'
            await update.message.reply_text("🔙 Возвращаемся к выбору вопроса...")
            await show_question_for_selection(update, context)
        elif user_id == ADMIN_ID and context.user_data.get('admin_action'):
            del context.user_data['admin_action']
            await start(update, context)
        else:
            await start(update, context)
    elif text == "➕ Добавить вариант":
        data = context.user_data.get('creating_test')
        if data and data.get('step') == 'collecting_options':
            if len(data.get('current_options', [])) >= MAX_OPTIONS:
                await update.message.reply_text(
                    f"⚠️ *Максимум {MAX_OPTIONS} вариантов!* Нажми «✅ Готово»",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_options_keyboard()
                )
                return
            data['waiting_for_option'] = True
            await update.message.reply_text(
                f"✏️ *Напиши вариант №{len(data['current_options']) + 1}:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_cancel_keyboard()
            )
    elif text == "✅ Готово":
        data = context.user_data.get('creating_test')
        if data and data.get('step') == 'collecting_options':
            options = data.get('current_options', [])
            if len(options) < 2:
                await update.message.reply_text(
                    f"⚠️ *Нужно минимум 2 варианта!* Добавь ещё",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_options_keyboard()
                )
                data['waiting_for_option'] = True
                return
            
            keyboard = []
            for i, opt in enumerate(options):
                keyboard.append([InlineKeyboardButton(f"{i+1}. {opt[:30]}", callback_data=f"correct_{i}")])
            
            await update.message.reply_text(
                f"❓ *Вопрос:* {data['current_question']}\n\n"
                f"👇 *Какой вариант ПРАВИЛЬНЫЙ?* 👇",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            data['waiting_for_option'] = False
    else:
        if 'creating_test' in context.user_data:
            await handle_create_test(update, context)
        elif context.user_data.get('admin_action'):
            await handle_admin_input(update, context)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("group_"):
        await select_question_group(update, context)
    elif data == "next_question":
        await next_question_callback(update, context)
    elif data == "random_question":
        await random_question_callback(update, context)
    elif data == "select_question":
        await select_this_question(update, context)
    elif data.startswith("correct_"):
        await select_correct(update, context)
    elif data.startswith("greeting_"):
        await greeting_choice(update, context)
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
            text = f"📝 *{test['title']}*\n\n*Вопросы и ответы:*\n"
            for i, q in enumerate(test['questions'], 1):
                text += f"\n*{i}. {q}*\n"
                for j, opt in enumerate(test['options'][i-1]):
                    prefix = "✅" if j == test['correct_answers'][i-1] else "➖"
                    text += f"   {prefix} {opt}\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_test_{test_id}")]
            ])
            
            await query.message.reply_text(text[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    elif data.startswith("back_to_test_"):
        test_id = int(data.replace("back_to_test_", ""))
        test = get_test_by_id(test_id)
        if test:
            attempts = get_test_attempts(test_id)
            avg_score = sum(a['score'] for a in attempts) / len(attempts) if attempts else 0
            
            text = (f"📝 *{test['title']}*\n\n"
                    f"👥 Прошли: {len(attempts)} подруг\n"
                    f"🎯 Средний результат: {avg_score:.0f}%\n\n"
                    f"👇 Выбери действие:")
            
            await query.message.edit_text(
                text, 
                parse_mode=ParseMode.MARKDOWN, 
                reply_markup=get_test_actions_keyboard(test_id)
            )
    elif data.startswith("share_"):
        test_id = int(data.replace("share_", ""))
        await query.message.reply_text("📤 *Поделись тестом с подругой!*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(test_id))
    elif data.startswith("answers_"):
        test_id = int(data.replace("answers_", ""))
        user_id = query.from_user.id
        
        if not is_premium(user_id):
            await query.answer("💎 Только для ПРЕМИУМ!", show_alert=True)
            return
        
        test = get_test_by_id(test_id)
        attempts = get_test_attempts(test_id)
        
        if not attempts:
            await query.message.reply_text("👻 *Пока никто не прошёл тест*", parse_mode=ParseMode.MARKDOWN)
            return
        
        text = f"📊 *ОТВЕТЫ ПОДРУГ*\n\n"
        text += f"📝 *{test['title']}*\n\n"
        text += f"👥 *Прошли тест:* {len(attempts)} подруг\n\n"
        text += f"👇 *Выбери подругу, чтобы посмотреть её ответы:*"
        
        keyboard = []
        for a in attempts[:10]:
            name = a['friend_name'][:20]
            keyboard.append([InlineKeyboardButton(
                f"👤 {name}: {a['score']:.0f}%", 
                callback_data=f"friend_details_{test_id}_{a['friend_name']}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_test_{test_id}")])
        
        await query.message.reply_text(
            text, 
            parse_mode=ParseMode.MARKDOWN, 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data.startswith("friend_details_"):
        parts = data.split("_", 2)
        test_id = int(parts[2].split("_")[0])
        friend_name = parts[2].split("_", 1)[1] if "_" in parts[2] else parts[2]
        
        test = get_test_by_id(test_id)
        attempts = get_test_attempts(test_id)
        
        attempt = None
        for a in attempts:
            if a['friend_name'] == friend_name:
                attempt = a
                break
        
        if not attempt:
            await query.answer("❌ Ответы не найдены", show_alert=True)
            return
        
        score = attempt['score']
        level, description = get_detailed_stats(score)
        prediction = get_friendship_prediction(score, friend_name)
        
        text = f"👤 *{friend_name}*\n"
        text += f"📝 *{test['title']}*\n"
        text += f"━━━━━━━━━━━━━━━━\n"
        text += f"🎯 *Результат:* {score:.0f}%\n"
        text += f"🏆 *Уровень:* {level}\n"
        text += f"📊 *{description}*\n"
        text += f"━━━━━━━━━━━━━━━━\n\n"
        
        correct_count = sum(1 for i, a in enumerate(attempt['answers']) 
                           if i < len(test['correct_answers']) and a == test['correct_answers'][i])
        total_q = len(test['questions'])
        
        text += f"✅ *Правильных ответов:* {correct_count} из {total_q}\n"
        
        if score >= 80:
            text += f"💕 *Она тебя отлично знает!*\n\n"
        elif score >= 60:
            text += f"🌸 *Она тебя хорошо знает!*\n\n"
        elif score >= 40:
            text += f"👋 *Она тебя неплохо знает*\n\n"
        else:
            text += f"🤔 *Вам стоит получше узнать друг друга*\n\n"
        
        text += f"🔮 *Предсказание дружбы:*\n"
        text += f"_{prediction}_\n\n"
        
        text += "━━━━━━━━━━━━━━━━\n"
        text += "*Детальные ответы:*\n\n"
        
        for i, q in enumerate(test['questions'][:5]):
            text += f"*{i+1}. {q}*\n"
            
            if i < len(attempt['answers']):
                user_answer_idx = attempt['answers'][i]
                correct_idx = test['correct_answers'][i]
                
                is_correct = user_answer_idx == correct_idx
                user_answer = test['options'][i][user_answer_idx] if user_answer_idx < len(test['options'][i]) else "❓"
                correct_answer = test['options'][i][correct_idx]
                
                if is_correct:
                    text += f"   ✅ *{user_answer}*\n\n"
                else:
                    text += f"   ❌ *{user_answer}*\n"
                    text += f"   ✅ *Правильно: {correct_answer}*\n\n"
            else:
                text += f"   ❓ *Нет ответа*\n"
                text += f"   ✅ *Правильно: {test['options'][i][test['correct_answers'][i]]}*\n\n"
        
        if len(test['questions']) > 5:
            text += f"\n... и ещё {len(test['questions']) - 5} вопросов\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 К списку подруг", callback_data=f"answers_{test_id}")],
            [InlineKeyboardButton("📊 Общая статистика", callback_data=f"back_to_test_{test_id}")]
        ])
        
        if len(text) > 4000:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            await query.message.reply_text(parts[0], parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
            for part in parts[1:]:
                await query.message.reply_text(part, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    elif data.startswith("delete_"):
        test_id = int(data.replace("delete_", ""))
        delete_test(query.from_user.id, test_id)
        await query.message.reply_text("🗑 Тест удалён!", reply_markup=get_main_keyboard(query.from_user.id))
    elif data in ["buy_month", "buy_year"]:
        await buy_premium(update, context)
    
    await query.answer()

# === MAIN ===
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^🌸 Создать тест$"), create_test_start))
    app.add_handler(MessageHandler(filters.Regex("^👑 Мои тесты$"), my_tests_handler))
    app.add_handler(MessageHandler(filters.Regex("^💎 Премиум$"), premium_handler))
    app.add_handler(MessageHandler(filters.Regex("^🔧 Админ-панель$"), admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^📊 Статистика$"), admin_stats))
    app.add_handler(MessageHandler(filters.Regex("^🎁 Подарить премиум$"), admin_give_premium_start))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Назад$"), start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.VOICE, save_greeting))
    app.add_handler(MessageHandler(filters.VIDEO, save_greeting))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🚀✨ Бот запущен! ВСЕ ИСПРАВЛЕНИЯ ПРИМЕНЕНЫ ✨🚀")
    app.run_polling()

if __name__ == "__main__":
    main()
