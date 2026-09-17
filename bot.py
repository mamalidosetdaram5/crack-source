"""
Telegram Self-Bot - نسخه بهینه
================================
دستورات توی Saved Messages:
  .watch on -100xxxxxxxxx   → فعال کردن مانیتور گروه
  .watch off -100xxxxxxxxx  → غیرفعال کردن مانیتور گروه
  .watched                  → لیست گروه‌های فعال
  .hashes                   → تعداد hash های ذخیره شده
  .scan -100xxxxxxxxx       → اسکن تاریخچه چنل و hash همه ویدیوها
"""

import asyncio
import hashlib
import io
import json
import os
import re
import tempfile

import cv2
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument

# ─── تنظیمات ───────────────────────────────────────────────────────────────
API_ID   = 29206821        # از my.telegram.org
API_HASH = "6fc091b004de021d44c76f01e27fe91c"       # از my.telegram.org
SESSION  = "selfbot"

MAX_CHUNK = 1 * 1024 * 1024  # 1MB برای فریم اول کافیه

DATA_FILE = "selfbot_data.json"

# ─── pattern کپشن ──────────────────────────────────────────────────────────
# خط ID: 「 𝐈𝐃 : 8214 Dolce & Gabbana X Rarity 💠 」
ID_LINE_PATTERN = re.compile(
    r"「\s*𝐈𝐃\s*:\s*\d+\s+(.+?)\s*」",
    re.UNICODE
)

# حذف اموجی‌های آخر اسم
TRAILING_EMOJI = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u27BF\u2B50\u2B55\uFE0F\u200D"
    r"\u20D0-\u20FF\u2300-\u23FF\u25A0-\u25FF\u2700-\u27BF"
    r"\U0001F000-\U0001F9FF\U0001FA00-\U0001FAFF\s]+$",
    re.UNICODE
)

CAPTION_MARKER = "⛩ A new character has just spawned"

# ─── دیتا ──────────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"watched_groups": [], "hashes": {}}

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data = load_data()

# ─── توابع کمکی ────────────────────────────────────────────────────────────
def parse_name(caption: str) -> str | None:
    m = ID_LINE_PATTERN.search(caption)
    if not m:
        return None
    name = m.group(1).strip()
    name = TRAILING_EMOJI.sub("", name).strip()
    return name if name else None


async def get_video_hash8(client, message) -> str | None:
    """فقط 1MB اول دانلود، فریم اول استخراج، MD5[:8] برگردون"""
    try:
        buf = io.BytesIO()
        downloaded = 0

        async for chunk in client.iter_download(message.media, chunk_size=64*1024):
            buf.write(chunk)
            downloaded += len(chunk)
            if downloaded >= MAX_CHUNK:
                break

        buf.seek(0)
        raw = buf.read()

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        cap = cv2.VideoCapture(tmp_path)
        ret, frame = cap.read()
        cap.release()

        try:
            os.unlink(tmp_path)
        except:
            pass

        if not ret or frame is None:
            print("[hash] فریم اول پیدا نشد")
            return None

        md5 = hashlib.md5(frame.tobytes()).hexdigest()
        return md5[:8]

    except Exception as e:
        print(f"[hash error] {e}")
        return None


def is_valid_video(message) -> bool:
    if not message.media:
        return False
    if not isinstance(message.media, MessageMediaDocument):
        return False
    doc = message.media.document
    for attr in doc.attributes:
        if type(attr).__name__ in ("DocumentAttributeVideo", "DocumentAttributeAnimated"):
            return True
    if hasattr(doc, "mime_type") and "video" in (doc.mime_type or ""):
        return True
    return False


# ─── کلاینت ────────────────────────────────────────────────────────────────
client = TelegramClient(SESSION, API_ID, API_HASH)
_me_id = None

async def get_me_id():
    global _me_id
    if _me_id is None:
        me = await client.get_me()
        _me_id = me.id
    return _me_id


# ─── دستورات (Saved Messages) ───────────────────────────────────────────────
@client.on(events.NewMessage(outgoing=True))
async def handle_commands(event):
    me_id = await get_me_id()
    if event.chat_id != me_id:
        return

    text = event.raw_text.strip()

    # .watch on -100xxx
    m = re.match(r"^\.watch on (-\d+)$", text)
    if m:
        gid = int(m.group(1))
        if gid not in data["watched_groups"]:
            data["watched_groups"].append(gid)
            save_data(data)
            await event.edit(f"✅ مانیتور فعال: `{gid}`")
        else:
            await event.edit(f"ℹ️ قبلاً فعال بود: `{gid}`")
        return

    # .watch off -100xxx
    m = re.match(r"^\.watch off (-\d+)$", text)
    if m:
        gid = int(m.group(1))
        if gid in data["watched_groups"]:
            data["watched_groups"].remove(gid)
            save_data(data)
            await event.edit(f"🔴 غیرفعال شد: `{gid}`")
        else:
            await event.edit(f"ℹ️ این گروه مانیتور نبود: `{gid}`")
        return

    # .watched
    if text == ".watched":
        if data["watched_groups"]:
            lst = "\n".join(f"`{g}`" for g in data["watched_groups"])
            await event.edit(f"📋 گروه‌های فعال:\n{lst}")
        else:
            await event.edit("📋 هیچ گروهی فعال نیست")
        return

    # .hashes
    if text == ".hashes":
        await event.edit(f"🗄 تعداد hash ذخیره شده: `{len(data['hashes'])}`")
        return

    # .scan -100xxx
    m = re.match(r"^\.scan (-\d+)$", text)
    if m:
        channel_id = int(m.group(1))
        await event.edit(f"🔍 شروع اسکن `{channel_id}` ...")
        count_new = 0
        count_skip = 0
        count_total = 0

        try:
            async for msg in client.iter_messages(channel_id, filter=None):
                if not is_valid_video(msg):
                    continue
                caption = msg.message or ""
                if CAPTION_MARKER not in caption:
                    continue

                name = parse_name(caption)
                if not name:
                    continue

                count_total += 1

                h8 = await get_video_hash8(client, msg)
                if not h8:
                    count_skip += 1
                    continue

                if h8 not in data["hashes"]:
                    data["hashes"][h8] = name
                    save_data(data)
                    count_new += 1
                    print(f"[scan] {h8} → {name}")
                else:
                    count_skip += 1

                # هر ۱۰ تا آپدیت وضعیت بده
                if (count_new + count_skip) % 10 == 0:
                    await event.edit(
                        f"🔍 اسکن در حال انجام...\n"
                        f"✅ جدید: `{count_new}` | ⏭ تکراری: `{count_skip}` | 📦 کل: `{count_total}`"
                    )

        except Exception as e:
            await event.edit(f"❌ خطا: {e}")
            return

        await event.edit(
            f"✅ اسکن تموم شد!\n"
            f"📦 کل ویدیو: `{count_total}`\n"
            f"🆕 hash جدید: `{count_new}`\n"
            f"⏭ تکراری/خطا: `{count_skip}`"
        )
        return


# ─── ثبت hash از ویدیوهای خودت (live) ──────────────────────────────────────
@client.on(events.NewMessage(outgoing=True))
async def handle_own_video(event):
    """ویدیویی که الان فرستادی با کپشن خاص → hash ذخیره"""
    me_id = await get_me_id()
    # توی saved messages دستور نباشه
    if event.chat_id == me_id:
        return
    if not is_valid_video(event.message):
        return

    caption = event.message.message or ""
    if CAPTION_MARKER not in caption:
        return

    name = parse_name(caption)
    if not name:
        print(f"[own] اسم پارس نشد: {caption[:80]}")
        return

    print(f"[own] hash گرفتن: {name}")
    h8 = await get_video_hash8(client, event.message)
    if not h8:
        return

    data["hashes"][h8] = name
    save_data(data)
    print(f"[saved] {h8} → {name}")


# ─── مانیتور گروه‌ها ──────────────────────────────────────────────────────
@client.on(events.NewMessage(incoming=True))
async def handle_group_video(event):
    """ویدیو در گروه مانیتور → hash → match → ارسال به Saved Messages"""
    if event.chat_id not in data["watched_groups"]:
        return
    if not is_valid_video(event.message):
        return

    caption = event.message.message or ""
    if CAPTION_MARKER not in caption:
        return

    print(f"[group] ویدیو با کپشن خاص در {event.chat_id}")
    h8 = await get_video_hash8(client, event.message)
    if not h8:
        return

    if h8 not in data["hashes"]:
        print(f"[group] hash {h8} در دیتابیس نیست")
        return

    name = data["hashes"][h8]
    pick_cmd = f"/pick {name}"

    me_id = await get_me_id()
    await client.send_message(me_id, f"`{pick_cmd}`")
    print(f"[match] {h8} → ارسال شد: {pick_cmd}")


# ─── اجرا ──────────────────────────────────────────────────────────────────
async def main():
    await client.start()
    me = await client.get_me()
    global _me_id
    _me_id = me.id
    print(f"✅ لاگین: {me.first_name} (@{me.username})")
    print(f"📋 گروه‌های مانیتور: {data['watched_groups']}")
    print(f"🗄  hash ذخیره شده: {len(data['hashes'])}")
    print("─" * 40)
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
