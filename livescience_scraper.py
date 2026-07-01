import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
import time
import json
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==================== CONFIG ====================
SITEMAP_INDEX = "https://www.livescience.com/sitemap.xml"
SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "LiveScience_Raw"
SERVICE_ACCOUNT_FILE = 'khoahoctv/credentials.json'

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==================== GOOGLE SHEETS ====================
def init_gsheet():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        env_creds = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
        if env_creds:
            os.makedirs(os.path.dirname(SERVICE_ACCOUNT_FILE), exist_ok=True)
            with open(SERVICE_ACCOUNT_FILE, 'w', encoding='utf-8') as f:
                f.write(env_creds)
        else:
            print("❌ Không tìm thấy credentials.json hoặc GOOGLE_SHEETS_CREDENTIALS")
            return None

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scope)
        client = gspread.authorize(creds)
        
        try:
            sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            print(f"[*] Tạo mới Sheet '{SHEET_NAME}'...")
            sheet = client.open_by_key(SHEET_ID).add_worksheet(title=SHEET_NAME, rows=1000, cols=10)
            sheet.append_row(["Title", "Date", "Link", "Image", "Views", "Crawl_Date", "Status", "TranslatedTitle", "TranslatedContent", "FullTextEn"])
        
        return sheet
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheets: {e}")
        return None

# ==================== SITEMAP SCRAPER ====================
def get_recent_sitemaps():
    print("[*] Đang tải sitemap index...")
    try:
        r = requests.get(SITEMAP_INDEX, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'xml')
        sitemaps = [loc.text for loc in soup.find_all('loc') if re.search(r'sitemap-\d{4}-\d{2}\.xml', loc.text)]
        # Sort sitemaps to get newest first (e.g. sitemap-2024-05.xml)
        sitemaps.sort(reverse=True)
        # Quét tất cả các tháng trong lịch sử thay vì chỉ 3 tháng
        return sitemaps
    except Exception as e:
        print(f"❌ Lỗi tải sitemap index: {e}")
        return []

def get_health_links(sitemap_url):
    print(f"[*] Quét sitemap: {sitemap_url}")
    try:
        r = requests.get(sitemap_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'xml')
        # Lấy các link chứa /health/
        links = [loc.text for loc in soup.find_all('loc') if '/health/' in loc.text]
        print(f"   => Tìm thấy {len(links)} bài health.")
        return links
    except Exception as e:
        print(f"❌ Lỗi quét {sitemap_url}: {e}")
        return []

def scrape_article(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        
        title = soup.find('h1')
        title = title.text.strip() if title else ""
        
        # Lấy toàn bộ nội dung bài viết
        body = soup.find('div', id='article-body')
        if body:
            # Lọc bỏ các đoạn script, style không cần thiết
            for tag in body(['script', 'style']):
                tag.decompose()
            desc = body.get_text(separator='\n', strip=True)
        else:
            # Fallback nếu không có article-body
            desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', property='og:description')
            desc = desc['content'].strip() if desc else ""
        
        img = soup.find('meta', property='og:image')
        img = img['content'] if img else ""
        
        pubdate = soup.find('meta', property='article:published_time')
        pubdate = pubdate['content'] if pubdate else datetime.now().isoformat()
        
        if not title:
            return None
            
        return {
            "title": title,
            "link": url,
            "description": desc,
            "image": img,
            "pubdate": pubdate
        }
    except Exception as e:
        print(f"   [!] Lỗi cào {url}: {e}")
        return None

# ==================== MAIN ====================
def main():
    print("=== LIVESCIENCE RAW SCRAPER ===")
    sheet = init_gsheet()
    if not sheet:
        return
        
    print("[*] Lấy danh sách bài đã cào từ Google Sheet...")
    existing_links = set(sheet.col_values(2)[1:]) # Cột 2 là Link
    print(f"   => Đã có {len(existing_links)} bài trong Sheet.")
    
    sitemaps = get_recent_sitemaps()
    all_health_links = []
    for sm in sitemaps:
        all_health_links.extend(get_health_links(sm))
        time.sleep(1)
        
    # Lọc bài chưa cào
    new_links = [l for l in all_health_links if l not in existing_links]
    print(f"[*] Tìm thấy {len(new_links)} bài MỚI hoàn toàn.")
    
    # Cào thử 200 bài để không quá tải (có thể tăng lên)
    limit = 200
    links_to_scrape = new_links[:limit]
    
    new_rows = []
    for i, link in enumerate(links_to_scrape, 1):
        print(f"[{i}/{len(links_to_scrape)}] Cào: {link}")
        data = scrape_article(link)
        if data:
            desc = data['description']
            if len(desc) > 30000:
                desc = desc[:30000] + "\n...[TRUNCATED]"
                
            new_rows.append([
                data['title'],
                data['pubdate'],      # Date
                data['link'],
                data['image'],
                "0",                  # Views (không có trên LiveScience, để mặc định 0)
                datetime.now().strftime("%Y-%m-%d %H:%M"), # Crawl_Date
                "NEW",                # Status
                "",                   # TranslatedTitle
                "",                   # TranslatedContent
                desc   # FullTextEn
            ])
        time.sleep(0.5)
        
    if new_rows:
        print(f"[*] Đang đẩy {len(new_rows)} bài lên Google Sheet...")
        sheet.append_rows(new_rows)
        print("✅ Hoàn tất!")
    else:
        print("[-] Không có bài mới nào được cào.")

if __name__ == "__main__":
    main()
