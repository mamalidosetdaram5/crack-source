# قابلیت‌های یکپارچهٔ TelegramSelf

این نسخه قابلیت‌های درخواستی را در فایل `lib/self_features.py` پیاده‌سازی می‌کند. وضعیت‌ها در `settings/self_features.json` ذخیره می‌شوند و بعد از خاموش/روشن شدن برنامه باقی می‌مانند.

## راه‌اندازی

1. وابستگی‌ها را نصب کنید: `pip install -r requirements.txt`
2. مقادیر `admin_user_id`، `api_id` و `api_hash` را در `lib/Information.py` تنظیم کنید.
3. برنامه را با `python3 main.py` اجرا کنید.
4. برای مشاهدهٔ راهنمای کوتاه داخل تلگرام، `featurehelp` یا `/featurehelp` را از حساب ادمین بفرستید.

## فرمان‌ها

فرمان‌های `On/Off` نسبت به حروف بزرگ و کوچک حساس نیستند و می‌توانند با یا بدون `/` فرستاده شوند. فرمان‌های معمولی مانند `Self On` روی چت فعلی اثر می‌گذارند و فرمان‌های `Selfall On` روی همهٔ چت‌ها.

| گروه | فرمان‌ها |
|---|---|
| سلف و منشی | `Self On/Off`، `Selfall On/Off`، `Monshi On/Off`، `MonshiOffline On/Off`، `SmartMonshi On/Off` |
| متن منشی | ریپلای روی متن/عکس/گیف/ویس و ارسال `SetMonshi` یا `SetSmartMonshi` |
| زمان آفلاین | `SetMonshiOffline 30` |
| حالت‌ها | `Poker On/Off`، `PokerAll On/Off`، `Typing On/Off`، `TypingAll On/Off` |
| خواندن | `MarkRead`، `MarkReadAll`، `MarkReadGPs`، `MarkReadPvs`، `MarkReadChannels`، `TagRead`، `TagReadAll` |
| پشتیبان | `SetRealm 123456`، `Save On/Off`، `SavePv On/Off` |
| ترجمه | `SetLang en`، `Langs`، `trmode On/Off` |
| استیکر | ریپلای و `SetSticker`، سپس `sticker On/Off`، `GetSticker`، `SetStickerTime 30` |
| متن خودکار | `SetTexter متن` یا ریپلای، `texter On/Off`، `GetTexter`، `SetTexterTime 30` |

برای قابلیت‌های چتی، خاموش‌کردن با `Off` فقط همان چت را تغییر می‌دهد. گزینه‌های `All` وضعیت عمومی را کنترل می‌کنند. برای پشتیبان‌گیری و ترجمه، ابتدا ریلم را با آیدی عددی تنظیم کنید.

## نکات اجرایی

حالت Self از fast replyهای موجود پروژه استفاده می‌کند؛ بنابراین برای پاسخ‌های متنی، از امکانات فعلی `Freplay` و `Lreplay` استفاده کنید. حالت منشی در پیام خصوصی فعال است. در حالت هوشمند، منشی برای هر کاربر فقط اولین پیام را پاسخ می‌دهد. فایل‌های رسانه‌ای منشی در `settings/templates` نگهداری می‌شوند.

این پروژه یک یوزربات است؛ استفادهٔ زیاد از ارسال خودکار، فوروارد و اکشن‌ها ممکن است باعث محدودیت تلگرام شود. فاصلهٔ پیش‌فرض استیکر و متن خودکار ۳۰ دقیقه است تا از ارسال‌های مکرر جلوگیری شود.
