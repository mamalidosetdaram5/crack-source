import requests
import os
import shutil
import time

def upload_to_catbox(file_path):
    """
    فایل مورد نظر را در Catbox آپلود کرده و لینک مستقیم آن را برمی‌گرداند.
    """
    url = 'https://catbox.moe/user/api.php'
    data = {'reqtype': 'fileupload'}
    
    try:
        with open(file_path, 'rb') as f:
            files = {'fileToUpload': f}
            response = requests.post(url, data=data, files=files)
            
        if response.status_code == 200:
            return response.text.strip()
        else:
            return f"خطا در آپلود. کد وضعیت: {response.status_code}\nپیام: {response.text}"
    except Exception as e:
        return f"خطای غیرمنتظره: {str(e)}"

def create_zip_from_folder(folder_path):
    """
    یک پوشه را به فایل ZIP تبدیل می‌کند.
    """
    # گرفتن اسم پوشه و اضافه کردن timestamp برای جلوگیری از تداخل اسم‌ها
    folder_name = os.path.basename(os.path.abspath(folder_path))
    timestamp = int(time.time())
    zip_base_name = f"{folder_name}_{timestamp}"
    
    # ساخت فایل زیپ
    zip_file_path = shutil.make_archive(zip_base_name, 'zip', folder_path)
    return zip_file_path

if __name__ == "__main__":
    path_input = input("لطفاً مسیر فایل یا پوشه را وارد کنید: ").strip()
    path_input = path_input.strip('"').strip("'")
    
    if not os.path.exists(path_input):
        print("❌ خطا: مسیر وارد شده در سیستم وجود ندارد.")
    else:
        file_to_upload = path_input
        is_temp_zip = False
        
        # بررسی اینکه آیا مسیر وارد شده پوشه است یا فایل
        if os.path.isdir(path_input):
            print(f"\n📁 مسیر وارد شده یک پوشه است. در حال فشرده‌سازی (Zip)...")
            file_to_upload = create_zip_from_folder(path_input)
            is_temp_zip = True
            print(f"✅ پوشه با موفقیت فشرده شد: {os.path.basename(file_to_upload)}")
        
        print(f"\n🚀 در حال آپلود: {os.path.basename(file_to_upload)} ...")
        
        try:
            result = upload_to_catbox(file_to_upload)
            
            print("-" * 40)
            if result.startswith("http"):
                print("✅ آپلود با موفقیت انجام شد!")
                print(f"🔗 لینک مستقیم:\n{result}")
            else:
                print(f"❌ {result}")
        finally:
            # پاک کردن فایل زیپ موقت از روی سیستم بعد از اتمام کار (چه موفق چه ناموفق)
            if is_temp_zip and os.path.exists(file_to_upload):
                os.remove(file_to_upload)
                print("\n🧹 فایل زیپ موقت از روی سیستم شما پاک شد.")
