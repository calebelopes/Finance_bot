import os
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from utils import messages as msg
from utils import db

# Message handler
import datetime


def _parse_action_value(text: str) -> tuple[str, float]:
    """
    Parse user input into (action, value).

    Supports:
    - "dinner 20.5"
    - "coffee shop 4.5"  (multi-word action; last token is the number)
    """
    parts = text.strip().split()
    if len(parts) < 2:
        raise ValueError("Expected: <action> <value>")

    def _parse_number_ptbr(raw: str) -> float:
        """
        Parse numbers allowing pt-BR decimal comma.

        Examples:
        - "12,50" -> 12.5
        - "1.234,56" -> 1234.56
        - "1,234.56" -> 1234.56 (also accepted)
        """
        s = raw.strip().replace(" ", "")
        if not s:
            raise ValueError("Value is empty")

        if "," in s and "." in s:
            # Decimal separator is whichever appears last
            if s.rfind(",") > s.rfind("."):
                # pt-BR style: thousands "." and decimal ","
                s = s.replace(".", "").replace(",", ".")
            else:
                # en-US style: thousands "," and decimal "."
                s = s.replace(",", "")
        elif "," in s:
            # pt-BR style: decimal "," (any "." are treated as thousands)
            s = s.replace(".", "").replace(",", ".")
        else:
            # plain digits or "." decimal; tolerate stray thousands commas
            s = s.replace(",", "")

        return float(s)

    raw_value = parts[-1]
    value = _parse_number_ptbr(raw_value)
    action = " ".join(parts[:-1]).strip()
    if not action:
        raise ValueError("Action is empty")
    return action, value


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_info = f"User: {user.username or user.first_name} (ID: {user.id})"

    text: Optional[str] = update.message.text if update.message else None
    if not text:
        return
    try:
        action, value = _parse_action_value(text)
        db.store_data(action, value)
        value_str = f"{value:.2f}".replace(".", ",")
        await update.message.reply_text(msg.stored.format(action=action, value=value_str))
        print(f"[{timestamp}] {user_info} - Stored: Action = {action}, Value = {value}")
    except ValueError:
        await update.message.reply_text(msg.invalid)

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(msg.start)

# Main function
def main():
    db.setup_database()
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("Missing TOKEN environment variable (Telegram bot token).")
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()