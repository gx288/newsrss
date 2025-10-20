import feedparser
import os
import json
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from bs4 import BeautifulSoup
import re

# Cấu hình
RSS_FEED_URL = "https://cdn.24h.com.vn/upload/rss/suckhoedoisong.rss"
SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = os.getenv("SHEET_NAME", "Sheet1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

# Danh sách model ưu tiên
MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-1.0-pro"]

# Cấu hình Google Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Biến theo dõi tổng quát
processed_count = 0
skipped_count = 0
error_count = 0
ad_count = 0  # Đếm số bài quảng cáo bị bỏ qua

# Cấu hình Google Sheets
def get_gspread_client():
    print("Bắt đầu cấu hình Google Sheets client...")
    creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    print("Hoàn tất cấu hình Google Sheets client.")
    return client

def get_existing_links():
    """Lấy danh sách link đã lưu trong Google Sheet"""
    print("Bắt đầu lấy danh sách link đã xử lý từ Google Sheet...")
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        links = sheet.col_values(3)[1:]  # Bỏ header
        print(f"Đã lấy {len(links)} link từ Google Sheet.")
        return set(links)  # Chuyển thành set để kiểm tra nhanh
    except Exception as e:
        print(f"Lỗi khi lấy link từ Sheet: {str(e)}")
        return set()

def get_rss_feed():
    print("Bắt đầu lấy dữ liệu từ RSS feed...")
    feed = feedparser.parse(RSS_FEED_URL)
    if not feed.entries:
        print("Không tìm thấy bài viết nào trong RSS feed.")
        return []
    existing_links = get_existing_links()
    articles = []
    for i, entry in enumerate(feed.entries, 1):
        print(f"Đang kiểm tra bài {i}: {entry.title}")
        link = entry.link
        if link in existing_links:
            print(f"Bỏ qua bài đã xử lý: {entry.title}")
            global skipped_count
            skipped_count += 1
            continue
        title = entry.title
        description = entry.description
        pubdate = entry.get('published', entry.get('updated', ''))
        image_url = None
        soup = BeautifulSoup(description, 'html.parser')
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            image_url = img_tag['src']
        articles.append({"title": title, "description": description, "link": link, "image_url": image_url, "pubdate": pubdate})
        print(f"Đã thêm bài {len(articles)}: {title} vào danh sách xử lý.")
    print(f"Hoàn tất lấy RSS feed: {len(articles)} bài mới sẽ được xử lý.")
    return articles

def is_advertisement(title, description):
    """Kiểm tra xem bài viết có phải là quảng cáo không"""
    ad_keywords = [
        r'\b(sản phẩm|thương hiệu|sản phẩm|quảng cáo|khuyến mãi|giảm giá|ưu đãi|mua ngay|đặt hàng)\b',
        r'\b(giới thiệu|sử dụng|chất lượng cao|uy tín|hiệu quả nhất)\b.*(thương hiệu|sản phẩm)',
        r'\b(độc quyền|chỉ có tại|liên hệ ngay)\b'
    ]
    content = (title + " " + description).lower()
    for pattern in ad_keywords:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False

def get_gemini_model():
    """Thử các model theo thứ tự ưu tiên"""
    for model_name in MODEL_PRIORITY:
        try:
            print(f"Thử sử dụng model: {model_name}")
            model = genai.GenerativeModel(model_name)
            # Thử một yêu cầu nhỏ để kiểm tra quota
            model.generate_content("Test")
            print(f"Sử dụng model: {model_name}")
            return model
        except Exception as e:
            print(f"Model {model_name} không khả dụng: {str(e)}")
    raise Exception("Không có model nào khả dụng")

def rewrite_content(title, description):
    print(f"Bắt đầu tóm tắt bài: {title}")
    if is_advertisement(title, description):
        print(f"Bỏ qua bài '{title}' vì có dấu hiệu quảng cáo.")
        global ad_count
        ad_count += 1
        return None, None
    prompt = f"{PROMPT}\nTiêu đề: {title}\nMô tả: {description}"
    try:
        model = get_gemini_model()
        response = model.generate_content(prompt)
        content = response.text.strip()
        # Xử lý để đảm bảo định dạng đúng
        parts = content.split("👇👇👇")
        if len(parts) < 2:
            print(f"Định dạng phản hồi từ Gemini không hợp lệ cho bài: {title}")
            return None, None
        summary_title = parts[0].strip()
        summary_content = parts[1].strip()
        # Xóa "TIÊU ĐỀ: " nếu có
        summary_title = re.sub(r'^TIÊU ĐỀ:\s*', '', summary_title, flags=re.IGNORECASE)
        # Xóa dấu ** trong nội dung
        summary_title = summary_title.replace("**", "")
        summary_content = summary_content.replace("**", "")
        print(f"Hoàn tất tóm tắt bài: {title}")
        return summary_title, summary_content
    except Exception as e:
        print(f"Lỗi khi tóm tắt bài {title}: {str(e)}")
        return None, None

def append_to_gsheet(title, summary_title, summary_content, link, image_url, pubdate):
    print(f"Bắt đầu ghi bài '{title}' vào Google Sheet...")
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    row = [title, summary_title + "\n👇👇👇\n" + summary_content, link, image_url, pubdate]
    sheet.append_row(row)
    print(f"Hoàn tất ghi bài '{title}' vào Google Sheet.")
    global processed_count
    processed_count += 1

def main():
    print("=== BẮT ĐẦU CHẠY SCRIPT ===")
    articles = get_rss_feed()
    if not articles:
        print("Không có bài mới để xử lý.")
        return
    for i, article in enumerate(articles, 1):
        print(f"\nXử lý bài {i}/{len(articles)}: {article['title']}")
        summary_title, summary_content = rewrite_content(article["title"], article["description"])
        if not summary_title or not summary_content:
            print(f"Bỏ qua bài '{article['title']}' do lỗi tóm tắt hoặc quảng cáo.")
            global error_count
            error_count += 1
            continue
        append_to_gsheet(article["title"], summary_title, summary_content, article["link"], article["image_url"], article["pubdate"])
    print("\n=== TỔNG QUÁT ===")
    print(f"Tổng số bài xử lý thành công: {processed_count}")
    print(f"Tổng số bài bỏ qua do trùng: {skipped_count}")
    print(f"Tổng số bài bỏ qua do quảng cáo: {ad_count}")
    print(f"Tổng số bài lỗi (tóm tắt thất bại): {error_count}")
    print("=== KẾT THÚC SCRIPT ===")

if __name__ == "__main__":
    main()
