"""
Tiện ích tạo hash cho URL và news_id.
Dùng SHA-256 trên canonical URL để dedup chính xác.
"""
import hashlib
import re
from urllib.parse import urlparse, urlunparse


def canonical_url(url: str) -> str:
    """Chuẩn hoá URL: bỏ query string, fragment, trailing slash."""
    p = urlparse(url.strip())
    path = p.path.rstrip("/")
    return urlunparse((p.scheme, p.netloc, path, "", "", ""))


def url_hash(url: str) -> str:
    """Trả về SHA-256 hex của canonical URL (12 ký tự đầu)."""
    canon = canonical_url(url)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12].upper()


def make_news_id(source_id: str, date_str: str, url: str) -> str:
    """
    Tạo news_id theo định dạng: SOURCE_YYYYMMDD_HASH
    Ví dụ: CAFEF_20250614_A1B2C3D4E5F6
    """
    h = url_hash(url)
    return f"{source_id}_{date_str}_{h}"