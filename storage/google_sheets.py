"""
Google Sheets Writer.
Ghi dữ liệu vào các sheet: NEWS_RAW, CRAWL_LOG, DAILY_SUMMARY.
Dùng gspread batch_update để tối ưu quota API.
"""
import os
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from crawler.parser import Article
from utils.hash import make_news_id, url_hash
from utils.logger import logger

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Tên các sheet — phải trùng khớp với file Spreadsheet thực tế
SHEET_NEWS_RAW     = "NEWS_RAW"
SHEET_CRAWL_LOG    = "CRAWL_LOG"
SHEET_DAILY_SUMMARY = "DAILY_SUMMARY"

# Thứ tự cột NEWS_RAW (theo tài liệu đồ án)
NEWS_RAW_HEADERS = [
    "news_id", "title", "summary", "content",
    "published_date", "source", "url",
    "industry_group", "tickers", "keywords", "event_type",
    "crawl_time", "content_hash", "crawl_status",
    "error_message", "checked_by", "checked_time", "note",
]

CRAWL_LOG_HEADERS = [
    "log_id", "crawl_time", "session", "total_found",
    "new_articles", "duplicates", "failed", "duration_sec", "note",
]

DAILY_SUMMARY_HEADERS = [
    "date", "morning_count", "evening_count",
    "total_count", "last_updated",
]

BATCH_SIZE = 20  # Số dòng ghi một lần để tránh vượt quota


def _get_client() -> gspread.Client:
    import json

    # GitHub Actions: đọc credentials từ biến môi trường
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # Local: đọc từ file
        cred_path = os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_PATH",
            "credentials/service_account.json"
        )
        creds = Credentials.from_service_account_file(cred_path, scopes=SCOPES)

    return gspread.authorize(creds)


def _get_or_create_sheet(spreadsheet: gspread.Spreadsheet, name: str, headers: list[str]):
    """Lấy sheet theo tên. Nếu chưa có thì tạo mới và ghi header."""
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        logger.info(f"[Sheets] Tạo sheet mới: {name}")
        ws = spreadsheet.add_worksheet(title=name, rows=10000, cols=len(headers))
        ws.append_row(headers, value_input_option="USER_ENTERED")
    return ws


def _ensure_headers(ws: gspread.Worksheet, headers: list[str]):
    """Nếu sheet trống (không có header) thì ghi header vào dòng 1."""
    first_row = ws.row_values(1)
    if not first_row:
        ws.append_row(headers, value_input_option="USER_ENTERED")


def write_news_raw(articles: list[Article], stats: dict, session: str) -> int:
    """
    Ghi danh sách Article vào sheet NEWS_RAW.
    Ghi theo lô BATCH_SIZE để tối ưu API quota.
    Trả về số dòng đã ghi thành công.
    """
    if not articles:
        logger.info("[Sheets] Không có bài mới để ghi.")
        return 0

    spreadsheet_id = os.getenv("SPREADSHEET_ID", "")
    source_id = os.getenv("SOURCE_ID", "CAFEF")
    industry_group = os.getenv("INDUSTRY_GROUP", "")

    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_sheet(spreadsheet, SHEET_NEWS_RAW, NEWS_RAW_HEADERS)
    _ensure_headers(ws, NEWS_RAW_HEADERS)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_to_write: list[list] = []

    for article in articles:
        date_part = datetime.now().strftime("%Y%m%d")
        news_id = make_news_id(source_id, date_part, article.url)
        content_hash_val = url_hash(article.url)  # hash URL làm dedup key

        row = [
            news_id,                     # news_id
            article.title,               # title
            article.summary,             # summary
            article.content,             # content
            article.published_date,      # published_date
            "CafeF",                     # source
            article.url,                 # url
            industry_group,              # industry_group
            "",                          # tickers (để trống, xử lý thủ công hoặc mở rộng sau)
            ", ".join(article.tags),     # keywords (dùng tags làm keywords)
            "",                          # event_type (để trống)
            now_str,                     # crawl_time
            content_hash_val,            # content_hash
            "success",                   # crawl_status
            "",                          # error_message
            "",                          # checked_by
            "",                          # checked_time
            "",                          # note
        ]
        rows_to_write.append(row)

    # Ghi theo lô
    written = 0
    for i in range(0, len(rows_to_write), BATCH_SIZE):
        batch = rows_to_write[i: i + BATCH_SIZE]
        ws.append_rows(batch, value_input_option="USER_ENTERED")
        written += len(batch)
        logger.info(f"[Sheets] Đã ghi {written}/{len(rows_to_write)} dòng vào {SHEET_NEWS_RAW}")

    return written


def write_crawl_log(session: str, stats: dict, duration_sec: float, note: str = "") -> None:
    """Ghi một dòng log vào sheet CRAWL_LOG."""
    spreadsheet_id = os.getenv("SPREADSHEET_ID", "")
    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_sheet(spreadsheet, SHEET_CRAWL_LOG, CRAWL_LOG_HEADERS)
    _ensure_headers(ws, CRAWL_LOG_HEADERS)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_part = datetime.now().strftime("%Y%m%d")
    log_id = f"LOG_{date_part}_{session[:3].upper()}_{int(datetime.now().timestamp())}"

    row = [
        log_id,
        now_str,
        session,
        stats.get("total_found", 0),
        stats.get("new", 0),
        stats.get("duplicate", 0),
        stats.get("failed", 0),
        round(duration_sec, 1),
        note,
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"[Sheets] Đã ghi log vào {SHEET_CRAWL_LOG}: {log_id}")


def update_daily_summary(new_count: int, session: str) -> None:
    """
    Cập nhật DAILY_SUMMARY: cộng dồn số bài theo buổi sáng/chiều.
    Nếu đã có dòng hôm nay thì cập nhật, chưa có thì tạo mới.
    """
    spreadsheet_id = os.getenv("SPREADSHEET_ID", "")
    client = _get_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_sheet(spreadsheet, SHEET_DAILY_SUMMARY, DAILY_SUMMARY_HEADERS)
    _ensure_headers(ws, DAILY_SUMMARY_HEADERS)

    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Tìm dòng hôm nay
    all_values = ws.get_all_values()
    today_row_idx = None
    for i, row in enumerate(all_values):
        if row and row[0] == today:
            today_row_idx = i + 1  # 1-indexed
            break

    is_morning = "MORNING" in session.upper()

    if today_row_idx:
        # Đọc giá trị hiện tại và cộng thêm
        existing = ws.row_values(today_row_idx)
        morning = int(existing[1]) if len(existing) > 1 and existing[1].isdigit() else 0
        evening = int(existing[2]) if len(existing) > 2 and existing[2].isdigit() else 0

        if is_morning:
            morning += new_count
        else:
            evening += new_count

        total = morning + evening
        ws.update(
            f"A{today_row_idx}:E{today_row_idx}",
            [[today, morning, evening, total, now_str]],
        )
    else:
        # Tạo dòng mới
        morning = new_count if is_morning else 0
        evening = 0 if is_morning else new_count
        ws.append_row(
            [today, morning, evening, morning + evening, now_str],
            value_input_option="USER_ENTERED",
        )

    logger.info(f"[Sheets] Đã cập nhật {SHEET_DAILY_SUMMARY} cho {today}")