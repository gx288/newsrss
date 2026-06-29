import os
import json
import time
import re
import gspread
import google.generativeai as genai
import xml.etree.ElementTree as ET
from xml.dom import minidom
from google.oauth2.service_account import Credentials

# ==================== CONFIG ====================
SHEET_ID = "14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo"
SHEET_NAME = "LiveScience_Raw"
SERVICE_ACCOUNT_FILE = 'khoahoctv/credentials.json'
RSS_OUTPUT_FILE = "livescience_vi.rss"
BATCH_SIZE = 15  # Số bài xử lý mỗi lần chạy (để tiết kiệm API key)

# ==================== PROMPT ====================
PROMPT_TEMPLATE = """
Hãy đóng vai một chuyên gia sáng tạo nội dung về khoa học/y học thú vị. Đọc bài báo tiếng Anh dưới đây, dịch và viết lại thành một bài đăng Facebook tiếng Việt (khoảng 600-1000 ký tự) theo các tiêu chí:

1. VĂN PHONG: Dân dã, dễ hiểu, cực kỳ hấp dẫn, khơi gợi sự tò mò của người đọc về những sự thật y khoa/khoa học kỳ thú. Tuyệt đối không dùng từ ngữ quá hàn lâm học thuật. Giữ giọng điệu điềm tĩnh, chuẩn xác khoa học, không cợt nhả.
2. NỘI DUNG: 
- Truyền tải trọn vẹn những thông tin, sự thật thú vị nhất từ bài báo gốc.
- Không đưa ra các khẳng định y khoa tuyệt đối (kiểu "chữa khỏi hoàn toàn", "100%"). Giữ tính trung lập và an toàn.
3. BỐ CỤC & TIÊU ĐỀ:
- Dòng đầu tiên là TIÊU ĐỀ VIẾT IN HOA TẤT CẢ. TIÊU ĐỀ PHẢI THẬT "GIẬT TÍT", GÂY TÒ MÒ HOẶC SỐC NHƯNG KHÔNG SAI SỰ THẬT. Bạn hãy học theo cấu trúc của các mẫu tiêu đề sau: 
  + "Những bộ phận 'bẩn' nhất của lợn, ăn càng ít càng tốt kẻo rước độc vào người"
  + "Cuồng dâm: Nguyên nhân, triệu chứng và cách điều trị"
  + "2 loại quả vừa là 'vua loại bỏ huyết khối', vừa là 'khắc tinh của ung thư'"
  + "Khám phá mới: Tinh trùng con người bơi lội thách thức định luật Newton"
  + "Lý do tuyệt vời để bạn chọn đi xe đạp"
- Cuối tiêu đề có "👇👇👇".
- Chia nội dung thành 3-4 đoạn ngắn. Đầu mỗi đoạn dùng 1 emoji phù hợp với ngữ cảnh đoạn đó (không dùng trùng lặp emoji).
- Viết thành các đoạn văn trôi chảy, không dùng "tiêu đề phụ ngắn" ở đầu mỗi đoạn.
- Đặt tất cả các hashtag ở cuối bài viết (ví dụ: #khampha #suckhoe #khoahoc #suthatthuvi).
- Không dùng đại từ nhân xưng.
4. XỬ LÝ BÀI TỔNG HỢP NHIỀU TIN (NEWS ROUNDUP):
- Nếu bài báo gốc là một bài tổng hợp chứa nhiều tin tức/sự kiện khác nhau (ví dụ: "Science news this week"), bạn TUYỆT ĐỐI KHÔNG liệt kê lắt nhắt tất cả các tin.
- Thay vào đó, HÃY CHỌN RA ĐÚNG 1 TIN TỨC THÚ VỊ NHẤT, ĐỘC ĐÁO NHẤT trong bài đó và đào sâu viết thành 1 bài post hoàn chỉnh duy nhất chỉ về chủ đề đó. Bỏ qua hoàn toàn các tin còn lại.

Trả về theo định dạng:
[TIÊU ĐỀ]
[NỘI DUNG]

Bài báo gốc (Tiếng Anh):
Tiêu đề: {title}
Mô tả: {description}
"""

MODEL_PRIORITY = [
    "gemini-3-pro-preview",
    "gemini-3-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

# ==================== INITS ====================
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

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

def get_gemini_model():
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    for model_name in MODEL_PRIORITY:
        try:
            print(f"[*] Thử model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            model.generate_content("Test")
            print(f"   => Đã kết nối model: {model_name}")
            return model
        except Exception as e:
            print(f"   [!] Model {model_name} lỗi: {e}")
    raise Exception("Không kết nối được bất kỳ model Gemini nào. Hết quota?")

# ==================== CORE ====================
def rewrite_article(model, title, description):
    prompt = PROMPT_TEMPLATE.format(title=title, description=description)
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Tách tiêu đề và nội dung
        parts = text.split("👇👇👇")
        if len(parts) >= 2:
            new_title = parts[0].replace("👇👇👇", "").strip()
            new_title = re.sub(r'^\**TIÊU ĐỀ:?\**\s*', '', new_title, flags=re.IGNORECASE)
            new_title = new_title.replace("**", "")
            
            new_content = parts[1].strip()
            new_content = new_content.replace("**", "")
            return new_title, new_content
        else:
            # Fallback nếu AI trả về không có 👇👇👇
            lines = text.split("\n")
            new_title = lines[0].strip().replace("**", "")
            new_content = "\n".join(lines[1:]).strip().replace("**", "")
            return new_title, new_content
    except Exception as e:
        print(f"❌ Lỗi AI: {e}")
        return None, None

def create_rss(all_records):
    print("\n=== ĐANG TẠO RSS ===")
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Khám phá Khoa học & Sức khỏe (LiveScience Vi)"
    ET.SubElement(channel, "link").text = "https://www.livescience.com/health"
    ET.SubElement(channel, "description").text = "Tổng hợp sự thật y khoa, khoa học thú vị"

    done_records = [r for r in all_records if r.get('Status') == 'DONE']
    # Chỉ lấy 100 bài mới nhất cho RSS
    done_records = sorted(done_records, key=lambda x: x.get('PubDate', ''), reverse=True)[:100]

    for item_data in done_records:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = item_data.get('TranslatedTitle', item_data['Title'])
        ET.SubElement(item, "link").text = item_data['Link']
        ET.SubElement(item, "guid", isPermaLink="true").text = item_data['Link']
        ET.SubElement(item, "pubDate").text = item_data.get('PubDate', '')
        
        content = item_data.get('TranslatedContent', item_data['Description'])
        img = item_data.get('Image', '')
        desc_html = content.replace('\n', '<br/>')
        if img:
            desc_html += f'<br/><br/><img src="{img}" alt="thumbnail"/>'
            
        desc_elem = ET.SubElement(item, "description")
        desc_elem.text = f"<![CDATA[{desc_html}]]>"

    xmlstr = ET.tostring(rss, encoding='unicode')
    pretty_xml = minidom.parseString(xmlstr).toprettyxml(indent="  ")
    clean_xml = "\n".join(line for line in pretty_xml.splitlines() if line.strip())

    with open(RSS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(clean_xml)
    print(f"✅ Đã lưu {len(done_records)} bài vào {RSS_OUTPUT_FILE}")

def main():
    print("=== AI CONTENT GENERATOR & RSS BUILDER ===")
    sheet = init_gsheet()
    if not sheet:
        return
        
    try:
        model = get_gemini_model()
    except Exception as e:
        print(e)
        return

    records = sheet.get_all_records()
    if not records:
        print("[-] Không có dữ liệu trong sheet.")
        return

    processed = 0
    for i, row in enumerate(records):
        if processed >= BATCH_SIZE:
            print(f"[*] Đã xử lý đủ limit hôm nay ({BATCH_SIZE} bài). Dừng lại để tiết kiệm quota.")
            break
            
        if row.get('Status') == 'NEW':
            title = row.get('Title')
            desc = row.get('FullTextEn')
            print(f"\n=> Đang xử lý: {title[:60]}...")
            
            new_title, new_content = rewrite_article(model, title, desc)
            if new_title and new_content:
                # Update records array
                row['TranslatedTitle'] = new_title
                row['TranslatedContent'] = new_content
                row['Status'] = 'DONE'
                
                # Update sheet (index is i + 2 because header is row 1)
                row_idx = i + 2
                sheet.update(f'G{row_idx}:I{row_idx}', [['DONE', new_title, new_content]])
                print(f"   [+] OK! Tiêu đề mới: {new_title}")
                processed += 1
                time.sleep(2) # Tránh rate limit
            else:
                print("   [-] Dịch thất bại, bỏ qua.")
                row['Status'] = 'ERROR'
                sheet.update(f'G{i+2}', [['ERROR']])

    # Sau khi xử lý xong, tải lại toàn bộ records mới nhất để tạo RSS
    updated_records = sheet.get_all_records()
    create_rss(updated_records)
    print("\n🎉 KẾT THÚC!")

if __name__ == "__main__":
    main()
