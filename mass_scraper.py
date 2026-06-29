import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
import time
import json
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== CONFIG ====================
SITEMAP_INDEX = "https://www.livescience.com/sitemap.xml"
JSON_OUTPUT = "livescience_full_raw.json"
MAX_WORKERS = 10  # Số luồng an toàn tránh bị block
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==================== SITEMAP SCRAPER ====================
def get_all_sitemaps():
    print("[*] Đang tải sitemap index...")
    try:
        r = requests.get(SITEMAP_INDEX, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'xml')
        sitemaps = [loc.text for loc in soup.find_all('loc') if re.search(r'sitemap-\d{4}-\d{2}\.xml', loc.text)]
        sitemaps.sort(reverse=True)
        print(f"   => Tìm thấy {len(sitemaps)} file sitemaps lịch sử.")
        return sitemaps
    except Exception as e:
        print(f"❌ Lỗi tải sitemap index: {e}")
        return []

def get_health_links(sitemap_url):
    try:
        r = requests.get(sitemap_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'xml')
        links = [loc.text for loc in soup.find_all('loc') if '/health/' in loc.text]
        return links
    except Exception as e:
        print(f"❌ Lỗi quét {sitemap_url}: {e}")
        return []

def scrape_article(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        
        title = soup.find('h1')
        title = title.text.strip() if title else ""
        
        body = soup.find('div', id='article-body')
        if body:
            for tag in body(['script', 'style']):
                tag.decompose()
            desc = body.get_text(separator='\n', strip=True)
        else:
            desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', property='og:description')
            desc = desc['content'].strip() if desc else ""
        
        img = soup.find('meta', property='og:image')
        img = img['content'] if img else ""
        
        pubdate = soup.find('meta', property='article:published_time')
        pubdate = pubdate['content'] if pubdate else datetime.now().isoformat()
        
        if not title or not desc:
            return None
            
        return {
            "title": title,
            "link": url,
            "description": desc,
            "image": img,
            "pubdate": pubdate
        }
    except Exception as e:
        return None

# ==================== MAIN ====================
def main():
    print("=== MASS SCRAPER (MULTI-THREADING) ===")
    
    # 1. Quét toàn bộ Sitemap
    sitemaps = get_all_sitemaps()
    all_health_links = []
    
    print("\n[*] Bắt đầu quét đa luồng để tìm link Health...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(get_health_links, sm): sm for sm in sitemaps}
        for i, future in enumerate(as_completed(future_to_url), 1):
            links = future.result()
            all_health_links.extend(links)
            print(f"   [{i}/{len(sitemaps)}] Quét xong sitemap, tổng link tìm được: {len(all_health_links)}", end='\r')
    
    all_health_links = list(set(all_health_links))
    print(f"\n✅ Đã chốt danh sách {len(all_health_links)} link Health duy nhất.")

    # Tải dữ liệu đã cào (nếu có) để chạy tiếp (resume)
    existing_data = {}
    if os.path.exists(JSON_OUTPUT):
        with open(JSON_OUTPUT, 'r', encoding='utf-8') as f:
            try:
                data_list = json.load(f)
                for item in data_list:
                    existing_data[item['link']] = item
            except:
                pass
    
    links_to_scrape = [link for link in all_health_links if link not in existing_data]
    print(f"[*] Tìm thấy {len(links_to_scrape)} link MỚI cần cào nội dung.")

    if not links_to_scrape:
        print("🎉 Không còn bài nào mới để cào!")
        return

    # 2. Cào nội dung đa luồng
    print("\n[*] Bắt đầu cào nội dung (Full text) đa luồng...")
    results = []
    success = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_link = {executor.submit(scrape_article, link): link for link in links_to_scrape}
        for i, future in enumerate(as_completed(future_to_link), 1):
            data = future.result()
            if data:
                results.append(data)
                success += 1
            print(f"   [{i}/{len(links_to_scrape)}] Đã cào thành công: {success} bài", end='\r')
            
            # Cứ mỗi 100 bài lưu file 1 lần cho an toàn
            if i % 100 == 0:
                with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
                    json.dump(list(existing_data.values()) + results, f, ensure_ascii=False, indent=2)

    # Lưu lần cuối
    with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(list(existing_data.values()) + results, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 HOÀN TẤT! Đã cào được {success} bài mới. Lưu tại {JSON_OUTPUT}")

if __name__ == "__main__":
    main()
