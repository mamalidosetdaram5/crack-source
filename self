#!/usr/bin/env python3
import asyncio
import json
import os
import random
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession

# ========== CONFIGURATION ==========
API_ID = 27291470
API_HASH = 'b5fb1f8dc111c7baf967b527eb677e5f'
PHONE = '+989123456789'  # شماره تلفن خودتون رو اینجا بذارید
SESSION_FILE = 'selfbot.session'
CONFIG_FILE = 'selfbot_config.json'

# Source bots that trigger the pick (bot_id -> command)
SOURCE_BOTS = {
    8307651649: {"cmd": "/pick"},
}

# Name bot to get character info
NAME_BOT = '@zswaifu_cheat_bot'

# Default captions (used if not in config)
DEFAULT_CAPTIONS = {
    8307651649: [
        {"name": "🪞 Spirit", "text": "🪞 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🔮 Eloria", "text": "🔮 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "⛩ Infernal", "text": "⛩ A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "⚪️ Common", "text": "⚪️ A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🟠 Rare", "text": "🟠 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🟢 Mystic", "text": "🟢 A new character has just spawned in the chat! 🍣", "enabled": True},
        {"name": "🟡 Legendary", "text": "🟡 A new character has just spawned in the chat! 🍣", "enabled": True},
    ]
}

# Default settings
DEFAULT_CONFIG = {
    "pick_delay": 1.0,
    "delay_min": 0.5,
    "delay_max": 2.0,
    "skip_chance": 0,
    "happy_enabled": True,
    "happy_msgs": ["عالی شد! 🔥", "انجام شد 💪", "اوکی شد 🥰"],
    "tracked_groups": {},
    "group_settings": {},  # per-group: {"auto_pick": true/false}
}

# ========== STATE ==========
_name_bot_entity = None
_pending = {}
_pending_results = {}
config = {}

def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        # Merge with defaults
        config = DEFAULT_CONFIG.copy()
        config.update(loaded)
        # Ensure nested dicts exist
        config.setdefault("tracked_groups", {})
        config.setdefault("group_settings", {})
        config.setdefault("captions", {})
        # Convert string keys to int for tracked_groups
        config["tracked_groups"] = {int(k): v for k, v in config["tracked_groups"].items()}
        config["group_settings"] = {int(k): v for k, v in config["group_settings"].items()}
        # Convert captions keys to int
        config["captions"] = {int(k): v for k, v in config["captions"].items()}
    else:
        config = DEFAULT_CONFIG.copy()
        config["captions"] = {}
    return config

def save_config():
    # Convert int keys to string for JSON
    to_save = config.copy()
    to_save["tracked_groups"] = {str(k): v for k, v in config["tracked_groups"].items()}
    to_save["group_settings"] = {str(k): v for k, v in config["group_settings"].items()}
    to_save["captions"] = {str(k): v for k, v in config["captions"].items()}
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)

def get_group_setting(gid, key, default):
    return config["group_settings"].get(gid, {}).get(key, default)

def set_group_setting(gid, key, value):
    if gid not in config["group_settings"]:
        config["group_settings"][gid] = {}
    config["group_settings"][gid][key] = value
    save_config()

def get_active_texts(bot_id):
    caps = config.get("captions", {}).get(bot_id)
    if caps is None:
        caps = DEFAULT_CAPTIONS.get(bot_id, [])
    return [c["text"] for c in caps if c.get("enabled", True)]

def get_delay():
    if config["delay_max"] > 0 and config["delay_max"] > config["delay_min"]:
        return random.uniform(config["delay_min"], config["delay_max"])
    return config["pick_delay"]

def should_skip():
    return config["skip_chance"] > 0 and random.randint(1, 100) <= config["skip_chance"]

def random_happy():
    return random.choice(config["happy_msgs"])

async def main():
    global _name_bot_entity, config
    
    config = load_config()
    
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"Self-bot started as @{me.username or me.id}")

    try:
        _name_bot_entity = await client.get_input_entity(NAME_BOT)
        print(f"Name bot resolved: {NAME_BOT}")
    except Exception as e:
        print(f"Could not resolve name bot: {e}")
        return

    @client.on(events.NewMessage(outgoing=True))
    async def handle_commands(e):
        txt = (e.raw_text or "").strip()
        mid = (await e.client.get_me()).id
        
        # Only process commands in Saved Messages
        if e.chat_id != mid:
            return
        
        # Activate group by sending group ID in saved messages
        if txt.lstrip('-').isdigit():
            gid = int(txt)
            config["tracked_groups"][gid] = str(gid)
            try:
                ent = await client.get_entity(gid)
                config["tracked_groups"][gid] = getattr(ent, 'title', str(gid))
            except:
                pass
            save_config()
            await e.reply(f"✅ Group added: {gid} ({config['tracked_groups'][gid]})")
            return
        
        # Remove group
        if txt.startswith(".del ") and txt[5:].lstrip('-').isdigit():
            gid = int(txt[5:])
            if gid in config["tracked_groups"]:
                name = config["tracked_groups"].pop(gid)
                config["group_settings"].pop(gid, None)
                save_config()
                await e.reply(f"🗑 Group removed: {gid} ({name})")
            else:
                await e.reply(f"❌ Group not found: {gid}")
            return
        
        # Toggle auto-pick for a group: .pick on/off <group_id>
        if txt.startswith(".pick "):
            parts = txt.split()
            if len(parts) == 3:
                action = parts[1]
                gid = int(parts[2])
                if gid not in config["tracked_groups"]:
                    await e.reply(f"❌ Group not tracked: {gid}")
                    return
                if action == "on":
                    set_group_setting(gid, "auto_pick", True)
                    await e.reply(f"✅ Auto-pick ON for {config['tracked_groups'][gid]} ({gid})")
                elif action == "off":
                    set_group_setting(gid, "auto_pick", False)
                    await e.reply(f"❌ Auto-pick OFF for {config['tracked_groups'][gid]} ({gid})")
                else:
                    await e.reply("Usage: .pick on|off <group_id>")
            return
        
        # Global auto-pick toggle: .autopick on/off
        if txt.startswith(".autopick "):
            action = txt.split()[1]
            if action == "on":
                config["global_auto_pick"] = True
                save_config()
                await e.reply("✅ Global auto-pick ON")
            elif action == "off":
                config["global_auto_pick"] = False
                save_config()
                await e.reply("❌ Global auto-pick OFF")
            return
        
        # Set delay: .delay <fixed> or .delay <min> <max>
        if txt.startswith(".delay "):
            parts = txt.split()
            if len(parts) == 2:
                try:
                    val = float(parts[1])
                    config["pick_delay"] = val
                    config["delay_min"] = 0
                    config["delay_max"] = 0
                    save_config()
                    await e.reply(f"✅ Fixed delay set to {val}s")
                except:
                    await e.reply("❌ Invalid number")
            elif len(parts) == 3:
                try:
                    mn = float(parts[1])
                    mx = float(parts[2])
                    if mn < 0 or mx < 0 or mn >= mx:
                        raise ValueError
                    config["delay_min"] = mn
                    config["delay_max"] = mx
                    config["pick_delay"] = 0
                    save_config()
                    await e.reply(f"✅ Random delay: {mn}-{mx}s")
                except:
                    await e.reply("❌ Usage: .delay <min> <max>")
            return
        
        # Set skip chance: .skip <0-100>
        if txt.startswith(".skip "):
            try:
                val = int(txt.split()[1])
                if 0 <= val <= 100:
                    config["skip_chance"] = val
                    save_config()
                    await e.reply(f"✅ Skip chance: {val}%")
                else:
                    await e.reply("❌ Value 0-100")
            except:
                await e.reply("❌ Usage: .skip <0-100>")
            return
        
        # Toggle happy messages: .happy on/off
        if txt.startswith(".happy "):
            action = txt.split()[1]
            if action == "on":
                config["happy_enabled"] = True
                save_config()
                await e.reply("✅ Happy messages ON")
            elif action == "off":
                config["happy_enabled"] = False
                save_config()
                await e.reply("❌ Happy messages OFF")
            return
        
        # Add happy message: .happyadd <text>
        if txt.startswith(".happyadd "):
            msg = txt[10:]
            config["happy_msgs"].append(msg)
            save_config()
            await e.reply(f"✅ Added happy message")
            return
        
        # List happy messages: .happylist
        if txt == ".happylist":
            lines = [f"{i+1}. {m}" for i, m in enumerate(config["happy_msgs"])]
            await e.reply("Happy messages:\n" + "\n".join(lines))
            return
        
        # Remove happy message: .happydel <num>
        if txt.startswith(".happydel "):
            try:
                idx = int(txt.split()[1]) - 1
                if 0 <= idx < len(config["happy_msgs"]):
                    removed = config["happy_msgs"].pop(idx)
                    save_config()
                    await e.reply(f"✅ Removed: {removed}")
                else:
                    await e.reply("❌ Invalid index")
            except:
                await e.reply("❌ Usage: .happydel <num>")
            return
        
        # Caption management: .cap list|add|del|toggle|clear <bot_id> [args]
        if txt.startswith(".cap "):
            parts = txt.split(maxsplit=3)
            if len(parts) < 2:
                await e.reply("Usage: .cap list|add|del|toggle|clear <bot_id> [args]")
                return
            
            cmd = parts[1]
            bot_id = None
            arg_start = 2
            
            # Get bot_id from args or use first source bot
            if len(parts) > 2 and parts[2].lstrip('-').isdigit():
                bot_id = int(parts[2])
                arg_start = 3
            elif SOURCE_BOTS:
                bot_id = list(SOURCE_BOTS.keys())[0]
            
            if not bot_id:
                await e.reply("❌ No source bot configured")
                return
            
            # Ensure captions exist for this bot
            if "captions" not in config:
                config["captions"] = {}
            if bot_id not in config["captions"]:
                config["captions"][bot_id] = DEFAULT_CAPTIONS.get(bot_id, []).copy()
            
            caps = config["captions"][bot_id]
            args = parts[arg_start:] if len(parts) > arg_start else []
            
            if cmd == "list":
                if not caps:
                    await e.reply(f"📋 No captions for bot {bot_id}")
                    return
                lines = []
                for i, cap in enumerate(caps):
                    status = "✅" if cap.get("enabled", True) else "❌"
                    lines.append(f"{i+1}. {status} {cap['name']}: {cap['text'][:50]}...")
                await e.reply(f"📋 Captions for bot {bot_id}:\n" + "\n".join(lines))
            
            elif cmd == "add" and args:
                name = f"Custom {len(caps)+1}"
                text = " ".join(args)
                caps.append({"name": name, "text": text, "enabled": True})
                save_config()
                await e.reply(f"✅ Added caption '{name}' for bot {bot_id}")
            
            elif cmd == "del" and args and args[0].isdigit():
                idx = int(args[0]) - 1
                if 0 <= idx < len(caps):
                    removed = caps.pop(idx)
                    save_config()
                    await e.reply(f"✅ Deleted: {removed['name']}")
                else:
                    await e.reply("❌ Invalid index")
            
            elif cmd == "toggle" and args and args[0].isdigit():
                idx = int(args[0]) - 1
                if 0 <= idx < len(caps):
                    caps[idx]["enabled"] = not caps[idx].get("enabled", True)
                    save_config()
                    status = "✅" if caps[idx]["enabled"] else "❌"
                    await e.reply(f"{status} {caps[idx]['name']}")
                else:
                    await e.reply("❌ Invalid index")
            
            elif cmd == "clear":
                config["captions"][bot_id] = []
                save_config()
                await e.reply(f"✅ Cleared all captions for bot {bot_id}")
            
            else:
                await e.reply("Usage: .cap list|add|del|toggle|clear <bot_id> [args]")
            return
        
        # List tracked groups with status
        if txt == ".status":
            if not config["tracked_groups"]:
                await e.reply("No groups tracked.")
            else:
                lines = []
                for gid, name in config["tracked_groups"].items():
                    gs = config["group_settings"].get(gid, {})
                    ap = gs.get("auto_pick", config.get("global_auto_pick", True))
                    status = "🟢" if ap else "🔴"
                    lines.append(f"{status} {name} ({gid})")
                await e.reply("Tracked groups:\n" + "\n".join(lines))
            return
        
        # Show current settings
        if txt == ".settings":
            g_ap = config.get("global_auto_pick", True)
            txt = (
                f"⚙️ **Settings**\n\n"
                f"🌐 Global auto-pick: {'ON' if g_ap else 'OFF'}\n"
                f"⏱ Delay: {config['delay_min']}-{config['delay_max']}s" if config['delay_max'] > 0 else f"⏱ Fixed delay: {config['pick_delay']}s\n"
                f"🎯 Skip chance: {config['skip_chance']}%\n"
                f"😊 Happy messages: {'ON' if config['happy_enabled'] else 'OFF'} ({len(config['happy_msgs'])} msgs)\n"
                f"📋 Tracked groups: {len(config['tracked_groups'])}\n"
                f"🤖 Source bots: {len(SOURCE_BOTS)}"
            )
            await e.reply(txt)
            return
        
        # Help
        if txt == ".help":
            help_text = (
                "🤖 **Self-bot Pick Helper**\n\n"
                "**Group Management:**\n"
                "▫️ Send group ID (e.g. `-1001234567890`) → Add group\n"
                "▫️ `.del <group_id>` → Remove group\n"
                "▫️ `.pick on|off <group_id>` → Toggle auto-pick per group\n"
                "▫️ `.autopick on|off` → Global auto-pick toggle\n\n"
                "**Caption Management:**\n"
                "▫️ `.cap list [bot_id]` → List captions for bot\n"
                "▫️ `.cap add [bot_id] <text>` → Add caption\n"
                "▫️ `.cap del [bot_id] <num>` → Delete caption\n"
                "▫️ `.cap toggle [bot_id] <num>` → Toggle enable/disable\n"
                "▫️ `.cap clear [bot_id]` → Clear all captions\n\n"
                "**Settings:**\n"
                "▫️ `.delay <sec>` → Fixed delay\n"
                "▫️ `.delay <min> <max>` → Random delay range\n"
                "▫️ `.skip <0-100>` → Skip chance %\n"
                "▫️ `.happy on|off` → Toggle happy messages\n"
                "▫️ `.happyadd <text>` → Add happy message\n"
                "▫️ `.happylist` → List happy messages\n"
                "▫️ `.happydel <num>` → Remove happy message\n\n"
                "**Info:**\n"
                "▫️ `.status` → Groups with auto-pick status\n"
                "▫️ `.settings` → Current settings\n"
                "▫️ `.help` → This help"
            )
            await e.reply(help_text)
            return

    @client.on(events.NewMessage)
    async def handle_name_response(e):
        global _name_bot_entity
        if _name_bot_entity and e.sender_id == _name_bot_entity.id:
            rid = e.reply_to_msg_id
            if rid in _pending:
                d = _pending[rid]
                if not d['done']:
                    d['response'] = e
                    d['done'] = True
                    if 'event' in d:
                        d['event'].set()

    @client.on(events.NewMessage)
    async def handle_source_bot(e):
        global _name_bot_entity
        cid = e.chat_id
        if cid not in config["tracked_groups"]:
            return
        
        # Check per-group auto-pick setting
        gs = config["group_settings"].get(cid, {})
        group_auto_pick = gs.get("auto_pick", config.get("global_auto_pick", True))
        
        bc = SOURCE_BOTS.get(e.sender_id)
        if not bc:
            return
        
        if not e.message.media:
            return
        
        ct = (e.message.raw_text or "").strip()
        if not any(t in ct for t in get_active_texts(e.sender_id)):
            return
        
        try:
            # Send media to Name Bot
            sent = await client.send_file(_name_bot_entity, e.message.media)
            rid = sent.id
            
            evt = asyncio.Event()
            _pending[rid] = {'done': False, 'response': None, 'event': evt}
            
            try:
                await asyncio.wait_for(evt.wait(), timeout=10)
            except asyncio.TimeoutError:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Timeout waiting for name bot")
                pass
            
            resp_data = _pending.pop(rid, None)
            resp = resp_data['response'] if resp_data else None
            
            if not resp or not resp.text:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No response from name bot")
                return
            
            # Extract character name
            name = None
            text = resp.text
            
            # Format 1: ⚡ /pick nefertari
            if "⚡ /pick" in text:
                name = text.split("⚡ /pick")[1].strip().split('\n')[0].strip().strip("'\"`")
            # Format 2: ⚡Name: Naruto
            elif "⚡Name:" in text:
                name = text.split("⚡Name:")[1].strip().split('\n')[0].strip().strip("'\"`")
            # Format 3: 🔍 اسم کاراکتر: Akeno Himejima
            elif "🔍 اسم کاراکتر:" in text:
                name = text.split("🔍 اسم کاراکتر:", 1)[1].strip().strip("'\"`")
            # Format 4: اسم کاراکتر: Akeno Himejima
            elif "اسم کاراکتر:" in text:
                name = text.split("اسم کاراکتر:", 1)[1].strip().strip("'\"`")
            
            if not name:
                name = text.strip().split('\n')[-1].strip().strip("'\"`")
            
            now = datetime.now().strftime("%H:%M:%S")
            group_name = config["tracked_groups"].get(cid, str(cid))
            
            if name:
                print(f"[{now}] 🎯 Character found: {name} | Group: {group_name} ({cid})")
                
                # Save media with caption to saved messages
                cap = f"Character: {name}\nGroup: {group_name} ({cid})\nTime: {now}\nSource: {e.sender_id}"
                try:
                    await client.send_file('me', e.message.media, caption=cap)
                except Exception as ex:
                    print(f"Failed to save media: {ex}")
                
                # Auto-pick logic
                if group_auto_pick:
                    if should_skip():
                        print(f"[{now}] ⏭ Skipped {name}")
                        return
                    
                    delay = get_delay()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    
                    cmd = bc["cmd"]
                    pm = await client.send_message(cid, f"{cmd} {name}", parse_mode=None)
                    
                    if config["happy_enabled"]:
                        await client.send_message(cid, random_happy())
                    
                    _pending_results[pm.id] = {'cid': cid, 'name': name}
            else:
                print(f"[{now}] ❌ Name not found in response | Group: {group_name}")
                await client.send_message('me', f"❌ Name not found | {cid}\nResponse: {resp.text[:200]}")
                
        except Exception as ex:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {ex}")

    @client.on(events.NewMessage)
    async def handle_pick_result(e):
        if not e.message.reply_to_msg_id:
            return
        rid = e.message.reply_to_msg_id
        pr = _pending_results.pop(rid, None)
        if not pr:
            return
        text = (e.raw_text or "").strip()
        if not text:
            return
        
        now_iran = datetime.now(timezone(timedelta(hours=3, minutes=30))).strftime("%Y-%m-%d %H:%M:%S")
        
        if "Picked Successfully" in text:
            n, a, i_d, r = "", "", "", ""
            for line in text.split('\n'):
                if line.startswith("Name:"): n = line.split("Name:", 1)[1].strip()
                elif line.startswith("Anime:"): a = line.split("Anime:", 1)[1].strip()
                elif line.startswith("ID:"): i_d = line.split("ID:", 1)[1].strip()
                elif line.startswith("Rarity:"): r = line.split("Rarity:", 1)[1].strip()
            result = f"✅ {pr['name']}\nName: {n}\nAnime: {a}\nID: {i_d}\nRarity: {r}\n⏰ {now_iran}"
        else:
            result = f"❌ {pr['name']}\n⏰ {now_iran}"
        
        print(f"[{now_iran}] Pick result: {result}")

    print("Listening for source bot messages...")
    print("Commands available in Saved Messages. Type .help for list.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
