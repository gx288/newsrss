import feedparser
import os
import json
import tempfile
import shutil
from google import genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from bs4 import BeautifulSoup
import gspread.exceptions
from icrawler.builtin import BingImageCrawler

# Cấu hình
SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
RSS_SHEET_NAME = "RSS"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

# Danh sách model ưu tiên (cập nhật cho Gemini hiện tại tháng 12/2025)
MODEL_PRIORITY = [
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-1.0-pro",
]

# Prompt
PROMPT = """
Tóm tắt thành vài đoạn văn ngắn (không dùng các đoạn tóm tắt ngắn ở đầu đoạn văn), có emoji (khác nhau) phù hợp với nội dung của đoạn đặt ở đầu dòng và hashtag ở cuối cùng của bài viết. Khoảng 500-1000 kí tự phù hợp với Facebook. Hãy viết thành đoạn văn trôi chảy, không dùng "tiêu đề ngắn". Hãy đặt tất cả hashtag ở cuối bài viết, không đặt ở cuối mỗi đoạn. Thêm hashtag #dongysonha. Viết theo quy tắc 4C, đầy đủ ý, nội dung phù hợp với tiêu đề, giải quyết được tình trạng, câu hỏi trong tiêu đề, làm thỏa mãn người đọc, trung thực, không dùng đại từ nhân xưng. Kết quả trả về có 1 phần tiêu đề được VIẾT IN HOA TẤT CẢ và "👇👇👇" cuối tiêu đề.
"""

# Tạo client Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# Biến theo dõi
processed_count = 0
skipped_count = 0
error_count = 0

def get_gspread_client():
    print("Bắt đầu cấu hình Google Sheets client...")
    creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    print("Hoàn tất cấu hình Google Sheets client.")
    return client

def get_rss_feeds():
    print("Bắt đầu lấy danh sách RSS feed từ Google Sheet...")
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(RSS_SHEET_NAME)
        data = sheet.get_all_values()
        if len(data) < 2:
            print("Không tìm thấy dữ liệu RSS feed.")
            return []
        feeds = []
        for row in data[1:]:
            rss_url = row[0].strip()
            sheet_name = row[1].strip() if len(row) > 1 else ""
            if rss_url and sheet_name:
                feeds.append({"rss_url": rss_url, "sheet_name": sheet_name})
                print(f"Đã thêm RSS: {rss_url} -> {sheet_name}")
        print(f"Tổng cộng {len(feeds)} RSS feed.")
        return feeds
    except Exception as e:
        print(f"Lỗi khi lấy danh sách RSS feed: {str(e)}")
        return []

def get_existing_links(sheet_name):
    print(f"Bắt đầu lấy danh sách link đã xử lý từ trang tính {sheet_name}...")
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        links = sheet.col_values(3)[1:]  # Cột 3: Link
        print(f"Đã lấy {len(links)} link cũ.")
        return set(links)
    except gspread.exceptions.WorksheetNotFound:
        print(f"Trang tính {sheet_name} chưa tồn tại → coi như chưa có link nào.")
        return set()
    except Exception as e:
        print(f"Lỗi khi lấy link: {str(e)}")
        return set()

def search_image_with_icrawler(query):
    """
    Dùng icrawler để tìm và tải 1 ảnh đầu tiên từ Bing (kích thước medium trở lên).
    Trả về URL của ảnh đầu tiên tìm được.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        crawler = BingImageCrawler(
            downloader_threads=2,
            storage={'root_dir': temp_dir},
            log_level='INFO'  # Có thể đổi thành 'DEBUG' nếu muốn xem chi tiết
        )
        # Filters: size >= medium, chỉ lấy 5 để nhanh, min_size để đảm bảo chất lượng
        filters = dict(size='medium')  # 'large', 'medium', 'small'
        crawler.crawl(
            keyword=query,
            filters=filters,
            max_num=5,  # Chỉ cần vài cái để chọn
            min_size=(400, 400)  # Kích thước tối thiểu
        )
        
        # Tìm file ảnh đầu tiên trong thư mục temp (icrawler lưu theo số)
        downloaded_files = []
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    downloaded_files.append(os.path.join(root, f))
        
        if downloaded_files:
            # Lấy ảnh đầu tiên
            first_image_path = downloaded_files[0]
            print(f"Đã tìm được ảnh fallback từ Bing (icrawler): {first_image_path}")
            return first_image_path  # Trả về path local để upload sau
        else:
            print("icrawler không tải được ảnh nào.")
            return None
    except Exception as e:
        print(f"Lỗi khi dùng icrawler tìm ảnh: {str(e)}")
        return None
    finally:
        # Dọn dẹp temp dir (giữ lại nếu muốn debug)
        shutil.rmtree(temp_dir, ignore_errors=True)

def get_rss_feed(rss_url, sheet_name):
    print(f"Bắt đầu lấy dữ liệu từ RSS feed: {rss_url}...")
    feed = feedparser.parse(rss_url)
    if not feed.entries:
        print(f"Không có entry nào trong RSS {rss_url}.")
        return []
    existing_links = get_existing_links(sheet_name)
    articles = []
    for entry in feed.entries:
        link = entry.link
        if link in existing_links:
            global skipped_count
            skipped_count += 1
            continue
        title = entry.title
        description = entry.description
        pubdate = entry.get('published') or entry.get('pubDate') or entry.get('updated') or ''
        
        image_url = None
        local_image_path = None  # Để lưu path nếu dùng icrawler
        
        # Ưu tiên ảnh từ enclosures
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enc in entry.enclosures:
                if enc.get('type', '').startswith('image/'):
                    image_url = enc.get('url')
                    break
        
        # Nếu không, lấy từ description
        if not image_url:
            soup = BeautifulSoup(description, 'html.parser')
            img_tag = soup.find('img')
            if img_tag and img_tag.get('src'):
                src = img_tag['src']
                if src.startswith('http') and "holder.png" not in src:
                    image_url = src
        
        # Nếu vẫn không có hoặc placeholder → dùng icrawler tìm fallback
        if not image_url or "holder.png" in str(image_url):
            print(f"Không có ảnh hợp lệ từ RSS cho bài: {title}. Đang tìm fallback bằng icrawler...")
            local_image_path = search_image_with_icrawler(title)
            # Nếu tìm được local path, sẽ upload lên đâu đó hoặc để URL = path (nhưng Sheets chấp nhận URL http)
            # Vấn đề: icrawler tải về local, nhưng Sheets cần URL công khai.
            # Giải pháp tạm: Nếu bạn có hosting (Imgur, Cloudinary...), upload lên lấy URL.
            # Ở đây tạm để None nếu không có URL công khai.
            # Hoặc dùng placeholder default.
            if local_image_path:
                print("Tìm được ảnh local nhưng chưa có cách upload → tạm bỏ qua ảnh fallback.")
                # TODO: Thêm upload to Imgur hoặc Google Drive để lấy link công khai nếu cần.
        
        articles.append({
            "title": title,
            "description": description,
            "link": link,
            "image_url": image_url,  # URL từ RSS hoặc None
            "local_image_path": local_image_path,  # Nếu có fallback local
            "pubdate": pubdate
        })
        print(f"Đã thêm bài mới: {title} (ảnh: {'có URL' if image_url else 'không hoặc local'})")
        
        if len(articles) >= 5:
            print(f"Đạt giới hạn 5 bài mới cho RSS {rss_url}.")
            break
    print(f"Hoàn tất: {len(articles)} bài mới sẽ xử lý.")
    return articles

# Các hàm còn lại giữ nguyên (rewrite_content, append_to_gsheet, main)
# ... (copy từ code trước)

def rewrite_content(title, description):
    print(f"Bắt đầu tóm tắt bài: {title}")
    prompt = f"{PROMPT}\nTiêu đề: {title}\nMô tả: {description}"
    for model_name in MODEL_PRIORITY:
        print(f"Thử model: {model_name}")
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            content = response.text.strip()
            parts = content.split("👇👇👇")
            if len(parts) < 2:
                print(f"Định dạng không hợp lệ từ {model_name}. Thử model khác...")
                continue
            summary_title = parts[0].strip()
            summary_content = parts[1].strip()
            print(f"Tóm tắt thành công với {model_name}")
            return summary_title, summary_content
        except Exception as e:
            print(f"Lỗi với {model_name}: {str(e)}")
            continue
    print(f"Hết model khả dụng cho bài '{title}'.")
    return None, None

def append_to_gsheet(title, summary_title, summary_content, link, image_url, pubdate, sheet_name):
    print(f"Bắt đầu ghi bài '{title}' vào {sheet_name}...")
    try:
        client_gs = get_gspread_client()
        spreadsheet = client_gs.open_by_key(SHEET_ID)
        try:
            sheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            print(f"Tạo sheet mới: {sheet_name}")
            sheet = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=10)
        header = ["Original Title", "Summary", "Link", "Image URL", "Publish Date", "Ảnh", "Ngày"]
        if not sheet.get_all_values():
            sheet.insert_row(header, 1)
        row = [title, summary_title + "\n👇👇👇\n" + summary_content, link, image_url or "", pubdate, "", ""]
        sheet.insert_row(row, 2)
        image_formula = '=IF(D2<>""; IMAGE(D2); "")'
        date_formula = '=IF(E2<>""; DATE(MID(E2; FIND(","; E2)+9; 4); MATCH(MID(E2; FIND(","; E2)+5; 3); {"Jan";"Feb";"Mar";"Apr";"May";"Jun";"Jul";"Aug";"Sep";"Oct";"Nov";"Dec"}; 0); MID(E2; FIND(","; E2)+2; 2)); "")'
        sheet.update('F2', [[image_formula]], value_input_option='USER_ENTERED')
        sheet.update('G2', [[date_formula]], value_input_option='USER_ENTERED')
        global processed_count
        processed_count += 1
    except Exception as e:
        print(f"Lỗi ghi sheet: {str(e)}")
        global error_count
        error_count += 1

def main():
    print("=== BẮT ĐẦU CHẠY SCRIPT ===")
    feeds = get_rss_feeds()
    if not feeds:
        print("Không có RSS nào để xử lý.")
        return
    for feed in feeds:
        rss_url = feed["rss_url"]
        sheet_name = feed["sheet_name"]
        print(f"\n=== XỬ LÝ RSS: {rss_url} ===")
        articles = get_rss_feed(rss_url, sheet_name)
        if not articles:
            print("Không có bài mới.")
            continue
        for i, article in enumerate(articles, 1):
            print(f"\nXử lý bài {i}/{len(articles)}: {article['title']}")
            summary_title, summary_content = rewrite_content(article["title"], article["description"])
            if not summary_title or not summary_content:
                print(f"Bỏ qua bài do lỗi tóm tắt.")
                global error_count
                error_count += 1
                continue
            append_to_gsheet(
                article["title"], summary_title, summary_content,
                article["link"], article["image_url"], article["pubdate"], sheet_name
            )
    print("\n=== TỔNG KẾT ===")
    print(f"Thành công: {processed_count}")
    print(f"Trùng lặp: {skipped_count}")
    print(f"Lỗi: {error_count}")
    print("=== KẾT THÚC ===")

if __name__ == "__main__":
    main()
