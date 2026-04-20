#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PodrugaTestBot — простой и красивый бот для тестов между подругами
Версия: 2.0 — ЛЁГКАЯ И ПОНЯТНАЯ
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
MAX_QUESTIONS = 5
MAX_OPTIONS = 4

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
    'love': '💖 Любовь',
    'humor': '😂 Приколы',
    'myself': '🌸 Про меня'
}

QUESTIONS = {
    'friendship': [
        "✨ Как долго мы дружим? ✨", "💕 Где мы познакомились? 💕", "🎨 Мой любимый цвет? 🎨",
        "🍕 Моя любимая еда? 🍕", "💃 Моё любимое занятие? 💃", "📺 Мой любимый сериал? 📺",
        "😤 Что меня бесит? 😤", "🌟 Моя заветная мечта? 🌟", "🎵 Мой любимый исполнитель? 🎵", "📚 Моя любимая книга? 📚"
    ],
    'love': [
        "💘 Какой тип парня мне нравится? 💘", "💕 Что для меня важно в отношениях? 💕",
        "😳 Как я показываю симпатию? 😳", "🌹 Моё идеальное свидание? 🌹", "✨ Что меня влюбляет? ✨",
        "🎁 Какой подарок я мечтаю получить? 🎁", "🙄 Что меня раздражает в парнях? 🙄",
        "📱 Мой краш из тиктока? 📱", "💋 Первый поцелуй - это важно? 💋", "💍 Хочу ли я замуж? 💍"
    ],
    'humor': [
        "🏃‍♀️ Что я делаю, когда опаздываю? 🏃‍♀️", "🤪 Моя самая странная привычка? 🤪",
        "💃 Как я танцую? 💃", "🍪 Что я ем ночью? 🍪", "👀 Как я вру? 👀",
        "😱 Что делаю при виде паука? 😱", "🐌 Мой смешной страх? 🐌", "💬 Моя коронная фраза? 💬",
        "🛌 Как я сплю? 🛌", "🎤 Моя песня в караоке? 🎤"
    ],
    'myself': [
        "💪 Моя суперсила? 💪", "🦄 Что мне нужно для счастья? 🦄", "🎧 Как я справляюсь со стрессом? 🎧",
        "👩‍🎤 Кем я хочу стать в будущем? 👩‍🎤", "💅 Что я больше всего люблю в себе? 💅",
        "😨 Мой главный страх? 😨", "✨ Моя фишка? ✨", "🌈 Что меня вдохновляет? 🌈",
        "🕰️ Моя лучшая черта характера? 🕰️", "💎 Моё самое большое достижение? 💎"
    ]
}

# === СТАТУСЫ ДРУЖБЫ ===
def get_friendship_status(score):
    if score >= 90: return "👯‍♀️ СЁСТРЫ НАВЕК! 💕"
    if score >= 70: return "💎 ЛУЧШИЕ ПОДРУГИ! 💎"
    if score >= 50: return "🌸 ХОРОШИЕ ПОДРУЖКИ! 🌸"
    if score >= 30: return "👋 ПРИЯТЕЛЬНИЦЫ! 👋"
    return "🤔 ПОКА ЗНАКОМЫЕ 🤔"

# === БАЗА ДАННЫХ ===
def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Пользователи
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        tests_created INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        premium_until TEXT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Тесты
    c.execute('''CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id INTEGER,
        creator_name TEXT,
        title TEXT,
        questions TEXT,
        options TEXT,
        correct_answers TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Пройденные тесты
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

def create_test(creator_id, creator_name, title, questions, options, correct_answers):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO tests (creator_id, creator_name, title, questions, options, correct_answers)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (creator_id, creator_name, title, json.dumps(questions), json.dumps(options), json.dumps(correct_answers)))
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
    
    # Рамка
    draw.rectangle([0, 0, width, 4], fill=primary)
    draw.rectangle([0, height-4, width, height], fill=primary)
    
    # Заголовок
    title = "💎 ПРЕМИУМ ДИПЛОМ 💎" if is_premium_user else "🌸 ДИПЛОМ ПОДРУЖКИ 🌸"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    title_width = bbox[2] - bbox[0]
    draw.text((width//2 - title_width//2, 50), title, fill=primary, font=font_title)
    
    # Иконка
    icon = "👑" if is_premium_user else "📜"
    bbox = draw.textbbox((0, 0), icon, font=font_score)
    icon_width = bbox[2] - bbox[0]
    draw.text((width//2 - icon_width//2, 120), icon, fill=primary, font=font_score)
    
    # Имя
    name_display = user_name[:30]
    bbox = draw.textbbox((0, 0), name_display, font=font_name)
    name_width = bbox[2] - bbox[0]
    draw.text((width//2 - name_width//2, 220), name_display, fill=text_white, font=font_name)
    
    # Тест
    test_display = test_title[:40]
    bbox = draw.textbbox((0, 0), test_display, font=font_text)
    test_width = bbox[2] - bbox[0]
    draw.text((width//2 - test_width//2, 280), test_display, fill=text_gray, font=font_text)
    
    # Результат
    score_color = '#2EA043' if score >= 70 else '#FFA500' if score >= 50 else '#FF4444'
    score_text = f"{score:.0f}%"
    bbox = draw.textbbox((0, 0), score_text, font=font_score)
    score_width = bbox[2] - bbox[0]
    draw.text((width//2 - score_width//2, 350), score_text, fill=score_color, font=font_score)
    
    # Статус
    bbox = draw.textbbox((0, 0), status, font=font_text)
    status_width = bbox[2] - bbox[0]
    draw.text((width//2 - status_width//2, 470), status, fill=primary, font=font_text)
    
    # Поздравление
    congrats = "Поздравляем с прохождением теста!"
    bbox = draw.textbbox((0, 0), congrats, font=font_small)
    congrats_width = bbox[2] - bbox[0]
    draw.text((width//2 - congrats_width//2, 550), congrats, fill=text_gray, font=font_small)
    
    # Дата
    date_text = datetime.now().strftime("%d.%m.%Y")
    draw.text((50, height-40), date_text, fill=text_gray, font=font_small)
    
    # ID
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
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🌸 Создать тест")],
        [KeyboardButton("👑 Мои тесты"), KeyboardButton("💎 Премиум")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True, one_time_keyboard=True)

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
    
    # Проверяем, перешли ли по ссылке на тест
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
    
    text = (f"🌸✨ *ПРИВЕТ, {user.first_name}!* ✨🌸\n\n"
            f"Создай тест о себе и отправь подружке!\n"
            f"Узнайте, насколько хорошо вы друг друга знаете 💕\n\n"
            f"🎁 *Бесплатно:* {FREE_TESTS_LIMIT} теста\n"
            f"📊 *Создано:* {tests_created}/{FREE_TESTS_LIMIT}\n"
            f"{'💎 *Статус:* ПРЕМИУМ (безлимит) ✨' if is_prem else ''}\n\n"
            f"Выбирай действие в меню 👇")
    
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

# === СОЗДАНИЕ ТЕСТА ===
async def create_test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not can_create_test(user_id):
        await update.message.reply_text(
            f"💔 *Лимит бесплатных тестов!* 💔\n\n"
            f"Ты создала {FREE_TESTS_LIMIT} теста.\n"
            f"💎 *Купи Премиум* для безлимита и красивых дипломов!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
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
    
    text = update.message.text
    if text == "❌ Отмена":
        del context.user_data['creating_test']
        await update.message.reply_text("❌ Создание отменено", reply_markup=get_main_keyboard())
        return
    
    step = data.get('step')
    
    if step == 'title':
        data['title'] = text.strip()
        data['step'] = 'group'
        await update.message.reply_text(
            "✨ Выбери тему для вопросов:",
            reply_markup=get_question_groups_keyboard()
        )
    
    elif step == 'questions_count':
        try:
            count = int(text.strip())
            if count < 3 or count > MAX_QUESTIONS:
                await update.message.reply_text(f"⚠️ От 3 до {MAX_QUESTIONS} вопросов!")
                return
            data['total_q'] = count
            data['current_q'] = 0
            data['questions_data'] = []
            data['step'] = 'selecting_question'
            await show_next_question(update, context)
        except ValueError:
            await update.message.reply_text("⚠️ Напиши число!")

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
        data['group_questions'] = all_questions[:20]
    else:
        data['group_questions'] = QUESTIONS.get(group, []).copy()
        random.shuffle(data['group_questions'])
    
    data['step'] = 'questions_count'
    await query.message.reply_text(
        f"📊 Сколько вопросов будет в тесте?\n"
        f"🔹 От 3 до {MAX_QUESTIONS} вопросов\n\n"
        f"✏️ Напиши число:",
        reply_markup=get_cancel_keyboard()
    )

async def show_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data:
        return
    
    questions = data.get('group_questions', [])
    if data['current_q'] >= len(questions):
        data['current_q'] = 0
    
    question_text = questions[data['current_q']]
    data['current_question'] = question_text
    data['current_options'] = []
    data['waiting_for_option'] = True
    
    await update.message.reply_text(
        f"📝 Вопрос {data['current_q'] + 1}/{data['total_q']}\n\n"
        f"{question_text}\n\n"
        f"✏️ Напиши вариант ответа №1:",
        reply_markup=get_cancel_keyboard()
    )

async def handle_collecting_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data or data.get('step') != 'selecting_question':
        return
    
    text = update.message.text
    if text == "❌ Отмена":
        del context.user_data['creating_test']
        await update.message.reply_text("❌ Создание отменено", reply_markup=get_main_keyboard())
        return
    
    if data.get('waiting_for_option'):
        if len(text) > 50:
            await update.message.reply_text("⚠️ Слишком длинный вариант! До 50 символов.")
            return
        
        data['current_options'].append(text.strip())
        
        if len(data['current_options']) < MAX_OPTIONS:
            await update.message.reply_text(
                f"✅ Вариант {len(data['current_options'])} добавлен!\n"
                f"✏️ Напиши вариант №{len(data['current_options']) + 1}:",
                reply_markup=get_cancel_keyboard()
            )
        else:
            await ask_for_correct_answer(update, context)
    else:
        await ask_for_correct_answer(update, context)

async def ask_for_correct_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('creating_test')
    if not data:
        return
    
    options = data['current_options']
    keyboard = []
    for i, opt in enumerate(options):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {opt[:30]}", callback_data=f"correct_{i}")])
    
    await update.message.reply_text(
        f"❓ Какой вариант ПРАВИЛЬНЫЙ?",
        reply_markup=InlineKeyboardMarkup(keyboard)
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
        await query.message.reply_text(f"✅ Вопрос {data['current_q']} сохранён!")
        await show_next_question(query, context)
    else:
        await finish_test_creation(query, context)

async def finish_test_creation(query, context):
    data = context.user_data.get('creating_test')
    user = query.from_user
    
    questions = [q['text'] for q in data['questions_data']]
    options = [q['options'] for q in data['questions_data']]
    correct = [q['correct'] for q in data['questions_data']]
    
    test_id = create_test(user.id, user.first_name, data['title'], questions, options, correct)
    
    del context.user_data['creating_test']
    
    text = (f"🎉✨ *ТЕСТ ГОТОВ!* ✨🎉\n\n"
            f"📝 *{data['title']}*\n"
            f"🔢 Вопросов: {data['total_q']}\n\n"
            f"💖 Отправь ссылку подружке!")
    
    await query.message.reply_text(
        text, 
        parse_mode=ParseMode.MARKDOWN, 
        reply_markup=get_share_keyboard(test_id)
    )
    await query.message.reply_text("🌸 Главное меню:", reply_markup=get_main_keyboard())

# === МОИ ТЕСТЫ ===
async def my_tests_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tests = get_user_tests(user_id)
    
    if not tests:
        await update.message.reply_text(
            "🌸 *У тебя пока нет тестов!*\n\n"
            "Создай свой первый тест через кнопку «🌸 Создать тест» 💕",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard()
        )
        return
    
    text = f"👑✨ *МОИ ТЕСТЫ* ✨👑\n\n"
    for t in tests:
        word = decline_word(t['attempts'], "подруга", "подруги", "подруг")
        text += f"📝 *{t['title'][:30]}*\n"
        text += f"   👥 Прошли: {t['attempts']} {word}\n"
        text += f"   📅 {t['created_at'][:10]}\n\n"
    
    text += "👇 Выбери тест для управления:"
    
    keyboard = []
    for t in tests[:10]:
        keyboard.append([InlineKeyboardButton(f"📝 {t['title'][:30]}", callback_data=f"mytest_{t['id']}")])
    
    await update.message.reply_text(
        text, 
        parse_mode=ParseMode.MARKDOWN, 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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
    
    await query.message.reply_text(
        text, 
        parse_mode=ParseMode.MARKDOWN, 
        reply_markup=get_test_actions_keyboard(test_id)
    )

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
    
    context.user_data['taking_test'] = {
        'test': test,
        'current': 0,
        'answers': []
    }
    
    await send_question(query, context)

async def send_question(query, context):
    data = context.user_data.get('taking_test')
    test = data['test']
    current = data['current']
    
    q_text = test['questions'][current]
    options = test['options'][current]
    
    text = f"❓ *Вопрос {current + 1}/{len(test['questions'])}*\n\n{q_text}"
    
    keyboard = []
    for i, opt in enumerate(options):
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
    
    score = sum(1 for i, a in enumerate(answers) if a == correct[i]) * 100 / len(answers)
    
    save_attempt(test['id'], user.id, user.first_name, answers, score)
    
    status = get_friendship_status(score)
    is_prem = is_premium(test['creator_id'])
    
    # Отправляем результат
    text = (f"🎉 *ТЕСТ ПРОЙДЕН!* 🎉\n\n"
            f"👤 {user.first_name}\n"
            f"📝 {test['title']}\n"
            f"🎯 Результат: {score:.0f}%\n"
            f"🏆 {status}")
    
    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    # Генерируем и отправляем диплом
    diploma = await generate_diploma(user.first_name, test['title'], score, status, is_prem)
    await query.message.reply_photo(
        diploma,
        caption=f"🎓 *ТВОЙ ДИПЛОМ!* 🎓",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await query.message.reply_text("🌸 Главное меню:", reply_markup=get_main_keyboard())
    del context.user_data['taking_test']

# === ПРЕМИУМ ===
async def premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_prem = is_premium(user_id)
    
    if is_prem:
        user = get_user(user_id)
        expiry = datetime.fromisoformat(user['premium_until']).strftime('%d.%m.%Y')
        text = (f"💎✨ *У ТЕБЯ ПРЕМИУМ!* ✨💎\n\n"
                f"♾️ Безлимитные тесты\n"
                f"🎓 Красивый диплом\n"
                f"📊 Ответы подруг\n\n"
                f"📅 Действует до: {expiry}")
    else:
        text = (f"💎 *ПРЕМИУМ ПОДПИСКА*\n\n"
                f"✨ Что даёт:\n"
                f"♾️ Безлимитные тесты\n"
                f"🎓 Красивый золотой диплом\n"
                f"📊 Смотреть ответы подруг\n\n"
                f"💰 Стоимость:\n"
                f"• 199₽ — месяц\n"
                f"• 1299₽ — год\n\n"
                f"👇 Выбери тариф:")
    
    await update.message.reply_text(
        text, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_premium_keyboard() if not is_prem else get_main_keyboard()
    )

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    is_month = query.data == "buy_month"
    price = "199₽" if is_month else "1299₽"
    
    await query.message.reply_text(
        f"💎 *ОПЛАТА ПРЕМИУМА*\n\n"
        f"Тариф: {'месяц' if is_month else 'год'}\n"
        f"Сумма: {price}\n\n"
        f"Для оплаты напишите: @LavaTopBot\n"
        f"После оплаты сообщите админу: @SergeyMarko\n\n"
        f"💖 Спасибо за поддержку!",
        parse_mode=ParseMode.MARKDOWN
    )

# === ОБРАБОТЧИКИ КНОПОК ===
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🌸 Создать тест":
        await create_test_start(update, context)
    elif text == "👑 Мои тесты":
        await my_tests_handler(update, context)
    elif text == "💎 Премиум":
        await premium_handler(update, context)
    elif text == "🔙 Назад":
        await start(update, context)
    else:
        if 'creating_test' in context.user_data:
            await handle_collecting_options(update, context)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("group_"):
        await select_question_group(update, context)
    elif data.startswith("correct_"):
        await select_correct(update, context)
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
                text += f"\n{i}. {q}\n"
                for j, opt in enumerate(test['options'][i-1]):
                    prefix = "✅" if j == test['correct_answers'][i-1] else "➖"
                    text += f"   {prefix} {opt}\n"
            await query.message.reply_text(text[:4000], parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("share_"):
        test_id = int(data.replace("share_", ""))
        await query.message.reply_text(
            "📤 *Поделись тестом с подругой!*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_share_keyboard(test_id)
        )
    elif data.startswith("answers_"):
        test_id = int(data.replace("answers_", ""))
        user_id = query.from_user.id
        if not is_premium(user_id):
            await query.answer("💎 Только для ПРЕМИУМ!", show_alert=True)
            return
        attempts = get_test_attempts(test_id)
        if not attempts:
            await query.message.reply_text("👻 Пока никто не прошёл тест")
        else:
            text = "📊 *ОТВЕТЫ ПОДРУГ*\n\n"
            for a in attempts[:5]:
                text += f"👤 {a['friend_name']}: {a['score']:.0f}%\n"
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("delete_"):
        test_id = int(data.replace("delete_", ""))
        delete_test(query.from_user.id, test_id)
        await query.message.reply_text("🗑 Тест удалён!", reply_markup=get_main_keyboard())
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
    app.add_handler(MessageHandler(filters.Regex("^🔙 Назад$"), start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🚀✨ Бот запущен! ЛЁГКАЯ ВЕРСИЯ ✨🚀")
    app.run_polling()

if __name__ == "__main__":
    main()
