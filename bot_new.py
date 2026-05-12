#!/usr/bin/env python3
import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

logging.basicConfig(level=logging.INFO)

async def start(update, context):
    await update.message.reply_text("✅ Бот работает!")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("🚀 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
