import sqlite3

DB_NAME = 'bot_simple.db'

conn = sqlite3.connect(DB_NAME)
c = conn.cursor()

# Таблица битв
c.execute('''CREATE TABLE IF NOT EXISTS battles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_id INTEGER,
    test_id INTEGER,
    battle_code TEXT UNIQUE,
    max_players INTEGER DEFAULT 3,
    time_limit INTEGER DEFAULT 600,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    status TEXT DEFAULT 'waiting'
)''')

# Участницы битв
c.execute('''CREATE TABLE IF NOT EXISTS battle_players (
    battle_id INTEGER,
    user_id INTEGER,
    score REAL DEFAULT 0,
    progress INTEGER DEFAULT 0,
    total_questions INTEGER DEFAULT 0,
    finished_at TIMESTAMP,
    UNIQUE(battle_id, user_id)
)''')

conn.commit()
conn.close()

# Обновляем bot.py - новый прайс
with open('bot.py', 'r') as f:
    content = f.read()

# Меняем функцию premium_handler
old_premium = '''async def premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_premium(user_id):
        user = get_user(user_id); expiry = datetime.fromisoformat(user['premium_until']).strftime('%d.%m.%Y')
        text = f"💎✨ *У ТЕБЯ ПРЕМИУМ!* ✨💎\\n\\n♾️ Безлимитные тесты\\n🎓 Золотой диплом\\n📊 Ответы подруг\\n\\n📅 *Действует до:* {expiry}\\n\\n💕 *Создавай тесты и проверяй подруг!*"
    else: text = "💎 *ПРЕМИУМ ПОДПИСКА*\\n\\n✨ *Что даёт:*\\n♾️ Безлимитные тесты\\n🎓 Золотой диплом\\n📊 Ответы подруг\\n\\n💰 *Стоимость:*\\n• 99₽ — 15 дней\\n• 149₽ — месяц\\n\\n👇 *Выбери тариф:*"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_premium_keyboard() if not is_premium(user_id) else get_main_keyboard(user_id))'''

new_premium = '''async def premium_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_premium(user_id):
        user = get_user(user_id); expiry = datetime.fromisoformat(user['premium_until']).strftime('%d.%m.%Y')
        text = f"💎✨ *У ТЕБЯ ПРЕМИУМ!* ✨💎\\n\\n♾️ Безлимитные тесты\\n👥 Битвы до 10 подруг\\n🎓 Золотой диплом\\n📊 Ответы подруг\\n💬 Чат после битвы\\n\\n📅 *Действует до:* {expiry}\\n\\n💕 *Создавай тесты и проверяй подруг!*"
    else: text = (
        "💎 *ПРЕМИУМ*\\n\\n"
        "✨ *Что даёт:*\\n"
        "♾️ Безлимитные тесты\\n"
        "👥 Битвы до 10 подруг\\n"
        "🎓 Золотой диплом\\n"
        "📊 Ответы подруг\\n"
        "💬 Чат после битвы\\n\\n"
        "💰 *Тарифы:*\\n"
        "🎮 49₽ — на 1 тест\\n"
        "📅 79₽ — на 24 часа\\n"
        "💎 149₽ — на неделю\\n"
        "👑 499₽ — навсегда\\n\\n"
        "👇 *Выбери тариф:*"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_premium_keyboard() if not is_premium(user_id) else get_main_keyboard(user_id))'''

if old_premium in content:
    content = content.replace(old_premium, new_premium)
    print("✅ premium_handler обновлён")
else:
    print("❌ premium_handler не найден")

# Новый прайс в кнопках
old_keyboard = '''def get_premium_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 15 дней — 99₽", callback_data="buy_15days")],
        [InlineKeyboardButton("💎 Месяц — 149₽", callback_data="buy_month")]
    ])'''

new_keyboard = '''def get_premium_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 1 тест — 49₽", callback_data="buy_1test")],
        [InlineKeyboardButton("📅 24 часа — 79₽", callback_data="buy_24h")],
        [InlineKeyboardButton("💎 Неделя — 149₽", callback_data="buy_week")],
        [InlineKeyboardButton("👑 Навсегда — 499₽", callback_data="buy_forever")]
    ])'''

if old_keyboard in content:
    content = content.replace(old_keyboard, new_keyboard)
    print("✅ Клавиатура премиум обновлена")
else:
    print("❌ Клавиатура не найдена")

with open('bot.py', 'w') as f:
    f.write(content)

print("✅ Часть 1 готова!")
