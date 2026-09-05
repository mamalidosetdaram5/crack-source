from pyrogram import Client, filters
import re
import asyncio

api_id = 12345678
api_hash = "your_api_hash_here"

app = Client("my_autogift_session", api_id=api_id, api_hash=api_hash)

DELAY_BETWEEN_GIFTS = 3
DELAY_AFTER_PAGE = 2

def extract_numbers(text):
    if not text:
        return []
    return re.findall(r'\[(\d+)\]', text)

async def click_confirm(client, chat_id, reply_msg_id):
    await asyncio.sleep(1.5)
    try:
        async for msg in app.get_chat_history(chat_id, limit=15):
            if msg.reply_to_message and msg.reply_to_message.id == reply_msg_id:
                if msg.reply_markup and msg.reply_markup.inline_keyboard:
                    for row in msg.reply_markup.inline_keyboard:
                        for btn in row:
                            if "✅" in btn.text:
                                await client.request_callback_answer(chat_id, msg.id, btn.callback_data)
                                return True
                if msg.text and "✅" in msg.text:
                    return True
                break
    except Exception as e:
        print(f"خطا در تایید: {e}")
    return False

@app.on_message(filters.command("start_gift", prefixes="!"))
async def auto_gift(client, message):
    if not message.reply_to_message:
        await message.reply_text("روی پیام لیست ریپلای کن.")
        return

    if len(message.command) < 2:
        await message.reply_text("آیدی شخص رو بنویس. مثال: !start_gift @user")
        return

    target_msg = message.reply_to_message
    target_user = message.command[1]

    await message.reply_text("در حال جستجو...")
    print("شروع جستجو...")

    user_msg = None
    async for msg in client.get_chat_history(message.chat.id, limit=200):
        if msg.from_user:
            uname = msg.from_user.username
            if uname and uname.lower() == target_user.strip("@").lower():
                user_msg = msg
                break
            if str(msg.from_user.id) == target_user.strip("@"):
                user_msg = msg
                break

    if not user_msg:
        await message.reply_text("پیام شخص پیدا نشد.")
        return

    await message.reply_text("شخص پیدا شد. شروع گیفت...")
    print("شخص پیدا شد.")

    current_msg = target_msg
    page = 1

    while True:
        print(f"\nصفحه {page}")

        if not current_msg.text:
            print("پیام متن ندارد.")
            break

        numbers = extract_numbers(current_msg.text)
        print(f"اعداد: {numbers}")

        if not numbers:
            await message.reply_text(f"صفحه {page} عددی نداشت.")
            break

        for num in numbers:
            print(f"ارسال /gift {num}")
            try:
                sent = await user_msg.reply_text(f"/gift {num}")
                print(f"ارسال شد: {sent.id}")
            except Exception as e:
                print(f"خطا: {e}")
                await message.reply_text(f"خطا: {e}")
                break

            await click_confirm(client, message.chat.id, sent.id)
            await asyncio.sleep(DELAY_BETWEEN_GIFTS)

        next_found = False
        if current_msg.reply_markup and current_msg.reply_markup.inline_keyboard:
            for row in current_msg.reply_markup.inline_keyboard:
                for btn in row:
                    if "➡" in btn.text:
                        print(f"دکمه بعد: {btn.text}")
                        try:
                            await client.request_callback_answer(
                                current_msg.chat.id,
                                current_msg.id,
                                btn.callback_data
                            )
                            next_found = True
                        except Exception as e:
                            print(f"خطا دکمه: {e}")
                        break
                if next_found:
                    break

        if not next_found:
            print("دکمه بعدی نیست. پایان.")
            await message.reply_text("پایان. دکمه بعدی نیست.")
            break

        await asyncio.sleep(DELAY_AFTER_PAGE)

        try:
            current_msg = await client.get_messages(
                current_msg.chat.id, current_msg.id
            )
        except Exception as e:
            print(f"خطا آپدیت: {e}")
            break

        page += 1

print("سلف آماده است.")
app.run()
