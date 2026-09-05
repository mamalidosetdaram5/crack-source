from pyrogram import Client, filters
import re
import asyncio

# ⚠️ اطلاعات اکانتت رو اینجا وارد کن (از my.telegram.org بگیر)
api_id = 29206821  # عدد باشه
api_hash = "6fc091b004de021d44c76f01e27fe91c"  # رشته متنی باشه

app = Client("my_autogift_session", api_id=api_id, api_hash=api_hash)

# تنظیمات_delay (خیلی مهم برای بن نشدن)
DELAY_BETWEEN_GIFTS = 3  # ثانیه صبر بین هر گیفت
DELAY_AFTER_PAGE = 2     # ثانیه صبر بعد از زدن دکمه صفحه بعد

async def extract_numbers(text):
    """اعداد داخل براکت [1234] رو استخراج می‌کنه"""
    return re.findall(r'\[(\d+)\)', text)

async def click_confirm_button(client, chat_id, reply_to_msg_id):
    """دنبال پیام بات می‌گرده و اگر دکمه ✅ داشت روش کلیک می‌کنه"""
    await asyncio.sleep(1.5) # صبر می‌کنیم تا بات جواب بده
    
    async for message in app.get_chat_history(chat_id, limit=10):
        if message.reply_to_message and message.reply_to_message.id == reply_to_msg_id:
            # پیام بات رو پیدا کردیم
            if message.reply_markup and message.reply_markup.inline_keyboard:
                for row in message.reply_markup.inline_keyboard:
                    for button in row:
                        if "✅" in button.text:
                            # کلیک کردن روی دکمه اینلاین
                            await client.request_callback_answer(chat_id, message.id, button.callback_data)
                            return True
            # اگر دکمه نبود و خود متن ✅ داشت، یعنی تایید شده
            if "✅" in message.text:
                return True
            break
    return False

@app.on_message(filters.command("start_gift", prefixes="!") & filters.reply)
async def auto_gift_handler(client, message):
    target_msg = message.reply_to_message
    
    if not target_msg.text:
        await message.reply_text("❌ لطفاً روی پیامی که لیست کاراکترها توش هست ریپلای کن.")
        return

    await message.reply_text("🚀 سلف اتو گیفت شروع به کار کرد...")
    
    current_msg = target_msg
    page_number = 1

    while True:
        # 1. استخراج اعداد از پیام فعلی
        numbers = await extract_numbers(current_msg.text)
        
        if not numbers:
            await message.reply_text(f"✅ صفحه {page_number} عددی برای گیفت نداشت یا تموم شد.")
            break

        await message.reply_text(f"📄 صفحه {page_number}: {len(numbers)} عدد پیدا شد. شروع به گیفت...")

        # 2. گیفت کردن اعداد یکی یکی
        for num in numbers:
            # ارسال دستور گیفت و ریپلای کردن روی پیام اصلی
            sent_msg = await current_msg.reply_text(f"/gift {num}")
            
            # 3. تایید گرفتن از بات (کلیک روی ✅ یا چک کردن متن)
            await click_confirm_button(client, current_msg.chat.id, sent_msg.id)
            
            # ⚠️ دیلی برای جلوگیری از بن شدن (بسیار مهم)
            await asyncio.sleep(DELAY_BETWEEN_GIFTS)

        # 4. چک کردن برای رفتن به صفحه بعد (دکمه ➡️)
        next_page_found = False
        if current_msg.reply_markup and current_msg.reply_markup.inline_keyboard:
            for row in current_msg.reply_markup.inline_keyboard:
                for button in row:
                    if "➡️" in button.text or "Next" in button.text:
                        # کلیک روی دکمه صفحه بعد
                        await client.request_callback_answer(current_msg.chat.id, current_msg.id, button.callback_data)
                        next_page_found = True
                        break
                if next_page_found:
                    break

        if not next_page_found:
            await message.reply_text("🏁 دکمه ➡️ پیدا نشد. یعنی به آخرین صفحه رسیدیم. سلف متوقف شد.")
            break

        # 5. صبر کردن برای آپدیت شدن پیام و گرفتن متن جدید
        await asyncio.sleep(DELAY_AFTER_PAGE)
        
        # گرفتن آپدیت جدید پیام (چون متن پیام بعد از کلیک روی ➡️ عوض میشه)
        current_msg = await client.get_messages(current_msg.chat.id, current_msg.id)
        page_number += 1

print("سلف آماده است. برای شروع، روی پیام لیست ریپلای کن و بفرست: !start_gift")
app.run()
