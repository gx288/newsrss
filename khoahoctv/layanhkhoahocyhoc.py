import time
import re
import json
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
# For bypassing Cloudflare, you may need to install undetected_chromedriver
# pip install undetected-chromedriver
import undetected_chromedriver as uc
import gspread
from google.oauth2.service_account import Credentials

# Setup Google Sheets API
# Instructions:
# 1. Go to Google Cloud Console, create a project, enable Google Sheets API.
# 2. Create a service account, download the JSON key file.
# 3. Share the Google Sheet with the service account email (edit access).
# Set the path to your service account JSON key
SERVICE_ACCOUNT_FILE = 'path/to/your/service-account-key.json'  # Replace with your file path

# Scopes for Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Authenticate and open the spreadsheet
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)

# Spreadsheet ID from the URL
SPREADSHEET_ID = '14tqKftTqlesnb0NqJZU-_f1EsWWywYqO36NiuDdmaTo'
SHEET_NAME = 'Khoahocyhoc'

# Open the sheet
sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

# Assume column C is links (index 3, since A=1, B=2, C=3)
# Column D is images (index 4)
# Row 1 is headers

def is_cloudflare_protected(html):
    return 'cloudflare' in html.lower() or 'cf-browser-verification' in html

def get_first_image_url(url, use_selenium=False):
    print(f"Debug: Accessing URL: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    if not use_selenium:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            html = response.text
            print("Debug: Fetched with requests. Checking for Cloudflare...")
            if is_cloudflare_protected(html):
                print("Debug: Cloudflare detected. Switching to Selenium.")
                return get_first_image_url(url, use_selenium=True)
            
            soup = BeautifulSoup(html, 'html.parser')
            # Find main content - adjust based on site structure
            # From test, assume main article is in div with class 'article-detail' or similar
            # You need to inspect the site; placeholder: find first img in body not in header/ads
            main_content = soup.find('div', class_='article-body')  # Adjust class name
            if not main_content:
                main_content = soup.find('article') or soup.find('div', id='content') or soup.body
            
            if main_content:
                imgs = main_content.find_all('img')
                for img in imgs:
                    src = img.get('src')
                    if src:
                        # Avoid ads: skip if src contains 'ad', 'banner', 'logo', or small size
                        if 'ad' in src.lower() or 'banner' in src.lower() or 'logo' in src.lower():
                            print(f"Debug: Skipping ad image: {src}")
                            continue
                        # Check if it's a real image (not gif, small icon)
                        if src.endswith('.jpg') or src.endswith('.png') or 'image' in src.lower():
                            full_src = urljoin(url, src)
                            print(f"Debug: Found potential first image: {full_src}")
                            return full_src
            print("Debug: No suitable image found.")
            return None
        except Exception as e:
            print(f"Debug: Requests failed: {e}. Trying Selenium.")
            return get_first_image_url(url, use_selenium=True)
    
    else:
        # Use Selenium for bypass
        try:
            options = Options()
            options.add_argument("--headless")  # Run headless
            options.add_argument(f"user-agent={headers['User-Agent']}")
            driver = uc.Chrome(options=options)  # Use undetected_chromedriver
            driver.get(url)
            time.sleep(5)  # Wait for page load and potential Cloudflare bypass
            html = driver.page_source
            driver.quit()
            print("Debug: Fetched with Selenium.")
            
            soup = BeautifulSoup(html, 'html.parser')
            # Same logic as above
            main_content = soup.find('div', class_='article-body')  # Adjust
            if not main_content:
                main_content = soup.find('article') or soup.find('div', id='content') or soup.body
            
            if main_content:
                imgs = main_content.find_all('img')
                for img in imgs:
                    src = img.get('src')
                    if src:
                        if 'ad' in src.lower() or 'banner' in src.lower() or 'logo' in src.lower():
                            print(f"Debug: Skipping ad image: {src}")
                            continue
                        if src.endswith('.jpg') or src.endswith('.png') or 'image' in src.lower():
                            full_src = urljoin(url, src)
                            print(f"Debug: Found potential first image: {full_src}")
                            return full_src
            print("Debug: No suitable image found with Selenium.")
            return None
        except Exception as e:
            print(f"Debug: Selenium failed: {e}")
            return None

# Process the sheet
rows = sheet.get_all_values()
for row_idx, row in enumerate(rows[1:], start=2):  # Skip header, start from row 2
    if len(row) < 4:
        continue  # Skip if row too short
    link = row[2].strip()  # Column C (index 2)
    image_cell = row[3].strip()  # Column D (index 3)
    
    if not link:
        print(f"Debug: Row {row_idx} - No link, skipping.")
        continue
    
    if image_cell:
        print(f"Debug: Row {row_idx} - Image already present ({image_cell}), skipping.")
        continue
    
    print(f"Debug: Processing row {row_idx} - Link: {link}")
    image_url = get_first_image_url(link)
    
    if image_url:
        # Update cell D in row_idx
        sheet.update_cell(row_idx, 4, image_url)  # Column D is 4
        print(f"Debug: Updated row {row_idx} with image: {image_url}")
    else:
        print(f"Debug: Could not find image for row {row_idx}")
    time.sleep(2)  # Delay to avoid rate limiting

print("Processing complete.")

# Test cases:
# 1. Test with provided link
test_link = "https://khoahoc.tv/cach-xu-ly-khi-say-thuoc-lao-128235"
print("\nTest Case 1: Provided link")
test_image = get_first_image_url(test_link)
print(f"Test Result: {test_image}")

# 2. Test a link without images or invalid
invalid_link = "https://example.com"  # Adjust to a real invalid
print("\nTest Case 2: Invalid or no image link")
test_image = get_first_image_url(invalid_link)
print(f"Test Result: {test_image}")

# 3. Test a link known to have Cloudflare (if any, placeholder)
# cf_link = "https://site-with-cf.com"
# print("\nTest Case 3: Cloudflare protected link")
# test_image = get_first_image_url(cf_link)
# print(f"Test Result: {test_image}")

# Note: Adjust the main_content finder based on actual site inspection.
# For khoahoc.tv, inspect the page to find the correct class for article body, e.g., 'post-content', 'entry-content', etc.
# If Cloudflare blocks frequently, consider using proxies or more advanced bypass.
