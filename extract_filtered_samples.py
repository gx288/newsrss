import json
from urllib.parse import urlparse
import re

HL_FILE = "healthline_data.json"
MNT_FILE = "mnt_data.json"

BAD_KEYWORDS = ['video', 'drug', 'medicare', 'sex', 'baby', 'womens-health', 'pregnancy', 'dosage', 'medications', 'interactions', '/es/']

def is_bad(url, title):
    text = (url + " " + title).lower()
    for bad in BAD_KEYWORDS:
        if bad in text:
            return True
    return False

hl_samples = []
mnt_samples = []

hl_groups = {
    'beauty': [],
    'mental': [],
    'eye': [],
    'nutrition': [],
    'neuro': []
}

mnt_groups = {
    'symptoms': [],
    'causes': [],
    'treatment': [],
    'arthritis': []
}

# Process Healthline
print("Processing Healthline...")
try:
    with open(HL_FILE, 'r', encoding='utf-8') as f:
        hl_data = json.load(f)
        for item in hl_data:
            if is_bad(item['url'], item['title']):
                continue
            
            url_lower = item['url'].lower()
            if '/beauty-skin-care/' in url_lower and len(hl_groups['beauty']) < 2:
                hl_groups['beauty'].append(item)
            elif '/mental-health/' in url_lower and len(hl_groups['mental']) < 2:
                hl_groups['mental'].append(item)
            elif '/eye-health/' in url_lower and len(hl_groups['eye']) < 2:
                hl_groups['eye'].append(item)
            elif '/nutrition/' in url_lower and len(hl_groups['nutrition']) < 2:
                hl_groups['nutrition'].append(item)
            elif '/neurological-health/' in url_lower and len(hl_groups['neuro']) < 2:
                hl_groups['neuro'].append(item)
except Exception as e:
    print("Healthline error:", e)

for group in hl_groups.values():
    hl_samples.extend(group)

# Process MNT
print("Processing MNT...")
try:
    with open(MNT_FILE, 'r', encoding='utf-8') as f:
        mnt_data = json.load(f)
        for item in mnt_data:
            if is_bad(item['url'], item['title']):
                continue
                
            title_lower = item['title'].lower()
            if 'symptoms' in title_lower and len(mnt_groups['symptoms']) < 2:
                mnt_groups['symptoms'].append(item)
            elif 'causes' in title_lower and len(mnt_groups['causes']) < 2:
                mnt_groups['causes'].append(item)
            elif 'treatment' in title_lower and len(mnt_groups['treatment']) < 2:
                mnt_groups['treatment'].append(item)
            elif 'arthritis' in title_lower and len(mnt_groups['arthritis']) < 2:
                mnt_groups['arthritis'].append(item)
except Exception as e:
    print("MNT error:", e)

for group in mnt_groups.values():
    mnt_samples.extend(group)

# Save
with open('healthline_filtered_samples.json', 'w', encoding='utf-8') as f:
    json.dump(hl_samples, f, ensure_ascii=False, indent=2)

with open('mnt_filtered_samples.json', 'w', encoding='utf-8') as f:
    json.dump(mnt_samples, f, ensure_ascii=False, indent=2)

print(f"Extracted {len(hl_samples)} HL samples and {len(mnt_samples)} MNT samples.")
