"""
Selfbot - Auto Forward & Extract Bot Response
============================================
دستورات:
  .enable <group_id> <user_id>  - فعال کردن برای یه گروه و یه کاربر
  .disable <group_id>            - غیرفعال کردن
  .captions add <caption>        - اضافه کردن کپشن (عمومی برای همه گروه‌ها)
  .captions remove <caption>     - حذف کپشن
  .captions list                 - لیست همه کپشن‌ها
  .status                        - وضعیت فعلی
"""

from telethon import TelegramClient, events
import json, os, re, asyncio

# ─── تنظیمات ────────────────────────────────────────────────────────────────
API_ID   = 29206821          # ← API ID خودت رو بذار
API_HASH = "6fc091b004de021d44c76f01e27fe91c"    # ← API Hash خودت رو بذار
SESSION  = "selfbot"  # اسم فایل session

# دیلی قبل از ارسال دستور توی گروه (ثانیه)
SEND_DELAY = 1.2

# ایدی ربات که پیام بهش فوروارد میشه
PICKER_BOT = "zswaifu_cheat_bot"

# ─── Config ─────────────────────────────────────────────────────────────────
CONFIG_FILE = "selfbot_config.json"

# ساختار:
# {
#   "captions": ["caption1", "caption2", ...],   ← عمومی برای همه گروه‌ها
#   "groups": { "group_id": user_id, ... }
# }

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            data = json.load(f)
            # مطمئن شو هر دو کلید وجود دارن
            data.setdefault("captions", [])
            data.setdefault("groups", {})
            return data
    return {"captions": [], "groups": {}}

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

config = load_config()

# pending: { group_id_str: chat_id }
pending = {}

# ─── Client ─────────────────────────────────────────────────────────────────
client = TelegramClient(SESSION, API_ID, API_HASH)


# ─── دستورات مدیریتی ────────────────────────────────────────────────────────

@client.on(events.NewMessage(outgoing=True, pattern=r'\.enable\s+(-?\d+)\s+(\d+)'))
async def cmd_enable(event):
    group_id = str(int(event.pattern_match.group(1)))
    user_id  = int(event.pattern_match.group(2))
    config["groups"][group_id] = user_id
    save_config()
    await event.edit(f"✅ فعال شد برای گروه `{group_id}` — کاربر: `{user_id}`")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.disable\s+(-?\d+)'))
async def cmd_disable(event):
    group_id = str(int(event.pattern_match.group(1)))
    if group_id in config["groups"]:
        del config["groups"][group_id]
        save_config()
        await event.edit(f"🔴 غیرفعال شد برای گروه `{group_id}`")
    else:
        await event.edit("❌ این گروه فعال نبود.")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.captions\s+add\s+(.+)'))
async def cmd_caption_add(event):
    caption = event.pattern_match.group(1).strip()
    if caption not in config["captions"]:
        config["captions"].append(caption)
        save_config()
        await event.edit(f"✅ کپشن اضافه شد:\n`{caption}`")
    else:
        await event.edit(f"⚠️ این کپشن قبلاً وجود داشت:\n`{caption}`")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.captions\s+remove\s+(.+)'))
async def cmd_caption_remove(event):
    caption = event.pattern_match.group(1).strip()
    if caption in config["captions"]:
        config["captions"].remove(caption)
        save_config()
        await event.edit(f"✅ کپشن حذف شد:\n`{caption}`")
    else:
        await event.edit("❌ کپشن پیدا نشد.")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.captions\s+list'))
async def cmd_caption_list(event):
    if not config["captions"]:
        await event.edit("📋 هیچ کپشنی ثبت نشده.")
        return
    lines = "\n".join(f"{i+1}. `{c}`" for i, c in enumerate(config["captions"]))
    await event.edit(f"📋 **کپشن‌های فعال ({len(config['captions'])}):**\n{lines}")


@client.on(events.NewMessage(outgoing=True, pattern=r'\.helps'))
async def cmd_help(event):
    await event.edit(
        "📖 **راهنمای دستورات Selfbot**\n\n"

        "**⚙️ مدیریت گروه‌ها:**\n"
        "`.enable <group_id> <user_id>`\n"
        "  └ فعال کردن برای یه گروه و کاربر مشخص\n\n"
        "`.disable <group_id>`\n"
        "  └ غیرفعال کردن یه گروه\n\n"

        "**📋 مدیریت کپشن‌ها (عمومی):**\n"
        "`.captions add <متن>`\n"
        "  └ اضافه کردن کپشن جدید\n\n"
        "`.captions remove <متن>`\n"
        "  └ حذف یه کپشن\n\n"
        "`.captions list`\n"
        "  └ دیدن لیست همه کپشن‌ها\n\n"

        "**📊 وضعیت:**\n"
        "`.status`\n"
        "  └ نمایش گروه‌های فعال و کپشن‌های ثبت‌شده\n\n"

        "`.helps`\n"
        "  └ نمایش همین راهنما\n\n"

        "**💡 نکات:**\n"
        "• کپشن‌ها برای همه گروه‌ها مشترکن\n"
        "• دیلی ارسال دستور: `1.5` ثانیه\n"
        "• تنظیمات توی `selfbot_config.json` ذخیره میشن"
    )


@client.on(events.NewMessage(outgoing=True, pattern=r'\.status'))
async def cmd_status(event):
    groups = config["groups"]
    captions = config["captions"]

    if not groups:
        groups_text = "هیچ گروهی فعال نیست."
    else:
        groups_text = "\n".join(f"• گروه `{gid}` — کاربر `{uid}`" for gid, uid in groups.items())

    caps_text = "\n".join(f"  {i+1}. `{c}`" for i, c in enumerate(captions)) if captions else "  —"

    await event.edit(
        f"📊 **وضعیت:**\n\n"
        f"**گروه‌های فعال:**\n{groups_text}\n\n"
        f"**کپشن‌های عمومی:**\n{caps_text}"
    )


# ─── شنیدن پیام‌های گروه ────────────────────────────────────────────────────

@client.on(events.NewMessage(incoming=True))
async def on_group_message(event):
    if not event.is_group and not event.is_channel:
        return

    group_id = str(event.chat_id)
    if group_id not in config["groups"]:
        return

    user_id  = config["groups"][group_id]
    captions = config["captions"]

    if event.sender_id != user_id:
        return

    if not captions:
        return

    msg_text = (event.message.message or "").strip()
    if not any(cap.lower() in msg_text.lower() for cap in captions):
        return

    # فوروارد به ربات
    bot = await client.get_entity(PICKER_BOT)
    await client.forward_messages(bot, event.message)
    pending[group_id] = event.chat_id
    print(f"[+] پیام فوروارد شد به {PICKER_BOT}")


# ─── شنیدن جواب ربات ────────────────────────────────────────────────────────

@client.on(events.NewMessage(incoming=True, from_users=PICKER_BOT))
async def on_bot_response(event):
    text = event.message.message or ""

    match = re.search(r'(/pick@\S+\s+\S+)', text)
    if not match:
        return

    command = match.group(1).strip()

    for group_id, chat_id in list(pending.items()):
        await asyncio.sleep(SEND_DELAY)
        await client.send_message(chat_id, command)
        print(f"[+] دستور ارسال شد به گروه {chat_id}: {command}")
        del pending[group_id]


# ─── اجرا ───────────────────────────────────────────────────────────────────
print("🤖 Selfbot در حال اجراست...")
client.start()
client.run_until_disconnected()
