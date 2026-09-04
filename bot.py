#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Group Leaderboard Bot — Anti-Spam Edition
====================================================
تک‌فایل، پایتون ۳، بدون نیاز به Redis یا PostgreSQL (فقط SQLite).

نصب:
    pip install python-telegram-bot --upgrade

اجرا:
    ۱) پایین‌تر در بخش CONFIG مقدار BOT_TOKEN را با توکن واقعی جایگزین کنید.
    ۲) python3 leaderboard_bot.py

امکانات:
    • شمارش پیام‌های هر عضو در هر گروه (به تفکیک هفته)
    • لیدربرد اعضای هر گروه + رتبه‌بندی کلی گروه‌ها
    • سیستم ضد اسپم دو لایه:
        ۱) فلود: تعداد پیام در بازه زمانی کوتاه بیشتر از حد مجاز
        ۲) تکرار: پیام‌های عیناً یکسان و پشت‌سرهم
      در صورت تشخیص اسپم:
        - پیام‌های اسپم در امتیاز رنکینگ شمارش نمی‌شوند
        - کاربر به‌صورت خودکار در گروه میوت می‌شود (اگر ربات ادمین باشد)
        - یک اخطار در گروه ارسال می‌شود

پیکربندی سریع پایین فایل، بخش CONFIG.

دستورات:
    /start /help          - راهنما (خصوصی)
    /aboutyou             - آمار شخصی در همه گروه‌ها (خصوصی)
    /groupleaderboard     - لیدربرد اعضای گروه فعلی (هفته جاری)
    /grouprank            - رتبه گروه فعلی بین همه گروه‌ها
    /globalranking        - رتبه‌بندی کلی گروه‌ها (خصوصی)
    /spamstatus           - آمار اسپم‌های شناسایی‌شده در گروه فعلی (ادمین)
    /unmute <reply>       - رفع میوت دستی با ریپلای روی پیام کاربر (ادمین)
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque

from telegram import Update, ChatPermissions
from telegram.constants import ChatType, ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ───────────────────────────── CONFIG ──────────────────────────────
# توکن ربات را همین‌جا بین کوتیشن‌ها بگذارید (از @BotFather دریافت می‌شود)
BOT_TOKEN = "8427889097:AAFH0TFhHKKutLNTyjdhm8GTK2SgTWGqDQ4"

FLOOD_MAX_MESSAGES = 6          # حداکثر پیام مجاز در بازه زمانی زیر
FLOOD_WINDOW_SECONDS = 8        # بازه زمانی تشخیص فلود (ثانیه)
DUPLICATE_MAX_REPEAT = 3        # حداکثر تعداد پیام یکسان پشت‌سرهم مجاز
MUTE_DURATION_MINUTES = 30      # مدت میوت خودکار پس از تشخیص اسپم
# ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("leaderboard_bot")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leaderboard.db")

# بافر درون‌حافظه‌ای برای تشخیص فلود/تکرار به ازای هر (chat_id, user_id)
_recent_messages: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=20))
_spam_counters: dict[int, int] = defaultdict(int)  # chat_id -> تعداد اسپم شناسایی‌شده


# ───────────────────────────── DATABASE ──────────────────────────────
def get_week_start() -> str:
    """تاریخ دوشنبهٔ هفته جاری (UTC)، به شکل YYYY-MM-DD."""
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    conn = db_connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title   TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id    INTEGER PRIMARY KEY,
            username   TEXT,
            first_name TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            chat_id    INTEGER,
            user_id    INTEGER,
            week_start TEXT,
            count      INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, user_id, week_start)
        );

        CREATE TABLE IF NOT EXISTS spam_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id   INTEGER,
            user_id   INTEGER,
            reason    TEXT,
            ts        TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def upsert_group(chat_id: int, title: str) -> None:
    conn = db_connect()
    conn.execute(
        "INSERT INTO groups (chat_id, title) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title",
        (chat_id, title),
    )
    conn.commit()
    conn.close()


def upsert_user(user_id: int, username: str | None, first_name: str) -> None:
    conn = db_connect()
    conn.execute(
        "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
        (user_id, username, first_name),
    )
    conn.commit()
    conn.close()


def increment_message_count(chat_id: int, user_id: int, week_start: str) -> None:
    conn = db_connect()
    conn.execute(
        """
        INSERT INTO messages (chat_id, user_id, week_start, count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(chat_id, user_id, week_start)
        DO UPDATE SET count = count + 1
        """,
        (chat_id, user_id, week_start),
    )
    conn.commit()
    conn.close()


def log_spam(chat_id: int, user_id: int, reason: str) -> None:
    conn = db_connect()
    conn.execute(
        "INSERT INTO spam_log (chat_id, user_id, reason, ts) VALUES (?, ?, ?, ?)",
        (chat_id, user_id, reason, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    _spam_counters[chat_id] += 1


# ───────────────────────────── ANTI-SPAM ──────────────────────────────
async def is_user_admin(update: Update) -> bool:
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == ChatType.PRIVATE:
        return True
    member = await chat.get_member(user.id)
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


def detect_spam(chat_id: int, user_id: int, text: str) -> str | None:
    """
    بررسی می‌کند آیا پیام جدید نشانه اسپم است یا نه.
    در صورت اسپم بودن، رشتهٔ دلیل را برمی‌گرداند؛ در غیر این صورت None.
    """
    key = (chat_id, user_id)
    now = datetime.now(timezone.utc)
    buf = _recent_messages[key]
    buf.append((now, text))

    # ۱) تشخیص فلود: چند پیام در بازه زمانی کوتاه
    window_start = now - timedelta(seconds=FLOOD_WINDOW_SECONDS)
    recent_count = sum(1 for ts, _ in buf if ts >= window_start)
    if recent_count > FLOOD_MAX_MESSAGES:
        return f"فلود: {recent_count} پیام در {FLOOD_WINDOW_SECONDS} ثانیه"

    # ۲) تشخیص پیام تکراری پشت‌سرهم
    if text:
        last_texts = [t for _, t in list(buf)[-DUPLICATE_MAX_REPEAT:]]
        if len(last_texts) == DUPLICATE_MAX_REPEAT and len(set(last_texts)) == 1:
            return f"تکرار: {DUPLICATE_MAX_REPEAT} پیام یکسان پشت‌سرهم"

    return None


async def mute_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    """کاربر را برای مدت مشخص در گروه میوت می‌کند. در صورت موفقیت True برمی‌گرداند."""
    until = datetime.now(timezone.utc) + timedelta(minutes=MUTE_DURATION_MINUTES)
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        return True
    except Exception as exc:
        logger.warning("عدم موفقیت در میوت کاربر %s در گروه %s: %s", user_id, chat_id, exc)
        return False


# ───────────────────────────── HANDLERS ──────────────────────────────
async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if user is None or user.is_bot:
        return

    upsert_group(chat.id, chat.title)
    upsert_user(user.id, user.username, user.first_name)

    text = msg.text or msg.caption or ""
    reason = detect_spam(chat.id, user.id, text)

    if reason:
        log_spam(chat.id, user.id, reason)
        display_name = f"@{user.username}" if user.username else user.first_name
        muted = await mute_user(context, chat.id, user.id)
        try:
            await msg.delete()
        except Exception:
            pass

        if muted:
            note = (
                f"🚫 {display_name} به دلیل رفتار اسپم‌مانند ({reason}) "
                f"به مدت {MUTE_DURATION_MINUTES} دقیقه میوت شد.\n"
                f"پیام‌های اسپم در رنکینگ محاسبه نمی‌شوند."
            )
        else:
            note = (
                f"⚠️ رفتار اسپم‌مانند از {display_name} تشخیص داده شد ({reason})، "
                f"اما ربات دسترسی محدودسازی ندارد. لطفاً ربات را ادمین کنید."
            )
        await context.bot.send_message(chat_id=chat.id, text=note)
        return  # پیام اسپم در رنکینگ شمارش نمی‌شود

    increment_message_count(chat.id, user.id, get_week_start())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "سلام! 👋\n\n"
        "من ربات آمار، لیدربرد و ضدِ اسپم گروه‌ها هستم.\n"
        "من را به یک گروه اضافه و **ادمین** کن (برای قابلیت میوت خودکار) تا شروع کنم.\n\n"
        "📋 دستورات:\n"
        "/help — راهنما\n"
        "/aboutyou — آمار شخصی خودت\n"
        "/groupleaderboard — لیدربرد گروه (داخل گروه)\n"
        "/grouprank — رتبه گروه (داخل گروه)\n"
        "/globalranking — رتبه‌بندی کلی گروه‌ها (خصوصی)\n"
        "/spamstatus — آمار اسپم گروه (ادمین، داخل گروه)"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def aboutyou(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    week_start = get_week_start()
    conn = db_connect()
    rows = conn.execute(
        """
        SELECT g.title, m.count
        FROM messages m JOIN groups g ON g.chat_id = m.chat_id
        WHERE m.user_id = ? AND m.week_start = ?
        ORDER BY m.count DESC
        """,
        (user.id, week_start),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("این هفته هنوز پیام معتبری از تو در گروه‌های ثبت‌شده ندیدم.")
        return

    lines = ["📊 آمار پیام‌های معتبر تو در این هفته:\n"]
    lines += [f"• {r['title'] or 'گروه ناشناس'}: {r['count']} پیام" for r in rows]
    await update.message.reply_text("\n".join(lines))


async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("این دستور فقط داخل گروه کار می‌کند.")
        return

    conn = db_connect()
    rows = conn.execute(
        """
        SELECT u.username, u.first_name, m.count
        FROM messages m JOIN users u ON u.user_id = m.user_id
        WHERE m.chat_id = ? AND m.week_start = ?
        ORDER BY m.count DESC LIMIT 10
        """,
        (chat.id, get_week_start()),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("این هفته هنوز پیام معتبری ثبت نشده.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"🏆 پرفعالیت‌ترین اعضای «{chat.title}» این هفته:\n"]
    for i, r in enumerate(rows):
        rank_icon = medals[i] if i < 3 else f"{i + 1}."
        name = f"@{r['username']}" if r["username"] else r["first_name"]
        lines.append(f"{rank_icon} {name} — {r['count']} پیام")
    await update.message.reply_text("\n".join(lines))


async def grouprank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("این دستور فقط داخل گروه کار می‌کند.")
        return

    week_start = get_week_start()
    conn = db_connect()
    rows = conn.execute(
        """
        SELECT chat_id, SUM(count) AS total
        FROM messages WHERE week_start = ?
        GROUP BY chat_id ORDER BY total DESC
        """,
        (week_start,),
    ).fetchall()
    conn.close()

    rank, my_total = None, 0
    for i, r in enumerate(rows, start=1):
        if r["chat_id"] == chat.id:
            rank, my_total = i, r["total"]
            break

    if rank is None:
        await update.message.reply_text("هنوز آماری برای این گروه در این هفته ثبت نشده.")
        return

    await update.message.reply_text(
        f"📈 رتبه گروه «{chat.title}»: {rank} از {len(rows)}\n"
        f"مجموع پیام‌های معتبر این هفته: {my_total}"
    )


async def globalranking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("این دستور را در خصوصی با من اجرا کن.")
        return

    conn = db_connect()
    rows = conn.execute(
        """
        SELECT g.title, SUM(m.count) AS total
        FROM messages m JOIN groups g ON g.chat_id = m.chat_id
        WHERE m.week_start = ?
        GROUP BY m.chat_id ORDER BY total DESC LIMIT 15
        """,
        (get_week_start(),),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("هنوز هیچ گروهی آمار معتبری ثبت نکرده.")
        return

    lines = ["🌍 رتبه‌بندی کلی گروه‌ها (پیام معتبر این هفته):\n"]
    lines += [f"{i}. {r['title'] or 'گروه ناشناس'} — {r['total']} پیام" for i, r in enumerate(rows, 1)]
    await update.message.reply_text("\n".join(lines))


async def spamstatus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("این دستور فقط داخل گروه کار می‌کند.")
        return
    if not await is_user_admin(update):
        await update.message.reply_text("این دستور فقط برای ادمین‌های گروه است.")
        return

    conn = db_connect()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM spam_log WHERE chat_id = ?", (chat.id,)
    ).fetchone()
    recent = conn.execute(
        """
        SELECT u.username, u.first_name, s.reason, s.ts
        FROM spam_log s LEFT JOIN users u ON u.user_id = s.user_id
        WHERE s.chat_id = ? ORDER BY s.id DESC LIMIT 5
        """,
        (chat.id,),
    ).fetchall()
    conn.close()

    lines = [f"🛡 مجموع موارد اسپم شناسایی‌شده در این گروه: {row['c']}\n"]
    if recent:
        lines.append("آخرین موارد:")
        for r in recent:
            name = f"@{r['username']}" if r["username"] else (r["first_name"] or "ناشناس")
            lines.append(f"• {name} — {r['reason']}")
    await update.message.reply_text("\n".join(lines))


async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("این دستور فقط داخل گروه کار می‌کند.")
        return
    if not await is_user_admin(update):
        await update.message.reply_text("این دستور فقط برای ادمین‌های گروه است.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("برای رفع میوت، این دستور را روی پیام کاربر ریپلای کن.")
        return

    target = update.message.reply_to_message.from_user
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await update.message.reply_text(f"✅ کاربر {target.first_name} از حالت میوت خارج شد.")
    except Exception as exc:
        await update.message.reply_text(f"خطا در رفع میوت: {exc}")


# ───────────────────────────── MAIN ──────────────────────────────
def main() -> None:
    token = BOT_TOKEN
    if not token or token == "اینجا-توکن-خودت-را-بگذار":
        raise SystemExit(
            "خطا: توکن ربات تنظیم نشده.\n"
            "بالای فایل، متغیر BOT_TOKEN را با توکن واقعی از BotFather پر کنید."
        )

    init_db()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("aboutyou", aboutyou))
    app.add_handler(CommandHandler("groupleaderboard", groupleaderboard))
    app.add_handler(CommandHandler("grouprank", grouprank))
    app.add_handler(CommandHandler("globalranking", globalranking))
    app.add_handler(CommandHandler("spamstatus", spamstatus))
    app.add_handler(CommandHandler("unmute", unmute_cmd))

    app.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), track_message))

    logger.info("ربات در حال اجراست...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
