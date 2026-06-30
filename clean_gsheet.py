import os
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "LiveScience_Raw"
SERVICE_ACCOUNT_FILE = 'khoahoctv/credentials.json'

# Các từ khóa cần lọc bỏ (viết thường để dễ so sánh)
BAD_KEYWORDS = ['review', 'covid', 'coronavirus', 'sars-cov-2', 'pandemic']

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
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        return sheet
    except Exception as e:
        print(f"❌ Lỗi kết nối Google Sheets: {e}")
        return None

def is_bad_title(title):
    t = str(title).lower()
    for word in BAD_KEYWORDS:
        if word in t:
            return True
    return False

def main():
    print("=== DỌN DẸP RÁC TRÊN GOOGLE SHEETS ===")
    sheet = init_gsheet()
    if not sheet: return
    
    print("[*] Đang tải toàn bộ dữ liệu từ Sheet...")
    all_data = sheet.get_all_values()
    
    if not all_data:
        print("Sheet trống.")
        return
        
    headers = all_data[0]
    rows = all_data[1:]
    
    print(f"[*] Tìm thấy {len(rows)} bài viết. Bắt đầu quét tiêu đề...")
    
    good_rows = []
    bad_count = 0
    
    for row in rows:
        title = row[0] if len(row) > 0 else ""
        if is_bad_title(title):
            print(f"  -> Xóa: {title}")
            bad_count += 1
        else:
            good_rows.append(row)
            
    print(f"\n[*] Tổng kết: Quét xong. Cần xóa {bad_count} bài rác.")
    
    if bad_count == 0:
        print("🎉 Sheet của bạn đã sạch sẽ, không có bài nào cần xóa!")
        return
        
    print("[*] Đang tiến hành xóa và cập nhật lại Sheet (Xóa 1 phát ăn ngay)...")
    
    # Kỹ thuật xóa siêu tốc: Xóa trắng sheet rồi dán lại các bài tốt
    # Tránh việc gọi API xóa từng dòng sẽ mất hàng tiếng đồng hồ và bị Google chặn
    sheet.clear()
    
    # Ghép header và dữ liệu tốt lại
    final_data = [headers] + good_rows
    
    # Cập nhật lại toàn bộ trong 1 lệnh duy nhất
    sheet.update(range_name='A1', values=final_data, value_input_option='USER_ENTERED')
    
    print(f"✅ Thành công! Đã xóa {bad_count} bài rác. Trên Sheet hiện còn lại {len(good_rows)} bài sạch.")

if __name__ == "__main__":
    main()
