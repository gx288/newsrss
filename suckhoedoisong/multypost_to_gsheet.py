import feedparser
import os
import json
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from bs4 import BeautifulSoup
import re

# Cấu hình
SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
RSS_SHEET_NAME = "RSS"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

# Danh sách model theo thứ tự ưu tiên
MODEL_PRIORITY = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-1.0-pro"]

# Prompt cho Google Gemini
PROMPT = """
Tóm tắt thành vài đoạn văn ngắn (không dùng các đoạn tóm tắt ngắn ở đầu đoạn văn), có emoji (khác nhau) phù hợp với nội dung của đoạn đặt ở đầu dòng và hashtag ở cuối cùng của bài viết. Khoảng 500-1000 kí tự phù hợp với Facebook. Hãy viết thành đoạn văn trôi chảy, không dùng "tiêu đề ngắn". Hãy đặt tất cả hashtag ở cuối bài viết, không đặt ở cuối mỗi đoạn. Thêm hashtag #dongysonha. Viết theo quy tắc 4C, đầy đủ ý, nội dung phù hợp với tiêu đề, giải quyết được tình trạng, câu hỏi trong tiêu đề, làm thỏa mãn người đọc, trung thực, không dùng đại từ nhân xưng. Kết quả trả về có 1 phần tiêu đề được VIẾT IN HOA TẤT CẢ và "👇👇👇" cuối tiêu đề.
"""

# Cấu hình Google Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Biến theo dõi tổng quát
processed_count = 0
skipped_count = 0
error_count = 0

# Cấu hình Google Sheets
def get_gspread_client():
    print("Bắt đầu cấu hình Google Sheets client...")
    creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    print("Hoàn tất cấu hình Google Sheets client.")
    return client

def get_rss_feeds():
    """Lấy danh sách RSS feed và tên trang tính từ sheet RSS"""
    print("Bắt đầu lấy danh sách RSS feed từ Google Sheet...")
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(RSS_SHEET_NAME)
        data = sheet.get_all_values()
        if len(data) < 2:
            print("Không tìm thấy dữ liệu RSS feed trong sheet RSS.")
            return []
        feeds = []
        for row in data[1:]:  # Bỏ header
            rss_url = row[0].strip()
            sheet_name = row[1].strip() if len(row) > 1 else ""
            if rss_url and sheet_name:
                feeds.append({"rss_url": rss_url, "sheet_name": sheet_name})
                print(f"Đã thêm RSS: {rss_url} với trang tính: {sheet_name}")
        print(f"Tổng cộng {len(feeds)} RSS feed được tìm thấy.")
        return feeds
    except Exception as e:
        print(f"Lỗi khi lấy danh sách RSS feed: {str(e)}")
        return []

def get_existing_links(sheet_name):
    """Lấy danh sách link đã lưu trong Google Sheet"""
    print(f"Bắt đầu lấy danh sách link đã xử lý từ trang tính {sheet_name}...")
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        links = sheet.col_values(3)[1:]  # Bỏ header
        print(f"Đã lấy {len(links)} link từ trang tính {sheet_name}.")
        return set(links)
    except Exception as e:
        print(f"Lỗi khi lấy link từ trang tính {sheet_name}: {str(e)}")
        return set()

def get_rss_feed(rss_url, sheet_name):
    print(f"Bắt đầu lấy dữ liệu từ RSS feed: {rss_url}...")
    feed = feedparser.parse(rss_url)
    if not feed.entries:
        print(f"Không tìm thấy bài viết nào trong RSS feed {rss_url}.")
        return []
    existing_links = get_existing_links(sheet_name)
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
        # Lấy ngày đăng
        pubdate = entry.get('pubDate', entry.get('published', entry.get('updated', '')))
        # Lấy URL hình ảnh
        image_url = None
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enclosure in entry.enclosures:
                if enclosure.get('type', '').startswith('image/'):
                    image_url = enclosure.get('url')
                    break
        if not image_url:
            soup = BeautifulSoup(description, 'html.parser')
            img_tag = soup.find('img')
            if img_tag and img_tag.get('src'):
                image_url = img_tag['src']
        articles.append({
            "title": title,
            "description": description,
            "link": link,
            "image_url": image_url,
            "pubdate": pubdate
        })
        print(f"Đã thêm bài {len(articles)}: {title} vào danh sách xử lý.")
    print(f"Hoàn tất lấy RSS feed {rss_url}: {len(articles)} bài mới sẽ được xử lý.")
    return articles

def rewrite_content(title, description):
    print(f"Bắt đầu tóm tắt bài: {title}")
    prompt = f"{PROMPT}\nTiêu đề: {title}\nMô tả: {description}"
    for model_name in MODEL_PRIORITY:
        print(f"Thử tóm tắt với model: {model_name}")
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            content = response.text.strip()
            parts = content.split("👇👇👇")
            if len(parts) < 2:
                print(f"Định dạng phản hồi từ {model_name} không hợp lệ cho bài: {title}")
                return None, None
            summary_title = parts[0].strip()
            summary_content = parts[1].strip()
            print(f"Hoàn tất tóm tắt bài: {title} với model {model_name}")
            return summary_title, summary_content
        except Exception as e:
            if "429" in str(e) and "Quota exceeded" in str(e):
                print(f"Quota exceeded for model {model_name}, bài '{title}'. Chuyển sang model tiếp theo...")
                continue
            else:
                print(f"Lỗi khi tóm tắt bài {title} với model {model_name}: {str(e)}")
                continue
    print(f"Hết model khả dụng cho bài '{title}'. Kiểm tra danh sách model tại https://ai.google.dev/gemini-api/docs/models")
    return None, None

def append_to_gsheet(title, summary_title, summary_content, link, image_url, pubdate, sheet_name):
    print(f"Bắt đầu ghi bài '{title}' vào trang tính {sheet_name}...")
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        row = [title, summary_title + "\n👇👇👇\n" + summary_content, link, image_url, pubdate]
        sheet.append_row(row)
        print(f"Hoàn tất ghi bài '{title}' vào trang tính {sheet_name}.")
        global processed_count
        processed_count += 1
    except Exception as e:
        print(f"Lỗi khi ghi bài '{title}' vào trang tính {sheet_name}: {str(e)}")
        global error_count
        error_count += 1

def main():
    print("=== BẮT ĐẦU CHẠY SCRIPT ===")
    feeds = get_rss_feeds()
    if not feeds:
        print("Không có RSS feed để xử lý.")
        return
    for feed in feeds:
        rss_url = feed["rss_url"]
        sheet_name = feed["sheet_name"]
        print(f"\n=== XỬ LÝ RSS FEED: {rss_url} ===")
        articles = get_rss_feed(rss_url, sheet_name)
        if not articles:
            print(f"Không có bài mới để xử lý từ {rss_url}.")
            continue
        for i, article in enumerate(articles, 1):
            print(f"\nXử lý bài {i}/{len(articles)}: {article['title']}")
            summary_title, summary_content = rewrite_content(article["title"], article["description"])
            if not summary_title or not summary_content:
                print(f"Bỏ qua bài '{article['title']}' do lỗi tóm tắt.")
                global error_count
                error_count += 1
                continue
            append_to_gsheet(
                article["title"], summary_title, summary_content,
                article["link"], article["image_url"], article["pubdate"], sheet_name
            )
    print("\n=== TỔNG QUÁT ===")
    print(f"Tổng số bài xử lý thành công: {processed_count}")
    print(f"Tổng số bài bỏ qua do trùng: {skipped_count}")
    print(f"Tổng số bài lỗi (tóm tắt thất bại): {error_count}")
    print("=== KẾT THÚC SCRIPT ===")

if __name__ == "__main__":
    main()
