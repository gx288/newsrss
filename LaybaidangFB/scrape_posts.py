import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from facebook_scraper import get_posts
from datetime import datetime
import time

# --- CẤU HÌNH ---
SHEET_ID = '14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo'
PAGE_NAME = 'ptthady' # ID của page từ link bạn đưa
SHEET_TAB_NAME = 'BS Thu Hà'

def connect_google_sheet():
    """Kết nối và trả về worksheet"""
    # Lấy credentials từ biến môi trường
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
    if not creds_json:
        raise ValueError("Không tìm thấy biến môi trường GOOGLE_SHEETS_CREDENTIALS")
    
    creds_dict = json.loads(creds_json)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    sh = client.open_by_key(SHEET_ID)
    
    try:
        worksheet = sh.worksheet(SHEET_TAB_NAME)
    except gspread.exceptions.WorksheetNotFound:
        # Tạo sheet mới nếu chưa có
        worksheet = sh.add_worksheet(title=SHEET_TAB_NAME, rows=1000, cols=10)
        # Tạo header
        worksheet.append_row(['Post URL', 'Time', 'Text', 'Image URL', 'Scraped Date'])
        
    return worksheet

def main():
    print(f"--- Bắt đầu quét page {PAGE_NAME} ---")
    worksheet = connect_google_sheet()
    
    # Lấy danh sách link đã tồn tại để tránh trùng lặp (Cột A)
    existing_links = set(worksheet.col_values(1))
    
    new_rows = []
    
    # pages=3 nghĩa là quét khoảng 3 trang scroll (tầm 10-15 bài gần nhất)
    # Không nên quét quá nhiều một lúc để tránh bị Facebook chặn IP
    try:
        # options={"comments": False} để chạy nhanh hơn
        posts = get_posts(PAGE_NAME, pages=3, options={"comments": False})
        
        for post in posts:
            post_url = post.get('post_url')
            
            # Nếu link này chưa có trong sheet thì mới thêm
            if post_url and post_url not in existing_links:
                # Xử lý dữ liệu
                post_text = post.get('text', '')[:4000] # Cắt bớt nếu quá dài để vừa ô Excel
                post_time = str(post.get('time'))
                post_image = post.get('image')
                scraped_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                print(f"-> Tìm thấy bài mới: {post_url}")
                
                # Sắp xếp thứ tự cột: Link | Time | Text | Image | ScrapedTime
                new_rows.append([
                    post_url,
                    post_time,
                    post_text,
                    post_image,
                    scraped_date
                ])
                # Thêm vào set tạm để tránh trùng lặp ngay trong lần chạy này
                existing_links.add(post_url)
            else:
                pass # Bài đã tồn tại
                
    except Exception as e:
        print(f"Lỗi khi quét Facebook: {e}")

    # Ghi vào sheet (ghi ngược từ dưới lên để bài mới nhất ở dưới cùng theo logic append)
    # Tuy nhiên facebook-scraper thường trả bài mới nhất trước.
    # Nếu muốn bài cũ ở trên, bài mới ở dưới, ta đảo ngược list new_rows
    if new_rows:
        new_rows.reverse() 
        worksheet.append_rows(new_rows)
        print(f"Đã lưu thành công {len(new_rows)} bài viết mới.")
    else:
        print("Không có bài viết mới nào.")

if __name__ == "__main__":
    main()
