# Prompt for Google Gemini
PROMPT = """
Tóm tắt thành vài đoạn văn ngắn (không dùng các đoạn tóm tắt ngắn ở đầu đoạn văn), có emoji (khác nhau) phù hợp với nội dung của đoạn đặt ở đầu dòng và hashtag ở cuối cùng của bài viết. Khoảng 100-200 kí tự hãy viết thành đoạn văn trôi chảy, không dùng "tiêu đề ngắn". Hãy đặt tất cả hashtag ở cuối bài viết, không đặt ở cuối mỗi đoạn. Viết theo quy tắc 4C, trung lập, không dùng đại từ nhân xưng. Kết quả trả về có 1 phần tiêu đề được VIẾT IN HOA TẤT CẢ và "👇👇👇" cuối tiêu đề. Trích dẫn Theo 24h.com.vn nếu trong bài có đề cập (đặt trước hashtag).
"""

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

# Cấu hình Google Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Cấu hình Google Sheets
def get_gspread_client():
    creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(creds)
    return client

def get_rss_feed():
    feed = feedparser.parse(RSS_FEED_URL)
    if not feed.entries:
        print("No entries found in RSS feed")
        return None
    entry = feed.entries[0]  # Lấy bài mới nhất
    title = entry.title
    description = entry.description
    link = entry.link
    pubdate = entry.pubdate
    # Lấy hình ảnh từ description (CDATA)
    image_url = None
    soup = BeautifulSoup(description, 'html.parser')
    img_tag = soup.find('img')
    if img_tag and img_tag.get('src'):
        image_url = img_tag['src']
    return {"title": title, "description": description, "link": link, "image_url": image_url, "pubdate": pubdate}

def rewrite_content(title, description):
    prompt = f"{PROMPT}\nTiêu đề: {title}\nMô tả: {description}"
    response = model.generate_content(prompt)
    # Xử lý để đảm bảo định dạng đúng
    content = response.text.strip()
    # Tách tiêu đề và nội dung
    parts = content.split("👇👇👇")
    if len(parts) < 2:
        print("Invalid response format from Gemini")
        return None, None
    summary_title = parts[0].strip()
    summary_content = parts[1].strip()
    return summary_title, summary_content

def append_to_gsheet(title, summary_title, summary_content, link, image_url, pubdate):
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
    # Ghi dữ liệu vào sheet
    row = [title, summary_title + "\n👇👇👇\n" + summary_content, link, image_url, pubdate]
    sheet.append_row(row)
    print("Appended to Google Sheet successfully!")

def main():
    # Lấy dữ liệu từ RSS
    article = get_rss_feed()
    if not article:
        return
    # Viết lại nội dung bằng Gemini
    summary_title, summary_content = rewrite_content(article["title"], article["description"])
    if not summary_title or not summary_content:
        print("Failed to generate summary")
        return
    # Ghi vào Google Sheet
    append_to_gsheet(article["title"], summary_title, summary_content, article["link"], article["image_url"], article["pubdate"])

if __name__ == "__main__":
    main()
