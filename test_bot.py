import asyncio
import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise Exception("BOT_TOKEN not found")

logging.basicConfig(level=logging.INFO)

async def start(update, context):
    await update.message.reply_text("✅ Тестовый бот работает! Отправь /help")

async def help_command(update, context):
    await update.message.reply_text("Доступные команды:\n/start - приветствие\n/help - помощь")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    print("🚀 Тестовый бот запущен! Отправь /start в Telegram.")
    app.run_polling()

if __name__ == "__main__":
    main()
