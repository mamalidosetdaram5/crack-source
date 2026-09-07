import os
import asyncio
import sqlite3
import requests
from telethon import TelegramClient, events, functions
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

# ==========================================
# تنظیمات اصلی (حتماً پر کنید)
# ==========================================
API_ID = 29206821          # عدد API ID
API_HASH = '6fc091b004de021d44c76f01e27fe91c' # رشته API Hash
SESSION_NAME = 'ultimate_selfbot'

TARGET_USERS = [
    7367084221
    # آیدی عددی پیوی‌هایی که می‌خواهید آرشیو شوند
    # در اولین اجرا، فایل all_private_chats.txt ساخته می‌شود
]

# تنظیمات آپلود عکس
AUTO_UPLOAD = True
UPLOAD_SERVICE = 'catbox'  # 'catbox' یا 'imgbb' یا 'imgur'
IMGUR_CLIENT_ID = ''
IMGBB_API_KEY = ''

# ==========================================
# تنظیمات دیتابیس
# ==========================================
MEDIA_DIR = 'selfbot_media_cache'
DB_FILE = 'selfbot_cache.db'
CONFIG_FILE = 'selfbot_config.txt'
os.makedirs(MEDIA_DIR, exist_ok=True)

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS antidel_cache (
        chat_id INTEGER, message_id INTEGER, sender_name TEXT,
        text_content TEXT, media_type TEXT, media_path TEXT, date TEXT,
        PRIMARY KEY (chat_id, message_id)
    )
''')
conn.commit()

def get_config(key):
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            for line in f:
                if line.startswith(f"{key}="):
                    return line.split('=')[1].strip() == 'True'
    # پیش‌فرض: همه چیز روشن است
    return True

def set_config(key, value):
    lines = []
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f: lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found: lines.append(f"{key}={value}\n")
    with open(CONFIG_FILE, 'w') as f: f.writelines(lines)

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# ==========================================
# توابع آپلود عکس
# ==========================================
def upload_to_catbox(file_path):
    try:
        with open(file_path, 'rb') as f:
            files = {'fileToUpload': f}
            data = {'reqtype': 'fileupload', 'userhash': ''}
            response = requests.post('https://catbox.moe/user/api.php', files=files, data=data, timeout=30)
            if response.status_code == 200:
                return response.text.strip()
    except Exception as e:
        print(f"خطا در آپلود به Catbox: {e}")
    return None

def upload_to_imgbb(file_path):
    if not IMGBB_API_KEY: return None
    try:
        with open(file_path, 'rb') as f:
            payload = {'key': IMGBB_API_KEY, 'image': f}
            response = requests.post('https://api.imgbb.com/1/upload', data=payload, timeout=30)
            if response.status_code == 200:
                return response.json()['data']['url']
    except Exception as e:
        print(f"خطا در آپلود به ImgBB: {e}")
    return None

def upload_to_imgur(file_path):
    if not IMGUR_CLIENT_ID: return None
    try:
        headers = {'Authorization': f'Client-ID {IMGUR_CLIENT_ID}'}
        with open(file_path, 'rb') as f:
            response = requests.post('https://api.imgur.com/3/image', headers=headers, files={'image': f}, timeout=30)
            if response.status_code == 200:
                return response.json()['data']['link']
    except Exception as e:
        print(f"خطا در آپلود به Imgur: {e}")
    return None

def upload_image(file_path):
    if not AUTO_UPLOAD: return None
    if UPLOAD_SERVICE == 'catbox': return upload_to_catbox(file_path)
    elif UPLOAD_SERVICE == 'imgbb': return upload_to_imgbb(file_path)
    elif UPLOAD_SERVICE == 'imgur': return upload_to_imgur(file_path)
    return None

# ==========================================
# توابع آرشیو بی‌صدا
# ==========================================
async def extract_admin_channels():
    print("🔍 [آرشیو] استخراج لیست کانال‌های مدیریتی...")
    with open('admin_channels.txt', 'w', encoding='utf-8') as f:
        f.write("📋 لیست کانال‌هایی که در آن‌ها ادمین یا مالک هستید:\n" + "="*50 + "\n\n")
        async for dialog in client.iter_dialogs():
            if dialog.is_channel:
                try:
                    perms = await client.get_permissions(dialog.id, 'me')
                    if perms.is_admin or perms.is_creator:
                        title = dialog.name
                        link = f"https://t.me/{dialog.entity.username}" if dialog.entity.username else "کانال خصوصی"
                        if link == "کانال خصوصی":
                            try:
                                full_chat = await client(functions.channels.GetFullChannelRequest(dialog.id))
                                if full_chat.full_chat.exported_invite: link = full_chat.full_chat.exported_invite.link
                            except: pass
                        role = "مالک" if perms.is_creator else "ادمین"
                        f.write(f"📛 نام: {title}\n🔗 لینک: {link}\n🆔 آیدی: {dialog.id}\n👤 جایگاه: {role}\n" + "-"*50 + "\n")
                    await asyncio.sleep(0.2)
                except: pass
    print("✅ [آرشیو] فایل admin_channels.txt ساخته شد.")

async def list_all_private_chats():
    print("📝 [آرشیو] ساخت لیست تمام پیوی‌ها...")
    with open('all_private_chats.txt', 'w', encoding='utf-8') as f:
        f.write("📋 لیست پیوی‌ها (آیدی عددی را در TARGET_USERS کپی کنید):\n" + "="*60 + "\n\n")
        async for dialog in client.iter_dialogs():
            if dialog.is_user:
                user = await client.get_entity(dialog.id)
                name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "بدون نام"
                username = f"@{user.username}" if user.username else "بدون یوزرنیم"
                f.write(f"👤 نام: {name}\n🆔 آیدی عددی: {dialog.id}\n🔗 یوزرنیم: {username}\n" + "-"*60 + "\n")
    print("✅ [آرشیو] فایل all_private_chats.txt ساخته شد.")

async def archive_user_photos_and_messages():
    if not TARGET_USERS:
        print("⚠️ [آرشیو] لیست TARGET_USERS خالی است.")
        return
    for user_id in TARGET_USERS:
        print(f"📂 [آرشیو] آرشیو کامل پیوی {user_id}...")
        try:
            user_entity = await client.get_entity(user_id)
            user_name = (user_entity.username or user_entity.first_name or "Unknown").replace("/", "_")
            folder_name = f"PV_Archive_{user_id}_{user_name}"
            os.makedirs(folder_name, exist_ok=True)
            
            text_file = os.path.join(folder_name, 'chat_history.txt')
            downloaded_file = os.path.join(folder_name, 'downloaded_ids.txt')
            downloaded_ids = set()
            if os.path.exists(downloaded_file):
                with open(downloaded_file, 'r') as f: downloaded_ids = set(f.read().splitlines())

            photo_count = 0
            message_count = 0
            
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(f"📋 تاریخچه چت با {user_name} (آیدی: {user_id})\n" + "="*70 + "\n\n")
                
                async for message in client.iter_messages(user_id, limit=1000):
                    message_count += 1
                    sender = "من" if message.out else (await message.get_sender()).first_name or "کاربر"
                    date_str = message.date.strftime("%Y-%m-%d %H:%M:%S")
                    
                    f.write(f"[{date_str}] {sender}:\n")
                    
                    if message.text: f.write(f"📝 متن: {message.text}\n")
                    
                    if message.photo:
                        photo_count += 1
                        file_path = os.path.join(folder_name, f"photo_{message.id}.jpg")
                        await client.download_media(message.photo, file=file_path)
                        
                        upload_link = None
                        if AUTO_UPLOAD: upload_link = upload_image(file_path)
                        
                        if upload_link:
                            f.write(f"🖼️ عکس: {file_path}\n🔗 لینک آپلود: {upload_link}\n")
                        else:
                            f.write(f"🖼️ عکس: {file_path}\n")
                    
                    if message.video: f.write(f"🎥 ویدیو (دانلود نشده)\n")
                    if message.voice: f.write(f"🎤 ویس (دانلود نشده)\n")
                    if message.document and not message.photo and not message.video: f.write(f"📄 فایل ضمیمه\n")
                    
                    f.write("-" * 70 + "\n")
                    
                    if message_count % 50 == 0:
                        await asyncio.sleep(1)
                        print(f"  ⏳ ذخیره پیام {message_count}/1000...")
            
            print(f"✅ [آرشیو] {message_count} پیام ({photo_count} عکس) در '{text_file}' ذخیره شد.")
        except Exception as e: print(f"❌ خطا در {user_id}: {e}")

async def run_archiver_background():
    try:
        await extract_admin_channels()
        await list_all_private_chats()
        await archive_user_photos_and_messages()
        print("🎉 [آرشیو] تمام عملیات آرشیو تمام شد.")
    except Exception as e:
        print(f"❌ خطا در آرشیو: {e}")

# ==========================================
# دستورات کنترلی
# ==========================================
@client.on(events.NewMessage(outgoing=True, pattern=r'^\.(antidel|najva|archive)\s*(on|off|status|help|start)?'))
async def handle_commands(event):
    command = event.pattern_match.group(1).lower()
    action = (event.pattern_match.group(2) or 'help').lower()
    
    if command == 'antidel':
        if action == 'on': set_config('antidel', 'True'); await event.edit("✅ آنتی‌دلیت روشن شد. (تمام پیوی‌ها)")
        elif action == 'off': set_config('antidel', 'False'); await event.edit("❌ آنتی‌دلیت خاموش شد.")
        elif action == 'status': await event.edit(f"📊 آنتی‌دلیت: {'روشن ✅' if get_config('antidel') else 'خاموش ❌'}")
        else: await event.edit("📖 `.antidel on/off/status`\n⚠️ برای تست: پیام طرف مقابل را پاک کنید، نه پیام خودتان را!")
        
    elif command == 'najva':
        if action == 'on': set_config('najva', 'True'); await event.edit("✅ لاگ نجوا روشن شد. (تمام گروه‌ها)")
        elif action == 'off': set_config('najva', 'False'); await event.edit("❌ لاگ نجوا خاموش شد.")
        elif action == 'status': await event.edit(f"📊 نجوا: {'روشن ✅' if get_config('najva') else 'خاموش ❌'}")
        else: await event.edit("📖 `.najva on/off/status`")
        
    elif command == 'archive':
        if action == 'start':
            await event.edit("🔄 شروع مجدد آرشیو...")
            asyncio.create_task(run_archiver_background())
        else:
            await event.edit("📖 `.archive start`")

# ==========================================
# ماژول نجوا (تمام پیام‌های ربات‌ها در پیوی)
# ==========================================
@client.on(events.NewMessage(incoming=True))
async def log_whispers(event):
    if not get_config('najva') or not event.is_private: return
    sender = await event.get_sender()
    if sender and sender.bot:
        text_content = event.text if event.text else "[پیام غیرمتنی]"
        log_msg = (
            f"🤫 **[نجوا/پیام ربات]**\n"
            f"🤖 ربات: `{sender.first_name or sender.username}`\n"
            f"📝 متن:\n{text_content}"
        )
        await client.send_message('me', log_msg)

# ==========================================
# ماژول آنتی‌دلیت (تمام پیوی‌ها)
# ==========================================
@client.on(events.NewMessage(incoming=True))
async def cache_message(event):
    if not get_config('antidel') or not event.is_private: return
    
    sender = await event.get_sender()
    sender_name = sender.first_name or sender.username or "کاربر ناشناس" if sender else "ناشناس"
    text_content = event.text if event.text else ""
    date_str = event.date.strftime("%Y-%m-%d %H:%M:%S")
    media_type = None; media_path = None
    
    if event.media:
        if isinstance(event.media, MessageMediaPhoto): media_type = 'photo'; file_ext = '.jpg'
        elif isinstance(event.media, MessageMediaDocument):
            mime = event.media.document.mime_type
            if 'video' in mime: media_type = 'video'; file_ext = '.mp4'
            elif 'audio' in mime or 'voice' in mime: media_type = 'voice'; file_ext = '.ogg'
            else: media_type = 'document'; file_ext = '.bin'
        media_path = os.path.join(MEDIA_DIR, f"{event.chat_id}_{event.id}{file_ext}")
        try: await client.download_media(event.media, file=media_path)
        except: media_path = None

    cursor.execute('INSERT OR REPLACE INTO antidel_cache VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (event.chat_id, event.id, sender_name, text_content, media_type, media_path, date_str))
    conn.commit()

@client.on(events.MessageDeleted)
async def handle_deleted(event):
    if not get_config('antidel'): return
    
    # حالت ۱: chat_id مشخص است (پیوی)
    if event.chat_id and event.chat_id > 0:
        for msg_id in event.deleted_ids:
            await process_cached_message(event.chat_id, msg_id, "حذف شد 🗑️")
    
    # حالت ۲: chat_id None است (برخی کلاینت‌ها) - باید دیتابیس را چک کنیم
    elif event.chat_id is None:
        for msg_id in event.deleted_ids:
            cursor.execute('SELECT chat_id FROM antidel_cache WHERE message_id = ?', (msg_id,))
            row = cursor.fetchone()
            if row and row[0] > 0:
                await process_cached_message(row[0], msg_id, "حذف شد 🗑️")

@client.on(events.MessageEdited)
async def handle_edited(event):
    if not get_config('antidel') or not event.is_private: return
    
    cursor.execute('SELECT text_content, media_type, media_path, date FROM antidel_cache WHERE chat_id = ? AND message_id = ?', (event.chat_id, event.id))
    row = cursor.fetchone()
    if row:
        old_text, media_type, media_path, date_str = row
        new_text = event.text or ""
        
        # اگر متن تغییر کرده، نسخه قبلی را بفرست
        if old_text != new_text:
            await process_cached_message(event.chat_id, event.id, "ویرایش شد ⚠️")
            
            # به‌روزرسانی دیتابیس
            cursor.execute('UPDATE antidel_cache SET text_content = ? WHERE chat_id = ? AND message_id = ?', (new_text, event.chat_id, event.id))
            conn.commit()

async def process_cached_message(chat_id, msg_id, action_text):
    cursor.execute('SELECT sender_name, text_content, media_type, media_path, date FROM antidel_cache WHERE chat_id = ? AND message_id = ?', (chat_id, msg_id))
    row = cursor.fetchone()
    if row:
        sender_name, text_content, media_type, media_path, date_str = row
        caption = f"🚨 **پیام {action_text}**\n👤 فرستنده: `{sender_name}`\n🕒 زمان: `{date_str}`\n"
        if text_content: caption += f"📝 متن:\n`{text_content}`\n"
        try:
            if media_path and os.path.exists(media_path):
                await client.send_file('me', media_path, caption=caption)
                os.remove(media_path)
            elif text_content:
                await client.send_message('me', caption)
            else:
                await client.send_message('me', caption + "\n[بدون محتوا]")
        except Exception as e: print(f"خطا در ارسال: {e}")
        
        cursor.execute('DELETE FROM antidel_cache WHERE chat_id = ? AND message_id = ?', (chat_id, msg_id))
        conn.commit()

# ==========================================
# اجرای نهایی
# ==========================================
print("🚀 سلف‌بات در حال راه‌اندازی...")
print("✅ آنتی‌دلیت و نجوا به صورت پیش‌فرض روشن هستند.")
print("⚠️ نکته مهم: برای تست آنتی‌دلیت، باید پیام طرف مقابل را پاک کنید، نه پیام خودتان را!")
client.start()

client.loop.create_task(run_archiver_background())

print("✅ سلف‌بات آماده است.")
client.run_until_disconnected()
