"""
config.py
=========
Toàn bộ cấu hình hệ thống tập trung tại đây.
Thay đổi cấu hình chỉ cần sửa file này, không đụng code logic.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
GSPREAD_CREDS_JSON = os.getenv("GSPREAD_CREDS", "")   # JSON string từ Secret

# Tên các sheet (phải khớp chính xác với file Spreadsheet)
SHEET_NEWS_RAW       = "NEWS_RAW"
SHEET_CRAWL_LOG      = "CRAWL_LOG"
SHEET_DAILY_SUMMARY  = "DAILY_SUMMARY"
SHEET_CONFIG_SOURCES = "CONFIG_SOURCES"

# ---------------------------------------------------------------------------
# Thông tin nhóm (điền theo nhóm của bạn)
# ---------------------------------------------------------------------------
INDUSTRY_GROUP = os.getenv("INDUSTRY_GROUP", "Ngân hàng - Chứng khoán - Bảo hiểm")
GROUP_ID       = os.getenv("GROUP_ID", "G1")
SOURCE_ID      = "VIETSTOCK"
SOURCE_NAME    = "Vietstock"

# ---------------------------------------------------------------------------
# Vietstock — URL và selector
# ---------------------------------------------------------------------------
BASE_URL      = "https://vietstock.vn"
LISTING_URL   = "https://vietstock.vn/chu-de/1-2/moi-cap-nhat.htm"

# Các chuyên mục cần crawl và nhãn tương ứng
CATEGORIES = {
    "Chứng khoán":      "https://vietstock.vn/chung-khoan.htm",
    "Doanh nghiệp":     "https://vietstock.vn/doanh-nghiep.htm",
    "Tài chính":        "https://vietstock.vn/tai-chinh.htm",
    "Bất động sản":     "https://vietstock.vn/bat-dong-san.htm",
    "Vĩ mô":            "https://vietstock.vn/kinh-te/vi-mo.htm",
    "Hàng hóa":         "https://vietstock.vn/hang-hoa.htm",
    "Kinh tế - Đầu tư": "https://vietstock.vn/kinh-te/kinh-te-dau-tu.htm",
    "Thế giới":         "https://vietstock.vn/the-gioi.htm",
}

# CSS Selectors cho trang listing
LISTING_SELECTORS = {
    # Container mỗi bài trong danh sách
    "article_item":    "div.news-item, article.news-item, div.item-news",
    # Tiêu đề + link
    "title_link":      "h2 a, h3 a, .title a, .news-title a",
    # Tóm tắt ngắn
    "summary":         "p.sapo, p.summary, .brief, .intro",
    # Ngày đăng
    "published_date":  "span.time, time, .date, .post-time",
    # Ảnh thumbnail
    "thumbnail":       "img.lazy, img[data-src], .thumb img",
}

# CSS Selectors cho trang bài viết chi tiết
DETAIL_SELECTORS = {
    "title":          "h1.article-title, h1.title, h1",
    "summary":        "p.sapo, p.summary, .article-sapo, h2.sapo",
    "content":        "div.article-content, div.content-detail, div#article-body",
    "published_date": "span.time, span.date, time[datetime], .article-time",
    "author":         "span.author, .author-name, .by-author",
    "category":       "div.breadcrumb a:last-child, .category-name",
    "tags":           "div.tags a, .article-tags a, .tag-list a",
    # Các mã cổ phiếu thường xuất hiện dạng link đến finance.vietstock.vn
    "tickers":        "a[href*='finance.vietstock.vn/'][href*='.htm']",
}

# ---------------------------------------------------------------------------
# Từ khóa phân loại (dùng để điền cột keywords & event_type)
# ---------------------------------------------------------------------------
KEYWORDS_MAP = {
    "lãi suất":              "vĩ mô",
    "nợ xấu":                "rủi ro tín dụng",
    "trái phiếu":            "trái phiếu",
    "cổ tức":                "cổ tức",
    "tăng vốn":              "tăng vốn",
    "ipo":                   "IPO",
    "m&a":                   "M&A",
    "kết quả kinh doanh":    "kết quả kinh doanh",
    "vn-index":              "thị trường chứng khoán",
    "tỷ giá":                "tỷ giá",
    "lạm phát":              "vĩ mô",
    "gdp":                   "vĩ mô",
    "giá thép":              "giá hàng hóa",
    "bất động sản":          "bất động sản",
    "niêm yết":              "niêm yết",
    "giao dịch nội bộ":      "giao dịch nội bộ",
}

# ---------------------------------------------------------------------------
# Crawler settings
# ---------------------------------------------------------------------------
MAX_PAGES        = 5        # Số trang listing tối đa mỗi lần chạy
REQUEST_DELAY    = 1.5      # Giây chờ giữa mỗi request (tránh bị block)
REQUEST_TIMEOUT  = 15       # Timeout mỗi request (giây)
MAX_RETRY        = 3        # Số lần retry khi lỗi
BATCH_WRITE_SIZE = 20       # Ghi Google Sheets mỗi batch N hàng

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------
TIMEZONE = "Asia/Ho_Chi_Minh"