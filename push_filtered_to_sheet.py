import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "MNT_HL_Filtered"
SERVICE_ACCOUNT_FILE = 'khoahoctv/credentials.json'
JSON_INPUT = 'mnt_hl_filtered.json'
CHUNK_SIZE = 100 # Cực kỳ an toàn để không dính lỗi 413 Payload Too Large của Google API

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
    print("=== ĐẨY DỮ LIỆU ĐÃ LỌC LÊN GOOGLE SHEETS ===")
    
    if not os.path.exists(JSON_INPUT):
        print(f"❌ Không tìm thấy file {JSON_INPUT}")
        return
        
    with open(JSON_INPUT, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"[*] Đọc thành công {len(data)} bài từ file JSON cục bộ.")
    
    sheet = init_gsheet()
    if not sheet: return
    
    print("[*] Đang tải danh sách bài đã có trên Sheet để tránh trùng lặp...")
    existing_links = set(sheet.col_values(3)[1:])  # Cột 3 là Link
    print(f"   => Trên Sheet đang có {len(existing_links)} bài.")
    
    rows_to_push = []
    for item in data:
        link = item.get('url', item.get('link', ''))
        if link and link not in existing_links:
            desc = item.get('content', '')
            if len(desc) > 30000:
                desc = desc[:30000] + "\n...[TRUNCATED]"
                
            rows_to_push.append([
                item.get('title', ''),
                item.get('crawled_at', item.get('pubdate', '')),
                link,
                item.get('image', ''),
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
    
    # Chia nhỏ dữ liệu thành các lô để đẩy lên (tránh lỗi quá tải của Google Sheets API)
    total_pushed = 0
    for i in range(0, len(rows_to_push), CHUNK_SIZE):
        chunk = rows_to_push[i:i+CHUNK_SIZE]
        try:
            sheet.append_rows(chunk, value_input_option="USER_ENTERED")
            total_pushed += len(chunk)
            print(f"✅ Đã đẩy lô {i//CHUNK_SIZE + 1}: {total_pushed}/{len(rows_to_push)} bài...")
            time.sleep(2) # Nghỉ 2 giây để tránh bị Rate Limit
        except Exception as e:
            print(f"❌ Lỗi khi đẩy lô {i//CHUNK_SIZE + 1}: {e}")
            
    print(f"🎉 Hoàn tất! Đã đẩy thành công {total_pushed} bài lên Sheet '{SHEET_NAME}'.")

if __name__ == "__main__":
    main()
