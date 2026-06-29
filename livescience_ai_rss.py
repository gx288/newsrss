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
- Dòng đầu tiên là TIÊU ĐỀ VIẾT IN HOA TẤT CẢ.
- TIÊU ĐỀ PHẢI NGẮN GỌN (tối đa 15 từ), gây tò mò nhưng TUYỆT ĐỐI KHÔNG CƯỜNG ĐIỆU.
- KHÔNG sử dụng các từ ngữ giật gân rẻ tiền như: "SỰ THẬT SỐC", "SHOCK", "BÍ ẨN BẤT NGỜ", "KINH TỞM KHỦNG KHIẾP". Hãy dùng ngôn từ điềm tĩnh, khoa học nhưng vẫn hấp dẫn.
- Bạn hãy học theo cấu trúc của các mẫu tiêu đề sau (trực diện, lịch sự): 
  + "NHỮNG BỘ PHẬN 'BẨN' NHẤT CỦA LỢN, ĂN CÀNG ÍT CÀNG TỐT"
  + "CUỒNG DÂM: NGUYÊN NHÂN, TRIỆU CHỨNG VÀ CÁCH ĐIỀU TRỊ"
  + "TINH TRÙNG CON NGƯỜI BƠI LỘI THÁCH THỨC ĐỊNH LUẬT NEWTON"
  + "ĐÓNG BĂNG NÃO BẰNG THUỐC: HY VỌNG MỚI CHO BỆNH NHÂN ĐỘT QUỴ"
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
    "gemini-2.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest",
    "gemini-pro",
    "gemini-1.0-pro",
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
    
    print("[*] Đang tải danh sách model khả dụng từ Google...")
    available_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                model_name = m.name.replace('models/', '')
                available_models.append(model_name)
    except Exception as e:
        print(f"❌ Lỗi khi lấy danh sách model: {e}")
        
    print(f"[*] Các model khả dụng trong tài khoản: {available_models}")
    
    # Lọc bỏ các model không chuyên viết text (gemma, âm thanh, hình ảnh, robot, chuyên ngành...)
    ignored_keywords = ['gemma', 'image', 'tts', 'audio', 'clip', 'robotics', 'computer-use', 'antigravity', 'deep-research', 'nano', 'lyria']
    text_models = [m for m in available_models if 'gemini' in m.lower() and not any(k in m.lower() for k in ignored_keywords)]
    
    # Ưu tiên các model đời mới nhất (3.5, 3.1, 3.0, 2.5) chuyên viết text
    priority = [
        "gemini-3.5-flash", "gemini-3.1-pro-preview", "gemini-3-pro-preview", 
        "gemini-3.1-flash-lite", "gemini-3-flash-preview", 
        "gemini-2.5-pro", "gemini-2.5-flash", 
        "gemini-pro-latest", "gemini-flash-latest",
        "gemini-2.0-pro", "gemini-2.0-flash"
    ]
    
    models_to_try = [p for p in priority if p in text_models]
    
    # Bổ sung các model text còn lại vào cuối danh sách dự phòng
    for m in text_models:
        if m not in models_to_try:
            models_to_try.append(m)
            
    if not models_to_try:
        models_to_try = priority # Fallback

    for model_name in models_to_try:
        try:
            print(f"[*] Thử model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            model.generate_content("Test")
            print(f"   => Đã kết nối model: {model_name}")
            return model
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str:
                print(f"   [!] Model {model_name} hết QUOTA tạm thời.")
            else:
                print(f"   [!] Model {model_name} lỗi: {e}")
                
    raise Exception("Không kết nối được bất kỳ model Gemini nào. Hết quota toàn bộ hệ thống?")

# ==================== CORE ====================
def rewrite_article(model, title, description):
    prompt = PROMPT_TEMPLATE.format(title=title, description=description)
    safety_settings = {
        'HATE': 'BLOCK_NONE',
        'HARASSMENT': 'BLOCK_NONE',
        'SEXUAL' : 'BLOCK_NONE',
        'DANGEROUS' : 'BLOCK_NONE'
    }
    response = model.generate_content(prompt, safety_settings=safety_settings)
    text = response.text.strip()
    
    if text.upper() == "SKIP" or "SKIP" in text.upper()[:10]:
        return "SKIP", "SKIP"
        
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
        
        content = item_data.get('TranslatedContent', item_data.get('FullTextEn', ''))
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

    try:
        values = sheet.get_all_values()
    except Exception as e:
        print(f"[-] Lỗi khi lấy dữ liệu sheet: {e}")
        return
        
    if len(values) <= 1:
        print("[-] Không có dữ liệu trong sheet.")
        return
        
    headers = values[0]
    records = []
    for row_values in values[1:]:
        row_dict = {}
        for idx, val in enumerate(row_values):
            if idx < len(headers):
                # Nếu có cột trùng tên, nó sẽ tự đè lên cột trước đó (tránh lỗi duplicate header)
                row_dict[headers[idx]] = val
        records.append(row_dict)

    processed = 0
    updates = []
    for i, row in enumerate(records):
        if processed >= BATCH_SIZE:
            print(f"[*] Đã xử lý đủ limit hôm nay ({BATCH_SIZE} bài). Dừng lại để tiết kiệm quota.")
            break
            
        if row.get('Status') == 'NEW':
            title = row.get('Title')
            desc = row.get('FullTextEn')
            print(f"\n=> Đang xử lý: {title[:60]}...")
            
            row_idx = i + 2
            
            # Retry logic for AI Quota Exceeded (429)
            new_title, new_content = None, None
            retry_count = 3
            while retry_count > 0:
                try:
                    new_title, new_content = rewrite_article(model, title, desc)
                    break
                except Exception as e:
                    print(f"   [!] Lỗi AI ({e}). Thử lại... ({retry_count} lần nữa)")
                    retry_count -= 1
                    time.sleep(5)
                    if retry_count == 0:
                        print("   [!] Đổi sang model Gemini khác do lỗi liên tục...")
                        try:
                            model = get_gemini_model()
                            new_title, new_content = rewrite_article(model, title, desc)
                        except Exception as e2:
                            print(f"   [-] Vẫn lỗi: {e2}")
            
            if new_title == "SKIP":
                print("   [-] Bỏ qua bài tổng hợp (SKIPPED).")
                row['Status'] = 'SKIPPED_ROUNDUP'
                updates.append({'range': f'G{row_idx}', 'values': [['SKIPPED_ROUNDUP']]})
            elif new_title and new_content:
                row['TranslatedTitle'] = new_title
                row['TranslatedContent'] = new_content
                row['Status'] = 'DONE'
                
                updates.append({'range': f'G{row_idx}:I{row_idx}', 'values': [['DONE', new_title, new_content]]})
                print(f"   [+] OK! Tiêu đề mới: {new_title}")
                processed += 1
                time.sleep(2) # Tránh rate limit AI
            else:
                print("   [-] Dịch thất bại, bỏ qua.")
                row['Status'] = 'ERROR'
                updates.append({'range': f'G{row_idx}', 'values': [['ERROR']]})

    if updates:
        print(f"\n[*] Đang cập nhật {len(updates)} dòng lên Google Sheets cùng lúc (Batch Update)...")
        try:
            sheet.batch_update(updates)
            print("✅ Cập nhật Google Sheets thành công!")
        except Exception as e:
            print(f"❌ Lỗi khi cập nhật Google Sheets: {e}")

    # Sau khi xử lý xong, tải lại toàn bộ records mới nhất để tạo RSS
    try:
        updated_values = sheet.get_all_values()
        updated_headers = updated_values[0]
        updated_records = []
        for row_values in updated_values[1:]:
            row_dict = {}
            for idx, val in enumerate(row_values):
                if idx < len(updated_headers):
                    row_dict[updated_headers[idx]] = val
            updated_records.append(row_dict)
    except Exception as e:
        print(f"[-] Lỗi khi lấy dữ liệu tạo RSS: {e}")
        updated_records = records # fallback dùng records cũ
    create_rss(updated_records)
    print("\n🎉 KẾT THÚC!")

if __name__ == "__main__":
    main()
