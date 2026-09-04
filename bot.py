#!/usr/bin/env python3
"""
Simple Telegram Group Leaderboard Bot - Single file, Python 3, SQLite
=======================================================================

نیازمندی‌ها:
    pip install python-telegram-bot --upgrade

اجرا:
    export BOT_TOKEN="توکن ربات از BotFather"
    python3 leaderboard_bot.py

امکانات:
    /start            - معرفی ربات (خصوصی)
    /help             - راهنما
    /aboutyou         - آمار شخصی خودت در همه گروه‌ها
    /groupleaderboard - لیدربرد کاربران فعال گروه فعلی (پیام‌های هفته جاری)
    /grouprank        - رتبه گروه فعلی نسبت به بقیه گروه‌ها (بر اساس تعداد پیام هفته جاری)
    /globalranking    - لیست همه گروه‌ها به ترتیب فعالیت (فقط خصوصی)

نکته: این نسخه ساده‌شده RimTUB/TopSupergroupsBot است. بدون نیاز به Redis یا PostgreSQL،
همه چیز در یک فایل SQLite (leaderboard.db) کنار همین اسکریپت ذخیره می‌شود.
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leaderboard.db")


def get_week_start():
    """شروع هفته جاری (دوشنبه، ساعت 00:00 UTC) به صورت رشته تاریخ."""
    now = datetime.utcnow()
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_connect()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            chat_id INTEGER,
            user_id INTEGER,
            week_start TEXT,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, user_id, week_start)
        );
        """
    )
    conn.commit()
    conn.close()


async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هر پیام گروهی رو می‌شماره (به جز پیام‌های خود ربات‌ها)."""
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if user is None or user.is_bot:
        return

    week_start = get_week_start()
    conn = db_connect()
    cur = conn.cursor()

    cur.execute(
        "INSERT OR REPLACE INTO groups (chat_id, title) VALUES (?, ?)",
        (chat.id, chat.title),
    )
    cur.execute(
        "INSERT OR REPLACE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
        (user.id, user.username, user.first_name),
    )
    cur.execute(
        """
        INSERT INTO messages (chat_id, user_id, week_start, count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(chat_id, user_id, week_start)
        DO UPDATE SET count = count + 1
        """,
        (chat.id, user.id, week_start),
    )
    conn.commit()
    conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! 👋\n"
        "من ربات آمار و لیدربرد گروه‌ها هستم.\n"
        "من رو به یک گروه اضافه کن تا شروع کنم به شمارش فعالیت اعضا.\n\n"
        "دستورات:\n"
        "/help - راهنما\n"
        "/aboutyou - آمار شخصی خودت\n"
        "/groupleaderboard - لیدربرد گروه (داخل گروه اجرا کن)\n"
        "/grouprank - رتبه گروه (داخل گروه اجرا کن)\n"
        "/globalranking - رتبه‌بندی کلی گروه‌ها (خصوصی)"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def aboutyou(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    week_start = get_week_start()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT g.title, m.count
        FROM messages m
        JOIN groups g ON g.chat_id = m.chat_id
        WHERE m.user_id = ? AND m.week_start = ?
        ORDER BY m.count DESC
        """,
        (user.id, week_start),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("این هفته هنوز پیامی از تو در گروه‌های ثبت‌شده ندیدم.")
        return

    lines = ["📊 آمار پیام‌های تو در این هفته:\n"]
    for row in rows:
        title = row["title"] or "گروه ناشناس"
        lines.append(f"• {title}: {row['count']} پیام")
    await update.message.reply_text("\n".join(lines))


async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("این دستور فقط داخل گروه کار می‌کنه.")
        return

    week_start = get_week_start()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.username, u.first_name, m.count
        FROM messages m
        JOIN users u ON u.user_id = m.user_id
        WHERE m.chat_id = ? AND m.week_start = ?
        ORDER BY m.count DESC
        LIMIT 10
        """,
        (chat.id, week_start),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("این هفته هنوز پیامی ثبت نشده.")
        return

    lines = [f"🏆 پرفعالیت‌ترین اعضای «{chat.title}» این هفته:\n"]
    for i, row in enumerate(rows, start=1):
        name = f"@{row['username']}" if row["username"] else row["first_name"]
        lines.append(f"{i}. {name} — {row['count']} پیام")
    await update.message.reply_text("\n".join(lines))


async def grouprank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("این دستور فقط داخل گروه کار می‌کنه.")
        return

    week_start = get_week_start()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT chat_id, SUM(count) as total
        FROM messages
        WHERE week_start = ?
        GROUP BY chat_id
        ORDER BY total DESC
        """,
        (week_start,),
    )
    rows = cur.fetchall()
    conn.close()

    rank = None
    total_groups = len(rows)
    my_total = 0
    for i, row in enumerate(rows, start=1):
        if row["chat_id"] == chat.id:
            rank = i
            my_total = row["total"]
            break

    if rank is None:
        await update.message.reply_text("هنوز آماری برای این گروه در این هفته ثبت نشده.")
        return

    await update.message.reply_text(
        f"📈 رتبه گروه «{chat.title}»: {rank} از {total_groups}\n"
        f"مجموع پیام‌های این هفته: {my_total}"
    )


async def globalranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != ChatType.PRIVATE:
        await update.message.reply_text("این دستور رو توی خصوصی با من اجرا کن.")
        return

    week_start = get_week_start()
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT g.title, SUM(m.count) as total
        FROM messages m
        JOIN groups g ON g.chat_id = m.chat_id
        WHERE m.week_start = ?
        GROUP BY m.chat_id
        ORDER BY total DESC
        LIMIT 15
        """,
        (week_start,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("هنوز هیچ گروهی آماری ثبت نکرده.")
        return

    lines = ["🌍 رتبه‌بندی کلی گروه‌ها (بر اساس پیام این هفته):\n"]
    for i, row in enumerate(rows, start=1):
        title = row["title"] or "گروه ناشناس"
        lines.append(f"{i}. {title} — {row['total']} پیام")
    await update.message.reply_text("\n".join(lines))


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit(
            "خطا: متغیر محیطی BOT_TOKEN تنظیم نشده.\n"
            "مثال: export BOT_TOKEN='123456:ABC-your-token'"
        )

    init_db()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("aboutyou", aboutyou))
    app.add_handler(CommandHandler("groupleaderboard", groupleaderboard))
    app.add_handler(CommandHandler("grouprank", grouprank))
    app.add_handler(CommandHandler("globalranking", globalranking))

    # شمارش هر پیام متنی/غیرمتنی داخل گروه‌ها (باید غیر از دستورات هم باشه)
    app.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), track_message))

    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
