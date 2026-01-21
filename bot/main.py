import os
import sys
from pathlib import Path
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

# Allow running this file directly from ./bot (PowerShell: `cd bot; python .\\main.py`)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

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

    normalized = " ".join(text.strip().lower().split())
    greetings = {
        "oi",
        "olá",
        "ola",
        "eai",
        "e aí",
        "bom dia",
        "boa tarde",
        "boa noite",
        "hello",
        "hi",
        "hey",
        "start",
    }
    if normalized in greetings:
        await update.message.reply_text(msg.greeting)
        return
    try:
        action, value = _parse_action_value(text)
        db.store_action(user.id, user.username, action, value)
        # Log usage only when user actually performed an action (stored successfully)
        db.log_usage(user.id, user.username, "action_stored")
        value_str = f"{value:.2f}".replace(".", ",")
        await update.message.reply_text(msg.stored.format(action=action, value=value_str))
        print(f"[{timestamp}] {user_info} - Stored: Action = {action}, Value = {value}")
    except ValueError:
        await update.message.reply_text(msg.invalid)

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(msg.start)


async def _post_init(_: Application) -> None:
    # Log once the application is initialized and running
    db.log_app_event("app_started")

# Main function
def main():
    db.setup_database()
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("Missing TOKEN environment variable (Telegram bot token).")

    # If you're on a corporate network with a TLS-inspecting proxy, using the OS
    # trust store often fixes SSLCertVerificationError on Windows.
    # Enable by setting USE_SYSTEM_CA=1 (requires truststore dependency).
    if os.getenv("USE_SYSTEM_CA") == "1":
        try:
            import truststore  # type: ignore

            truststore.inject_into_ssl()
        except Exception as exc:
            raise RuntimeError(f"Failed to enable system CA store (truststore): {exc}") from exc

    # Corporate networks may MITM TLS with a custom root CA (self-signed chain).
    # If you hit SSLCertVerificationError, set TELEGRAM_CA_BUNDLE to a PEM file path.
    ca_bundle = os.getenv("TELEGRAM_CA_BUNDLE")
    request = HTTPXRequest(httpx_kwargs={"verify": ca_bundle}) if ca_bundle else HTTPXRequest()

    application = Application.builder().token(token).request(request).post_init(_post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()