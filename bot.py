from telethon import TelegramClient, events, errors
from telethon.tl.custom import Button
import asyncio
import json
import os
import random
from datetime import datetime

api_id = 29206821
api_hash = '6fc091b004de021d44c76f01e27fe91c'
client = TelegramClient('mmd1', api_id, api_hash)

TRIGGER_TEXT = "سلام بر همه اعضا گروه!"
NAME_BOT_USERNAME = '@zswaifu_cheat_bot'

SOURCE_BOTS = {
    8307651649: {"cmd": "/pick"},
}

HAPPY_FILE = 'happy.json'

def load_happy():
    if os.path.exists(HAPPY_FILE):
        with open(HAPPY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return [
        "عالی شد داداش! 🔥",
        "انجام شد گلم 💪",
        "اوکی شد، فدات 🥰",
        "مرسی که هستی کارآموز عزیز ❤️",
        "تموم شد، بریم بعدی 🚀",
        "همیشه برنده‌ای سید 👑",
        "شاهکاری امشبم 😎",
        "دقیقاً همینه که میخوای 🤝",
        "فدات بشم اوکیه ✨",
        "مثل همیشه عالی بودی 👍",
        "کارت درسته سرباز 🫡",
        "نوبل شد، دمت گرم 🌟",
        "همینه دیگه، ادامه بده 🔥",
        "گل گفتی داداش 🌹",
    ]

def save_happy(msgs):
    with open(HAPPY_FILE, 'w', encoding='utf-8') as f:
        json.dump(msgs, f, ensure_ascii=False, indent=2)

happy_messages = load_happy()

def save_happy_setting(val):
    global happy_enabled
    happy_enabled = val
    s = {}
    if os.path.exists('happy_setting.json'):
        with open('happy_setting.json', 'r') as f:
            s = json.load(f)
    s['enabled'] = val
    with open('happy_setting.json', 'w') as f:
        json.dump(s, f)

if os.path.exists('happy_setting.json'):
    with open('happy_setting.json', 'r') as f:
        happy_enabled = json.load(f).get('enabled', True)

def r():
    return random.choice(happy_messages)

auto_pick_enabled = True
happy_enabled = True
spamming_tasks = {}
tracked_chats = set()
_pending_requests = {}
_name_bot_id = None
_captions_cache = {}

def bot_caption_file(bot_id):
    return f'captions_{bot_id}.json'

def default_captions():
    return [
        {"name": "ُ🪞 Spirit", "text": "🪞 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🔮 Eloria", "text": "🔮 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "⛩ Infernal", "text": "⛩ A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "⚪️ Common", "text": "⚪️ A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🟠 Rare", "text": "🟠 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🟢 Mystic", "text": "🟢 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🟡 Legendary", "text": "🟡 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🎭 Elandra", "text": "🎭 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🪐 Arcane", "text": "🪐 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🌋 Velora", "text": "🌋 A new character has just spawned in the chat! 🍣", "enabled": True},
    ]

def load_bot_captions(bot_id):
    path = bot_caption_file(bot_id)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if data and isinstance(data[0], str):
                data = [{"name": f"Cap {i+1}", "text": t, "enabled": True} for i, t in enumerate(data)]
                save_bot_captions(bot_id, data)
            return data
    return default_captions()

def save_bot_captions(bot_id, caps):
    with open(bot_caption_file(bot_id), 'w', encoding='utf-8') as f:
        json.dump(caps, f, ensure_ascii=False, indent=2)
    _captions_cache[bot_id] = caps

def active_texts(bot_id):
    caps = _captions_cache.get(bot_id) or load_bot_captions(bot_id)
    return [c["text"] for c in caps if c.get("enabled", True)]

SPAWN_TRIGGERS = {
    "❓ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ!": "𝙎𝙥𝙖𝙬𝙣𝙚𝙙 𝙎𝙪𝙥𝙧𝙚𝙢𝙚 🪞 𝙤𝙧 𝘾𝙖𝙩𝙖𝙥𝙝𝙧𝙖𝙘𝙩 ✨@MyNameMamad",
    "⚡ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ!": "𝙎𝙥𝙖𝙬𝙣𝙚𝙙 𝘾𝙧𝙤𝙨𝙨𝙑𝙚𝙧𝙨𝙚 ⚡️@MyNameMamad",
    "👾 𝖭𝖾𝗐 𝖢𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋 𝗁𝖺𝗌 𝖲𝗉𝖺𝗐𝗇𝖾𝖽 𝗂𝗇𝗍𝗈 𝗍𝗁𝖾 𝖼𝗁𝖺𝗍!": "Spawned taker edittttt 👾 @MyNameMamad",
    "🪩 𝖭𝖾𝗐 𝖢𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋 𝗁𝖺𝗌 𝖲𝗉𝖺𝗐𝗇𝖾𝖽 𝗂𝗇𝗍𝗈 𝗍𝗁𝖾 𝖼𝗁𝖺𝗍!": "Spawned taker Harmony 🪩 @MyNameMamad",
}

@client.on(events.NewMessage(outgoing=True, pattern=r'\.spam (\d+) (.+)'))
async def start_spam(event):
    delay = int(event.pattern_match.group(1))
    message = event.pattern_match.group(2)
    chat_id = event.chat_id
    if chat_id in spamming_tasks:
        await event.reply("اسپم درحال اجراست [ .stop ] بزن.")
        return
    async def spammer():
        try:
            while True:
                await client.send_message(chat_id, message)
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[ERROR] Spammer for {chat_id}: {e}")
            spamming_tasks.pop(chat_id, None)
    task = asyncio.create_task(spammer())
    spamming_tasks[chat_id] = task
    await event.reply(f"{r()} | هر {delay} ثانیه")

@client.on(events.NewMessage(outgoing=True, pattern=r'\.stop'))
async def stop_spam(event):
    chat_id = event.chat_id
    task = spamming_tasks.pop(chat_id, None)
    if task:
        task.cancel()
        await event.reply(r())
    else:
        await event.reply("هیچ اسپمی در حال اجرا نیست.")

@client.on(events.NewMessage)
async def monitor_spawn(event):
    chat_id = event.chat_id
    message_text = (event.raw_text or "").strip()
    for trigger, reply in SPAWN_TRIGGERS.items():
        if trigger in message_text:
            task = spamming_tasks.pop(chat_id, None)
            if task:
                task.cancel()
                await client.send_message(chat_id, reply)
            return

@client.on(events.NewMessage(outgoing=True))
async def secret_activate(event):
    msg_text = (event.raw_text or "").strip()
    me_id = (await event.client.get_me()).id
    is_saved = event.chat_id == me_id
    if is_saved and msg_text.lstrip('-').isdigit():
        tracked_chats.add(int(msg_text))
        await event.reply(r())
        return
    if msg_text == TRIGGER_TEXT:
        chat_id = event.chat_id
        tracked_chats.add(chat_id)
        try:
            await event.delete()
        except errors.MessageDeleteForbiddenError:
            pass
        await client.send_message('me', f"فعال شد:\n{chat_id}")
        return

@client.on(events.NewMessage(outgoing=True))
async def manage(event):
    msg = (event.raw_text or "").strip()

    if msg == ".help":
        await event.reply(
            "━━━━━━━━━━━━━━━━━━\n"
            "        راهنما\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "📌 فعالسازی:\n"
            "سلام بر همه اعضا گروه!\n"
            ".pick on / off / status\n\n"
            "📋 کپشن‌ها:\n"
            ".panel <bot_id>  (پنل دکمه‌ای)\n"
            ".cap list [bot_id]\n"
            ".cap add <bot_id> <text>\n"
            ".cap toggle <bot_id> <num>\n"
            ".cap del <bot_id> <num>\n"
            ".cap clear <bot_id>\n\n"
            "😊 پیام‌های تأیید:\n"
            ".happy on / off\n"
            ".happy list / add / del\n\n"
            "💬 اسپم:\n"
            ".spam <sec> <text>\n"
            ".stop\n\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        return

    if msg.startswith('.pick '):
        parts = msg.split(maxsplit=2)
        cmd = parts[1] if len(parts) > 1 else ""
        has_id = len(parts) == 3 and parts[2].lstrip('-').isdigit()
        if cmd == "on":
            target = int(parts[2]) if has_id else event.chat_id
            tracked_chats.add(target)
            await event.reply(r())
        elif cmd == "off":
            target = int(parts[2]) if has_id else event.chat_id
            tracked_chats.discard(target)
            await event.reply(r())
        elif cmd == "status":
            if not tracked_chats:
                await event.reply("هیچ گروهی فعال نیست.")
            else:
                await event.reply("گروه‌های فعال:\n" + "\n".join(str(g) for g in tracked_chats))
        return

    if msg.startswith('.happy '):
        global happy_enabled
        parts = msg.split(maxsplit=2)
        cmd = parts[1] if len(parts) > 1 else ""
        if cmd == "on":
            happy_enabled = True
            save_happy_setting(True)
            await event.reply(r())
        elif cmd == "off":
            happy_enabled = False
            save_happy_setting(False)
            await event.reply(r())
        elif cmd == "list":
            if not happy_messages:
                await event.reply("هیچ پیامی نیست.")
                return
            await event.reply("پیام‌ها:\n" + "\n".join(f"{i+1}. {m}" for i, m in enumerate(happy_messages)))
        elif cmd == "add" and len(parts) == 3:
            happy_messages.append(parts[2])
            save_happy(happy_messages)
            await event.reply(r())
        elif cmd == "del" and len(parts) == 3 and parts[2].isdigit():
            idx = int(parts[2]) - 1
            if 0 <= idx < len(happy_messages):
                removed = happy_messages.pop(idx)
                save_happy(happy_messages)
                await event.reply(r())
            else:
                await event.reply(r())
        return

    me_id = (await event.client.get_me()).id
    if event.chat_id != me_id:
        return

    if msg.startswith('.panel '):
        parts = msg.split()
        target = int(parts[1]) if len(parts) == 2 and parts[1].lstrip('-').isdigit() else list(SOURCE_BOTS.keys())[0]
        if target not in SOURCE_BOTS:
            await event.reply(r())
            return
        caps = load_bot_captions(target)
        buttons = []
        for i, c in enumerate(caps):
            status = "✅" if c.get("enabled", True) else "❌"
            buttons.append([Button.inline(f"{status} {c['name']}", data=f"t_{target}_{i}")])
        buttons.append([Button.inline("➕ Add New", data=f"an_{target}")])
        await event.reply(f"📋 Bot {target}:", buttons=buttons)
        return

    if msg.startswith('.cap '):
        parts = msg.split(maxsplit=3)
        cmd = parts[1] if len(parts) > 1 else ""
        bot_ids = list(SOURCE_BOTS.keys())
        target_bot = None
        if len(parts) >= 3 and parts[2].lstrip('-').isdigit():
            target_bot = int(parts[2])
            arg_offset = 3
        elif bot_ids:
            target_bot = bot_ids[0]
            arg_offset = 2
        if not target_bot or target_bot not in SOURCE_BOTS:
            await event.reply(r())
            return
        if cmd == "list":
            caps = load_bot_captions(target_bot)
            if not caps:
                await event.reply(f"هیچ کپشنی برای {target_bot} نیست.")
                return
            lines = []
            for i, c in enumerate(caps):
                status = "✅" if c.get("enabled", True) else "❌"
                lines.append(f"{i+1}. {status} {c['name']}: {c['text'][:40]}...")
            await event.reply(f"کپشن‌های {target_bot}:\n" + "\n".join(lines))
        elif cmd == "add" and len(parts) > arg_offset:
            new_text = parts[arg_offset]
            caps = load_bot_captions(target_bot)
            name = f"Custom {len(caps)+1}"
            caps.append({"name": name, "text": new_text, "enabled": True})
            save_bot_captions(target_bot, caps)
            await event.reply(r())
        elif cmd == "del" and len(parts) > arg_offset and parts[arg_offset].isdigit():
            idx = int(parts[arg_offset]) - 1
            caps = load_bot_captions(target_bot)
            if 0 <= idx < len(caps):
                caps.pop(idx)
                for j, c in enumerate(caps):
                    if c['name'].startswith("Custom "):
                        c['name'] = f"Custom {j+1}"
                save_bot_captions(target_bot, caps)
                await event.reply(r())
            else:
                await event.reply(r())
        elif cmd == "toggle" and len(parts) > arg_offset and parts[arg_offset].isdigit():
            idx = int(parts[arg_offset]) - 1
            caps = load_bot_captions(target_bot)
            if 0 <= idx < len(caps):
                caps[idx]["enabled"] = not caps[idx].get("enabled", True)
                save_bot_captions(target_bot, caps)
                await event.reply(r())
        elif cmd == "clear":
            save_bot_captions(target_bot, [])
            await event.reply(r())
        return

@client.on(events.NewMessage)
async def handle_name_bot_response(event):
    global _name_bot_id
    if _name_bot_id and event.sender_id == _name_bot_id:
        for data in _pending_requests.values():
            if not data['done']:
                data['response'] = event
                data['done'] = True
                break

@client.on(events.CallbackQuery)
async def panel_callback(event):
    data = event.data.decode()
    if data.startswith("t_"):
        _, bot_id, idx = data.split("_")
        bot_id, idx = int(bot_id), int(idx)
        caps = load_bot_captions(bot_id)
        if 0 <= idx < len(caps):
            caps[idx]["enabled"] = not caps[idx].get("enabled", True)
            save_bot_captions(bot_id, caps)
            buttons = []
            for i, c in enumerate(caps):
                status = "✅" if c.get("enabled", True) else "❌"
                buttons.append([Button.inline(f"{status} {c['name']}", data=f"t_{bot_id}_{i}")])
            buttons.append([Button.inline("➕ Add New", data=f"an_{bot_id}")])
            await event.edit(f"📋 Bot {bot_id}:", buttons=buttons)
    elif data.startswith("an_"):
        await event.answer("از .cap add <bot_id> <text> استفاده کن.")

@client.on(events.NewMessage(from_users=list(SOURCE_BOTS.keys())))
async def handle_source_bot(event):
    chat_id = event.chat_id
    if chat_id not in tracked_chats:
        return
    if not event.message.media:
        return
    bot_config = SOURCE_BOTS.get(event.sender_id)
    if not bot_config:
        return
    caption_text = (event.message.raw_text or "").strip()
    if not any(t in caption_text for t in active_texts(event.sender_id)):
        return

    is_video = hasattr(event.message.media, 'document') and event.message.media.document.mime_type and 'video' in event.message.media.document.mime_type

    if is_video:
        cmd = bot_config["cmd"]
        await client.send_message(chat_id, f"{cmd} (Christmas 2025)", parse_mode=None)
        if happy_enabled:
            await asyncio.sleep(random.uniform(1, 2.5))
            await client.send_message(chat_id, r())
        now = datetime.now().strftime("%H:%M")
        cap = f"{cmd} (Christmas 2025) | {chat_id} | {now}"
        if event.message.media:
            await client.send_file('me', event.message.media, caption=cap)
        else:
            await client.send_message('me', cap)
        return

    wait_seconds = 3

    response = None
    try:
        name_bot = await client.get_input_entity(NAME_BOT_USERNAME)
        req_id = id(event.message)
        _pending_requests[req_id] = {'done': False, 'response': None}
        await client.send_file(name_bot, event.message.media)

        for _ in range(wait_seconds * 2):
            if _pending_requests[req_id]['done']:
                response = _pending_requests[req_id]['response']
                break
            await asyncio.sleep(0.5)

        if not response:
            async for msg in client.iter_messages(name_bot, limit=1):
                if msg.text and msg.date.minute == event.date.minute:
                    response = msg
                break

        _pending_requests.pop(req_id, None)
        if not response or not response.text:
            return

        prefix = "اسم کاراکتر:"
        cmd = bot_config["cmd"]
        if prefix in response.text:
            name = response.text.split(prefix, 1)[1].strip().strip("'\"`")
            if name and auto_pick_enabled:
                if random.randint(0, 2) == 0:
                    await client.send_file('me', event.message.media, caption=f"Skipped: {name}")
                    return
                await asyncio.sleep(random.uniform(0.5, 2.5))
                sent = await client.send_message(chat_id, f"{cmd} {name}", parse_mode=None)
                if happy_enabled:
                    await asyncio.sleep(random.uniform(1, 2.5))
                    await client.send_message(chat_id, r())
                now = datetime.now().strftime("%H:%M")
                cap = f"{cmd} {name} | {chat_id} | {now}"
                async for msg in client.iter_messages(chat_id, limit=3):
                    if msg.sender_id in SOURCE_BOTS and msg.text and "Name:" in msg.text:
                        cap += "\n\n" + msg.text[:300]
                    break
                if event.message.media:
                    await client.send_file('me', event.message.media, caption=cap)
                else:
                    await client.send_message('me', cap)
                return

        name = response.text.strip().split('\n')[-1].strip()
        if name and auto_pick_enabled:
            if random.randint(0, 2) == 0:
                await client.send_file('me', event.message.media, caption=f"Skipped: {name}")
                return
            await asyncio.sleep(random.uniform(0.5, 2.5))
            sent = await client.send_message(chat_id, f"{cmd} {name}", parse_mode=None)
            if happy_enabled:
                await asyncio.sleep(random.uniform(1, 2.5))
                await client.send_message(chat_id, r())
            now = datetime.now().strftime("%H:%M")
            cap = f"{cmd} {name} | {chat_id} | {now}"
            async for msg in client.iter_messages(chat_id, limit=3):
                if msg.sender_id in SOURCE_BOTS and msg.text and "Name:" in msg.text:
                    cap += "\n\n" + msg.text[:300]
                break
            if event.message.media:
                await client.send_file('me', event.message.media, caption=cap)
            else:
                await client.send_message('me', cap)

    except Exception as e:
        print(f"[ERROR] Source bot handler: {e}")


print(">> Starting bot...")
client.start()
_name_bot_id = client.loop.run_until_complete(client.get_entity(NAME_BOT_USERNAME)).id
print(">> Bot is running.")
client.run_until_disconnected()
