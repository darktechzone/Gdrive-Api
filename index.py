"""
Google Drive Course Finder API
Professional grade – key rotation, error handling, logging, CORS, and branding.
"""
import os
import re
import time
import logging
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps

# ===== Configuration =====
app = Flask(__name__)
CORS(app)  # Allow all origins for public API

# Environment variables
API_KEYS = [
    os.environ.get("SERP_API_KEY_1", "b813055dc67284f12a11d5882507f63c63989928e2537f40df9d54fa6f785c8e"),
    os.environ.get("SERP_API_KEY_2", "442e4f026b6fcdcf196352b7961cc9144c6b2fb10d89f132f5bd5881a3ebec14"),
    os.environ.get("SERP_API_KEY_3", "")
]
# Remove any empty keys
API_KEYS = [key for key in API_KEYS if key]

CX = os.environ.get("CX")  # Custom Search Engine ID – REQUIRED
if not CX:
    logging.warning("CX environment variable not set – search will fail.")

# ===== Logging =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ===== Helper Functions =====

def extract_file_extension(link: str, title: str = "") -> str:
    """
    Attempt to determine file extension from link or title.
    Falls back to 'unknown'.
    """
    # First, try to extract from the link query parameters or path
    # Pattern: /file/d/ID or /uc?export=download&id=ID
    # The extension might be in the title or in the link's filename parameter.
    # Check if the link ends with a known extension
    ext_match = re.search(r'\.([a-zA-Z0-9]{2,6})(?:\?|$)', link)
    if ext_match:
        return ext_match.group(1).lower()

    # Check title for extension (e.g., "presentation.pptx")
    if title:
        title_ext = re.search(r'\.([a-zA-Z0-9]{2,6})$', title)
        if title_ext:
            return title_ext.group(1).lower()

    return "unknown"

def is_drive_link(link: str) -> bool:
    """Check if a link is a Google Drive file or folder link."""
    return 'drive.google.com' in link

def search_google(query: str, api_key: str, cx: str, num: int = 10) -> dict:
    """
    Perform a single search request to Google Custom Search API.
    Returns the full JSON response or raises an exception.
    """
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': api_key,
        'cx': cx,
        'q': query,
        'num': min(num, 10)  # max 10 per request
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()  # Raise HTTPError for bad responses
    return response.json()

def rotate_keys_search(query: str, cx: str, num: int = 10) -> tuple:
    """
    Try each API key in order until one succeeds.
    Returns (data, used_key_index) or raises an exception.
    """
    last_error = None
    for idx, key in enumerate(API_KEYS):
        try:
            data = search_google(query, key, cx, num)
            logger.info(f"Key {idx+1} succeeded for query: {query}")
            return data, idx
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            if status_code in (429, 403):
                # Quota exceeded or key disabled – try next
                logger.warning(f"Key {idx+1} failed with {status_code}: {e}")
                last_error = e
                continue
            else:
                # Other HTTP error – raise immediately
                logger.error(f"Key {idx+1} fatal error: {e}")
                raise
        except Exception as e:
            logger.error(f"Key {idx+1} unexpected error: {e}")
            raise
    # If we exhaust all keys
    if last_error:
        raise last_error
    else:
        raise Exception("All API keys exhausted without a specific error.")

# ===== Route: Health Check =====
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "branding": "⚡ Powered by DARK TECH ZONE",
        "keys_available": len(API_KEYS),
        "cx_configured": bool(CX)
    })

# ===== Route: Search =====
@app.route('/search', methods=['GET'])
def search_endpoint():
    # Validate query
    query = request.args.get('q')
    if not query:
        return jsonify({'error': 'Missing "q" parameter'}), 400

    # Validate CX
    if not CX:
        return jsonify({'error': 'Search engine ID (CX) not configured'}), 500

    # Optional parameters
    try:
        num = int(request.args.get('num', 10))
        if num < 1 or num > 10:
            num = 10
    except ValueError:
        num = 10

    # Optional file type filter (after search)
    filetype = request.args.get('filetype')  # e.g., 'pdf', 'docx'

    # Perform search with key rotation
    try:
        data, used_index = rotate_keys_search(query, CX, num)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return jsonify({
            'error': 'Search failed',
            'details': str(e)
        }), 503

    # Parse results
    items = data.get('items', [])
    total_results = data.get('searchInformation', {}).get('totalResults', 0)

    drive_links = []
    for item in items:
        link = item.get('link', '')
        if not is_drive_link(link):
            continue
        title = item.get('title', '')
        snippet = item.get('snippet', '')
        ext = extract_file_extension(link, title)
        # Optional file type filter
        if filetype and ext.lower() != filetype.lower():
            continue
        drive_links.append({
            'title': title,
            'link': link,
            'snippet': snippet,
            'file_extension': ext
        })

    # Prepare response
    response = {
        'query': query,
        'total_results': int(total_results) if total_results else 0,
        'drive_links_found': len(drive_links),
        'drive_links': drive_links,
        'source_key_index': used_index + 1,  # 1-based for user
        'source_key_prefix': API_KEYS[used_index][:8] + '...' if used_index < len(API_KEYS) else None,
        'branding': '⚡ Powered by DARK TECH ZONE'
    }

    return jsonify(response)

# ===== Route: Root =====
@app.route('/', methods=['GET'])
def root():
    return jsonify({
        'service': 'Google Drive Course Finder API',
        'version': '1.0',
        'endpoints': {
            '/search': 'Search for course materials – use ?q=course_name&num=10&filetype=pdf',
            '/health': 'Health check'
        },
        'branding': '⚡ Powered by DARK TECH ZONE'
    })

# ===== Error Handlers =====
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal server error: {e}")
    return jsonify({'error': 'Internal server error'}), 500

# ===== Local Development =====
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
