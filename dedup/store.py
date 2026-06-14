"""
Deduplication store dùng SQLite.
Lưu hash của URL đã crawl thành công.
Tự động dọn dẹp record cũ hơn 30 ngày.
"""
import sqlite3
import os
from datetime import datetime, timedelta
from utils.logger import logger
from utils.hash import url_hash


DB_PATH = os.path.join("data", "seen_urls.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_urls (
            url_hash    TEXT PRIMARY KEY,
            url         TEXT NOT NULL,
            crawled_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def is_seen(url: str) -> bool:
    """Kiểm tra URL đã được crawl trước đó chưa."""
    h = url_hash(url)
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT 1 FROM seen_urls WHERE url_hash = ?", (h,)
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def mark_seen(url: str) -> None:
    """Đánh dấu URL đã crawl thành công."""
    h = url_hash(url)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO seen_urls (url_hash, url, crawled_at) VALUES (?, ?, ?)",
            (h, url, now),
        )
        conn.commit()
    finally:
        conn.close()


def cleanup_old_records(days: int = 30) -> int:
    """Xoá các record cũ hơn `days` ngày. Trả về số dòng đã xoá."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = _get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM seen_urls WHERE crawled_at < ?", (cutoff,)
        )
        conn.commit()
        deleted = cur.rowcount
        if deleted > 0:
            logger.info(f"[Dedup] Đã dọn {deleted} record cũ hơn {days} ngày.")
        return deleted
    finally:
        conn.close()


def count_seen() -> int:
    """Đếm tổng số URL đã seen trong DB."""
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM seen_urls")
        return cur.fetchone()[0]
    finally:
        conn.close()