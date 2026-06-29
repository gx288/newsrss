import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "Filtered_Samples_Raw"
SERVICE_ACCOUNT_FILE = 'khoahoctv/credentials.json'

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

def process_file(filename, limit=10):
    if not os.path.exists(filename):
        return []
    
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    rows = []
    for item in data[:limit]:
        desc = item.get('content', '')
        if len(desc) > 49000:
            desc = desc[:49000] + "\n...[TRUNCATED]"
            
        rows.append([
            item.get('title', ''),
            item.get('crawled_at', ''),
            item.get('url', ''),
            item.get('image', ''),
            "0",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            "NEW",
            "",
            "",
            desc
        ])
    return rows

def main():
    print("=== ĐẨY DỮ LIỆU TEST LÊN GOOGLE SHEETS ===")
    sheet = init_gsheet()
    if not sheet: return
    
    rows_to_push = []
    print("[*] Lấy 10 bài MNT...")
    rows_to_push.extend(process_file("mnt_filtered_samples.json", 10))
    print("[*] Lấy 10 bài Healthline...")
    rows_to_push.extend(process_file("healthline_filtered_samples.json", 10))
    
    if rows_to_push:
        print(f"[*] Tổng cộng {len(rows_to_push)} bài. Đang đẩy lên Google Sheet '{SHEET_NAME}'...")
        sheet.append_rows(rows_to_push, value_input_option="USER_ENTERED")
        print("✅ Thành công!")
    else:
        print("Không có dữ liệu.")

if __name__ == "__main__":
    main()
