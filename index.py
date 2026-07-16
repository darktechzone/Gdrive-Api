"""
Google Drive Course Finder API – All Results, All Formats
Professional key rotation, full pagination, and DARK TECH ZONE branding.
"""
import os
import re
import time
import logging
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ===== Environment =====
API_KEYS = [
    os.environ.get("SERP_API_KEY_1", "b813055dc67284f12a11d5882507f63c63989928e2537f40df9d54fa6f785c8e"),
    os.environ.get("SERP_API_KEY_2", "442e4f026b6fcdcf196352b7961cc9144c6b2fb10d89f132f5bd5881a3ebec14"),
    os.environ.get("SERP_API_KEY_3", "")
]
API_KEYS = [k for k in API_KEYS if k]  # remove empty
CX = os.environ.get("CX")              # REQUIRED – your Custom Search Engine ID

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ===== Helpers =====

def get_file_extension(link: str, title: str = "") -> str:
    """Try to extract file extension from link or title; fallback to 'unknown'."""
    ext_match = re.search(r'\.([a-zA-Z0-9]{2,6})(?:\?|$)', link)
    if ext_match:
        return ext_match.group(1).lower()
    if title:
        title_ext = re.search(r'\.([a-zA-Z0-9]{2,6})$', title)
        if title_ext:
            return title_ext.group(1).lower()
    return "unknown"

def is_drive_link(link: str) -> bool:
    return 'drive.google.com' in link

def search_with_pagination(query: str, api_key: str, cx: str) -> list:
    """
    Perform paginated search to retrieve ALL Drive links for the query.
    Google CSE max is 100 results total; we loop start from 1 to 91 (step 10).
    """
    all_items = []
    start = 1
    num = 10  # max per page
    url = "https://www.googleapis.com/customsearch/v1"

    while True:
        params = {
            'key': api_key,
            'cx': cx,
            'q': query,
            'num': num,
            'start': start
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                break  # stop on error, will be handled by key rotation
            data = resp.json()
            items = data.get('items', [])
            if not items:
                break  # no more results
            all_items.extend(items)
            # Check if we have reached totalResults or end of pages
            total = int(data.get('searchInformation', {}).get('totalResults', 0))
            if total <= start + num - 1 or len(items) < num:
                break
            start += num
            time.sleep(0.1)  # small delay to avoid rate limits
        except Exception:
            break  # will be caught by outer try

    return all_items

def rotate_keys_paginated(query: str, cx: str) -> tuple:
    """Try each key; returns (items_list, used_key_index)."""
    last_error = None
    for idx, key in enumerate(API_KEYS):
        try:
            items = search_with_pagination(query, key, cx)
            if items:
                logger.info(f"Key {idx+1} fetched {len(items)} items for '{query}'")
                return items, idx
            else:
                # No items, but key worked – still consider success (empty result)
                return [], idx
        except Exception as e:
            logger.warning(f"Key {idx+1} error: {e}")
            last_error = e
            continue
    raise Exception("All API keys failed") from last_error

# ===== Routes =====

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "branding": "⚡ Powered by DARK TECH ZONE",
        "keys_available": len(API_KEYS),
        "cx_configured": bool(CX)
    })

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('q')
    if not query:
        return jsonify({'error': 'Missing "q" parameter'}), 400
    if not CX:
        return jsonify({'error': 'Search engine ID (CX) not configured'}), 500

    try:
        items, used_idx = rotate_keys_paginated(query, CX)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return jsonify({'error': 'Search failed', 'details': str(e)}), 503

    drive_links = []
    for item in items:
        link = item.get('link', '')
        if not is_drive_link(link):
            continue
        title = item.get('title', '')
        snippet = item.get('snippet', '')
        ext = get_file_extension(link, title)
        drive_links.append({
            'title': title,
            'link': link,
            'snippet': snippet,
            'file_extension': ext
        })

    return jsonify({
        'query': query,
        'total_results_found': len(items),
        'drive_links_found': len(drive_links),
        'drive_links': drive_links,
        'source_key_index': used_idx + 1,
        'source_key_prefix': API_KEYS[used_idx][:8] + '...' if used_idx < len(API_KEYS) else None,
        'branding': '⚡ Powered by DARK TECH ZONE'
    })

@app.route('/', methods=['GET'])
def root():
    return jsonify({
        'service': 'Google Drive Course Finder – All Results',
        'version': '2.0',
        'endpoints': {
            '/search': '?q=course_name (fetches all Drive links, any format)',
            '/health': 'Health check'
        },
        'branding': '⚡ Powered by DARK TECH ZONE'
    })

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
