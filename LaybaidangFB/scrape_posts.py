# scrape_posts.py
import json
import os
from datetime import datetime
import logging
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
from facebook_scraper import get_posts, exceptions

# CONFIG
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

    client = get_google_sheet_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        sheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=6)
        sheet.append_row(["Post URL", "Nội dung", "Link ảnh", "Thời gian đăng", "Ngày thu thập", "Ghi chú"])
        logger.info("Đã tạo sheet mới và header")

    existing_data = sheet.get_all_values()
    existing_urls = {row[0].strip() for row in existing_data[1:] if row and row[0].strip()}
    logger.info(f"Đã tìm thấy {len(existing_urls)} bài cũ")

    new_posts = []
    try:
        # Lấy 30 trang (khoảng 30-90 bài tùy page)
        for post in get_posts(
            account=PAGE_NAME,
            pages=30,
            options={
                "comments": False,
                "reactors": False,
                "allow_extra_requests": True,
                "timeout": 60,
                "progress": False
            }
        ):
            post_url = post.get("post_url", "").strip()
            if not post_url or post_url in existing_urls:
                continue

            content = post.get("text", "").replace("\n", " ").strip()[:2000]
            image = post.get("image") or (post.get("images") or [""])[0]
            time_obj = post.get("time")
            time_str = time_obj.strftime("%Y-%m-%d %H:%M:%S") if time_obj else str(time_obj or "")

            new_posts.append([
                post_url,
                content,
                image,
                time_str,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Mới"
            ])
            existing_urls.add(post_url)  # Tránh trùng trong run này
            logger.info(f"Tìm thấy bài mới: {post_url}")

    except exceptions.TemporarilyBanned as e:
        logger.error(f"Bị Facebook chặn tạm thời: {e}")
    except Exception as e:
        logger.error(f"Lỗi khi scrape: {e}", exc_info=True)

    if new_posts:
        sheet.append_rows(new_posts)
        logger.info(f"Đã thêm {len(new_posts)} bài viết mới")
    else:
        logger.info("Không tìm thấy bài mới")

    logger.info("=== Kết thúc ===")

if __name__ == "__main__":
    main()
