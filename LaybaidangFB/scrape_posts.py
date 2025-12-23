# scrape_posts.py
import json
import os
from datetime import datetime
import logging
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
from facebook_page_scraper import Facebook_scraper  # Thư viện mới

# Config
PAGE_NAME = "ptthady"
SPREADSHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "BS Thu Hà"

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
today = datetime.now().strftime("%Y-%m-%d")
log_file = LOG_DIR / f"{today}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def get_google_sheet_client():
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        logger.error("Thiếu GOOGLE_SHEETS_CREDENTIALS")
        raise ValueError("Thiếu GOOGLE_SHEETS_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

def main():
    logger.info("=== Bắt đầu thu thập bài viết trang Facebook ===")
    logger.info(f"Trang: {PAGE_NAME}")

    # Kết nối Google Sheets
    client = get_google_sheet_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        sheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=6)
        sheet.append_row(["Post URL", "Nội dung", "Link ảnh", "Thời gian đăng", "Ngày thu thập", "Ghi chú"])
        logger.info("Đã tạo sheet mới và header")

    # Lấy các URL đã có
    existing_data = sheet.get_all_values()
    existing_urls = {row[0].strip() for row in existing_data[1:] if row and row[0].strip()}
    logger.info(f"Đã tìm thấy {len(existing_urls)} bài cũ")

    # Thu thập bài mới bằng facebook-page-scraper
    scraper = Facebook_scraper(page_or_group_name=PAGE_NAME, browser="chrome", headless=True, timeout=90)
    # Thu thập bài mới bằng facebook-page-scraper
    new_posts = []

    try:
        scraper = Facebook_scraper(
            page_or_group_name=PAGE_NAME,
            browser="chrome",
            headless=True,
            timeout=90,
            take_screenshot=False,
            slow_mode=False
        )
        
        logger.info(f"Đang scrape page: {PAGE_NAME}")
        
        # scrap_to_json() không nhận posts_count nữa, nó sẽ lấy nhiều bài nhất có thể
        posts = scraper.scrap_to_json()  # ← Chỉ gọi như này, không truyền tham số

        for post_id, post_data in posts.items():
            post_url = f"https://www.facebook.com/{post_id}"
            if post_url in existing_urls:
                continue

            content = post_data.get("content", "").replace("\n", " ").strip()[:2000]
            images = post_data.get("images", []) or []
            image = images[0] if images else ""
            time_str = post_data.get("time", "")

            new_posts.append([
                post_url,
                content,
                image,
                time_str,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Mới"
            ])
            logger.info(f"Tìm thấy bài mới: {post_url}")

    except Exception as e:
        logger.error(f"Lỗi khi scrape Facebook: {e}", exc_info=True)

    # Ghi vào sheet
    if new_posts:
        sheet.append_rows(new_posts)
        logger.info(f"Đã thêm {len(new_posts)} bài viết mới")
    else:
        logger.info("Không tìm thấy bài mới")

    logger.info("=== Kết thúc ===")

if __name__ == "__main__":
    main()
