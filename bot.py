#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PodrugaTestBot — бот для тестов между подругами
Версия: 9.3 — ЮKASSA API (СБП) + ПРОСТАЯ ПРОВЕРКА ПЛАТЕЖА
БЕЗ Flask, БЕЗ вебхуков, БЕЗ заморочек!
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
import yookassa
from yookassa import Payment, Configuration
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
FREE_TESTS_LIMIT = 5
MAX_QUESTIONS = 10
MAX_OPTIONS = 4
ADMIN_ID = 710623393

# ЮKassa настройки
SHOP_ID = "1337862"
SECRET_KEY = "live_bkfu6oZ_mV5Q5jr5Kp7mBuq31aeJkEKoXpLEdAZGJhA"
Configuration.account_id = SHOP_ID
Configuration.secret_key = SECRET_KEY

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

def decline_friend_word(number):
    if 11 <= number % 100 <= 19:
        return "подруг"
    if number % 10 == 1:
        return "подруга"
    if 2 <= number % 10 <= 4:
        return "подруги"
    return "подруг"

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

# === ГОТОВЫЕ НАБОРЫ ===
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
    if score >= 90: return "СЁСТРЫ НАВЕК!"
    if score >= 70: return "ЛУЧШИЕ ПОДРУГИ!"
    if score >= 50: return "ХОРОШИЕ ПОДРУЖКИ!"
    if score >= 30: return "ПРИЯТЕЛЬНИЦЫ!"
    return "ПОКА ЗНАКОМЫЕ"

def get_friendship_prediction(score, name):
    if score >= 90:
        predictions = [
            f"{name} — твоя родственная душа! Вы понимаете друг друга с полуслова. Береги эту дружбу, она особенная!",
            f"{name} знает тебя лучше всех! Вы как сёстры — такие друзья встречаются раз в жизни.",
            f"{name} — твой идеальный мэтч в дружбе! Вы созданы друг для друга!"
        ]
    elif score >= 70:
        predictions = [
            f"{name} очень хорошо тебя знает! Вы близкие подруги, и ваша дружба только крепнет.",
            f"{name} понимает тебя почти во всём. Ещё немного — и вы станете лучшими подругами!",
            f"Вы с {name} на одной волне! Продолжайте узнавать друг друга ещё лучше."
        ]
    elif score >= 50:
        predictions = [
            f"{name} знает тебя неплохо, но есть куда расти! Проводите больше времени вместе.",
            f"Ваша дружба с {name} только расцветает! Узнавайте друг друга глубже.",
            f"{name} уже многое о тебе знает. Ещё немного — и вы станете ближе!"
        ]
    elif score >= 30:
        predictions = [
            f"{name} только начинает тебя узнавать. Это отличный повод пообщаться побольше!",
            f"Вы с {name} на пути к настоящей дружбе. Не останавливайтесь!",
            f"{name} знает о тебе основы. Расскажи ей о себе побольше!"
        ]
    else:
        predictions = [
            f"{name} пока плохо тебя знает. Но это только начало вашей дружбы!",
            f"{name} ещё предстоит узнать тебя получше. Устройте совместную прогулку!",
            f"Ваша дружба с {name} только зарождается. Впереди много интересного!"
        ]
    return random.choice(predictions)

def get_detailed_stats(score):
    if score >= 90: return "ЭКСПЕРТ", "Знает тебя наизусть!"
    elif score >= 70: return "ПРОФИ", "Отлично тебя знает!"
    elif score >= 50: return "ЛЮБИТЕЛЬ", "Хорошо тебя знает"
    elif score >= 30: return "НОВИЧОК", "Только узнаёт тебя"
    else: return "НЕЗНАКОМКА", "Почти не знает тебя"

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
    except:
        pass
    try:
        c.execute('ALTER TABLE tests ADD COLUMN greeting_file_id TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE tests ADD COLUMN answer_comments TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE tests ADD COLUMN question_photos TEXT')
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
    logger.info(f"✅ Премиум выдан пользователю {user_id} на {days} дней")
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

def get_all_users():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users')
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    return users

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
    bbox = draw.textbbox((0, 0), subtitle, font=font_small)
    sub_width = bbox[2] - bbox[0]
    draw.text((width//2 - sub_width//2, y), subtitle, fill=gray, font=font_small)
    
    y = 510
    draw.rectangle([width//5, y, width*4//5, y+3], fill=pink+'60')
    
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
            bbox = draw.textbbox((0, 0), percent_text, font=font_text)
            draw.text((bar_x + bar_width + 20, y), percent_text, fill=white, font=font_text)
            y += 75
    
    y += 20
    draw.rectangle([width//5, y, width*4//5, y+3], fill=pink+'60')
    
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
    bbox = draw.textbbox((0, 0), cert_text, font=font_small)
    cert_width = bbox[2] - bbox[0]
    draw.text((width-50-cert_width, footer_y), cert_text, fill=gray, font=font_small)
    
    stars = ["★", "★", "★", "★"]
    positions = [(40, 40), (width-40, 40), (40, height-40), (width-40, height-40)]
    for i, (x, y_pos) in enumerate(positions):
        draw.text((x-15, y_pos-15), stars[i], fill=gold, font=font_title)
    
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
        [KeyboardButton("➕ Начислить тесты"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True)

def get_options_keyboard():
    return ReplyKeyboardMarkup(
        [["➕ Добавить вариант", "✅ Готово", "🔙 Назад"]],
        resize_keyboard=True, one_time_keyboard=True
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
        [InlineKeyboardButton("📈 Статистика дружбы", callback_data=f"stats_friendship_{test_id}"),
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
            creator_username = f"(@{creator.get('username')})" if creator and creator.get('username') else ''
            
            text = (f"🌸✨ ПРИВЕТ, {user.first_name}! ✨🌸\n\n"
                    f"💕 *{creator_name}* {creator_username} приглашает тебя пройти тест!\n\n"
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
        text = (f"🌸✨ *ПРИВЕТ, {user.first_name}!* ✨🌸\n\n"
                f"Создай тест о себе и отправь подружке!\n"
                f"Узнайте, насколько хорошо вы друг друга знаете 💕\n\n"
                f"💎 *Статус:* ПРЕМИУМ ✨\n"
                f"♾️ *Безлимитные тесты*\n"
                f"📊 *Отправлено:* {tests_created} тестов\n\n"
                f"Выбирай действие в меню 👇")
    else:
        available = get_available_tests_count(user.id)
        if available > 0:
            word = decline_word(available, "тест", "теста", "тестов")
            tests_info = f"📊 *Осталось:* {available} {word}"
        else:
            tests_info = f"⚠️ *Лимит исчерпан!* Купи Премиум для продолжения"
        
        text = (f"🌸✨ *ПРИВЕТ, {user.first_name}!* ✨🌸\n\n"
                f"Создай тест о себе и отправь подружке!\n"
                f"Узнайте, насколько хорошо вы друг друга знаете 💕\n\n"
                f"🎁 *Бесплатно:* {FREE_TESTS_LIMIT} тестов\n"
                f"{tests_info}\n\n"
                f"💎 Хочешь безлимит и красивый диплом? Жми «💎 Премиум»\n\n"
                f"Выбирай действие в меню 👇")
    
    try:
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user.id))
    except Exception as e:
        logger.warning(f"Не удалось отправить приветствие: {e}")

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
    
    conn = get_db()
    c = conn.cursor()
    
    today = datetime.now().date().isoformat()
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
    week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
    month_ago = (datetime.now() - timedelta(days=30)).date().isoformat()
    
    c.execute('SELECT COUNT(*) FROM users')
    total_users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?', (today,))
    new_today = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?', (yesterday,))
    new_yesterday = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE created_at >= ?', (week_ago,))
    new_week = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE created_at >= ?', (month_ago,))
    new_month = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM tests')
    total_tests = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM tests WHERE DATE(created_at) = ?', (today,))
    tests_today = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM tests WHERE created_at >= ?', (week_ago,))
    tests_week = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM attempts')
    total_attempts = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM attempts WHERE DATE(completed_at) = ?', (today,))
    attempts_today = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL AND premium_until > ?', (today,))
    premium_active = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL')
    premium_total = c.fetchone()[0]
    
    c.execute('SELECT AVG(score) FROM attempts')
    avg_score = c.fetchone()[0] or 0
    
    conn.close()
    
    text = f"📊 *СТАТИСТИКА БОТА*\n\n"
    text += f"👥 *Пользователи:* {total_users} (+{new_today} сегодня)\n"
    text += f"📝 *Тестов создано:* {total_tests} (+{tests_today} сегодня)\n"
    text += f"🎯 *Пройдено тестов:* {total_attempts} (+{attempts_today} сегодня)\n"
    text += f"💎 *Премиум активных:* {premium_active}\n"
    text += f"💰 *Всего купили премиум:* {premium_total}\n"
    text += f"📈 *Средний результат:* {avg_score:.1f}%\n\n"
    text += f"📅 *Новых за неделю:* {new_week}\n"
    text += f"📅 *Новых за месяц:* {new_month}\n"
    text += f"📝 *Тестов за неделю:* {tests_week}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_refresh_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]
    ])
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def admin_refresh_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 Обновлено!")
    await query.message.delete()
    await admin_stats(update, context)

async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await admin_panel(update, context)

async def admin_give_premium_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("15 дней", callback_data="give_premium_15"),
         InlineKeyboardButton("30 дней", callback_data="give_premium_30")]
    ])
    
    await update.message.reply_text(
        "🎁 *ПОДАРИТЬ ПРЕМИУМ*\n\n👇 *Выбери количество дней:*",
        parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
    )
    context.user_data['admin_action'] = 'give_premium'

async def admin_add_tests_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    context.user_data['admin_action'] = 'add_tests'
    await update.message.reply_text(
        "➕ *НАЧИСЛИТЬ ТЕСТЫ*\n\nВведите username или ID и количество тестов:\nНапример: @anna 5 или 123456789 3\n\n❌ *Отмена* — чтобы выйти",
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
    )

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    context.user_data['admin_action'] = 'broadcast'
    await update.message.reply_text(
        "📢 *РАССЫЛКА*\n\nОтправь сообщение для всех пользователей.\n\n❌ *Отмена* — чтобы выйти",
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
    )

async def execute_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    message = update.message
    status_msg = await update.message.reply_text("📤 *Рассылаю...*", parse_mode=ParseMode.MARKDOWN)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id FROM users')
    users = c.fetchall()
    conn.close()
    
    total = len(users)
    success = 0
    
    for i, user in enumerate(users):
        try:
            await context.bot.send_message(chat_id=user['user_id'], text=message.text)
            success += 1
        except:
            pass
    
    await status_msg.edit_text(
        f"✅ *Рассылка завершена!*\n\n📊 Успешно: {success}/{total}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard()
    )
    del context.user_data['admin_action']

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    action = context.user_data.get('admin_action')
    if not action:
        return
    
    if action == 'broadcast':
        await execute_broadcast(update, context)
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
        await update.message.reply_text(
            f"✅ *{row['first_name'] or target}* получил премиум на *{days} {day_word}*! 🎉",
            parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard()
        )
        del context.user_data['admin_action']
    
    elif action == 'add_tests':
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Введите username и количество тестов!", reply_markup=get_admin_keyboard())
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
        conn.close()
        
        if not row:
            await update.message.reply_text(f"❌ Пользователь {target} не найден", reply_markup=get_admin_keyboard())
            del context.user_data['admin_action']
            return
        
        add_tests_to_user(row['user_id'], count)
        await update.message.reply_text(
            f"✅ *{row['first_name'] or target}* начислено *{count}* тестов!",
            parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard()
        )
        del context.user_data['admin_action']

# === СОЗДАНИЕ ТЕСТА ===
async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not can_create_test(user_id):
        await update.message.reply_text(
            f"💔 *Лимит бесплатных тестов!* 💔\n\n💎 *Купи Премиум* для безлимита!",
            parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user_id)
        )
        return
    
    context.user_data['creating_test'] = {'step': 'title'}
    
    is_prem = is_premium(user_id)
    if is_prem:
        tests_info = "♾️ *Премиум — безлимитные тесты*"
    else:
        available = get_available_tests_count(user_id)
        word = decline_word(available, "тест", "теста", "тестов")
        tests_info = f"📊 *Осталось тестов:* {available} {word}"
    
    await update.message.reply_text(
        f"🌸 *СОЗДАЁМ ТЕСТ*\n\n{tests_info}\n\nПридумай красивое название:\nНапример: «Насколько хорошо ты меня знаешь?»\n\n❌ *Отмена* — чтобы выйти",
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
    )

async def handle_create_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data:
        return
    if data.get('waiting_comment'):
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
            data['comments'] = {}
            data['photos'] = {}
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎤 Голосовое", callback_data="greeting_voice"),
                 InlineKeyboardButton("🎥 Видео", callback_data="greeting_video")],
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="greeting_skip")]
            ])
            await update.message.reply_text(
                "🎬✨ *ДОБАВЬ ПОЗДРАВЛЕНИЕ!* ✨🎬\n\nТвоя подружка получит его после прохождения теста!\n\n👇 Выбери тип или пропусти:",
                parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
            )
            data['step'] = 'greeting'
        except ValueError:
            await update.message.reply_text("⚠️ Напиши число!")

# === СОЗДАНИЕ ТЕСТА (продолжение) ===
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

async def show_presets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, preset in PRESET_GROUPS.items():
        keyboard.append([InlineKeyboardButton(preset['name'], callback_data=f"preset_{key}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_groups")])
    await query.message.edit_text("📦 *ГОТОВЫЕ НАБОРЫ ВОПРОСОВ*\n\nВыбери готовый набор для быстрого создания теста!\n\n👇 *Доступные наборы:*", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

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
    await query.message.reply_text(
        f"✅ Выбран набор: *{preset['name']}*\n\n📊 Сколько вопросов будет в тесте?\n🔹 От 2 до 5 вопросов\n\n✏️ Напиши число:",
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
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
    text = "🎤 Отправь голосовое сообщение\n\n❌ *Отмена* — чтобы пропустить" if choice == "voice" else "🎥 Отправь видео\n\n❌ *Отмена* — чтобы пропустить"
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

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
    await update.message.reply_text("✅ *Поздравление сохранено!*\n\n✨ *Приступаем к вопросам!* ✨", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(update.effective_user.id))
    await show_question_for_selection(update, context)

async def show_question_for_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data:
        return
    questions = data.get('group_questions', [])
    data['current_question_index'] = data.get('current_question_index', 0)
    question_text = questions[data['current_question_index']]
    data['current_question'] = question_text
    text = f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{question_text}\n\n👇 *Что делаем с этим вопросом?*"
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
    text = f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{questions[current_idx]}\n\n👇 *Что делаем с этим вопросом?*"
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
    text = f"📝 *Вопрос {data['current_q'] + 1}/{data['total_q']}*\n\n{all_questions[0]}\n\n👇 *Что делаем с этим вопросом?*"
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
        f"📝 *Вопрос:* {data['current_question']}\n\n✏️ *Напиши вариант ответа №1:*",
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
    )

async def add_photo_to_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('creating_test')
    if not data:
        return
    data['waiting_photo'] = True
    await query.message.reply_text("📸 *Отправь фото для этого вопроса*\n\n❌ *Отмена* — чтобы пропустить", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())

async def custom_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = context.user_data.get('creating_test')
    if not data:
        return
    data['waiting_custom_question'] = True
    await query.message.reply_text(
        "✏️ *ВВЕДИ СВОЙ ВОПРОС*\n\nНапиши свой уникальный вопрос:\n\n❌ *Отмена* — чтобы вернуться к выбору",
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
    )

async def save_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data or not data.get('waiting_photo'):
        return
    if not update.message.photo:
        await update.message.reply_text("❌ Отправь фото!")
        return
    photo_file_id = update.message.photo[-1].file_id
    if 'photos' not in data:
        data['photos'] = {}
    data['photos'][str(data['current_q'])] = photo_file_id
    data['waiting_photo'] = False
    data['step'] = 'collecting_options'
    data['current_options'] = []
    data['waiting_for_option'] = True
    await update.message.reply_text(
        "✅ *Фото добавлено!*\n\n"
        f"📝 *Вопрос:* {data['current_question']}\n\n"
        f"✏️ *Напиши вариант ответа №1:*",
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard()
    )

async def select_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    correct_idx = int(query.data.replace("correct_", ""))
    data = context.user_data.get('creating_test')
    if not data:
        return
    await query.message.reply_text(
        f"💬 *Хочешь добавить комментарий к правильному ответу?*\n\nНапиши комментарий или нажми «Пропустить»",
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
        
        msg = f"✅ *Вопрос {data['current_q']} сохранён!* ✅\n\n➡️ *Переходим к следующему...*"
        if hasattr(update_or_query, 'message'):
            await update_or_query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        else:
            await update_or_query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
        await show_question_for_selection(update_or_query, context)
    else:
        questions = [q['text'] for q in data['questions_data']]
        options = [q['options'] for q in data['questions_data']]
        correct = [q['correct'] for q in data['questions_data']]
        
        user = update_or_query.from_user if hasattr(update_or_query, 'from_user') else update_or_query.callback_query.from_user
        
        test_id = create_test(user.id, user.first_name, data['title'], questions, options, correct,
                              data.get('greeting_type'), data.get('greeting_file_id'),
                              data.get('comments', {}), data.get('photos', {}))
        
        del context.user_data['creating_test']
        
        text = f"🎉✨ *ТЕСТ ГОТОВ!* ✨🎉\n\n📝 *{data['title']}*\n🔢 Вопросов: {len(questions)}\n\n💖 Отправь ссылку подружке!"
        if hasattr(update_or_query, 'message'):
            await update_or_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(test_id))
        else:
            await update_or_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(test_id))
        await update_or_query.message.reply_text("🌸 Главное меню:", reply_markup=get_main_keyboard(user.id))

# === МОИ ТЕСТЫ ===
async def my_tests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tests = get_user_tests(user_id)
    
    if not tests:
        await update.message.reply_text("🌸 *У тебя пока нет тестов!*\n\nСоздай свой первый тест через кнопку «🌸 Создать тест» 💕", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user_id))
        return
    
    text = f"👑✨ *МОИ ТЕСТЫ* ✨👑\n\n"
    for i, t in enumerate(tests, 1):
        word = decline_friend_word(t['attempts'])
        text += f"{i}. 📝 *{t['title'][:30]}*\n   👥 Прошли: {t['attempts']} {word}\n\n"
    
    text += "👇 Выбери тест для управления:"
    keyboard = []
    for t in tests:
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
    text = f"📝 *{test['title']}*\n\n👥 Прошли: {len(attempts)} {decline_friend_word(len(attempts))}\n🎯 Средний результат: {avg_score:.0f}%\n\n👇 Выбери действие:"
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_test_actions_keyboard(test_id))

# === ПРОХОЖДЕНИЕ ТЕСТА ===
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
        await query.message.reply_text("💔 *Ты уже проходила этот тест!*\n\nКаждую подругу можно проверить только один раз ✨", parse_mode=ParseMode.MARKDOWN)
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
    
    test = data['test']
    current = data['current']
    correct_idx = test['correct_answers'][current]
    correct_answer = test['options'][current][correct_idx]
    is_correct = answer_idx == correct_idx
    
    data['answers'].append(answer_idx)
    
    if is_correct:
        result_text = f"✅ *ПРАВИЛЬНО!*\n\nТвой ответ: *{test['options'][current][answer_idx]}*"
    else:
        result_text = f"❌ *НЕПРАВИЛЬНО*\n\nТвой ответ: *{test['options'][current][answer_idx]}*\n✅ *Правильный ответ:* {correct_answer}"
    
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
    
    score = sum(1 for i in range(len(answers)) if answers[i] == correct[i]) * 100 / len(correct) if correct else 0
    save_attempt(test['id'], user.id, user.first_name, answers, score)
    status = get_friendship_status(score)
    prediction = get_friendship_prediction(score, user.first_name)
    
    try:
        creator_id = test['creator_id']
        notification_text = (f"🎉💖 *УРА! ТВОЙ ТЕСТ ПРОШЛИ!* 💖🎉\n\n"
                            f"👤 *{user.first_name}* прошла твой тест «{test['title']}»\n"
                            f"🎯 *Результат:* {score:.0f}%\n"
                            f"🏆 *Статус:* {status}")
        await context.bot.send_message(chat_id=creator_id, text=notification_text, parse_mode=ParseMode.MARKDOWN)
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
                await query.message.reply_voice(test['greeting_file_id'])
            elif test.get('greeting_type') == 'video':
                await query.message.reply_video(test['greeting_file_id'])
        except:
            pass
    
    await query.message.reply_text("✨ *Выбирай действие:* ✨", parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(user.id))
    del context.user_data['taking_test']

# === БИТВА ПОДРУГ ===
async def battle_friends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    test_id = int(query.data.replace("battle_", ""))
    test = get_test_by_id(test_id)
    attempts = get_test_attempts(test_id)
    
    if len(attempts) < 2:
        await query.message.reply_text("⚔️ *БИТВА ПОДРУГ*\n\n😢 Пока недостаточно участниц!\n📤 Поделись тестом с подругами!", parse_mode=ParseMode.MARKDOWN)
        return
    
    sorted_attempts = sorted(attempts, key=lambda x: x['score'], reverse=True)
    text = f"⚔️✨ *БИТВА ПОДРУГ* ✨⚔️\n\n📝 *{test['title']}*\n━━━━━━━━━━━━━━━━\n\n"
    
    for i, a in enumerate(sorted_attempts[:5], 1):
        score = a['score']
        status = get_friendship_status(score)
        if i == 1: medal = "🥇"
        elif i == 2: medal = "🥈"
        elif i == 3: medal = "🥉"
        else: medal = f"{i}."
        text += f"{medal} *{a['friend_name']}*\n   🎯 Результат: *{score:.0f}%*\n   🏆 Статус: {status}\n\n"
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# === СТАТИСТИКА ДРУЖБЫ ===
async def friendship_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    test_id = int(query.data.replace("stats_friendship_", ""))
    test = get_test_by_id(test_id)
    attempts = get_test_attempts(test_id)
    
    if not attempts:
        await query.message.reply_text("📈 *СТАТИСТИКА ДРУЖБЫ*\n\n😢 Пока никто не прошёл тест!", parse_mode=ParseMode.MARKDOWN)
        return
    
    text = f"📈✨ *СТАТИСТИКА ДРУЖБЫ* ✨📈\n\n📝 *{test['title']}*\n\n"
    for a in attempts[:10]:
        score = a['score']
        filled = int(score / 10)
        bar = "█" * filled + "░" * (10 - filled)
        text += f"💕 *{a['friend_name']}*\n   [{bar}] *{score:.0f}%*\n\n"
    
    avg_score = sum(a['score'] for a in attempts) / len(attempts)
    text += f"📊 *Средний результат:* {avg_score:.0f}%"
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# === ПРЕМИУМ (НОВАЯ ВЕРСИЯ С ПРОВЕРКОЙ ПЛАТЕЖА) ===
async def premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_prem = is_premium(user_id)
    
    if is_prem:
        user = get_user(user_id)
        expiry = datetime.fromisoformat(user['premium_until']).strftime('%d.%m.%Y')
        text = (f"💎✨ *У ТЕБЯ ПРЕМИУМ!* ✨💎\n\n♾️ Безлимитные тесты\n🎓 Красивый золотой диплом\n📊 Смотреть ответы подруг\n\n📅 *Действует до:* {expiry}")
    else:
        text = (f"💎 *ПРЕМИУМ ПОДПИСКА*\n\n✨ *Что даёт:*\n♾️ Безлимитные тесты\n🎓 Красивый золотой диплом\n📊 Смотреть ответы подруг\n\n💰 *Стоимость:*\n• 99₽ — 15 дней\n• 149₽ — месяц\n\n👇 *Выбери тариф:*")
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_premium_keyboard() if not is_prem else get_main_keyboard(user_id))

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание платежа через ЮKassa СБП"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "buy_15days":
        days = 15
        price_rub = 99
        title = "Premium на 15 дней"
    else:
        days = 30
        price_rub = 149
        title = "Premium на 30 дней"
    
    try:
        # Создаём платёж через API ЮKassa с приоритетом СБП
        payment = Payment.create({
            "amount": {
                "value": f"{price_rub}.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{BOT_USERNAME}"
            },
            "description": title,
            "metadata": {
                "user_id": user_id,
                "days": days
            },
            "capture": True,
            "payment_method_data": {
                "type": "sbp"
            }
        })
        
        logger.info(f"✅ Платёж создан: {payment.id} для пользователя {user_id}")
        
        # Кнопки
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💳 Оплатить {price_rub}₽ через СБП", url=payment.confirmation.confirmation_url)],
            [InlineKeyboardButton("✅ Я оплатил(а)", callback_data=f"check_payment_{payment.id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_premium")]
        ])
        
        await query.message.reply_text(
            f"💎 *{title}*\n\n"
            f"💰 Сумма: *{price_rub}₽*\n"
            f"📅 Срок: *{days} дней*\n\n"
            f"✨ *Что входит:*\n"
            f"♾️ Безлимитные тесты\n"
            f"🎓 Золотой диплом\n"
            f"📊 Ответы подруг\n\n"
            f"👇 *Нажми на кнопку для оплаты:*\n"
            f"💳 Оплата через СБП (мгновенно)\n\n"
            f"⚠️ *После оплаты нажми «✅ Я оплатил(а)»*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка создания платежа: {e}")
        await query.message.reply_text(
            "😢 *Ошибка при создании платежа*\n\nПопробуй позже или напиши администратору.",
            parse_mode=ParseMode.MARKDOWN
        )

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса платежа"""
    query = update.callback_query
    await query.answer("🔄 Проверяю платёж...")
    
    user_id = query.from_user.id
    payment_id = query.data.replace("check_payment_", "")
    
    try:
        payment = Payment.find_one(payment_id)
        
        if payment.status == "succeeded":
            # Платёж успешен
            days = int(payment.metadata.get('days', 30))
            give_premium(user_id, days)
            
            day_word = decline_word(days, "день", "дня", "дней")
            
            await query.message.edit_text(
                f"🎉✨ *ОПЛАТА ПРОШЛА!* ✨🎉\n\n"
                f"💎 *ПРЕМИУМ активирован на {days} {day_word}!*\n\n"
                f"♾️ Безлимитные тесты\n"
                f"🎓 Золотой диплом\n"
                f"📊 Ответы подруг\n\n"
                f"Спасибо за покупку! 💕",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_keyboard(user_id)
            )
            
        elif payment.status == "pending":
            await query.answer("⏳ Платёж ещё не поступил. Попробуй через минуту.", show_alert=True)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Проверить ещё раз", callback_data=f"check_payment_{payment_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_premium")]
            ])
            
            await query.message.edit_text(
                f"⏳ *Платёж ожидается...*\n\n"
                f"Если ты уже оплатила, подожди 1-2 минуты и нажми «🔄 Проверить ещё раз»\n\n"
                f"💡 *Оплата через СБП обычно приходит моментально*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            
        else:
            await query.message.edit_text(
                f"😢 *Платёж не прошёл*\n\nСтатус: {payment.status}\n\nПопробуй ещё раз.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_premium_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка проверки платежа: {e}")
        await query.answer("❌ Ошибка проверки. Попробуй позже.", show_alert=True)

async def cancel_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена покупки"""
    query = update.callback_query
    await query.answer()
    
    await query.message.edit_text(
        "💎 *ПРЕМИУМ ПОДПИСКА*\n\n"
        "✨ *Что даёт:*\n"
        "♾️ Безлимитные тесты\n"
        "🎓 Красивый золотой диплом\n"
        "📊 Смотреть ответы подруг\n\n"
        "💰 *Стоимость:*\n"
        "• 99₽ — 15 дней\n"
        "• 149₽ — месяц\n\n"
        "👇 *Выбери тариф:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_premium_keyboard()
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
    elif text == "➕ Начислить тесты" and user_id == ADMIN_ID:
        await admin_add_tests_start(update, context)
    elif text == "📢 Рассылка" and user_id == ADMIN_ID:
        await admin_broadcast_start(update, context)
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
        await start(update, context)
    elif text == "➕ Добавить вариант":
        data = context.user_data.get('creating_test')
        if data and data.get('step') == 'collecting_options':
            if len(data.get('current_options', [])) >= MAX_OPTIONS:
                await update.message.reply_text(f"⚠️ *Максимум {MAX_OPTIONS} вариантов!*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
                return
            data['waiting_for_option'] = True
            await update.message.reply_text(f"✏️ *Напиши вариант №{len(data['current_options']) + 1}:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())
    elif text == "✅ Готово":
        data = context.user_data.get('creating_test')
        if data and data.get('step') == 'collecting_options':
            options = data.get('current_options', [])
            if len(options) < 2:
                await update.message.reply_text("⚠️ *Нужно минимум 2 варианта!*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
                return
            keyboard = []
            for i, opt in enumerate(options):
                keyboard.append([InlineKeyboardButton(f"{i+1}. {opt[:30]}", callback_data=f"correct_{i}")])
            await update.message.reply_text(f"❓ *Вопрос:* {data['current_question']}\n\n👇 *Какой вариант ПРАВИЛЬНЫЙ?* 👇", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
            data['waiting_for_option'] = False
    else:
        # Обработка текста при создании теста
        data = context.user_data.get('creating_test')
        
        if data and data.get('waiting_comment'):
            await save_comment(update, context)
            return
        
        if data and data.get('waiting_custom_question'):
            text = update.message.text.strip()
            if len(text) < 5:
                await update.message.reply_text("⚠️ Вопрос должен быть длиннее 5 символов!")
                return
            data['current_question'] = text
            data['waiting_custom_question'] = False
            data['current_options'] = []
            data['step'] = 'collecting_options'
            data['waiting_for_option'] = True
            await update.message.reply_text(f"✅ *Вопрос сохранён!*\n\n📝 *{text}*\n\n✏️ *Напиши вариант ответа №1:*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_keyboard())
            return
        
        if data and data.get('step') == 'collecting_options':
            if data.get('waiting_for_option'):
                await handle_create_test(update, context)
            else:
                if len(data.get('current_options', [])) >= MAX_OPTIONS:
                    await update.message.reply_text(f"⚠️ *Максимум {MAX_OPTIONS} вариантов!* Нажми «✅ Готово»", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
                    return
                option_text = text.strip()
                if len(option_text) > 50:
                    await update.message.reply_text("⚠️ *Слишком длинный вариант!* До 50 символов.")
                    return
                data['current_options'].append(option_text)
                options_list = "\n".join([f"{i+1}. {o}" for i, o in enumerate(data['current_options'])])
                if len(data['current_options']) >= MAX_OPTIONS:
                    await update.message.reply_text(f"✅ *Достигнут максимум!* Нажми «✅ Готово»", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
                else:
                    await update.message.reply_text(f"✅ *Вариант добавлен!*\n\n{options_list}\n\n➕ *Можешь добавить ещё или нажать «Готово»*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_options_keyboard())
        elif 'creating_test' in context.user_data:
            await handle_create_test(update, context)
        elif context.user_data.get('admin_action'):
            await handle_admin_input(update, context)

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
        await query.message.edit_text("✨ Выбери тему для вопросов:", reply_markup=get_question_groups_keyboard())
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
        await query.message.edit_text(f"🎁 *ПОДАРИТЬ ПРЕМИУМ НА {days} {decline_word(days, 'ДЕНЬ', 'ДНЯ', 'ДНЕЙ')}*\n\nВведите username или ID пользователя:\nНапример: @anna или 123456789\n\n❌ *Отмена* — чтобы выйти", parse_mode=ParseMode.MARKDOWN)
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
            text = f"📝 *{test['title']}*\n\n*Вопросы и ответы:*\n"
            for i, q in enumerate(test['questions'], 1):
                text += f"\n*{i}. {q}*\n"
                for j, opt in enumerate(test['options'][i-1]):
                    prefix = "✅" if j == test['correct_answers'][i-1] else "➖"
                    text += f"   {prefix} {opt}\n"
            await query.message.reply_text(text[:4000], parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("share_"):
        test_id = int(data.replace("share_", ""))
        await query.message.reply_text("📤 *ПОДЕЛИСЬ ТЕСТОМ!*\n\n👇 Нажми на кнопку:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_share_keyboard(test_id))
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
        text = f"📊 *ОТВЕТЫ ПОДРУГ*\n\n📝 *{test['title']}*\n\n"
        for a in attempts[:10]:
            text += f"👤 *{a['friend_name']}*: {a['score']:.0f}%\n"
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("battle_"):
        await battle_friends(update, context)
    elif data.startswith("stats_friendship_"):
        await friendship_stats(update, context)
    elif data.startswith("delete_"):
        test_id = int(data.replace("delete_", ""))
        delete_test(query.from_user.id, test_id)
        await query.message.reply_text("🗑 Тест удалён!", reply_markup=get_main_keyboard(query.from_user.id))
    elif data in ["buy_15days", "buy_month"]:
        await buy_premium(update, context)
    elif data.startswith("check_payment_"):
        await check_payment(update, context)
    elif data == "cancel_premium":
        await cancel_premium(update, context)
    elif data == "admin_refresh_stats":
        await admin_refresh_stats(update, context)
    elif data == "back_to_admin":
        await back_to_admin(update, context)
    
    await query.answer()

# === MAIN ===
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Регистрируем хендлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^🌸 Создать тест$"), create_test_start))
    app.add_handler(MessageHandler(filters.Regex("^👑 Мои тесты$"), my_tests_handler))
    app.add_handler(MessageHandler(filters.Regex("^💎 Премиум$"), premium_handler))
    app.add_handler(MessageHandler(filters.Regex("^🔧 Админ-панель$"), admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^📊 Статистика$"), admin_stats))
    app.add_handler(MessageHandler(filters.Regex("^🎁 Подарить премиум$"), admin_give_premium_start))
    app.add_handler(MessageHandler(filters.Regex("^➕ Начислить тесты$"), admin_add_tests_start))
    app.add_handler(MessageHandler(filters.Regex("^📢 Рассылка$"), admin_broadcast_start))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Назад$"), start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.VOICE, save_greeting))
    app.add_handler(MessageHandler(filters.VIDEO, save_greeting))
    app.add_handler(MessageHandler(filters.PHOTO, save_photo))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🚀✨ Бот запущен! ЮKASSA API (СБП) — БЕЗ Flask, БЕЗ вебхуков! ✨🚀")
    app.run_polling()

if __name__ == "__main__":
    main()
