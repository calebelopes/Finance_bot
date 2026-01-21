import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from utils import messages as msg
from utils import db

# Message handler
import datetime

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_info = f"User: {user.username or user.first_name} (ID: {user.id})"

    text = update.message.text
    try:
        action, value = text.split()
        value = float(value)
        db.store_data(action, value)
        await update.message.reply_text(f"Stored: Action = {action}, Value = {value}")
        print(f"[{timestamp}] {user_info} - Stored: Action = {action}, Value = {value}")
    except ValueError:
        await update.message.reply_text(f"{user_info} - {msg.invalid}")

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(msg.start)

# Main function
def main():
    db.setup_database()
    application = Application.builder().token(os.getenv("TOKEN")).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()