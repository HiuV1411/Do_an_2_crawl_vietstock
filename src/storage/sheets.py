"""
sheets.py
=========
Toàn bộ tương tác với Google Sheets qua thư viện gspread.

Chức năng:
  - Kết nối (authenticate)
  - Load seen_urls từ NEWS_RAW để dedup
  - Ghi bài mới vào NEWS_RAW (batch)
  - Ghi log vào CRAWL_LOG
  - Cập nhật DAILY_SUMMARY
"""

import json
import logging
import time
from datetime import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from src.config import (
    SPREADSHEET_ID,
    GSPREAD_CREDS_JSON,
    SHEET_NEWS_RAW,
    SHEET_CRAWL_LOG,
    SHEET_DAILY_SUMMARY,
    BATCH_WRITE_SIZE,
    SOURCE_NAME,
    INDUSTRY_GROUP,
)
from src.crawler.utils import normalize_url, now_str, today_str

logger = logging.getLogger(__name__)

# Scopes cần thiết để đọc/ghi Google Sheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Cột URL trong sheet NEWS_RAW (cột G = index 6, 0-based)
COL_URL_INDEX = 6   # cột 'url' là cột thứ 7 (G), index 6


# ---------------------------------------------------------------------------
# Kết nối
# ---------------------------------------------------------------------------

def get_client() -> gspread.Client:
    """
    Tạo gspread Client từ Service Account credentials.

    Credentials được đọc từ biến môi trường GSPREAD_CREDS (JSON string).
    Khi chạy local: load từ file .env
    Khi chạy GitHub Actions: load từ GitHub Secrets
    """
    if not GSPREAD_CREDS_JSON:
        raise EnvironmentError(
            "Thiếu biến môi trường GSPREAD_CREDS. "
            "Hãy copy .env.example thành .env và điền credentials."
        )

    try:
        creds_dict = json.loads(GSPREAD_CREDS_JSON)
    except json.JSONDecodeError as e:
        raise ValueError(f"GSPREAD_CREDS không phải JSON hợp lệ: {e}")

    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    logger.debug("✓ Đã kết nối Google Sheets API")
    return client


def get_spreadsheet(client: gspread.Client) -> gspread.Spreadsheet:
    """Mở Spreadsheet theo SPREADSHEET_ID."""
    if not SPREADSHEET_ID:
        raise EnvironmentError("Thiếu biến môi trường SPREADSHEET_ID.")
    return client.open_by_key(SPREADSHEET_ID)


# ---------------------------------------------------------------------------
# Dedup: load URL đã crawl
# ---------------------------------------------------------------------------

def load_seen_urls(spreadsheet: gspread.Spreadsheet) -> set[str]:
    """
    Đọc toàn bộ cột 'url' từ sheet NEWS_RAW.
    Trả về set các URL đã normalize → dùng làm bộ lọc dedup.

    Chỉ gọi API 1 lần duy nhất (col_values), rất nhanh dù có nhiều nghìn hàng.
    """
    try:
        ws = spreadsheet.worksheet(SHEET_NEWS_RAW)
        # col_values trả về danh sách string của 1 cột, bỏ hàng header (index 0)
        # Cột G = cột 7 (gspread dùng 1-based)
        raw_urls = ws.col_values(COL_URL_INDEX + 1)[1:]   # bỏ header

        seen = {normalize_url(u) for u in raw_urls if u.strip()}
        logger.info(f"✓ Đã load {len(seen)} URL từ NEWS_RAW (dedup cache)")
        return seen

    except gspread.WorksheetNotFound:
        logger.warning(f"⚠ Sheet '{SHEET_NEWS_RAW}' chưa có — sẽ tạo mới khi ghi")
        return set()
    except Exception as e:
        logger.error(f"✗ Lỗi load seen_urls: {e}")
        return set()


# ---------------------------------------------------------------------------
# Header NEWS_RAW (18 cột)
# ---------------------------------------------------------------------------

NEWS_RAW_HEADERS = [
    # 12 cột BẮT BUỘC
    "news_id",
    "title",
    "summary",
    "content",
    "published_date",
    "source",
    "url",
    "industry_group",
    "tickers",
    "keywords",
    "event_type",
    "crawl_time",
    # 6 cột NÊN CÓ
    "content_hash",
    "crawl_status",
    "error_message",
    "checked_by",
    "checked_time",
    "note",
]


def _ensure_header(ws: gspread.Worksheet) -> None:
    """
    Kiểm tra row 1 có phải header chưa.
    Nếu sheet trống → ghi header vào row 1.
    """
    first_row = ws.row_values(1)
    if not first_row or first_row[0] != "news_id":
        ws.insert_row(NEWS_RAW_HEADERS, index=1)
        # Format header: bold
        ws.format("A1:R1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.9},
        })
        logger.info("✓ Đã tạo header cho NEWS_RAW")


def _article_to_row(article: dict) -> list:
    """Chuyển dict bài viết thành list theo thứ tự NEWS_RAW_HEADERS."""
    return [str(article.get(col, "")) for col in NEWS_RAW_HEADERS]


# ---------------------------------------------------------------------------
# Ghi NEWS_RAW
# ---------------------------------------------------------------------------

def write_news_raw(
    spreadsheet: gspread.Spreadsheet,
    articles: list[dict],
) -> int:
    """
    Ghi danh sách bài mới vào sheet NEWS_RAW theo batch.

    Args:
        spreadsheet: gspread.Spreadsheet đang mở
        articles:    Danh sách dict bài viết (output của crawler)

    Returns:
        Số hàng đã ghi thành công
    """
    if not articles:
        logger.info("Không có bài mới để ghi vào NEWS_RAW")
        return 0

    try:
        ws = spreadsheet.worksheet(SHEET_NEWS_RAW)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(SHEET_NEWS_RAW, rows=10000, cols=20)
        logger.info(f"✓ Đã tạo sheet '{SHEET_NEWS_RAW}'")

    _ensure_header(ws)

    # Chuyển articles thành list of list
    rows_to_write = [_article_to_row(a) for a in articles]
    total_written = 0

    # Ghi theo batch để tránh timeout và vượt quota API
    for i in range(0, len(rows_to_write), BATCH_WRITE_SIZE):
        batch = rows_to_write[i : i + BATCH_WRITE_SIZE]
        try:
            ws.append_rows(batch, value_input_option="USER_ENTERED")
            total_written += len(batch)
            logger.info(f"  ✓ Đã ghi batch {i//BATCH_WRITE_SIZE + 1}: {len(batch)} hàng")

            # Pause nhỏ giữa các batch để tránh quota 429
            if i + BATCH_WRITE_SIZE < len(rows_to_write):
                time.sleep(1.5)

        except gspread.exceptions.APIError as e:
            if "429" in str(e):
                logger.warning("  ⚠ Quota API (429) — chờ 60 giây rồi thử lại...")
                time.sleep(60)
                ws.append_rows(batch, value_input_option="USER_ENTERED")
                total_written += len(batch)
            else:
                raise

    logger.info(f"✓ Tổng cộng đã ghi {total_written} hàng vào NEWS_RAW")
    return total_written


# ---------------------------------------------------------------------------
# Ghi CRAWL_LOG
# ---------------------------------------------------------------------------

CRAWL_LOG_HEADERS = [
    "log_date", "member", "source", "keyword_group",
    "date_range", "records_found", "records_added",
    "duplicates", "failed", "status", "note",
]


def write_crawl_log(
    spreadsheet: gspread.Spreadsheet,
    stats: dict,
    session_label: str = "",
    error_note: str = "",
) -> None:
    """
    Ghi 1 dòng vào CRAWL_LOG sau mỗi lần crawl.

    Args:
        spreadsheet:   Spreadsheet đang mở
        stats:         {found, new, skipped_duplicate, failed}
        session_label: 'morning' hoặc 'evening'
        error_note:    Mô tả lỗi nếu có
    """
    try:
        ws = spreadsheet.worksheet(SHEET_CRAWL_LOG)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(SHEET_CRAWL_LOG, rows=2000, cols=15)
        ws.insert_row(CRAWL_LOG_HEADERS, index=1)
        ws.format("A1:K1", {"textFormat": {"bold": True}})

    status = "done" if stats.get("failed", 0) == 0 else "partial"
    if stats.get("new", 0) == 0 and stats.get("failed", 0) > 0:
        status = "failed"

    note = f"Session: {session_label}"
    if error_note:
        note += f" | Lỗi: {error_note}"

    row = [
        today_str(),                          # log_date
        "GitHub Actions (auto)",              # member
        SOURCE_NAME,                          # source
        INDUSTRY_GROUP,                       # keyword_group
        today_str(),                          # date_range
        stats.get("found", 0),               # records_found
        stats.get("new", 0),                 # records_added
        stats.get("skipped_duplicate", 0),   # duplicates
        stats.get("failed", 0),              # failed
        status,                              # status
        note,                                # note
    ]

    ws.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"✓ Đã ghi CRAWL_LOG: {row}")


# ---------------------------------------------------------------------------
# Cập nhật DAILY_SUMMARY
# ---------------------------------------------------------------------------

DAILY_SUMMARY_HEADERS = [
    "date", "total_records", "new_records_today", "sources_updated",
    "date_coverage_from", "date_coverage_to", "missing_days",
    "duplicate_count", "issue_status", "next_action",
]


def update_daily_summary(
    spreadsheet: gspread.Spreadsheet,
    new_count: int,
    duplicate_count: int,
) -> None:
    """
    Cập nhật hoặc thêm 1 dòng trong DAILY_SUMMARY cho ngày hôm nay.
    """
    try:
        ws_news = spreadsheet.worksheet(SHEET_NEWS_RAW)
        total_rows = len(ws_news.col_values(1)) - 1  # trừ header
    except Exception:
        total_rows = 0

    try:
        ws = spreadsheet.worksheet(SHEET_DAILY_SUMMARY)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(SHEET_DAILY_SUMMARY, rows=1000, cols=12)
        ws.insert_row(DAILY_SUMMARY_HEADERS, index=1)
        ws.format("A1:J1", {"textFormat": {"bold": True}})

    today = today_str()

    # Kiểm tra đã có dòng cho ngày hôm nay chưa
    dates_col = ws.col_values(1)[1:]  # bỏ header
    if today in dates_col:
        # Cập nhật dòng hiện có
        row_idx = dates_col.index(today) + 2  # +2 vì 1-based + header
        ws.update_cell(row_idx, 3, new_count)            # new_records_today
        ws.update_cell(row_idx, 2, total_rows)           # total_records
        ws.update_cell(row_idx, 8, duplicate_count)      # duplicate_count
        logger.info(f"✓ Đã cập nhật DAILY_SUMMARY ngày {today}")
    else:
        # Thêm dòng mới
        row = [
            today,          # date
            total_rows,     # total_records
            new_count,      # new_records_today
            SOURCE_NAME,    # sources_updated
            "",             # date_coverage_from
            today,          # date_coverage_to
            "",             # missing_days
            duplicate_count, # duplicate_count
            "",             # issue_status
            "",             # next_action
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
        logger.info(f"✓ Đã thêm dòng DAILY_SUMMARY ngày {today}")