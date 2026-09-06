from pyrogram import Client, filters
import re
import asyncio

api_id = 29206821  # <-- آیدی خودت
api_hash = "6fc091b004de021d44c76f01e27fe91c"  # <-- هش خودت

app = Client("my_autogift_session", api_id=api_id, api_hash=api_hash)

# ⭐️ آیدی عددی بات که باید منتظر پیامش بمونیم
BOT_ID = 8307651649 
DELAY_BETWEEN_GIFTS = 3
DELAY_AFTER_PAGE = 2

def extract_numbers(content):
    if not content: return []
    return re.findall(r'\[(\d+)\]', content)

async def wait_for_bot_and_confirm(client, chat_id, sent_msg_id):
    """⏳ منتظر می‌مونه تا بات جواب بده و دکمه ✅ رو می‌زنه"""
    print(f"⏳ در انتظار پاسخ بات (ID: {BOT_ID}) برای پیام {sent_msg_id}...")
    start_time = asyncio.get_event_loop().time()
    timeout = 30  # ۳۰ ثانیه زمان می‌دیم به بات
    
    while asyncio.get_event_loop().time() - start_time < timeout:
        # بررسی ۳۰ پیام آخر چت
        async for msg in client.get_chat_history(chat_id, limit=30):
            # چک می‌کنه که پیام حتماً از طرف بات مورد نظر باشه
            if msg.from_user and msg.from_user.id == BOT_ID:
                # چک می‌کنه که پیام بات، ریپلای به پیام گیفت ما باشه
                if msg.reply_to_message and msg.reply_to_message.id == sent_msg_id:
                    print(f"🤖 پاسخ بات پیدا شد!")
                    
                    # حالا دنبال دکمه ✅ توی پیام بات می‌گرده
                    if msg.reply_markup and msg.reply_markup.inline_keyboard:
                        for row in msg.reply_markup.inline_keyboard:
                            for btn in row:
                                if "✅" in btn.text:
                                    print(f"🖱️ کلیک روی دکمه تایید: {btn.text}")
                                    try:
                                        await client.request_callback_answer(chat_id, msg.id, btn.callback_data)
                                        print("✅ دکمه تایید با موفقیت کلیک شد.")
                                        return True
                                    except Exception as e:
                                        print(f"❌ خطا در کلیک دکمه: {e}")
                    
                    # اگر دکمه نداشت ولی متنش ✅ داشت
                    if msg.text and "✅" in msg.text:
                        print("✅ تایید متنی دریافت شد.")
                        return True
                        
                    print(f"⚠️ بات جواب داد ولی دکمه ✅ نداشت. متن: {msg.text}")
                    return True # اگر بات جواب داد ولی دکمه نداشت، میره عدد بعدی
                    
        await asyncio.sleep(1) # هر یک ثانیه چت رو چک می‌کنه
        
    print("⚠️ تایم اوت: بات جواب نداد.")
    return False

@app.on_message(filters.command("start_gift", prefixes="!"))
async def auto_gift(client, message):
    if not message.reply_to_message:
        await message.reply_text("❌ روی پیام لیست ریپلای کن.")
        return

    if len(message.command) < 2:
        await message.reply_text("❌ آیدی شخص رو بنویس.")
        return

    target_msg = message.reply_to_message
    target_user = message.command[1]
    target_clean = target_user.strip("@")

    await message.reply_text("🔍 در حال جستجوی پیام معتبر...")
    print("🔍 شروع جستجو...")

    user_msg = None
    async for msg in client.get_chat_history(message.chat.id, limit=200):
        if (msg.from_user and 
            not msg.from_user.is_bot and 
            not msg.sender_chat and 
            not msg.service and 
            not msg.forward_date):
            
            uname = msg.from_user.username
            uid = str(msg.from_user.id)
            
            if (uname and uname.lower() == target_clean.lower()) or (uid == target_clean):
                user_msg = msg
                print(f"✅ پیام معتبر پیدا شد! ID: {msg.id}")
                break

    if not user_msg:
        await message.reply_text("❌ پیام معتبری پیدا نشد.")
        return

    await message.reply_text("✅ شخص پیدا شد. شروع گیفت...")
    
    current_msg = target_msg
    page = 1

    while True:
        print(f"\n--- صفحه {page} ---")
        msg_content = current_msg.text or current_msg.caption
        
        if not msg_content:
            print("⚠️ پیام لیست متن/کپشن ندارد.")
            break

        numbers = extract_numbers(msg_content)
        print(f"🔢 اعداد: {numbers}")

        if not numbers:
            await message.reply_text(f"✅ صفحه {page} عددی نداشت.")
            break

        for num in numbers:
            print(f"📤 ارسال /gift {num}")
            try:
                sent = await client.send_message(
                    chat_id=message.chat.id,
                    text=f"/gift {num}",
                    reply_to_message_id=user_msg.id
                )
                print(f"✅ ارسال شد. ID: {sent.id}")
            except Exception as e:
                print(f"❌ خطا در ارسال: {e}")
                await message.reply_text(f"❌ خطا: {e}")
                break

            # ⭐️ اینجا منتظر می‌مونه تا بات جواب بده و دکمه ✅ رو بزنه
            await wait_for_bot_and_confirm(client, message.chat.id, sent.id)
            
            await asyncio.sleep(DELAY_BETWEEN_GIFTS)

        # ⭐️ آپدیت کردن پیام مرجع برای گرفتن دکمه‌های جدید (تغییر از ۴ به ۲)
        try:
            current_msg = await client.get_messages(current_msg.chat.id, current_msg.id)
            print("🔄 پیام مرجع آپدیت شد (دکمه‌های جدید بررسی می‌شن).")
        except Exception as e:
            print(f"❌ خطا در آپدیت پیام مرجع: {e}")
            break

        # پیدا کردن دکمه صفحه بعد (➡️) روی پیام مرجعِ آپدیت شده
        next_found = False
        if current_msg.reply_markup and current_msg.reply_markup.inline_keyboard:
            for row in current_msg.reply_markup.inline_keyboard:
                for btn in row:
                    if "➡" in btn.text or "Next" in btn.text or "▶" in btn.text:
                        print(f"➡️ دکمه بعدی پیدا شد: {btn.text}")
                        try:
                            await client.request_callback_answer(current_msg.chat.id, current_msg.id, btn.callback_data)
                            next_found = True
                            print("✅ دکمه صفحه بعد کلیک شد.")
                        except Exception as e:
                            print(f"❌ خطا در کلیک دکمه: {e}")
                        break
                if next_found: 
                    break

        if not next_found:
            print("🏁 پایان. دکمه بعدی نیست.")
            await message.reply_text("🏁 پایان. دکمه بعدی نیست.")
            break

        await asyncio.sleep(DELAY_AFTER_PAGE)
        page += 1

print("🚀 سلف آماده است.")
app.run()
