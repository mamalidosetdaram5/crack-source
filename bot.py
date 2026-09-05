from pyrogram import Client, filters
import re
import asyncio

# ⚠️ اطلاعات اکانتت رو اینجا وارد کن
api_id = 29206821  # عدد باشه
api_hash = "6fc091b004de021d44c76f01e27fe91c"  # رشته متنی باشه

app = Client("my_autogift_session", api_id=api_id, api_hash=api_hash)

# تنظیمات تاخیر (برای جلوگیری از بن شدن)
DELAY_BETWEEN_GIFTS = 3  # ثانیه صبر بین هر گیفت
DELAY_AFTER_PAGE = 2     # ثانیه صبر بعد از زدن دکمه صفحه بعد

async def extract_numbers(text):
    """اعداد داخل براکت [1234] رو استخراج می‌کنه"""
    return re.findall(r'\[(\d+)\]', text)from pyrogram import Client, filters
import re
import asyncio

# ⚠️ اطلاعات اکانتت رو اینجا وارد کن
api_id = 12345678  
api_hash = "your_api_hash_here"  

app = Client("my_autogift_session", api_id=api_id, api_hash=api_hash)

DELAY_BETWEEN_GIFTS = 3  
DELAY_AFTER_PAGE = 2     

async def extract_numbers(text):
    if not text:
        return []
    return re.findall(r'\[(\d+)\]', text)

async def click_confirm_button(client, chat_id, reply_to_msg_id):
    await asyncio.sleep(1.5) 
    try:
        async for message in app.get_chat_history(chat_id, limit=15):
            if message.reply_to_message and message.reply_to_message.id == reply_to_msg_id:
                if message.reply_markup and message.reply_markup.inline_keyboard:
                    for row in message.reply_markup.inline_keyboard:
                        for button in row:
                            if "✅" in button.text or "Confirm" in button.text:
                                await client.request_callback_answer(chat_id, message.id, button.callback_data)
                                return True
                if "✅" in (message.text or ""):
                    return True
                break
    except Exception as e:
        print(f"Error in click_confirm_button: {e}")
    return False

@app.on_message(filters.command("start_gift", prefixes="!"))
async def auto_gift_handler(client, message):
    if not message.reply_to_message:
        await message.reply_text("❌ لطفاً روی پیامی که لیست کاراکترها توش هست ریپلای کن.")
        return

    if len(message.command) < 2:
        await message.reply_text("❌ لطفاً آیدی یا یوزرنیم شخص مورد نظر رو هم بنویس.\nمثال: `!start_gift @username`")
        return

    target_msg = message.reply_to_message
    target_identifier = message.command[1] 
    
    await message.reply_text("🔍 در حال پیدا کردن پیام شخص مورد نظر...")
    print("🔍 در حال جستجو برای شخص مورد نظر...")

    target_user_msg = None
    async for msg in client.get_chat_history(message.chat.id, limit=200):
        if msg.from_user:
            if msg.from_user.username and msg.from_user.username.lower() == target_identifier.strip('@').lower():
                target_user_msg = msg
                break
            elif str(msg.from_user.id) == target_identifier.strip('@'):
                target_user_msg = msg
                break

    if not target_user_msg:
        await message.reply_text("❌ پیامی از این شخص پیدا نشد.")
        return

    await message.reply_text(f"✅ پیام شخص مورد نظر پیدا شد. شروع به گیفت کردن...")
    print("✅ شخص مورد نظر پیدا شد. شروع حلقه اصلی...")
    
    current_msg = target_msg
    page_number = 1

    while True:
        print(f"\n--- بررسی صفحه {page_number} ---")
        
        if not current_msg.text:
            print("⚠️ پیام لیست، متن ندارد (شاید عکس یا مدیا است).")
            await message.reply_text("⚠️ پیام لیست متن ندارد.")
            break

        print(f"متن پیام (۱۰۰ کاراکتر اول): {current_msg.text[:100]}...")
        numbers = await extract_numbers(current_msg.text)
        print(f"🔢 اعداد استخراج شده: {numbers}")
        
        if not numbers:
            print("❌ هیچ عددی پیدا نشد. توقف سلف.")
            await message.reply_text(f"✅ صفحه {page_number} عددی برای گیفت نداشت یا تموم شد.")
            break

        await message.reply_text(f"📄 صفحه {page_number}: {len(numbers)} عدد پیدا شد. شروع به گیفت...")

        for num in numbers:
            print(f"📤 در حال ارسال /gift {num} ...")
            try:
                # ⭐️ ارسال دستور و ریپلای روی پیام شخص مورد نظر
                sent_msg = await target_user_msg.reply_text(f"/gift {num}")
                print(f"✅ پیام /gift {num} با موفقیت ارسال شد. ID: {sent_msg.id}")
            except Exception as e:
                print(f"❌ خطا در ارسال پیام: {e}")
                await message.reply_text(f"❌ خطا در ارسال /gift {num}: {e}")
                break # اگر ارور داد، حلقه رو متوقف کن
                
            await click_confirm_button(client, current_msg.chat.id, sent_msg.id)
            await asyncio.sleep(DELAY_BETWEEN_GIFTS)

        next_page_found = False
        if current_msg.reply_markup and current_msg.reply_markup.inline_keyboard:
            for row in current_msg.reply_markup.inline_keyboard:
                for button in row:
                    if "➡️" in button.text or "Next" in button.text:
                        print(f"➡️ دکمه صفحه بعد پیدا شد: {button.text}")
                        try:
                            await client.request_callback_answer(current_msg.chat.id, current_msg.id, button.callback_data)
                            next_page_found = True
                        except Exception as e:
                            print(f"❌ خطا در کلیک دکمه صفحه بعد: {e}")
                        break
                if next_page_found:
                    break

        if not next_page_found:
            print("🏁 دکمه ➡️ پیدا نشد. توقف سلف.")
            await message.reply_text("🏁 دکمه ➡️ پیدا نشد. سلف متوقف شد.")
            break

        await asyncio.sleep(DELAY_AFTER_PAGE)
        
        try:
            current_msg = await client.get_messages(current_msg.chat.id, current_msg.id)
            print("🔄 پیام لیست آپدیت شد.")
        except Exception as e:
            print(f"❌ خطا در گرفتن آپدیت پیام: {e}")
            break
            
        page_number += 1

print("سلف آماده است. برای شروع، روی پیام لیست ریپلای کن و بفرست: !start_gift @username")
app.run()

async def click_confirm_button(client, chat_id, reply_to_msg_id):
    """دنبال پیام بات می‌گرده و اگر دکمه ✅ داشت روش کلیک می‌کنه یا متنش رو چک می‌کنه"""
    await asyncio.sleep(1.5) # صبر می‌کنیم تا بات جواب بده
    
    async for message in app.get_chat_history(chat_id, limit=15):
        if message.reply_to_message and message.reply_to_message.id == reply_to_msg_id:
            if message.reply_markup and message.reply_markup.inline_keyboard:
                for row in message.reply_markup.inline_keyboard:
                    for button in row:
                        if "✅" in button.text or "Confirm" in button.text:
                            await client.request_callback_answer(chat_id, message.id, button.callback_data)
                            return True
            if "✅" in message.text:
                return True
            break
    return False

@app.on_message(filters.command("start_gift", prefixes="!"))
async def auto_gift_handler(client, message):
    # 1. چک کردن اینکه حتماً روی یک پیام ریپلای شده باشه
    if not message.reply_to_message:
        await message.reply_text("❌ لطفاً روی پیامی که لیست کاراکترها توش هست ریپلای کن.")
        return

    # 2. چک کردن اینکه آیدی شخص مورد نظر رو وارد کرده باشه
    if len(message.command) < 2:
        await message.reply_text("❌ لطفاً آیدی یا یوزرنیم شخص مورد نظر رو هم بنویس.\nمثال: `!start_gift @username`")
        return

    target_msg = message.reply_to_message
    target_identifier = message.command[1] # همون @username یا آیدی عددی
    
    await message.reply_text("🔍 در حال پیدا کردن پیام شخص مورد نظر...")

    # 3. پیدا کردن آخرین پیام شخص مورد نظر توی چت
    target_user_msg = None
    async for msg in client.get_chat_history(message.chat.id, limit=200):
        if msg.from_user:
            # چک کردن با یوزرنیم
            if msg.from_user.username and msg.from_user.username.lower() == target_identifier.strip('@').lower():
                target_user_msg = msg
                break
            # چک کردن با آیدی عددی
            elif str(msg.from_user.id) == target_identifier.strip('@'):
                target_user_msg = msg
                break

    if not target_user_msg:
        await message.reply_text("❌ پیامی از این شخص توی ۲۰۰ پیام اخیر چت پیدا نشد. لطفاً مطمئن شو یوزرنیم/آیدی درسته یا یک پیام ازش بخواه تا بیاد بالای چت.")
        return

    await message.reply_text(f"✅ پیام شخص مورد نظر پیدا شد. شروع به گیفت کردن...")
    
    current_msg = target_msg
    page_number = 1

    while True:
        # 4. استخراج اعداد از پیام لیست
        numbers = await extract_numbers(current_msg.text)
        
        if not numbers:
            await message.reply_text(f"✅ صفحه {page_number} عددی برای گیفت نداشت یا تموم شد.")
            break

        await message.reply_text(f"📄 صفحه {page_number}: {len(numbers)} عدد پیدا شد. شروع به گیفت...")

        # 5. گیفت کردن اعداد یکی یکی
        for num in numbers:
            # ⭐️ نکته اصلی: ریپلای کردن روی پیام شخص مورد نظر (نه پیام لیست)
            sent_msg = await target_user_msg.reply_text(f"/gift {num}")
            
            # 6. تایید گرفتن از بات
            await click_confirm_button(client, current_msg.chat.id, sent_msg.id)
            
            # ⚠️ دیلی برای جلوگیری از بن شدن
            await asyncio.sleep(DELAY_BETWEEN_GIFTS)

        # 7. چک کردن برای رفتن به صفحه بعد (دکمه ➡️)
        next_page_found = False
        if current_msg.reply_markup and current_msg.reply_markup.inline_keyboard:
            for row in current_msg.reply_markup.inline_keyboard:
                for button in row:
                    if "➡️" in button.text or "Next" in button.text:
                        await client.request_callback_answer(current_msg.chat.id, current_msg.id, button.callback_data)
                        next_page_found = True
                        break
                if next_page_found:
                    break

        if not next_page_found:
            await message.reply_text("🏁 دکمه ➡️ پیدا نشد. یعنی به آخرین صفحه رسیدیم. سلف متوقف شد.")
            break

        # 8. صبر کردن برای آپدیت شدن پیام لیست
        await asyncio.sleep(DELAY_AFTER_PAGE)
        
        # گرفتن آپدیت جدید پیام لیست
        current_msg = await client.get_messages(current_msg.chat.id, current_msg.id)
        page_number += 1

print("سلف آماده است. برای شروع، روی پیام لیست ریپلای کن و بفرست: !start_gift @username")
app.run()
