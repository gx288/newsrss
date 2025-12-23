# scrape_posts.py
import json
import os
from datetime import datetime
import logging
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
from facebook_page_scraper import Facebook_scraper

# ===================== CONFIG =====================
PAGE_NAME = "ptthady"
SPREADSHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "BS Thu Hà"

# Tạo thư mục log
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

today = datetime.now().strftime("%Y-%m-%d")
log_file = LOG_DIR / f"{today}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===================================================

def get_google_sheet_client():
    """Lấy client Google Sheets từ secret"""
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        logger.error("Không tìm thấy biến môi trường GOOGLE_SHEETS_CREDENTIALS")
        raise ValueError("Thiếu GOOGLE_SHEETS_CREDENTIALS")

    try:
        creds_dict = json.loads(creds_json)
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Lỗi xác thực Google Sheets: {e}")
        raise


def main():
    logger.info("=== Bắt đầu thu thập bài viết trang Facebook ===")
    logger.info(f"Trang: {PAGE_NAME}")
    logger.info(f"Sheet: {SHEET_NAME} (spreadsheet ID: {SPREADSHEET_ID})")

    # 1. Kết nối Google Sheets
    try:
        client = get_google_sheet_client()
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        logger.error(f"Không thể mở spreadsheet: {e}")
        return

    # 2. Lấy hoặc tạo sheet
    try:
        sheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        logger.info(f"Tạo sheet mới: {SHEET_NAME}")
        sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=6)
        sheet.append_row([
            "Post URL",
            "Nội dung",
            "Link ảnh",
            "Thời gian đăng",
            "Ngày thu thập",
            "Ghi chú"
        ])
        logger.info("Đã tạo sheet và header thành công")

    # 3. Lấy danh sách link đã có (cột A)
    try:
        existing_data = sheet.get_all_values()
        existing_urls = {row[0].strip() for row in existing_data[1:] if row and row[0].strip()}
        logger.info(f"Đã tìm thấy {len(existing_urls)} bài viết cũ trong sheet")
    except Exception as e:
        logger.error(f"Lỗi khi đọc dữ liệu sheet: {e}")
        return

    # 4. Thu thập bài viết mới
    new_posts = []
    try:
        scraper = Facebook_scraper(
            page_or_group_name=PAGE_NAME,
            browser="chrome",
            headless=True,
            timeout=120  # Tăng thời gian chờ để scrape nhiều bài hơn
        )

        logger.info(f"Đang scrape page: {PAGE_NAME}")
        posts = scraper.scrap_to_json()  # Không truyền posts_count (API hiện tại)

        if not posts:
            logger.warning("Không tìm thấy bài viết nào (có thể bị chặn hoặc page không có bài mới)")

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

    # 5. Ghi bài mới vào sheet
    if new_posts:
        try:
            sheet.append_rows(new_posts)
            logger.info(f"ĐÃ THÊM THÀNH CÔNG {len(new_posts)} bài viết mới vào sheet")
        except Exception as e:
            logger.error(f"Lỗi khi ghi vào sheet: {e}")
    else:
        logger.info("Không tìm thấy bài viết mới nào")

    logger.info("=== Kết thúc thu thập ===")


if __name__ == "__main__":
    main()
