import os
import asyncio
import json
from datetime import datetime, timezone

from dotenv import load_dotenv
from google import genai
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

LOG_FILE = "log-session.json"

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing from .env")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing from .env")


# ============================================================
# GEMINI
# ============================================================

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={
        "timeout": 15000,
    },
)


# ============================================================
# SESSION LOGGING
# ============================================================

def load_users():
    """Load users from log-session.json."""

    if not os.path.exists(LOG_FILE):
        return {}

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_users(users):
    """Save users to log-session.json."""

    temp_file = LOG_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(users, file, indent=2, ensure_ascii=False)

    os.replace(temp_file, LOG_FILE)


def log_user(update: Update):
    """Capture Telegram user information."""

    user = update.effective_user

    if not user:
        return

    user_id = str(user.id)

    now = datetime.now(timezone.utc).isoformat()

    users = load_users()

    # New user
    if user_id not in users:
        users[user_id] = {
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "first_seen": now,
            "last_seen": now,
            "messages": 0,
        }

    # Existing user
    else:
        users[user_id]["username"] = user.username
        users[user_id]["first_name"] = user.first_name
        users[user_id]["last_name"] = user.last_name
        users[user_id]["last_seen"] = now

    users[user_id]["messages"] += 1

    save_users(users)


# ============================================================
# /start
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    log_user(update)

    await update.message.reply_text(
        "👋 Hello!\n\n"
        "I'm your Gemini AI bot.\n"
        "Send me a question, code, text, or anything you need help with."
    )


# ============================================================
# NORMAL MESSAGES
# ============================================================

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Log user before processing the message
    log_user(update)

    user_text = update.message.text

    await update.message.chat.send_action("typing")

    try:

        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model="gemini-3.5-flash-lite",
                contents=user_text,
            ),
            timeout=20,
        )

        if response.text:

            await update.message.reply_text(
                response.text
            )

        else:

            await update.message.reply_text(
                "❌ Gemini returned an empty response."
            )

    except asyncio.TimeoutError:

        print("Gemini request timed out.")

        await update.message.reply_text(
            "⏱️ Gemini took too long to respond. Please try again."
        )

    except Exception as e:

        error_text = str(e)

        print(f"Gemini error: {error_text}")

        if "503" in error_text or "UNAVAILABLE" in error_text:

            await update.message.reply_text(
                "⚠️ Gemini is temporarily busy. Please try again."
            )

        elif "429" in error_text:

            await update.message.reply_text(
                "⚠️ Gemini's free-tier limit was reached. "
                "Please try again later."
            )

        else:

            await update.message.reply_text(
                "❌ Something went wrong while contacting Gemini."
            )


# ============================================================
# MAIN
# ============================================================

def main():

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            chat
        )
    )

    print("🤖 Bot is running...")
    print("📊 User logging enabled.")
    print(f"📝 Log file: {LOG_FILE}")

    app.run_polling()


if __name__ == "__main__":
    main()