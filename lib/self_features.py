"""Feature pack for TelegramSelf.

All state is persisted in settings/self_features.json.  Commands are intentionally
case-insensitive and do not require a leading slash, matching the original project.
"""
from .library import *
from .Information import *

STATE_PATH = os.path.join("settings", "self_features.json")
TEMPLATE_DIR = os.path.join("settings", "templates")
DEFAULTS = {
    "self": False, "selfall": False,
    "monshi": False, "monshi_offline": False, "monshi_smart": False,
    "offline_minutes": 30,
    "last_admin_activity": 0,
    "poker_all": False, "typing_all": False,
    "markread_all": False, "markread_gps": False, "markread_pvs": False,
    "markread_channels": False, "tagread_all": False, "save_pv": False,
    "trmode": False, "sticker": False, "texter": False,
    "sticker_time": 30, "texter_time": 30, "lang": "en",
    "realm": None,
    "monshi_template": "سلام، در حال حاضر در دسترس نیستم.",
    "smart_template": "سلام، پیام شما را دیدم و به‌زودی پاسخ می‌دهم.",
    "sticker_template": None, "texter_template": "سلام!",
    "chats": {}
}


def _ensure_state():
    os.makedirs("settings", exist_ok=True)
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    if not os.path.exists(STATE_PATH):
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)


def load_state():
    _ensure_state()
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    merged = dict(DEFAULTS)
    merged.update(data)
    merged["chats"] = data.get("chats", {}) if isinstance(data.get("chats", {}), dict) else {}
    return merged


def save_state(state):
    _ensure_state()
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def _chat(state, chat_id):
    key = str(chat_id)
    if key not in state["chats"]:
        state["chats"][key] = {
            "self": False, "monshi": False, "poker": False, "typing": False,
            "markread": False, "tagread": False, "save": False,
            "sticker": False, "texter": False, "last_sticker": 0, "last_texter": 0,
            "seen": []
        }
    return state["chats"][key]


def _onoff(value):
    return str(value).strip().lower() in {"on", "روشن", "فعال", "1", "true"}


def _status(value):
    return "روشن ✅" if value else "خاموش ❌"


def _admin(event):
    return event.sender_id == admin_user_id


def _scope_value(state, event, name):
    c = _chat(state, event.chat_id)
    return bool(c.get(name, False) or state.get(name + "_all", False))


def _reply_text(event):
    pieces = (event.raw_text or "").strip().split(maxsplit=1)
    return pieces[1] if len(pieces) == 2 else ""


async def _set_template(event, key, label):
    if not _admin(event): return
    if not event.is_reply:
        await event.edit(f"❌ به پیام {label} ریپلای کنید."); return
    reply = await event.get_reply_message()
    state = load_state()
    if reply.media:
        path = os.path.join(TEMPLATE_DIR, key)
        downloaded = await client.download_media(reply, file=path)
        state[key + "_template"] = {"file": downloaded, "caption": reply.raw_text or ""}
    else:
        state[key + "_template"] = reply.raw_text or ""
    save_state(state)
    await event.edit(f"✅ متن/رسانهٔ {label} ذخیره شد.")


async def _send_template(chat_id, template):
    if isinstance(template, dict) and template.get("file") and os.path.exists(template["file"]):
        return await client.send_file(chat_id, template["file"], caption=template.get("caption", ""))
    if isinstance(template, str) and template:
        return await client.send_message(chat_id, template)
    return None


async def _read_all(kind=None):
    async for dialog in client.iter_dialogs():
        allowed = kind is None or (kind == "groups" and dialog.is_group) or (kind == "pvs" and dialog.is_user) or (kind == "channels" and dialog.is_channel)
        if allowed:
            try: await client.send_read_acknowledge(dialog.entity)
            except Exception: pass


async def _toggle(event, name, value, all_scope=False):
    state = load_state()
    if all_scope:
        state[name + "_all"] = value
    else:
        _chat(state, event.chat_id)[name] = value
    save_state(state)
    await event.edit(f"✅ {name} در {'همهٔ چت‌ها' if all_scope else 'این چت'}: {_status(value)}")


async def feature_command(event):
    """Handle requested commands. Return True when the message was a feature command."""
    if not _admin(event): return False
    raw = (event.raw_text or "").strip()
    clean = raw.lstrip("/").strip()
    parts = clean.split()
    if not parts: return False
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    onoff = _onoff(arg)
    if cmd in {"featurehelp", "selfhelp"}:
        await feature_help(event)
        return True
    if cmd in {"self", "selfall", "monshi", "monshioffline", "smartmonshi", "poker", "pokerall", "typing", "typingall", "markread", "markreadall", "markreadgps", "markreadpvs", "markreadchannels", "tagread", "tagreadall", "save", "savepv", "trmode", "sticker", "texter"} and arg:
        mapping = {"monshioffline":"monshi_offline", "smartmonshi":"monshi_smart", "pokerall":"poker_all", "typingall":"typing_all", "markreadall":"markread_all", "markreadgps":"markread_gps", "markreadpvs":"markread_pvs", "markreadchannels":"markread_channels", "tagreadall":"tagread_all", "savepv":"save_pv", "trmode":"trmode"}
        name = mapping.get(cmd, cmd)
        all_scope = cmd.endswith("all")
        if cmd == "pokerall": name = "poker"; all_scope = True
        if cmd == "typingall": name = "typing"; all_scope = True
        if cmd == "selfall": name = "self"; all_scope = True
        if cmd == "markreadall": name = "markread"; all_scope = True
        if cmd == "tagreadall": name = "tagread"; all_scope = True
        if cmd in {"monshioffline", "smartmonshi", "trmode", "markreadgps", "markreadpvs", "markreadchannels", "savepv"}:
            state = load_state()
            global_name = mapping.get(cmd, cmd)
            state[global_name] = onoff
            save_state(state)
            await event.edit(f"✅ {global_name}: {_status(onoff)}")
            return True
        await _toggle(event, name, onoff, all_scope); return True
    if cmd == "setrealm":
        value = arg or str(event.chat_id)
        try: value = int(value)
        except ValueError: await event.edit("❌ آیدی چت نامعتبر است."); return True
        state = load_state(); state["realm"] = value; save_state(state); await event.edit(f"✅ ریلم تنظیم شد: `{value}`"); return True
    if cmd == "setmonshi": await _set_template(event, "monshi", "منشی"); return True
    if cmd == "setsmartmonshi": await _set_template(event, "smart", "منشی هوشمند"); return True
    if cmd == "setsticker": await _set_template(event, "sticker", "استیکر"); return True
    if cmd == "settexter":
        state = load_state(); text = _reply_text(event)
        if not text and event.is_reply:
            text = (await event.get_reply_message()).raw_text or ""
        state["texter_template"] = text
        save_state(state); await event.edit("✅ متن خودکار ذخیره شد."); return True
    if cmd == "getsticker" or cmd == "gettexter":
        state = load_state(); key = "sticker_template" if cmd == "getsticker" else "texter_template"; value = state.get(key)
        if isinstance(value, dict): await _send_template(event.chat_id, value)
        else: await event.edit(str(value or "تنظیمی ثبت نشده است."))
        return True
    if cmd == "setmonshioffline" and arg:
        try: minutes = max(1, int(arg))
        except ValueError: await event.edit("❌ زمان باید عدد دقیقه باشد."); return True
        state = load_state(); state["offline_minutes"] = minutes; save_state(state); await event.edit(f"✅ زمان آفلاین: {minutes} دقیقه"); return True
    if cmd in {"setstickertime", "settextertime"} and arg:
        try: minutes = max(1, int(arg))
        except ValueError: await event.edit("❌ زمان باید عدد دقیقه باشد."); return True
        state = load_state(); state["sticker_time" if cmd == "setstickertime" else "texter_time"] = minutes; save_state(state); await event.edit("✅ زمان ذخیره شد."); return True
    if cmd == "setlang" and arg:
        state = load_state(); state["lang"] = arg.lower(); save_state(state); await event.edit(f"✅ زبان مقصد ترجمه: `{arg.lower()}`"); return True
    if cmd == "langs":
        langs = ", ".join(f"{code}: {name}" for code, name in sorted(LANGUAGES.items()))
        await event.edit("**زبان‌های قابل استفاده:**\n" + langs[:3800]); return True
    return False


async def feature_message(event):
    """Passive behaviors for incoming messages."""
    state = load_state(); chat = _chat(state, event.chat_id)
    if event.sender_id == admin_user_id:
        state["last_admin_activity"] = time.time()
        save_state(state)
        return
    # Automatic read / mention read
    should_read = _scope_value(state, event, "markread") or (event.is_group and state.get("markread_gps")) or (event.is_private and state.get("markread_pvs")) or (event.is_channel and state.get("markread_channels"))
    if should_read:
        try: await client.send_read_acknowledge(event.chat_id, max_id=event.id)
        except Exception: pass
    if _scope_value(state, event, "tagread") and event.mentioned:
        try: await client.send_read_acknowledge(event.chat_id, max_id=event.id)
        except Exception: pass
    # Backup to realm
    if state.get("realm") and (_scope_value(state, event, "save") or (event.is_private and state.get("save_pv"))):
        try: await client.forward_messages(state["realm"], event.message, from_peer=event.chat_id)
        except Exception: pass
    # Automatic translation to realm
    if state.get("realm") and state.get("trmode") and event.raw_text:
        try:
            translated = await asyncio.to_thread(Translator().translate, event.raw_text, dest=state.get("lang", "en"))
            await client.send_message(state["realm"], f"🌐 {translated.text}")
        except Exception: pass
    # Monshi: only for private messages and offline/smart rules
    if event.is_private and _scope_value(state, event, "monshi"):
        send = True
        if state.get("monshi_offline"):
            last_activity = float(state.get("last_admin_activity", 0) or 0)
            send = last_activity > 0 and time.time() - last_activity >= state.get("offline_minutes", 30) * 60
        if state.get("monshi_smart"):
            seen = chat.setdefault("seen", [])
            send = send and event.sender_id not in seen
            if event.sender_id not in seen: seen.append(event.sender_id)
        if send:
            await _send_template(event.chat_id, state.get("monshi_template"))
            save_state(state)
    # Self mode preserves old fast-reply behavior while making it switchable.
    if _scope_value(state, event, "self"):
        try:
            reply = load_fast_replies().get((event.raw_text or "").lower())
            if reply: await event.reply(reply)
        except Exception: pass
    now = time.time()
    if event.is_group and _scope_value(state, event, "sticker") and now - chat.get("last_sticker", 0) >= state.get("sticker_time", 30) * 60:
        if state.get("sticker_template"): await _send_template(event.chat_id, state["sticker_template"]); chat["last_sticker"] = now
    if event.is_group and _scope_value(state, event, "texter") and now - chat.get("last_texter", 0) >= state.get("texter_time", 30) * 60:
        if state.get("texter_template"): await _send_template(event.chat_id, state["texter_template"]); chat["last_texter"] = now
    if chat.get("typing") or state.get("typing_all"):
        try:
            async with client.action(event.chat_id, "typing"): await asyncio.sleep(1)
        except Exception: pass
    if chat.get("poker") or state.get("poker_all"):
        try:
            async with client.action(event.chat_id, "game"): await asyncio.sleep(1)
        except Exception: pass
    save_state(state)


async def feature_handler(event):
    try:
        if event.sender_id == admin_user_id:
            state = load_state(); state["last_admin_activity"] = time.time(); save_state(state)
        if await feature_command(event): return
        await feature_message(event)
    except Exception as exc:
        print("feature handler:", exc)


async def feature_help(event):
    if not _admin(event): return
    await event.edit("""**راهنمای قابلیت‌های جدید**
`Self On/Off` پاسخ‌گویی سلف در همین چت
`Selfall On/Off` پاسخ‌گویی در همهٔ چت‌ها
`Monshi On/Off`، `MonshiOffline On/Off`، `SmartMonshi On/Off`
`SetMonshi` و `SetSmartMonshi` با ریپلای
`SetMonshiOffline 30`
`Poker`، `Typing`، `MarkRead`، `TagRead`، `Save`، `sticker`، `texter` با On/Off
برای همه: `...All On/Off`؛ همچنین `MarkReadGPs/Pvs/Channels`
`SetRealm 123456`، `SavePv On/Off`، `SetLang en`، `Langs`
`trmode On/Off`، `SetSticker`، `GetSticker`، `SetStickerTime 30`
`SetTexter متن`، `GetTexter`، `SetTexterTime 30`""")


def load_fast_replies():
    path = "settings/fast_replies.json"
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

# Compatibility aliases for callers that import the feature module directly.
load_state()

__all__ = ["feature_handler", "feature_help", "feature_command", "feature_message", "load_state"]
