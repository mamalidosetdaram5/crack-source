import os
import json
import re
import time
import sys
import asyncio
import subprocess
import tempfile
import traceback
from io import BytesIO
from collections import defaultdict
from PIL import Image
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo, Message, MessageMediaPhoto, MessageMediaDocument

API_ID = 27291470
API_HASH = "b5fb1f8dc111c7baf967b527eb677e5f"
BOT_TOKEN = "8976551206:AAEw9jioQg-jsVUkNpKLY4vNN_wQuvDqIdE"
ADMIN_IDS = [6716559782, 8192645915, 6745595929]
OWNER_ID = ADMIN_IDS[0]
FORCE_CHANNEL = "FlameWaifu_Cheat_Datebase"
FORCE_CHANNEL_LINK = "https://t.me/FlameWaifu_Cheat_Datebase"
SOURCE_CHANNEL = "Picker_database"  # channel username for auto-sync
DATA_FILE = "data.json"
AUTO_WATCH_FILE = "auto_watch_state.json"
USERS_FILE = "users.json"
BANNED_FILE = "banned.json"
ITEMS_PER_PAGE = 3
SYNC_DEFAULT_COMMAND = "/pick"
SYNC_IMAGE_COMMAND = "/pick"
SYNC_VIDEO_COMMAND = "/pick"
EXTERNAL_CHECK_BOT = "character_picker_bot"  # bot whose /check <id> replies we mirror via /checkid
EXTERNAL_CHECK_COMMAND = "/check"
EXTERNAL_CHECK_TIMEOUT = 3  # seconds to wait for the external bot's reply
EXTERNAL_CHECK_COOLDOWN = 2  # seconds to wait between consecutive requests in /checkid <range>
USER_SESSION_NAME = "reader_session"  # separate user account session, used only to
                                       # read channel history (bots can't do this
                                       # unless they're admins of the channel)

_data_cache = None
_data_dirty = False
RATE_LIMIT_SECONDS = 1
_last_usage = defaultdict(float)

# In-memory store for /report review flow.
# report_id -> {"hash": str, "type": "image"/"video", "duration": int,
#               "name": str, "reporter_id": int, "status": "pending"/"approved"/"rejected"}
_pending_reports = {}
_report_counter = 0
# admin_id -> report_id  (set while we're waiting for the admin to type the
# command to save an approved report under)
_awaiting_command_from_admin = {}

# In-memory store mapping a short id -> search query text, used so callback
# button data (limited to 64 bytes) can reference a /search query without
# embedding the raw (possibly long/unicode) text in every button.
_search_queries = {}
_search_query_counter = 0


def load_data():
    global _data_cache
    if _data_cache is not None:
        return _data_cache
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            _data_cache = json.load(f)
    else:
        _data_cache = {}
    return _data_cache


def save_data(data):
    global _data_cache, _data_dirty
    _data_cache = data
    _data_dirty = True


def _flush_data():
    global _data_dirty
    if _data_dirty:
        with open(DATA_FILE, "w") as f:
            json.dump(_data_cache, f, indent=2)
        _data_dirty = False


def load_auto_watch_state():
    """Returns True if channel auto-watch is enabled, persisted on disk so it
    survives bot restarts."""
    if os.path.exists(AUTO_WATCH_FILE):
        try:
            with open(AUTO_WATCH_FILE, "r") as f:
                return bool(json.load(f).get("enabled", False))
        except Exception:
            return False
    return False


def save_auto_watch_state(enabled):
    with open(AUTO_WATCH_FILE, "w") as f:
        json.dump({"enabled": bool(enabled)}, f)


def has_media(msg):
    try:
        if getattr(msg, 'photo', None):
            return True
        doc = getattr(msg, 'document', None)
        if doc and getattr(doc, 'mime_type', None):
            mt = doc.mime_type
            if mt.startswith("image/") or mt.startswith("video/"):
                return True
        media = getattr(msg, 'media', None)
        if media:
            if isinstance(media, (MessageMediaPhoto, MessageMediaDocument)):
                return True
    except Exception:
        pass
    return False


def is_video(msg):
    try:
        doc = getattr(msg, 'document', None)
        if doc and getattr(doc, 'mime_type', None):
            return doc.mime_type.startswith("video/")
        import telethon.tl.types as t
        media = getattr(msg, 'media', None)
        if isinstance(media, t.MessageMediaDocument):
            doc2 = media.document
            if doc2 and doc2.mime_type:
                return doc2.mime_type.startswith("video/")
    except Exception:
        pass
    return False


def get_video_duration(msg):
    try:
        doc = getattr(msg, 'document', None)
        if doc and doc.attributes:
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeVideo):
                    return attr.duration
        media = getattr(msg, 'media', None)
        if media:
            doc2 = getattr(media, 'document', None)
            if doc2 and doc2.attributes:
                for attr in doc2.attributes:
                    if isinstance(attr, DocumentAttributeVideo):
                        return attr.duration
    except Exception:
        pass
    return 0


def get_key(hash8, media_type, duration=0):
    if media_type == "video":
        return f"{hash8}_{duration}s"
    return hash8


async def get_video_frame(msg):
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        await msg.download_media(tmp_path)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-ss", "0.7", "-i", tmp_path,
            "-vframes", "1", "-f", "image2pipe",
            "-vcodec", "mjpeg", "-q:v", "2", "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        data, _ = await proc.communicate()
        return data if data else None
    except FileNotFoundError:
        return None
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def download_media_thumb(msg):
    try:
        if is_video(msg):
            data = await get_video_frame(msg)
            if data:
                return data
            for t in [-1, 0, 1]:
                try:
                    data = await msg.download_media(bytes, thumb=t)
                    if data:
                        return data
                except Exception:
                    pass
            data = await msg.download_media(bytes)
            return data
        for t in [-1, 0, 1]:
            try:
                data = await msg.download_media(bytes, thumb=t)
                if data:
                    return data
            except Exception:
                pass
        data = await msg.download_media(bytes)
        return data
    except Exception:
        return None


def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return []


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def track_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        save_users(users)


def load_banned():
    if os.path.exists(BANNED_FILE):
        with open(BANNED_FILE, "r") as f:
            return json.load(f)
    return []


def save_banned(banned):
    with open(BANNED_FILE, "w") as f:
        json.dump(banned, f, indent=2)


def is_banned(user_id):
    return user_id in load_banned()


def is_rate_limited(user_id):
    now = time.time()
    last = _last_usage[user_id]
    if now - last < RATE_LIMIT_SECONDS:
        return True
    _last_usage[user_id] = now
    return False


def get_image_hash(img_bytes):
    img = Image.open(BytesIO(img_bytes)).convert("L")
    img = img.resize((9, 8), Image.LANCZOS)
    pixels = list(img.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (1 if pixels[y * 9 + x] > pixels[y * 9 + x + 1] else 0)
    return hex(bits)[2:].zfill(16)[:8]


def _clean_extracted_name(name):
    if not name:
        return name
    # remove emoji / symbol / pictograph ranges
    name = re.sub(
        r'[\u2000-\u206F\uFE00-\uFE0F\U0001F000-\U0001FFFF\u2600-\u27BF\u2300-\u23FF]',
        '', name
    )
    # remove leftover bracket/quote punctuation from templates like 「 」 『 』 【 】
    name = re.sub(r'[「」『』\[\]【】〈〉《》]', '', name)
    # collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    # strip trailing punctuation
    name = name.strip(' -–—:،,.').strip()
    return name


def extract_id_and_name(caption):
    """Return (id_str, clean_name) parsed from a caption, or (None, None)."""
    if not caption:
        return None, None
    patterns = [
        r'(?:I\s*D|𝐈𝐃|𝐈\s*𝐃|ＩＤ|Ｉ\s*Ｄ|Id|id|ｉｄ)\s*[:\s]+\s*(\d+)\s+(.+)',
        r'[「『\[]?\s*(?:ID|𝐈𝐃|ＩＤ|Id|id)\s*[:\s]+\s*(\d+)\s+(.+?)\s*[🕯️]?\s*[」』\]]?',
        r'\b(\d{3,5})\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b',
    ]
    for line in caption.split("\n"):
        line = line.strip()
        if not line:
            continue
        for pat in patterns:
            try:
                m = re.search(pat, line)
                if not m:
                    continue
                if m.lastindex and m.lastindex >= 2:
                    id_str = m.group(1).strip()
                    name = m.group(2).strip()
                else:
                    id_str = None
                    name = m.group(1).strip()
                name = _clean_extracted_name(name)
                if name and len(name) > 1:
                    return id_str, name
            except Exception:
                continue
    return None, None


def extract_name_from_caption(caption):
    _id, name = extract_id_and_name(caption)
    return name


def extract_name_from_checkbot_caption(caption):
    """Parses the reply format used by the external '@character_picker_bot'
    style check bots, where the name sits on the very first line between a
    bullet+dash marker, e.g.:
        •—Skirk—•
    Returns the clean name, or None if the pattern isn't found.
    """
    if not caption:
        return None
    m = re.search(r'[•●▪]\s*[—–\-]+\s*(.+?)\s*[—–\-]+\s*[•●▪]', caption)
    if not m:
        return None
    name = _clean_extracted_name(m.group(1))
    return name or None


def is_admin(user_id):
    return user_id in ADMIN_IDS

def is_owner(user_id):
    return user_id == OWNER_ID


async def is_member(client, user_id):
    if not FORCE_CHANNEL:
        return True
    try:
        await client.get_permissions(FORCE_CHANNEL, user_id)
        return True
    except Exception:
        return False


async def force_join(event, client):
    if not FORCE_CHANNEL:
        return True
    if is_admin(event.sender_id):
        return True
    if await is_member(client, event.sender_id):
        return True
    link = FORCE_CHANNEL_LINK or f"https://t.me/{FORCE_CHANNEL}"
    await event.reply(
        "🚫 <b>دسترسی محدود</b>\n\n"
        "برای استفاده از ربات باید عضو کانال زیر باشید:",
        buttons=[Button.url("🔗 عضویت در کانال", link)],
        parse_mode="html"
    )
    return False


def make_list_page(data, page, filter_type, search_query=None):
    items = []
    q = (search_query or "").strip().lower()
    for key, val in data.items():
        t = val.get("type", "image")
        if filter_type != "all" and t != filter_type:
            continue
        if q:
            name = (val.get("name") or "").lower()
            if q not in key.lower() and q not in name:
                continue
        items.append((key, val))
    items.sort(key=lambda x: x[0])
    total = len(items)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_items = items[start:end]
    return page_items, page, total_pages, total


async def send_list_page(event, client, page, filter_type, search_id="-"):
    data = load_data()
    if not data:
        await event.edit("📭 هیچ موردی ذخیره نشده.")
        return
    search_query = _search_queries.get(search_id) if search_id and search_id != "-" else None
    page_items, cur, total_pages, total = make_list_page(data, page, filter_type, search_query)
    if not page_items:
        await event.edit("📭 هیچ موردی برای این صفحه وجود ندارد.")
        return
    lines = []
    for key, val in page_items:
        t = val.get("type", "image")
        icon = "🎬" if t == "video" else "🖼"
        dur = f" ({val['duration']}s)" if t == "video" and "duration" in val else ""
        lines.append(f"{icon} <code>{key}</code> ➜ {val['command']} {val['name']}{dur}")
    header = f"🔎 <b>نتایج جستجو</b> «{search_query}» ({filter_type})" if search_query else f"📋 <b>لیست ذخیره شده‌ها</b> ({filter_type})"
    text = (
        f"{header}\n"
        f"صفحه {cur + 1} از {total_pages} — مجموع: {total}\n\n"
        + "\n".join(lines)
    )
    buttons = []
    row = []
    if cur > 0:
        row.append(Button.inline("◀️ قبلی", f"list|{cur - 1}|{filter_type}|{search_id}"))
    if cur < total_pages - 1:
        row.append(Button.inline("بعدی ▶️", f"list|{cur + 1}|{filter_type}|{search_id}"))
    if row:
        buttons.append(row)
    filter_row = [
        Button.inline("همه", f"list|0|all|{search_id}"),
        Button.inline("🖼 تصویر", f"list|0|image|{search_id}"),
        Button.inline("🎬 ویدیو", f"list|0|video|{search_id}"),
    ]
    buttons.insert(0, filter_row)
    await event.edit(text, buttons=buttons, parse_mode="html")


async def main():
    print("Starting bot...")
    try:
        client = TelegramClient("bot_session", API_ID, API_HASH)
        client.parse_mode = "html"
        await client.start(bot_token=BOT_TOKEN)
        me = await client.get_me()
        print(f"Bot @{me.username} started successfully!")
    except Exception as e:
        print(f"Failed to start bot: {e}")
        traceback.print_exc()
        return

    # Separate USER account client, used only for reading channel history.
    # Telegram bots are not allowed to call GetHistoryRequest (iter_messages)
    # on a channel unless the bot is an admin there; a normal user account
    # can read the history of any public channel it can see. This client is
    # read-only: it never sends messages, joins chats, or does anything else.
    reader_client = None
    try:
        reader_client = TelegramClient(USER_SESSION_NAME, API_ID, API_HASH)
        await reader_client.start()  # first run: asks for phone + login code in this terminal
        reader_me = await reader_client.get_me()
        print(f"Reader account @{reader_me.username or reader_me.id} connected (read-only, for channel history).")
    except Exception as e:
        print(f"Failed to start reader account: {e}")
        traceback.print_exc()
        reader_client = None  # /pick and /pick <range> will report this as unavailable

    # Auto-watch: when enabled, every new post in SOURCE_CHANNEL with a valid
    # "ID : <num> <name>" caption is saved automatically, and a log message
    # is sent to the first admin. Registered on reader_client (the user
    # account) because bots don't receive channel updates unless they're
    # admins of the channel. Using a single-key dict (instead of a bare
    # variable) so nested functions can read/write it without `nonlocal`.
    _auto_watch = {"enabled": load_auto_watch_state()}

    if reader_client is not None:
        @reader_client.on(events.NewMessage(chats=(SOURCE_CHANNEL or "").strip().strip("@") or None))
        async def on_channel_new_post(event):
            try:
                if not _auto_watch["enabled"]:
                    return
                msg = event.message
                if not has_media(msg):
                    return
                caption = msg.message or msg.text or ""
                cap_id, cap_name = extract_id_and_name(caption)
                if not cap_id or not cap_name:
                    return  # no recognizable "ID : n name" caption, skip silently

                ok, result = await process_and_save_forced(msg, cap_name, SYNC_DEFAULT_COMMAND)

                log_target = ADMIN_IDS[0] if ADMIN_IDS else None
                if not log_target:
                    return

                if ok:
                    vid = result["vid"]
                    icon = "🎬" if vid else "🖼"
                    dur_text = f" ({result['duration']}s)" if vid else ""
                    await client.send_message(
                        log_target,
                        f"🆕 <b>پست خودکار ذخیره شد</b>\n"
                        f"{icon} <b>نام:</b> <code>{result['name']}</code>\n"
                        f"🔹 <b>کد:</b> <code>{cap_id}</code>\n"
                        f"🔹 <b>دستور:</b> <code>{SYNC_DEFAULT_COMMAND}</code>\n"
                        f"🔹 <b>هش:</b> <code>{result['key']}</code>{dur_text}",
                        parse_mode="html"
                    )
                else:
                    reason = {"no_thumb": "دانلود مدیا ناموفق بود.", "error": "خطای داخلی."}.get(result, result)
                    await client.send_message(
                        log_target,
                        f"⚠️ <b>خطا در ذخیره خودکار</b>\n"
                        f"🔹 <b>کد:</b> <code>{cap_id}</code>\n"
                        f"🔹 <b>نام:</b> <code>{cap_name}</code>\n"
                        f"🔹 <b>دلیل:</b> {reason}",
                        parse_mode="html"
                    )
            except Exception as e:
                print(f"Error in on_channel_new_post: {e}")
                traceback.print_exc()

    @client.on(events.NewMessage(pattern=r"^/autowatch(@\w+)?(\s+(on|off|status))?$"))
    async def autowatch_cmd(event):
        try:
            if not is_admin(event.sender_id):
                return
            arg = (event.pattern_match.group(3) or "").lower()

            if not arg or arg == "status":
                state_text = "🟢 روشن" if _auto_watch["enabled"] else "🔴 خاموش"
                channel = (SOURCE_CHANNEL or "").strip().strip("@") or "(تنظیم نشده)"
                await event.reply(
                    f"👁 <b>وضعیت اسکن خودکار کانال</b>: {state_text}\n"
                    f"📎 <b>چنل:</b> @{channel}\n\n"
                    f"برای روشن/خاموش کردن: <code>/autowatch on</code> یا <code>/autowatch off</code>",
                    parse_mode="html"
                )
                return

            if reader_client is None and arg == "on":
                await event.reply(
                    "⚠️ حساب خواننده (reader account) متصل نیست، اسکن خودکار کار نخواهد کرد.",
                    parse_mode="html"
                )
                return

            enable = (arg == "on")
            _auto_watch["enabled"] = enable
            save_auto_watch_state(enable)
            await event.reply(
                f"✅ اسکن خودکار کانال {'🟢 روشن' if enable else '🔴 خاموش'} شد.",
                parse_mode="html"
            )
        except Exception as e:
            print(f"Error in autowatch_cmd: {e}")

    @client.on(events.NewMessage(pattern=r"^/ping$"))
    async def ping(event):
        await event.reply("pong")

    async def process_and_save_forced(msg, name, cmd):
        """Like process_and_save, but overwrites an existing duplicate entry
        instead of skipping it (used for the /pick <id> channel lookup)."""
        try:
            vid = is_video(msg)
            duration = get_video_duration(msg) if vid else 0
            img_bytes = await download_media_thumb(msg)
            if not img_bytes:
                return False, "no_thumb"
            hash8 = get_image_hash(img_bytes)
            key = get_key(hash8, "video" if vid else "image", duration)
            data = load_data()
            entry = {
                "command": cmd,
                "name": name,
                "type": "video" if vid else "image",
                "hash": hash8,
            }
            if vid:
                entry["duration"] = duration
            data[key] = entry
            save_data(data)
            _flush_data()
            return True, {"key": key, "name": name, "vid": vid, "duration": duration}
        except Exception:
            return False, "error"

    async def find_and_save_by_id(entity, target_id):
        """Scan `entity` newest-first for a caption containing `target_id`,
        download+save its media. Returns a dict:
          {"status": "saved", "name": ..., "key": ..., "vid": ..., "duration": ...}
          {"status": "not_found"}
          {"status": "error", "reason": ...}
        """
        if reader_client is None:
            return {"status": "error", "reason": "no_reader"}
        found_msg = None
        found_name = None
        checked = 0
        async for msg in reader_client.iter_messages(entity):
            checked += 1
            if not has_media(msg):
                continue
            caption = msg.message or msg.text or ""
            cap_id, cap_name = extract_id_and_name(caption)
            if cap_id == target_id:
                found_msg = msg
                found_name = cap_name
                break  # iter_messages is newest-first, so this is the latest post
            if checked > 5000:
                break

        if not found_msg:
            return {"status": "not_found"}

        ok, result = await process_and_save_forced(found_msg, found_name, SYNC_DEFAULT_COMMAND)
        if not ok:
            return {"status": "error", "reason": result}

        return {
            "status": "saved",
            "name": result["name"],
            "key": result["key"],
            "vid": result["vid"],
            "duration": result["duration"],
        }

    async def check_via_external_bot(target_id):
        """Uses reader_client (the personal user account) to send
        `EXTERNAL_CHECK_COMMAND <target_id>` to EXTERNAL_CHECK_BOT in a
        private chat, waits for its reply (media + caption), parses the
        name, and saves it exactly like the other pick flows. Returns the
        same shape as find_and_save_by_id.
        """
        if reader_client is None:
            return {"status": "error", "reason": "no_reader"}

        try:
            bot_entity = await reader_client.get_entity(EXTERNAL_CHECK_BOT)
        except Exception:
            return {"status": "error", "reason": "bot_not_found"}

        loop = asyncio.get_event_loop()
        fut = loop.create_future()

        async def _on_reply(event):
            if not fut.done():
                fut.set_result(event.message)

        # Temporary handler: only listens to messages coming from the
        # external bot's chat, removed again right after we get a reply
        # (or time out) so it doesn't pile up across many /checkid calls.
        reply_filter = events.NewMessage(chats=bot_entity, incoming=True)
        reader_client.add_event_handler(_on_reply, reply_filter)

        try:
            await reader_client.send_message(bot_entity, f"{EXTERNAL_CHECK_COMMAND} {target_id}")
            try:
                reply_msg = await asyncio.wait_for(fut, timeout=EXTERNAL_CHECK_TIMEOUT)
            except asyncio.TimeoutError:
                return {"status": "error", "reason": "timeout"}
        finally:
            reader_client.remove_event_handler(_on_reply, reply_filter)

        caption = reply_msg.message or reply_msg.text or ""

        # Some check-bots reply with plain text first ("searching...") before
        # the real result with media; if what we caught has no media, give
        # it one more short window for a follow-up message with media.
        if not has_media(reply_msg):
            fut2 = loop.create_future()

            async def _on_reply2(event):
                if not fut2.done():
                    fut2.set_result(event.message)

            reader_client.add_event_handler(_on_reply2, reply_filter)
            try:
                reply_msg = await asyncio.wait_for(fut2, timeout=EXTERNAL_CHECK_TIMEOUT)
                caption = reply_msg.message or reply_msg.text or ""
            except asyncio.TimeoutError:
                return {"status": "error", "reason": "no_media"}
            finally:
                reader_client.remove_event_handler(_on_reply2, reply_filter)

        if not has_media(reply_msg):
            return {"status": "error", "reason": "no_media"}

        name = extract_name_from_checkbot_caption(caption)
        if not name:
            return {"status": "error", "reason": "no_name"}

        ok, result = await process_and_save_forced(reply_msg, name, SYNC_DEFAULT_COMMAND)
        if not ok:
            return {"status": "error", "reason": result}

        return {
            "status": "saved",
            "name": result["name"],
            "key": result["key"],
            "vid": result["vid"],
            "duration": result["duration"],
        }


    @client.on(events.NewMessage(pattern=r"^/pick(@\w+)?\s+(\d+)\s*$"))
    async def pick_by_id(event):
        """/pick <id> — scans SOURCE_CHANNEL for the newest post whose caption
        contains that ID (e.g. 「 ID : 7840 Balalaika 」), grabs its media,
        and saves it under the default command with the name parsed from the
        caption."""
        if not is_admin(event.sender_id):
            return
        try:
            if reader_client is None:
                await event.reply(
                    "⚠️ حساب خواننده (reader account) متصل نیست. لاگ کنسول ربات را بررسی کنید.",
                    parse_mode="html"
                )
                return

            target_id = event.pattern_match.group(2).strip()
            channel = (SOURCE_CHANNEL or "").strip().strip("@")
            if not channel:
                await event.reply("⚠️ SOURCE_CHANNEL تنظیم نشده.", parse_mode="html")
                return

            status = await event.reply(f"🔎 در حال جستجوی کد <code>{target_id}</code> در @{channel} ...", parse_mode="html")
            try:
                entity = await reader_client.get_entity(channel)
            except Exception:
                await status.edit("⚠️ چنل پیدا نشد.")
                return

            r = await find_and_save_by_id(entity, target_id)

            if r["status"] == "not_found":
                await status.edit(f"❌ هیچ پستی با کد <code>{target_id}</code> پیدا نشد.", parse_mode="html")
                return
            if r["status"] == "error":
                reason = {"no_thumb": "دانلود مدیا ناموفق بود.", "error": "خطای داخلی.", "no_reader": "حساب خواننده متصل نیست."}.get(r["reason"], r["reason"])
                await status.edit(f"⚠️ خطا در ذخیره: {reason}", parse_mode="html")
                return

            vid = r["vid"]
            icon = "🎬" if vid else "🖼"
            dur_text = f"\n🔹 <b>مدت:</b> <code>{r['duration']}s</code>" if vid else ""
            await status.edit(
                f"✅ <b>ذخیره شد</b>\n"
                f"{icon} <b>نوع:</b> <code>{'ویدیو' if vid else 'تصویر'}</code>\n"
                f"🔹 <b>کد:</b> <code>{target_id}</code>\n"
                f"🔹 <b>نام:</b> <code>{r['name']}</code>\n"
                f"🔹 <b>دستور:</b> <code>{SYNC_DEFAULT_COMMAND}</code>\n"
                f"🔹 <b>هش:</b> <code>{r['key']}</code>{dur_text}",
                parse_mode="html"
            )
        except Exception as e:
            print(f"Error in pick_by_id: {e}")
            traceback.print_exc()
        finally:
            raise events.StopPropagation

    @client.on(events.NewMessage(pattern=r"^/pick(@\w+)?\s+(\d+)\s*-\s*(\d+)\s*$"))
    async def pick_by_range(event):
        """/pick <start>-<end> — runs the same single-ID lookup for every
        integer in the (inclusive) range, one at a time, and reports a
        summary at the end (found vs. not found)."""
        if not is_admin(event.sender_id):
            return
        try:
            if reader_client is None:
                await event.reply(
                    "⚠️ حساب خواننده (reader account) متصل نیست. لاگ کنسول ربات را بررسی کنید.",
                    parse_mode="html"
                )
                return

            start = int(event.pattern_match.group(2))
            end = int(event.pattern_match.group(3))
            if start > end:
                start, end = end, start

            channel = (SOURCE_CHANNEL or "").strip().strip("@")
            if not channel:
                await event.reply("⚠️ SOURCE_CHANNEL تنظیم نشده.", parse_mode="html")
                return

            total = end - start + 1
            if total > 5000:
                await event.reply(
                    f"⚠️ بازه <code>{start}-{end}</code> شامل {total} کد است که خیلی زیاده. "
                    f"لطفاً بازه کوچک‌تری بفرستید (حداکثر 5000).",
                    parse_mode="html"
                )
                return

            status = await event.reply(
                f"🔎 شروع جستجوی بازه <code>{start}-{end}</code> ({total} کد) در @{channel} ...",
                parse_mode="html"
            )
            try:
                entity = await reader_client.get_entity(channel)
            except Exception:
                await status.edit("⚠️ چنل پیدا نشد.")
                return

            saved = []
            not_found = []
            errors = []
            t0 = time.time()

            for i, code in enumerate(range(start, end + 1), start=1):
                target_id = str(code)
                r = await find_and_save_by_id(entity, target_id)
                if r["status"] == "saved":
                    saved.append((target_id, r["name"]))
                elif r["status"] == "not_found":
                    not_found.append(target_id)
                else:
                    errors.append(target_id)
                await asyncio.sleep(0.3)  # be gentle with Telegram's API / flood limits

                if i % 5 == 0 or i == total:
                    elapsed = int(time.time() - t0)
                    try:
                        await status.edit(
                            f"🔎 <b>در حال پردازش بازه</b> <code>{start}-{end}</code>\n"
                            f"📨 پیشرفت: {i}/{total} ({elapsed}ثانیه)\n"
                            f"✅ پیدا شده: {len(saved)}\n"
                            f"❌ پیدا نشده: {len(not_found)}\n"
                            f"⚠️ خطا: {len(errors)}",
                            parse_mode="html"
                        )
                    except Exception:
                        pass

            elapsed = int(time.time() - t0)
            summary_lines = [
                f"✅ <b>پردازش بازه {start}-{end} تمام شد</b>",
                f"⏱ زمان: {elapsed}ثانیه",
                f"📦 کل کدها: {total}",
                f"🆕 ذخیره شده: {len(saved)}",
                f"❌ پیدا نشده: {len(not_found)}",
                f"⚠️ خطا: {len(errors)}",
            ]
            if not_found:
                nf_preview = ", ".join(not_found[:50])
                more = f" و {len(not_found) - 50} مورد دیگر" if len(not_found) > 50 else ""
                summary_lines.append(f"\n❌ <b>کدهای پیدا نشده:</b>\n<code>{nf_preview}</code>{more}")
            if errors:
                err_preview = ", ".join(errors[:50])
                summary_lines.append(f"\n⚠️ <b>کدهای با خطا:</b>\n<code>{err_preview}</code>")

            await status.edit("\n".join(summary_lines), parse_mode="html")
        except Exception as e:
            print(f"Error in pick_by_range: {e}")
            traceback.print_exc()
        finally:
            raise events.StopPropagation

    _checkid_error_text = {
        "no_reader": "حساب خواننده متصل نیست.",
        "bot_not_found": f"ربات @{EXTERNAL_CHECK_BOT} پیدا نشد.",
        "timeout": "ربات دیگر پاسخ نداد (timeout).",
        "no_media": "پاسخ ربات دیگر عکس/ویدیو نداشت.",
        "no_name": "نام از پاسخ ربات دیگر قابل استخراج نبود.",
        "no_thumb": "دانلود مدیا ناموفق بود.",
        "error": "خطای داخلی.",
    }

    @client.on(events.NewMessage(pattern=r"^/checkid(@\w+)?\s+(\d+)\s*$"))
    async def checkid_single(event):
        """/checkid <id> — asks EXTERNAL_CHECK_BOT (via the reader account)
        for this id with /check <id>, parses its reply, and saves it under
        SYNC_DEFAULT_COMMAND with the name found between the •—...—• marker."""
        if not is_admin(event.sender_id):
            return
        try:
            if reader_client is None:
                await event.reply(
                    "⚠️ حساب خواننده (reader account) متصل نیست. لاگ کنسول ربات را بررسی کنید.",
                    parse_mode="html"
                )
                return

            target_id = event.pattern_match.group(2).strip()
            status = await event.reply(
                f"🔎 در حال پرسیدن کد <code>{target_id}</code> از @{EXTERNAL_CHECK_BOT} ...",
                parse_mode="html"
            )

            r = await check_via_external_bot(target_id)

            if r["status"] == "error":
                reason = _checkid_error_text.get(r["reason"], r["reason"])
                await status.edit(f"⚠️ خطا: {reason}", parse_mode="html")
                return

            vid = r["vid"]
            icon = "🎬" if vid else "🖼"
            dur_text = f"\n🔹 <b>مدت:</b> <code>{r['duration']}s</code>" if vid else ""
            await status.edit(
                f"✅ <b>ذخیره شد</b>\n"
                f"{icon} <b>نوع:</b> <code>{'ویدیو' if vid else 'تصویر'}</code>\n"
                f"🔹 <b>کد:</b> <code>{target_id}</code>\n"
                f"🔹 <b>نام:</b> <code>{r['name']}</code>\n"
                f"🔹 <b>دستور:</b> <code>{SYNC_DEFAULT_COMMAND}</code>\n"
                f"🔹 <b>هش:</b> <code>{r['key']}</code>{dur_text}",
                parse_mode="html"
            )
        except Exception as e:
            print(f"Error in checkid_single: {e}")
            traceback.print_exc()
        finally:
            raise events.StopPropagation

    @client.on(events.NewMessage(pattern=r"^/checkid(@\w+)?\s+(\d+)\s*-\s*(\d+)\s*$"))
    async def checkid_range(event):
        """/checkid <start>-<end> — same as checkid_single but looped over a
        range, one code at a time (each one is a real message round-trip to
        the external bot, so this is capped smaller than /pick's range)."""
        if not is_admin(event.sender_id):
            return
        try:
            if reader_client is None:
                await event.reply(
                    "⚠️ حساب خواننده (reader account) متصل نیست. لاگ کنسول ربات را بررسی کنید.",
                    parse_mode="html"
                )
                return

            start = int(event.pattern_match.group(2))
            end = int(event.pattern_match.group(3))
            if start > end:
                start, end = end, start

            total = end - start + 1
            max_range = 100
            if total > max_range:
                est_minutes = (total * EXTERNAL_CHECK_COOLDOWN) // 60
                await event.reply(
                    f"⚠️ بازه <code>{start}-{end}</code> شامل {total} کد است. "
                    f"چون بین هر درخواست {EXTERNAL_CHECK_COOLDOWN} ثانیه فاصله می‌اندازیم تا لیمیت نشویم، "
                    f"حداکثر بازه مجاز {max_range} کد است (این بازه حدود {est_minutes} دقیقه طول می‌کشید).",
                    parse_mode="html"
                )
                return

            status = await event.reply(
                f"🔎 شروع پرسیدن بازه <code>{start}-{end}</code> ({total} کد) از @{EXTERNAL_CHECK_BOT} ...",
                parse_mode="html"
            )

            saved = []
            failed = []  # (id, reason)
            t0 = time.time()

            for i, code in enumerate(range(start, end + 1), start=1):
                target_id = str(code)
                r = await check_via_external_bot(target_id)
                if r["status"] == "saved":
                    saved.append((target_id, r["name"]))
                else:
                    failed.append((target_id, _checkid_error_text.get(r["reason"], r["reason"])))
                await asyncio.sleep(EXTERNAL_CHECK_COOLDOWN)  # be gentle with both Telegram and the external bot

                if i % 3 == 0 or i == total:
                    elapsed = int(time.time() - t0)
                    try:
                        await status.edit(
                            f"🔎 <b>در حال پردازش بازه</b> <code>{start}-{end}</code>\n"
                            f"📨 پیشرفت: {i}/{total} ({elapsed}ثانیه)\n"
                            f"✅ ذخیره شده: {len(saved)}\n"
                            f"⚠️ ناموفق: {len(failed)}",
                            parse_mode="html"
                        )
                    except Exception:
                        pass

            elapsed = int(time.time() - t0)
            summary_lines = [
                f"✅ <b>پردازش بازه {start}-{end} تمام شد</b>",
                f"⏱ زمان: {elapsed}ثانیه",
                f"📦 کل کدها: {total}",
                f"🆕 ذخیره شده: {len(saved)}",
                f"⚠️ ناموفق: {len(failed)}",
            ]
            if failed:
                fail_preview = ", ".join(f"{fid}({reason})" for fid, reason in failed[:30])
                more = f" و {len(failed) - 30} مورد دیگر" if len(failed) > 30 else ""
                summary_lines.append(f"\n⚠️ <b>کدهای ناموفق:</b>\n<code>{fail_preview}</code>{more}")

            await status.edit("\n".join(summary_lines), parse_mode="html")
        except Exception as e:
            print(f"Error in checkid_range: {e}")
            traceback.print_exc()
        finally:
            raise events.StopPropagation

    # Commands that have their own dedicated handler and must never be
    # swallowed by the generic "<command> <text>" media-register handler
    # below, even though its pattern also matches them.
    _reserved_command_words = {
        "pick", "report", "search", "delete", "ban", "unban", "broadcast",
        "sync", "start", "help", "ownerhelp", "ownerstats", "list",
        "export", "import", "ping", "fl", "find", "testc", "autowatch",
        "checkid",
    }

    @client.on(events.NewMessage(pattern=r"^/(\w+)(@\w+)?\s+(.+)"))
    async def admin_register(event):
        try:
            command_word = (event.pattern_match.group(1) or "").lower()
            if command_word in _reserved_command_words:
                return  # let the dedicated handler for this command deal with it

            if not is_admin(event.sender_id):
                return

            msg = event.message
            if not has_media(event):
                if msg.is_reply:
                    replied = await msg.get_reply_message()
                    if replied and has_media(replied):
                        msg = replied
                    else:
                        await event.reply("⚠️ روی یک عکس یا ویدیو ریپلای کنید.", parse_mode="html")
                        return
                else:
                    await event.reply("⚠️ لطفاً یک عکس یا ویدیو همراه با دستور بفرستید.", parse_mode="html")
                    return

            command = event.pattern_match.group(1)
            char_name = event.pattern_match.group(3).strip()
            vid = is_video(msg)
            duration = get_video_duration(msg) if vid else 0

            img_bytes = await download_media_thumb(msg)
            if not img_bytes:
                await event.reply("⚠️ خطا در دانلود.", parse_mode="html")
                return

            hash8 = get_image_hash(img_bytes)
            key = get_key(hash8, "video" if vid else "image", duration)

            entry = {
                "command": f"/{command}",
                "name": char_name,
                "type": "video" if vid else "image",
                "hash": hash8,
            }
            if vid:
                entry["duration"] = duration

            data = load_data()
            data[key] = entry
            save_data(data)
            _flush_data()

            media_icon = "🎬" if vid else "🖼"
            dur_text = f"\n🔹 <b>مدت:</b> <code>{duration}s</code>" if vid else ""
            await event.reply(
                f"✅ <b>ذخیره شد</b>\n"
                f"{media_icon} <b>نوع:</b> <code>{'ویدیو' if vid else 'تصویر'}</code>\n"
                f"🔹 <b>دستور:</b> <code>/{command}</code>\n"
                f"🔹 <b>نام:</b> <code>{char_name}</code>\n"
                f"🔹 <b>هش:</b> <code>{key}</code>{dur_text}",
                parse_mode="html"
            )
        except Exception as e:
            print(f"Error in admin_register: {e}")
            traceback.print_exc()

    async def check_media(msg_obj, reply_to):
        vid = is_video(msg_obj)
        duration = get_video_duration(msg_obj) if vid else 0
        img_bytes = await download_media_thumb(msg_obj)
        if not img_bytes:
            return None
        hash8 = get_image_hash(img_bytes)
        data = load_data()
        key = get_key(hash8, "video" if vid else "image", duration)
        if key in data:
            return data[key]
        if hash8 in data:
            return data[hash8]
        return None

    @client.on(events.NewMessage)
    async def check_image(event):
        try:
            if event.message.text and event.message.text.startswith("/"):
                return

            if not has_media(event):
                return

            if not event.is_private:
                return

            if is_rate_limited(event.sender_id):
                return

            if is_banned(event.sender_id):
                return

            if not await force_join(event, client):
                return

            track_user(event.sender_id)
            info = await check_media(event.message, event)
            if info:
                await event.reply(f"<code>{info['command']} {info['name']}</code>", parse_mode="html")
            else:
                await event.reply("❌ هیچ شخصیتی با این تصویر یا ویدیو یافت نشد.")
        except Exception as e:
            print(f"Error in check_image: {e}")

    @client.on(events.NewMessage(pattern=r"^/(fl|find)(@\w+)?$"))
    async def find_in_group(event):
        try:
            print(f"Received /fl from {event.sender_id} in chat {event.chat_id}")

            if is_rate_limited(event.sender_id):
                return

            if is_banned(event.sender_id):
                return

            if not await force_join(event, client):
                return

            if not event.message.is_reply:
                await event.reply("⚠️ روی یک عکس یا ویدیو ریپلای کنید.", parse_mode="html")
                return

            replied = await event.message.get_reply_message()
            if not replied or not has_media(replied):
                await event.reply("⚠️ روی یک عکس یا ویدیو ریپلای کنید.", parse_mode="html")
                return

            track_user(event.sender_id)
            info = await check_media(replied, event)
            if info:
                await event.reply(f"<code>{info['command']} {info['name']}</code>", parse_mode="html")
            else:
                await event.reply("❌ هیچ شخصیتی با این عکس یا ویدیو یافت نشد.")
        except Exception as e:
            print(f"Error in find_in_group: {e}")

    @client.on(events.NewMessage(pattern=r"^/report(@\w+)?\s+(.+)"))
    async def report_missing(event):
        global _report_counter
        try:
            if is_banned(event.sender_id):
                return
            msg = event.message
            replied = None
            if msg.is_reply:
                replied = await msg.get_reply_message()

            target_msg = replied if (replied and has_media(replied)) else msg
            if not has_media(target_msg):
                await event.reply("⚠️ روی یک عکس یا ویدیو ریپلای کنید یا عکس بفرستید.", parse_mode="html")
                return

            suggested = event.pattern_match.group(2).strip()
            vid = is_video(target_msg)
            duration = get_video_duration(target_msg) if vid else 0

            img_bytes = await download_media_thumb(target_msg)
            if not img_bytes:
                await event.reply("⚠️ خطا در دانلود.", parse_mode="html")
                return

            hash8 = get_image_hash(img_bytes)
            key = get_key(hash8, "video" if vid else "image", duration)
            sender = await event.get_sender()
            name = sender.first_name or ""
            username = f"@{sender.username}" if sender.username else ""

            _report_counter += 1
            report_id = str(_report_counter)
            _pending_reports[report_id] = {
                "hash": hash8,
                "key": key,
                "type": "video" if vid else "image",
                "duration": duration,
                "name": suggested,
                "reporter_id": event.sender_id,
                "status": "pending",
            }

            caption = (
                f"📬 <b>گزارش جدید #{report_id}</b>\n\n"
                f"👤 <b>کاربر:</b> {name} {username} (<code>{event.sender_id}</code>)\n"
                f"💬 <b>پیشنهاد:</b> <code>{suggested}</code>\n"
                f"🔹 <b>هش:</b> <code>{key}</code>\n"
                f"📎 <b>chat:</b> <code>{event.chat_id}</code>"
            )
            buttons = [
                [
                    Button.inline("✅ قبول", data=f"rpt_ok:{report_id}".encode()),
                    Button.inline("❌ رد", data=f"rpt_no:{report_id}".encode()),
                ]
            ]

            for aid in ADMIN_IDS:
                try:
                    # forward the actual media so the admin can see exactly
                    # what's being reported, with the review caption + buttons
                    await client.send_file(
                        aid,
                        target_msg.media,
                        caption=caption,
                        parse_mode="html",
                        buttons=buttons,
                    )
                except Exception:
                    # fallback: text-only if forwarding media fails for some reason
                    try:
                        await client.send_message(aid, caption, parse_mode="html", buttons=buttons)
                    except Exception:
                        pass

            await event.reply("✅ گزارش شما ارسال شد. ادمین بررسی خواهد کرد.", parse_mode="html")
        except Exception as e:
            print(f"Error in report_missing: {e}")

    @client.on(events.CallbackQuery(pattern=r"^rpt_ok:(.+)$"))
    async def report_approve_cb(event):
        try:
            if not is_admin(event.sender_id):
                await event.answer("⛔️ فقط ادمین.", alert=True)
                return
            report_id = event.pattern_match.group(1).decode()
            report = _pending_reports.get(report_id)
            if not report:
                await event.answer("⚠️ این گزارش دیگر معتبر نیست.", alert=True)
                return
            if report["status"] != "pending":
                await event.answer(f"این گزارش قبلاً {('قبول' if report['status']=='approved' else 'رد')} شده.", alert=True)
                return

            _awaiting_command_from_admin[event.sender_id] = report_id
            await event.answer()
            await event.reply(
                f"✏️ نام: <code>{report['name']}</code> — هش: <code>{report['key']}</code>\n"
                f"لطفاً دستوری که باید زیر این آیتم ذخیره شود را بفرستید (مثلاً <code>/pick</code>):",
                parse_mode="html"
            )
        except Exception as e:
            print(f"Error in report_approve_cb: {e}")

    @client.on(events.CallbackQuery(pattern=r"^rpt_no:(.+)$"))
    async def report_reject_cb(event):
        try:
            if not is_admin(event.sender_id):
                await event.answer("⛔️ فقط ادمین.", alert=True)
                return
            report_id = event.pattern_match.group(1).decode()
            report = _pending_reports.get(report_id)
            if not report:
                await event.answer("⚠️ این گزارش دیگر معتبر نیست.", alert=True)
                return
            if report["status"] != "pending":
                await event.answer(f"این گزارش قبلاً {('قبول' if report['status']=='approved' else 'رد')} شده.", alert=True)
                return

            report["status"] = "rejected"
            await event.answer("❌ رد شد.")
            try:
                await event.edit(buttons=None)
            except Exception:
                pass
        except Exception as e:
            print(f"Error in report_reject_cb: {e}")

    @client.on(events.NewMessage())
    async def admin_report_command_reply(event):
        """Catches the admin's reply after tapping ✅ on a report, where they
        type the command (e.g. /pick) to save the entry under. Must not
        interfere with any other command, so it only acts when this admin is
        in the _awaiting_command_from_admin state and the message looks like
        a bare command (e.g. '/pick', 'pick')."""
        try:
            sender_id = event.sender_id
            if sender_id not in _awaiting_command_from_admin:
                return
            if not is_admin(sender_id):
                return
            text = (event.raw_text or "").strip()
            if not text:
                return
            # Only consume this message if it looks like a plain command
            # word starting with '/', with no arguments (e.g. '/pick').
            # Anything with a space/newline, or not starting with '/', is
            # left alone so it can't accidentally swallow unrelated commands
            # like '/pick 7840' or '/sync'.
            if not text.startswith("/"):
                return
            if " " in text or "\n" in text:
                return
            if not re.fullmatch(r"/\w+", text):
                return
            # Don't swallow the bot's own bare-word commands (they run via
            # their own handlers regardless); only a genuinely new command
            # name should be captured here as "the command to save under".
            _known_bare_commands = {
                "/ping", "/fl", "/find", "/start", "/help", "/ownerhelp",
                "/ownerstats", "/list", "/export", "/import", "/testc", "/sync",
            }
            if text.lower() in _known_bare_commands:
                return

            report_id = _awaiting_command_from_admin.pop(sender_id)
            report = _pending_reports.get(report_id)
            if not report or report["status"] != "pending":
                await event.reply("⚠️ این گزارش دیگر در انتظار نیست.", parse_mode="html")
                return

            command = text if text.startswith("/") else f"/{text}"

            entry = {
                "command": command,
                "name": report["name"],
                "type": report["type"],
                "hash": report["hash"],
            }
            if report["type"] == "video":
                entry["duration"] = report["duration"]

            data = load_data()
            data[report["key"]] = entry
            save_data(data)
            _flush_data()

            report["status"] = "approved"

            await event.reply(
                f"✅ <b>ذخیره شد</b>\n"
                f"🔹 <b>نام:</b> <code>{report['name']}</code>\n"
                f"🔹 <b>دستور:</b> <code>{command}</code>\n"
                f"🔹 <b>هش:</b> <code>{report['key']}</code>",
                parse_mode="html"
            )

            try:
                await client.send_message(
                    report["reporter_id"],
                    f"✅ گزارش شما تایید و اضافه شد: <code>{command} {report['name']}</code>",
                    parse_mode="html"
                )
            except Exception:
                pass
        except Exception as e:
            print(f"Error in admin_report_command_reply: {e}")

    async def player_help(event):
        text = (
            "🤖 <b>راهنمای ربات</b>\n\n"
            "📱 <b>پیوی خصوصی:</b>\n"
            "عکس یا ویدیو بفرستید تا بات تشخیص بده\n\n"
            "👥 <b>گروه:</b>\n"
            "روی عکس یا ویدیو ریپلای کنید با <code>/fl</code>\n\n"
            "📬 <b>گزارش:</b>\n"
            "اگه عکسی تشخیص داده نشد، ریپلای کنید با <code>/report [نام]</code>\n\n"
            "🔍 <b>تذکر:</b>\n"
            "فقط کاراکترهایی که ادمین ذخیره کرده قابل تشخیص هستند"
        )
        await event.reply(text, parse_mode="html")

    @client.on(events.NewMessage(pattern=r"^/start(@\w+)?$"))
    async def start_cmd(event):
        try:
            if is_admin(event.sender_id):
                await help_cmd(event)
            else:
                if FORCE_CHANNEL:
                    if not await force_join(event, client):
                        return
                await player_help(event)
        except Exception as e:
            print(f"Error in start_cmd: {e}")

    @client.on(events.NewMessage(pattern=r"^/help(@\w+)?$"))
    async def help_cmd(event):
        try:
            if is_admin(event.sender_id):
                await event.reply(
                    "📋 <b>راهنمای ادمین</b>\n\n"
                    "📥 <b>ذخیره:</b>\n"
                    "`/pick <نام>` همراه با عکس یا ویدیو\n"
                    "یا روی عکس ریپلای کنید با `/pick <نام>`\n\n"
                    "🔍 <b>بررسی (PV):</b>\n"
                    "عکس یا ویدیو بفرستید تا هش بشه\n\n"
                    "👥 <b>بررسی (گروه):</b>\n"
                    "`/fl` — ریپلای روی عکس/ویدیو\n\n"
                    "📋 <b>لیست:</b>\n"
                    "`/list` — همه\n"
                    "`/list image` — تصاویر\n"
                    "`/list video` — ویدیوها\n\n"
                    "❌ <b>حذف:</b>\n"
                    "`/delete <hash>`\n\n"
                    "🚫 <b>بن کردن:</b>\n"
                    "`/ban <id>` — مسدود\n"
                    "`/unban <id>` — رفع مسدود\n\n"
                    "📢 <b>پیام همگانی:</b>\n"
                    "`/broadcast <متن>`\n\n"
                    "🔄 <b>سینک خودکار:</b>\n"
                    "`/sync @channel` — اسکن دستی چنل\n"
                    "با SOURCE_CHANNEL فعال/غیرفعال میشه\n\n"
                    "📦 <b>خروجی/ورودی:</b>\n"
                    "`/export` — خروجی JSON\n"
                    "`/import` — ریپلای روی فایل JSON\n\n"
                    "🔒 <b>جوین اجباری:</b>\n"
                    "با `FORCE_CHANNEL` فعال/غیرفعال میشه"
                )
            else:
                if FORCE_CHANNEL:
                    if not await force_join(event, client):
                        return
                await player_help(event)
        except Exception as e:
            print(f"Error in help_cmd: {e}")

    @client.on(events.NewMessage(pattern=r"^/ownerhelp(@\w+)?$"))
    async def ownerhelp_cmd(event):
        try:
            if not is_owner(event.sender_id):
                await event.reply("⚠️ این دستور فقط برای اونر ربات است.", parse_mode="html")
                return
            await event.reply(
                "👑 <b>راهنمای اونر</b>\n\n"
                "🔹 <b>آیدی اونر:</b> <code>{}</code>\n"
                "🔹 <b>ادمین‌ها:</b>\n".format(OWNER_ID) +
                "\n".join(f"  <code>{a}</code>" for a in ADMIN_IDS) +
                "\n\n"
                "🔧 <b>متغیرهای کانفیگ:</b>\n"
                f"  <b>API_ID:</b> <code>{API_ID}</code>\n"
                f"  <b>API_HASH:</b> <code>{API_HASH[:6]}...</code>\n"
                f"  <b>BOT_TOKEN:</b> <code>{BOT_TOKEN[:6]}...</code>\n"
                f"  <b>FORCE_CHANNEL:</b> @{FORCE_CHANNEL}\n"
                f"  <b>SOURCE_CHANNEL:</b> @{SOURCE_CHANNEL}\n\n"
                "📁 <b>فایل‌های داده:</b>\n"
                f"  <code>{DATA_FILE}</code>\n"
                "  <code>users.json</code>\n"
                "  <code>banned.json</code>\n\n"
                "⚙️ <b>دستورات اختصاصی:</b>\n"
                "  `/ownerhelp` — همین پیام\n"
                "  `/sync @channel` — اسکن چنل سورس\n\n"
                "📊 <b>آمار:</b>\n"
                "  /ownerstats — آمار ربات\n\n"
                "💡 <b>نکته:</b> تمامی ادمین‌ها به `/help` ادمین دسترسی دارند."
            )
        except Exception as e:
            print(f"Error in ownerhelp_cmd: {e}")

    @client.on(events.NewMessage(pattern=r"^/ownerstats(@\w+)?$"))
    async def ownerstats_cmd(event):
        try:
            if not is_owner(event.sender_id):
                return
            data = load_data()
            users = load_users()
            banned = load_banned()
            img_c = sum(1 for v in data.values() if v.get("type") == "image")
            vid_c = sum(1 for v in data.values() if v.get("type") == "video")
            await event.reply(
                "📊 <b>آمار ربات</b>\n\n"
                f"🖼 تصاویر: {img_c}\n"
                f"🎬 ویدیوها: {vid_c}\n"
                f"📦 مجموع: {len(data)}\n"
                f"👤 کاربران: {len(users)}\n"
                f"🚫 بن شده: {len(banned)}\n"
                f"👥 ادمین‌ها: {len(ADMIN_IDS)}",
                parse_mode="html"
            )
        except Exception as e:
            print(f"Error in ownerstats_cmd: {e}")

    @client.on(events.NewMessage(pattern=r"^/list(@\w+)?(\s+(image|video|all))?$"))
    async def list_cmd(event):
        try:
            if not is_admin(event.sender_id):
                return
            filter_type = event.pattern_match.group(3) or "all"
            data = load_data()
            if not data:
                await event.reply("📭 هیچ موردی ذخیره نشده.")
                return
            page_items, cur, total_pages, total = make_list_page(data, 0, filter_type)
            if not page_items:
                await event.reply("📭 هیچ موردی یافت نشد.")
                return
            lines = []
            for key, val in page_items:
                t = val.get("type", "image")
                icon = "🎬" if t == "video" else "🖼"
                dur = f" ({val['duration']}s)" if t == "video" and "duration" in val else ""
                lines.append(f"{icon} <code>{key}</code> ➜ {val['command']} {val['name']}{dur}")
            text = (
                f"📋 <b>لیست ذخیره شده‌ها</b> ({filter_type})\n"
                f"صفحه 1 از {total_pages} — مجموع: {total}\n\n"
                + "\n".join(lines)
            )
            buttons = []
            filter_row = [
                Button.inline("همه", f"list|0|all"),
                Button.inline("🖼 تصویر", f"list|0|image"),
                Button.inline("🎬 ویدیو", f"list|0|video"),
            ]
            buttons.append(filter_row)
            nav_row = []
            if cur < total_pages - 1:
                nav_row.append(Button.inline("بعدی ▶️", f"list|{cur + 1}|{filter_type}"))
            if nav_row:
                buttons.append(nav_row)
            await event.reply(text, buttons=buttons, parse_mode="html")
        except Exception as e:
            print(f"Error in list_cmd: {e}")

    @client.on(events.CallbackQuery(pattern=r"^list\|(\d+)\|(\w+)(?:\|(\S+))?$"))
    async def list_callback(event):
        try:
            if not is_admin(event.sender_id):
                await event.answer("دسترسی ندارید.", alert=True)
                return
            page = int(event.pattern_match.group(1).decode())
            filter_type = event.pattern_match.group(2).decode()
            search_id_raw = event.pattern_match.group(3)
            search_id = search_id_raw.decode() if search_id_raw else "-"
            await send_list_page(event, client, page, filter_type, search_id)
            await event.answer()
        except Exception as e:
            print(f"Error in list_callback: {e}")

    @client.on(events.NewMessage(pattern=r"^/search(@\w+)?\s+(.+)"))
    async def search_cmd(event):
        global _search_query_counter
        if not is_admin(event.sender_id):
            return
        try:
            query = event.pattern_match.group(2).strip()
            if not query:
                await event.reply("⚠️ عبارت جستجو را وارد کنید. مثال: <code>/search Balalaika</code>", parse_mode="html")
                return

            data = load_data()
            if not data:
                await event.reply("📭 هیچ موردی ذخیره نشده.")
                return

            page_items, cur, total_pages, total = make_list_page(data, 0, "all", query)
            if not page_items:
                await event.reply(f"🔎 هیچ موردی برای «{query}» (در هش یا نام) پیدا نشد.", parse_mode="html")
                return

            _search_query_counter += 1
            search_id = str(_search_query_counter)
            _search_queries[search_id] = query

            lines = []
            for key, val in page_items:
                t = val.get("type", "image")
                icon = "🎬" if t == "video" else "🖼"
                dur = f" ({val['duration']}s)" if t == "video" and "duration" in val else ""
                lines.append(f"{icon} <code>{key}</code> ➜ {val['command']} {val['name']}{dur}")
            text = (
                f"🔎 <b>نتایج جستجو</b> «{query}» (all)\n"
                f"صفحه 1 از {total_pages} — مجموع: {total}\n\n"
                + "\n".join(lines)
            )
            buttons = [[
                Button.inline("همه", f"list|0|all|{search_id}"),
                Button.inline("🖼 تصویر", f"list|0|image|{search_id}"),
                Button.inline("🎬 ویدیو", f"list|0|video|{search_id}"),
            ]]
            nav_row = []
            if cur < total_pages - 1:
                nav_row.append(Button.inline("بعدی ▶️", f"list|{cur + 1}|all|{search_id}"))
            if nav_row:
                buttons.append(nav_row)
            await event.reply(text, buttons=buttons, parse_mode="html")
        except Exception as e:
            print(f"Error in search_cmd: {e}")
        finally:
            raise events.StopPropagation

    @client.on(events.NewMessage(pattern=r"^/delete(@\w+)?\s+(.+)"))
    async def delete_hash(event):
        if not is_admin(event.sender_id):
            return
        try:
            target = event.pattern_match.group(2).strip()
            data = load_data()
            if target in data:
                del data[target]
                save_data(data)
                _flush_data()
                await event.reply(f"✅ هش <code>{target}</code> حذف شد.", parse_mode="html")
            else:
                await event.reply(f"⚠️ هش <code>{target}</code> یافت نشد.", parse_mode="html")
        except Exception as e:
            print(f"Error in delete_hash: {e}")
        finally:
            raise events.StopPropagation

    @client.on(events.NewMessage(pattern=r"^/ban(@\w+)?\s+(\d+)"))
    async def ban_user(event):
        try:
            if not is_admin(event.sender_id):
                return
            uid = int(event.pattern_match.group(2))
            banned = load_banned()
            if uid not in banned:
                banned.append(uid)
                save_banned(banned)
                await event.reply(f"🚫 کاربر <code>{uid}</code> بن شد.", parse_mode="html")
            else:
                await event.reply(f"⚠️ کاربر <code>{uid}</code> قبلاً بن شده.", parse_mode="html")
        except Exception as e:
            print(f"Error in ban_user: {e}")

    @client.on(events.NewMessage(pattern=r"^/unban(@\w+)?\s+(\d+)"))
    async def unban_user(event):
        try:
            if not is_admin(event.sender_id):
                return
            uid = int(event.pattern_match.group(2))
            banned = load_banned()
            if uid in banned:
                banned.remove(uid)
                save_banned(banned)
                await event.reply(f"✅ کاربر <code>{uid}</code> از بن خارج شد.", parse_mode="html")
            else:
                await event.reply(f"⚠️ کاربر <code>{uid}</code> در لیست بن نیست.", parse_mode="html")
        except Exception as e:
            print(f"Error in unban_user: {e}")

    @client.on(events.NewMessage(pattern=r"^/export(@\w+)?$"))
    async def export_data(event):
        try:
            if not is_admin(event.sender_id):
                return
            data = load_data()
            path = f"export_{int(time.time())}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            await event.reply(file=path)
            os.unlink(path)
        except Exception as e:
            print(f"Error in export_data: {e}")

    @client.on(events.NewMessage(pattern=r"^/import(@\w+)?$"))
    async def import_data(event):
        try:
            if not is_admin(event.sender_id):
                return
            if not event.message.document:
                await event.reply("⚠️ لطفاً یک فایل JSON ارسال کنید.", parse_mode="html")
                return
            path = f"import_{event.sender_id}.json"
            await event.message.download_media(path)
            with open(path, "r", encoding="utf-8") as f:
                imported = json.load(f)
            os.unlink(path)
            if not isinstance(imported, dict):
                await event.reply("⚠️ فرمت فایل نامعتبر است.", parse_mode="html")
                return
            data = load_data()
            data.update(imported)
            save_data(data)
            _flush_data()
            await event.reply(f"✅ <code>{len(imported)}</code> مورد اضافه شد.", parse_mode="html")
        except Exception as e:
            print(f"Error in import_data: {e}")

    @client.on(events.NewMessage(pattern=r"^/broadcast(@\w+)?\s+(.+)"))
    async def broadcast(event):
        try:
            if not is_admin(event.sender_id):
                return
            text = event.pattern_match.group(2).strip()
            users = load_users()
            sent = 0
            failed = 0
            status_msg = await event.reply(f"📤 در حال ارسال به {len(users)} کاربر...")
            for uid in users:
                try:
                    await client.send_message(uid, text, parse_mode="html")
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    failed += 1
            await status_msg.edit(
                f"✅ ارسال شد.\n"
                f"موفق: {sent}\n"
                f"ناموفق: {failed}",
                parse_mode="html"
            )
        except Exception as e:
            print(f"Error in broadcast: {e}")

    async def process_and_save(msg, name, cmd=None):
        try:
            vid = is_video(msg)
            duration = get_video_duration(msg) if vid else 0
            img_bytes = await download_media_thumb(msg)
            if not img_bytes:
                return False, "no_thumb"
            hash8 = get_image_hash(img_bytes)
            key = get_key(hash8, "video" if vid else "image", duration)
            data = load_data()
            if key in data or hash8 in data:
                return False, "duplicate"
            if not cmd:
                cmd = SYNC_DEFAULT_COMMAND
            entry = {
                "command": cmd,
                "name": name,
                "type": "video" if vid else "image",
                "hash": hash8,
            }
            if vid:
                entry["duration"] = duration
            data[key] = entry
            save_data(data)
            _flush_data()
            return True, name
        except Exception:
            return False, "error"

    @client.on(events.NewMessage(pattern=r"^/testc(@\w+)?(\s+.+)?$"))
    async def test_caption(event):
        try:
            if not is_admin(event.sender_id):
                return
            text = event.pattern_match.group(2)
            if not text:
                reply = await event.get_reply_message()
                if reply:
                    text = f" {reply.message or reply.text or ''}"
                else:
                    await event.reply("متن یا ریپلای رو بفرست.", parse_mode="html")
                    return
            name = extract_name_from_caption(text.strip())
            if name:
                await event.reply(f"✅ نام استخراج شده: <code>{name}</code>", parse_mode="html")
            else:
                await event.reply("❌ هیچ اسمی استخراج نشد.", parse_mode="html")
        except Exception as e:
            print(f"Error in test_caption: {e}")

    @client.on(events.NewMessage(pattern=r"^/sync(@\w+)?(\s+@?\w+)?(\s*/[\w/]+)?$"))
    async def sync_channel(event):
        try:
            if not is_admin(event.sender_id):
                return
            channel = (event.pattern_match.group(2) or SOURCE_CHANNEL or "").strip().strip("@")
            sync_cmd = (event.pattern_match.group(3) or "").strip()
            if not channel:
                await event.reply("⚠️ چنلی مشخص نشده. از SOURCE_CHANNEL یا `/sync @channel` استفاده کنید.", parse_mode="html")
                return
            if reader_client is None:
                await event.reply(
                    "⚠️ حساب خواننده (reader account) متصل نیست. لاگ کنسول ربات را بررسی کنید.",
                    parse_mode="html"
                )
                return
            status = await event.reply(f"🔄 در حال اسکن @{channel} با {sync_cmd or SYNC_DEFAULT_COMMAND}...")
            try:
                entity = await reader_client.get_entity(channel)
            except Exception:
                await status.edit("⚠️ چنل پیدا نشد. مطمئن شوید چنل عمومی است.")
                return
            new_c = 0
            dup_c = 0
            err_c = 0
            matched = 0
            no_media_c = 0
            no_caption_c = 0
            count = 0
            t0 = time.time()
            dbg_count = 0
            await status.edit(f"🔄 اسکن @{channel} شروع شد ...")
            async for msg in reader_client.iter_messages(entity):
                count += 1
                if count % 10 == 0:
                    elapsed = int(time.time() - t0)
                    try:
                        await status.edit(f"🔄 اسکن @{channel} ... {count} پیام | {matched} تطابق ({elapsed}ثانیه)")
                    except Exception:
                        pass
                if not has_media(msg):
                    no_media_c += 1
                    continue
                caption = msg.message or msg.text or ""
                name = extract_name_from_caption(caption)
                if not name:
                    no_caption_c += 1
                    if dbg_count < 3 and caption:
                        dbg_count += 1
                        print(f"[SYNC-DBG#{dbg_count}] msg.id={msg.id} caption={repr(caption[:200])}")
                    continue
                matched += 1
                try:
                    ok, result = await process_and_save(msg, name)
                    if ok:
                        new_c += 1
                        vid = is_video(msg)
                        cmd = SYNC_VIDEO_COMMAND if vid else SYNC_IMAGE_COMMAND
                        for aid in ADMIN_IDS:
                            try:
                                await client.send_message(
                                    aid,
                                    f"✅ <b>از چنل ذخیره شد</b>\n"
                                    f"🔹 <b>نام:</b> <code>{result}</code>\n"
                                    f"🔹 <b>دستور:</b> <code>{cmd}</code>\n"
                                    f"{'🎬' if vid else '🖼'} <b>نوع:</b> <code>{'ویدیو' if vid else 'تصویر'}</code>",
                                    parse_mode="html"
                                )
                            except Exception:
                                pass
                    elif result == "duplicate":
                        dup_c += 1
                    else:
                        err_c += 1
                except Exception:
                    err_c += 1
            elapsed = int(time.time() - t0)
            await status.edit(
                f"✅ <b>اسکن @{channel} تمام شد</b>\n"
                f"⏱ زمان: {elapsed}ثانیه\n"
                f"📨 کل پیام‌ها: {count}\n"
                f"🎯 تطابق کپشن: {matched}\n"
                f"🆕 جدید: {new_c}\n"
                f"🔁 تکراری: {dup_c}\n"
                f"⏭ بدون مدیا: {no_media_c}\n"
                f"⏭ بدون کپشن: {no_caption_c}\n"
                f"❌ خطا: {err_c}",
                parse_mode="html"
            )
        except Exception as e:
            print(f"Error in sync_channel: {e}")
            traceback.print_exc()

    if SOURCE_CHANNEL:
        @client.on(events.NewMessage(chats=SOURCE_CHANNEL))
        async def auto_sync(event):
            try:
                msg = event.message
                if not has_media(msg):
                    return
                caption = msg.message or msg.text or ""
                name = extract_name_from_caption(caption)
                if not name:
                    return
                ok, result = await process_and_save(msg, name)
                if ok:
                    vid = is_video(msg)
                    cmd = SYNC_VIDEO_COMMAND if vid else SYNC_IMAGE_COMMAND
                    for aid in ADMIN_IDS:
                        try:
                            await client.send_message(
                                aid,
                                f"✅ <b>پست جدید از چنل</b>\n"
                                f"🔹 <b>نام:</b> <code>{result}</code>\n"
                                f"🔹 <b>دستور:</b> <code>{cmd}</code>\n"
                                f"{'🎬' if vid else '🖼'} <b>نوع:</b> <code>{'ویدیو' if vid else 'تصویر'}</code>",
                                parse_mode="html"
                            )
                        except Exception:
                            pass
            except Exception as e:
                print(f"Error in auto_sync: {e}")

    async def flush_loop():
        while True:
            await asyncio.sleep(30)
            _flush_data()

    asyncio.ensure_future(flush_loop())
    print("Listening for messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
