import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ==================== CONFIG ====================
JSON_INPUT = "livescience_full_raw.json"
SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "LiveScience_Raw"
SERVICE_ACCOUNT_FILE = 'khoahoctv/credentials.json'

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

def main():
    print("=== ĐẨY DỮ LIỆU JSON LÊN GOOGLE SHEETS ===")
    
    if not os.path.exists(JSON_INPUT):
        print(f"❌ Không tìm thấy file {JSON_INPUT}. Vui lòng chạy mass_scraper.py trước.")
        return
        
    with open(JSON_INPUT, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"[*] Đọc thành công {len(data)} bài từ file JSON cục bộ.")
    
    sheet = init_gsheet()
    if not sheet:
        return
        
    print("[*] Đang tải danh sách bài đã có trên Sheet...")
    existing_links = set(sheet.col_values(3)[1:])  # Cột 3 là Link
    print(f"   => Trên Sheet đang có {len(existing_links)} bài.")
    
    # Chuẩn bị dữ liệu theo format 10 cột
    # ["Title", "Date", "Link", "Image", "Views", "Crawl_Date", "Status", "TranslatedTitle", "TranslatedContent", "FullTextEn"]
    rows_to_push = []
    for item in data:
        if item['link'] not in existing_links:
            desc = item['description']
            if len(desc) > 49000:
                desc = desc[:49000] + "\n...[TRUNCATED]"
                
            rows_to_push.append([
                item['title'],
                item['pubdate'],
                item['link'],
                item['image'],
                "0",
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                "NEW",
                "",
                "",
                desc
            ])
            
    if not rows_to_push:
        print("🎉 Toàn bộ dữ liệu trong JSON đã có mặt trên Sheet. Không cần đẩy thêm.")
        return
        
    print(f"[*] Có {len(rows_to_push)} bài MỚI cần đẩy lên Sheet.")
    print("⏳ Đang đẩy dữ liệu 1 lượt lên Google Sheets (Xin vui lòng chờ khoảng vài chục giây)...")
    
    try:
        # append_rows sẽ gom 1 cục cực lớn đẩy lên chỉ bằng 1 HTTP Request
        sheet.append_rows(rows_to_push, value_input_option="USER_ENTERED")
        print(f"✅ Thành công! Đã tống {len(rows_to_push)} bài lên Google Sheet chỉ trong 1 nốt nhạc.")
    except Exception as e:
        print(f"❌ Lỗi khi đẩy dữ liệu: {e}")

if __name__ == "__main__":
    main()
