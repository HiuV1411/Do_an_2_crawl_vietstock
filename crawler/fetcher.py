"""
HTTP Fetcher với cơ chế retry tự động (tenacity).
Giả lập trình duyệt để tránh bị chặn.
"""
import time
import os
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from utils.logger import logger

TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://cafef.vn/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


@retry(
    reraise=True,
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=60, max=240),
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
)
def fetch_html(url: str) -> str:
    """
    Tải HTML của URL. Tự động retry tối đa MAX_RETRIES lần
    với exponential backoff (60s → 120s → 240s).
    Raises requests.HTTPError nếu status != 200.
    """
    logger.info(f"[Fetcher] GET {url}")
    resp = SESSION.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text