import feedparser
import os
import json
import google.genai as genai  # Package mới chính thức: pip install google-genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from bs4 import BeautifulSoup
import gspread.exceptions

# Cấu hình
SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
RSS_SHEET_NAME = "RSS"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

# Danh sách model ưu tiên (tháng 12/2025 - stable & preview mới nhất)
MODEL_PRIORITY = [
    "gemini-2.5-pro",           # Mạnh nhất, reasoning tốt nhất hiện tại
    "gemini-2.5-flash",         # Nhanh + chất lượng tốt, quota cao
    "gemini-2.5-flash-lite",    # Nhẹ nhất, tiết kiệm quota
    "gemini-2.0-flash",         # Fallback ổn định cũ hơn
]

# Prompt giữ nguyên
PROMPT = """
Tóm tắt thành vài đoạn văn ngắn (không dùng các đoạn tóm tắt ngắn ở đầu đoạn văn), có emoji (khác nhau) phù hợp với nội dung của đoạn đặt ở đầu dòng và hashtag ở cuối cùng của bài viết. Khoảng 500-1000 kí tự phù hợp với Facebook. Hãy viết thành đoạn văn trôi chảy, không dùng "tiêu đề ngắn". Hãy đặt tất cả hashtag ở cuối bài viết, không đặt ở cuối mỗi đoạn. Thêm hashtag #dongysonha. Viết theo quy tắc 4C, đầy đủ ý, nội dung phù hợp với tiêu đề, giải quyết được tình trạng, câu hỏi trong tiêu đề, làm thỏa mãn người đọc, trung thực, không dùng đại từ nhân xưng. Kết quả trả về có 1 phần tiêu đề được VIẾT IN HOA TẤT CẢ và "👇👇👇" cuối tiêu đề.
"""

# Cấu hình GenAI SDK mới
genai.configure(api_key=GEMINI_API_KEY)

# Biến theo dõi
processed_count = 0
skipped_count = 0
error_count = 0

# Các hàm Google Sheets (giữ nguyên, chỉ thêm xử lý WorksheetNotFound)
def get_gspread_client():
    print("Bắt đầu cấu hình Google Sheets client...")
    creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    print("Hoàn tất cấu hình Google Sheets client.")
    return client

def get_rss_feeds():
    # ... (giữ nguyên như trước)
    # (code lấy RSS từ sheet RSS)
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
        print(f"Tổng {len(feeds)} RSS feed.")
        return feeds
    except Exception as e:
        print(f"Lỗi lấy RSS: {e}")
        return []

def get_existing_links(sheet_name):
    # ... xử lý nếu sheet chưa tồn tại
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SHEET_ID).worksheet(sheet_name)
        links = sheet.col_values(3)[1:]
        print(f"Đã lấy {len(links)} link cũ từ {sheet_name}.")
        return set(links)
    except gspread.exceptions.WorksheetNotFound:
        print(f"Sheet {sheet_name} chưa tồn tại → coi như chưa có bài nào.")
        return set()
    except Exception as e:
        print(f"Lỗi lấy link: {e}")
        return set()

def get_rss_feed(rss_url, sheet_name):
    # ... giữ nguyên, giới hạn 5 bài mới
    # (code lấy feed, extract image, break sau 5 bài mới)

def rewrite_content(title, description):
    print(f"Bắt đầu tóm tắt: {title}")
    prompt = f"{PROMPT}\nTiêu đề: {title}\nMô tả: {description}"
    for model_name in MODEL_PRIORITY:
        print(f"Thử model: {model_name}")
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            content = response.text.strip()
            parts = content.split("👇👇👇")
            if len(parts) < 2:
                print(f"Định dạng sai từ {model_name}, thử model khác...")
                continue
            summary_title = parts[0].strip()
            summary_content = parts[1].strip()
            print(f"Thành công với {model_name}")
            return summary_title, summary_content
        except Exception as e:
            if "quota" in str(e).lower() or "429" in str(e):
                print(f"Quota exceeded {model_name} → thử tiếp...")
                continue
            print(f"Lỗi {model_name}: {e}")
            continue
    print(f"Không model nào hoạt động cho bài này.")
    return None, None

# append_to_gsheet và main() giữ nguyên như phiên bản trước

if __name__ == "__main__":
    main()
