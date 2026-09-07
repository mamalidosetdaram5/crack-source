import requests
import os

def upload_to_catbox(file_path):
    """
    فایل مورد نظر را در Catbox آپلود کرده و لینک مستقیم آن را برمی‌گرداند.
    """
    # بررسی وجود فایل
    if not os.path.exists(file_path):
        return "خطا: فایلی با این مسیر وجود ندارد."

    url = 'https://catbox.moe/user/api.php'
    
    # پارامترهای مورد نیاز برای API کت‌باکس
    data = {
        'reqtype': 'fileupload',
    }
    
    try:
        # باز کردن فایل به صورت باینری و ارسال آن
        with open(file_path, 'rb') as f:
            files = {
                'fileToUpload': f
            }
            response = requests.post(url, data=data, files=files)
            
        # بررسی موفقیت آمیز بودن درخواست
        if response.status_code == 200:
            # پاسخ کت‌باکس در صورت موفقیت، فقط لینک مستقیم فایل است
            direct_link = response.text.strip()
            return direct_link
        else:
            return f"خطا در آپلود. کد وضعیت: {response.status_code}\nپیام سرور: {response.text}"
            
    except Exception as e:
        return f"یک خطای غیرمنتظره رخ داد: {str(e)}"

# ================= بخش اجرای کد =================

if __name__ == "__main__":
    # مسیر فایل خودت رو اینجا وارد کن (مثلاً: 'C:/test/my_image.png' یا './my_file.zip')
    file_to_upload = input("لطفاً مسیر کامل فایل را وارد کنید: ").strip()
    
    # حذف کاراکترهای اضافی اگر کاربر مسیر را داخل نقل قول وارد کرده باشد
    file_to_upload = file_to_upload.strip('"').strip("'")
    
    print(f"\nدر حال آپلود فایل: {file_to_upload} ...")
    
    result = upload_to_catbox(file_to_upload)
    
    print("-" * 40)
    if result.startswith("http"):
        print("✅ آپلود با موفقیت انجام شد!")
        print(f"🔗 لینک مستقیم فایل:\n{result}")
    else:
        print(f"❌ {result}")
