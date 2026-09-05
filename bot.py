"""
Selfbot - Auto Forward & Extract Bot Response
============================================
دستورات:
  .enable <group_id> <user_id>  - فعال کردن برای یه گروه و یه کاربر
  .disable <group_id>            - غیرفعال کردن
  .captions add <group_id> <caption> - اضافه کردن کپشن
  .captions remove <group_id> <caption> - حذف کپشن
  .captions list <group_id>      - لیست کپشن‌ها
  .status                        - وضعیت فعلی
"""

from telethon import TelegramClient, events
from telethon.tl.types import Message
import json, os, re

# ─── تنظیمات ────────────────────────────────────────────────────────────────
API_ID   = 29206821          # ← API ID خودت رو بذار
API_HASH = "6fc091b004de021d44c76f01e27fe91c"         # ← API Hash خودت رو بذار
SESSION  = "selfbot"  # اسم فایل session

# ایدی ربات که پیام بهش فوروارد میشه
PICKER_BOT = "character_picker_bot"

# ─── State ──────────────────────────────────────────────────────────────────
CONFIG_FILE = "selfbot_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# config structure:
# { "group_id": { "user_id": 123, "captions": ["caption1", ...] } }
config = load_config()

# نگه داشتن پیام‌هایی که فوروارد شدن و منتظر جواب ربات هستیم
# { group_id: message_id_that_was_forwarded }
pending = {}

# ─── Client ─────────────────────────────────────────────────────────────────
client = TelegramClient(SESSION, API_ID, API_HASH)


# ─── دستورات مدیریتی (توی هر چتی) ──────────────────────────────────────────

@client.on(events.NewMessage(outgoing=True, pattern=r'\.enable\s+(-?\d+)\s+(\d+)'))
async def cmd_enable(event):
    group_id = int(event.pattern_match.group(1))
    user_id  = int(event.pattern_match.group(2))
    if str(group_id) not in config:
        config[str(group_id)] = {"user_id": user_id, "captions": []}
    else:
        config[str(group_id)]["user_id"] = user_id
    save_config(config)
    await event.edit(f"✅ فعال شد برای گروه `{group_id}` — کاربر: `{user_id}`")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.disable\s+(-?\d+)'))
async def cmd_disable(event):
    group_id = str(int(event.pattern_match.group(1)))
    if group_id in config:
        del config[group_id]
        save_config(config)
        await event.edit(f"🔴 غیرفعال شد برای گروه `{group_id}`")
    else:
        await event.edit("❌ این گروه فعال نبود.")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.captions\s+add\s+(-?\d+)\s+(.+)'))
async def cmd_caption_add(event):
    group_id = str(int(event.pattern_match.group(1)))
    caption  = event.pattern_match.group(2).strip()
    if group_id not in config:
        await event.edit("❌ اول با `.enable` گروه رو فعال کن.")
        return
    if caption not in config[group_id]["captions"]:
        config[group_id]["captions"].append(caption)
        save_config(config)
    await event.edit(f"✅ کپشن اضافه شد:\n`{caption}`")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.captions\s+remove\s+(-?\d+)\s+(.+)'))
async def cmd_caption_remove(event):
    group_id = str(int(event.pattern_match.group(1)))
    caption  = event.pattern_match.group(2).strip()
    if group_id in config and caption in config[group_id]["captions"]:
        config[group_id]["captions"].remove(caption)
        save_config(config)
        await event.edit(f"✅ کپشن حذف شد:\n`{caption}`")
    else:
        await event.edit("❌ کپشن پیدا نشد.")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.captions\s+list\s+(-?\d+)'))
async def cmd_caption_list(event):
    group_id = str(int(event.pattern_match.group(1)))
    if group_id not in config or not config[group_id]["captions"]:
        await event.edit("📋 هیچ کپشنی ثبت نشده.")
        return
    lines = "\n".join(f"• `{c}`" for c in config[group_id]["captions"])
    await event.edit(f"📋 کپشن‌های گروه `{group_id}`:\n{lines}")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.status'))
async def cmd_status(event):
    if not config:
        await event.edit("📊 هیچ گروهی فعال نیست.")
        return
    lines = []
    for gid, data in config.items():
        caps = ", ".join(data["captions"]) or "—"
        lines.append(f"**گروه** `{gid}` | **کاربر** `{data['user_id']}`\nکپشن‌ها: {caps}")
    await event.edit("📊 **وضعیت:**\n\n" + "\n\n".join(lines))


# ─── شنیدن پیام‌های گروه ────────────────────────────────────────────────────

@client.on(events.NewMessage(incoming=True))
async def on_group_message(event):
    if not event.is_group and not event.is_channel:
        return

    group_id = str(event.chat_id)
    if group_id not in config:
        return

    cfg      = config[group_id]
    user_id  = cfg["user_id"]
    captions = cfg["captions"]

    # بررسی فرستنده
    if event.sender_id != user_id:
        return

    # بررسی کپشن
    msg_caption = (event.message.message or "").strip()
    if not any(cap.lower() in msg_caption.lower() for cap in captions):
        return

    # فوروارد به ربات
    bot = await client.get_entity(PICKER_BOT)
    forwarded = await client.forward_messages(bot, event.message)
    pending[group_id] = event.chat_id  # گروه اصلی رو نگه می‌داریم
    print(f"[+] پیام فوروارد شد به {PICKER_BOT}")


# ─── شنیدن جواب ربات ────────────────────────────────────────────────────────

@client.on(events.NewMessage(incoming=True, from_users=PICKER_BOT))
async def on_bot_response(event):
    text = event.message.message or ""

    # پیدا کردن بخش /pick...
    # مثال: /pick@character_picker_bot raiden
    match = re.search(r'(/pick@\S+\s+\S+)', text)
    if not match:
        return

    command = match.group(1).strip()

    # ارسال توی گروه‌هایی که pending هستن
    for group_id, chat_id in list(pending.items()):
        await client.send_message(chat_id, command)
        print(f"[+] دستور ارسال شد به گروه {chat_id}: {command}")
        del pending[group_id]


# ─── اجرا ───────────────────────────────────────────────────────────────────
print("🤖 Selfbot در حال اجراست...")
client.start()
client.run_until_disconnected()
