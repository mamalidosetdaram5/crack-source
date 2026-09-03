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
BOT_TOKEN = "8976551206:AAGyWdTtvaQtgHElgYkriZNNmBs2s8rkLsA"
ADMIN_IDS = [6716559782, 8192645915, 6745595929]
OWNER_ID = ADMIN_IDS[0]
FORCE_CHANNEL = "FlameWaifu_Cheat_Datebase"
FORCE_CHANNEL_LINK = ""
SOURCE_CHANNEL = "Picker_database"  # channel username for auto-sync
DATA_FILE = "data.json"
USERS_FILE = "users.json"
BANNED_FILE = "banned.json"
SYNC_DEFAULT_COMMAND = "/pick"
SYNC_IMAGE_COMMAND = "/pick"
SYNC_VIDEO_COMMAND = "/pick"

_data_cache = None
_data_dirty = False
RATE_LIMIT_SECONDS = 1
_last_usage = defaultdict(float)


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


def make_list_page(data, page, filter_type):
    items = []
    for key, val in data.items():
        t = val.get("type", "image")
        if filter_type == "all" or t == filter_type:
            items.append((key, val))
    items.sort(key=lambda x: x[0])
    total = len(items)
    total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_items = items[start:end]
    return page_items, page, total_pages, total


async def send_list_page(event, client, page, filter_type):
    data = load_data()
    if not data:
        await event.edit("📭 هیچ موردی ذخیره نشده.")
        return
    page_items, cur, total_pages, total = make_list_page(data, page, filter_type)
    if not page_items:
        await event.edit("📭 هیچ موردی برای این صفحه وجود ندارد.")
        return
    lines = []
    for key, val in page_items:
        t = val.get("type", "image")
        icon = "🎬" if t == "video" else "🖼"
        dur = f" ({val['duration']}s)" if t == "video" and "duration" in val else ""
        lines.append(f"{icon} <code>{key}</code> ➜ {val['command']} {val['name']}{dur}")
    text = (
        f"📋 <b>لیست ذخیره شده‌ها</b> ({filter_type})\n"
        f"صفحه {cur + 1} از {total_pages} — مجموع: {total}\n\n"
        + "\n".join(lines)
    )
    buttons = []
    row = []
    if cur > 0:
        row.append(Button.inline("◀️ قبلی", f"list|{cur - 1}|{filter_type}"))
    if cur < total_pages - 1:
        row.append(Button.inline("بعدی ▶️", f"list|{cur + 1}|{filter_type}"))
    if row:
        buttons.append(row)
    filter_row = [
        Button.inline("همه", f"list|0|all"),
        Button.inline("🖼 تصویر", f"list|0|image"),
        Button.inline("🎬 ویدیو", f"list|0|video"),
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
        found_msg = None
        found_name = None
        checked = 0
        async for msg in client.iter_messages(entity):
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

    @client.on(events.NewMessage(pattern=r"^/pick(@\w+)?\s+(\d+)\s*$"))
    async def pick_by_id(event):
        """/pick <id> — scans SOURCE_CHANNEL for the newest post whose caption
        contains that ID (e.g. 「 ID : 7840 Balalaika 」), grabs its media,
        and saves it under the default command with the name parsed from the
        caption."""
        if not is_admin(event.sender_id):
            return
        try:
            target_id = event.pattern_match.group(2).strip()
            channel = (SOURCE_CHANNEL or "").strip().strip("@")
            if not channel:
                await event.reply("⚠️ SOURCE_CHANNEL تنظیم نشده.", parse_mode="html")
                return

            status = await event.reply(f"🔎 در حال جستجوی کد <code>{target_id}</code> در @{channel} ...", parse_mode="html")
            try:
                entity = await client.get_entity(channel)
            except Exception:
                await status.edit("⚠️ چنل پیدا نشد.")
                return

            r = await find_and_save_by_id(entity, target_id)

            if r["status"] == "not_found":
                await status.edit(f"❌ هیچ پستی با کد <code>{target_id}</code> پیدا نشد.", parse_mode="html")
                return
            if r["status"] == "error":
                reason = {"no_thumb": "دانلود مدیا ناموفق بود.", "error": "خطای داخلی."}.get(r["reason"], r["reason"])
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
                entity = await client.get_entity(channel)
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

    @client.on(events.NewMessage(pattern=r"^/(\w+)(@\w+)?\s+(.+)"))
    async def admin_register(event):
        try:
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

            for aid in ADMIN_IDS:
                try:
                    await client.send_message(
                        aid,
                        f"📬 <b>گزارش جدید</b>\n\n"
                        f"👤 <b>کاربر:</b> {name} {username} (<code>{event.sender_id}</code>)\n"
                        f"💬 <b>پیشنهاد:</b> <code>{suggested}</code>\n"
                        f"🔹 <b>هش:</b> <code>{key}</code>\n"
                        f"📎 <b>chat:</b> <code>{event.chat_id}</code>",
                        parse_mode="html"
                    )
                except Exception:
                    pass

            await event.reply("✅ گزارش شما ارسال شد. ادمین بررسی خواهد کرد.", parse_mode="html")
        except Exception as e:
            print(f"Error in report_missing: {e}")

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

    @client.on(events.CallbackQuery(pattern=r"^list\|(\d+)\|(.+)$"))
    async def list_callback(event):
        try:
            if not is_admin(event.sender_id):
                await event.answer("دسترسی ندارید.", alert=True)
                return
            page = int(event.pattern_match.group(1))
            filter_type = event.pattern_match.group(2)
            await send_list_page(event, client, page, filter_type)
            await event.answer()
        except Exception as e:
            print(f"Error in list_callback: {e}")

    @client.on(events.NewMessage(pattern=r"^/delete(@\w+)?\s+(.+)"))
    async def delete_hash(event):
        try:
            if not is_admin(event.sender_id):
                return
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
            status = await event.reply(f"🔄 در حال اسکن @{channel} با {sync_cmd or SYNC_DEFAULT_COMMAND}...")
            try:
                entity = await client.get_entity(channel)
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
            async for msg in client.iter_messages(entity):
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
