"""
utils.py
========
Các hàm tiện ích dùng chung cho toàn bộ crawler.
"""

import hashlib
import re
import time
import logging
from datetime import datetime
from urllib.parse import urlparse, urlunparse

import pytz
import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from src.config import (
    REQUEST_HEADERS,
    REQUEST_TIMEOUT,
    MAX_RETRY,
    SOURCE_ID,
    TIMEZONE,
    KEYWORDS_MAP,
)

logger = logging.getLogger(__name__)
TZ = pytz.timezone(TIMEZONE)


# ---------------------------------------------------------------------------
# Thời gian
# ---------------------------------------------------------------------------

def now_vn() -> datetime:
    """Trả về datetime hiện tại theo múi giờ Việt Nam."""
    return datetime.now(TZ)


def now_str() -> str:
    """Chuỗi thời gian hiện tại dạng YYYY-MM-DD HH:MM:SS."""
    return now_vn().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    """Ngày hôm nay dạng YYYY-MM-DD."""
    return now_vn().strftime("%Y-%m-%d")


def crawl_session_label() -> str:
    """
    Trả về nhãn phiên crawl: 'morning' nếu trước 14:00, 'evening' nếu sau.
    Dùng để điền cột crawl_session trong CRAWL_LOG.
    """
    hour = now_vn().hour
    return "morning" if hour < 14 else "evening"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """
    Chuẩn hóa URL để dùng làm khóa dedup:
    - Lowercase toàn bộ
    - Loại bỏ trailing slash
    - Bỏ query params và fragment (chỉ giữ scheme + netloc + path)
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip().lower())
        clean_path = parsed.path.rstrip("/")
        return urlunparse((parsed.scheme, parsed.netloc, clean_path, "", "", ""))
    except Exception:
        return url.strip().lower()


def extract_article_id(url: str) -> str:
    """
    Trích xuất ID bài viết từ URL Vietstock.
    Vietstock thường có dạng: /ten-bai-viet-123456789.htm
    → trả về '123456789'
    Nếu không tìm thấy số → trả về 8 ký tự đầu của MD5(url).
    """
    # Thử match số cuối trong path trước .htm
    match = re.search(r"-(\d{6,12})\.htm", url)
    if match:
        return match.group(1)
    # Fallback: dùng hash của URL
    return hashlib.md5(url.encode()).hexdigest()[:8].upper()


# ---------------------------------------------------------------------------
# news_id
# ---------------------------------------------------------------------------

def make_news_id(url: str, published_date: str) -> str:
    """
    Tạo news_id theo quy tắc: SOURCE_YYYYMMDD_HASH
    Ví dụ: VIETSTOCK_20250320_F9E8D7

    Args:
        url:            URL bài viết
        published_date: Chuỗi ngày đăng (bất kỳ format nào có YYYY-MM-DD)
    """
    # Lấy phần YYYYMMDD từ published_date
    date_part = re.sub(r"[^0-9]", "", published_date or "")[:8]
    if len(date_part) < 8:
        date_part = today_str().replace("-", "")

    # HASH: 6 ký tự cuối từ MD5(URL)
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[-6:].upper()

    return f"{SOURCE_ID}_{date_part}_{url_hash}"


def make_content_hash(title: str, content: str) -> str:
    """
    Tạo content_hash từ tiêu đề + nội dung (dùng để phát hiện bài trùng nội dung).
    """
    raw = (title or "") + (content or "")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# HTTP request với retry
# ---------------------------------------------------------------------------

@retry(
    stop=stop_after_attempt(MAX_RETRY),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def safe_get(url: str, session: requests.Session = None) -> requests.Response:
    """
    HTTP GET với retry tự động khi lỗi mạng.
    Raise HTTPError nếu status không phải 2xx.
    """
    client = session or requests
    resp = client.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# Phân loại từ khóa & event_type
# ---------------------------------------------------------------------------

def extract_keywords_and_event(title: str, summary: str, content: str) -> tuple[str, str]:
    """
    Quét title + summary + content để tìm từ khóa và gợi ý event_type.

    Returns:
        (keywords_str, event_type_str)
        keywords_str: các từ khóa tìm thấy, cách nhau bằng dấu phẩy
        event_type_str: loại sự kiện gợi ý đầu tiên tìm thấy
    """
    text = " ".join([
        (title or "").lower(),
        (summary or "").lower(),
        (content or "")[:500].lower(),
    ])

    found_keywords = []
    found_events = []

    for kw, event in KEYWORDS_MAP.items():
        if kw in text:
            found_keywords.append(kw)
            if event not in found_events:
                found_events.append(event)

    return (
        ", ".join(found_keywords) if found_keywords else "",
        found_events[0] if found_events else "tin tức",
    )


# ---------------------------------------------------------------------------
# Trích xuất mã cổ phiếu từ text
# ---------------------------------------------------------------------------

def extract_tickers_from_text(text: str) -> str:
    """
    Tìm các mã cổ phiếu Việt Nam (2-4 chữ hoa liên tiếp) trong văn bản.
    Loại bỏ các từ viết tắt thông thường không phải mã CK.

    Returns: chuỗi các mã, cách nhau bằng dấu phẩy. Ví dụ: "VCB, BID, CTG"
    """
    EXCLUDE = {
        "VN", "HN", "TP", "HCM", "GDP", "CPI", "IPO", "ETF", "VND",
        "USD", "EUR", "CEO", "CFO", "COO", "HOSE", "HNX", "UPCOM",
        "BSC", "SSC", "SBV", "MOF", "PM", "NN",
    }
    # Mã CK Việt Nam: 2-4 chữ cái in hoa, đứng riêng
    pattern = r"\b([A-Z]{2,4})\b"
    candidates = re.findall(pattern, text or "")
    tickers = sorted(set(c for c in candidates if c not in EXCLUDE))
    return ", ".join(tickers[:10])  # giới hạn 10 mã


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(level: int = logging.INFO) -> None:
    """Khởi tạo logging với format chuẩn."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )