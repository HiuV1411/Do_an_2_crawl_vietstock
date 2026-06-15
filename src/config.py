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
SOURCE_ID   = "TINNHANH"
SOURCE_NAME = "Tin nhanh chứng khoán"

# ---------------------------------------------------------------------------
# Vietstock — URL và selector
# ---------------------------------------------------------------------------
BASE_URL    = "https://www.tinnhanhchungkhoan.vn"
 
# Trang listing chính — trang chủ đã chứa tin mới nhất theo thứ tự
# Phân trang: ?page=2, ?page=3, ...
LISTING_URL = "https://www.tinnhanhchungkhoan.vn"

# Các chuyên mục cần crawl và nhãn tương ứng
CATEGORIES = {
    "Chứng khoán":            "https://www.tinnhanhchungkhoan.vn/chung-khoan/",
    "Nhận định":              "https://www.tinnhanhchungkhoan.vn/nhan-dinh/",
    "Vĩ mô":                  "https://www.tinnhanhchungkhoan.vn/vi-mo/",
    "Thông tin doanh nghiệp": "https://www.tinnhanhchungkhoan.vn/thong-tin-doanh-nghiep/",
    "Tài chính - Ngân hàng":  "https://www.tinnhanhchungkhoan.vn/tai-chinh-ngan-hang/",
    "Địa ốc":                 "https://www.tinnhanhchungkhoan.vn/dia-oc/",
    "Quốc tế":                "https://www.tinnhanhchungkhoan.vn/quoc-te/",
    "Trái phiếu":             "https://www.tinnhanhchungkhoan.vn/trai-phieu/",
}

# CSS Selectors cho trang listing
LISTING_SELECTORS = {
    # Mỗi bài báo trong listing là 1 thẻ h2 có chứa link
    "article_item":   "h2, h3",
    # Link + tiêu đề bên trong
    "title_link":     "a[href*='-post']",
    # Ngày thường nằm trong text node cạnh link
    "published_date": "span.time, span.date, time",
    # Thumbnail (nếu có)
    "thumbnail":      "img[src*='tinnhanhchungkhoan'], img[src*='image.tinnhanhchungkhoan']",
}

# CSS Selectors cho trang bài viết chi tiết
DETAIL_SELECTORS = {
    "title":          "h1",
    "summary":        "meta[name='description']",          # dùng attr content
    "content":        "div.detail-content, div.content-detail, article div.text",
    "published_date": "meta[property='article:published_time']",  # ISO datetime chính xác nhất
    "author":         "a[href*='author-search']",
    "category":       "meta[property='article:section']",  # "Nhận định,Chứng khoán"
    "tags":           "meta[name='article:tag']",           # "SHS,VN-Index,Dòng tiền,..."
    "article_id":     "meta[name='dable:item_id']",         # "391857"
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
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language":         "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding":         "gzip, deflate, br",
    "Connection":              "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":          "document",
    "Sec-Fetch-Mode":          "navigate",
    "Sec-Fetch-Site":          "none",
    "Sec-Fetch-User":          "?1",
    "Cache-Control":           "max-age=0",
    "Referer":                 "https://www.tinnhanhchungkhoan.vn/",
}

# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------
TIMEZONE = "Asia/Ho_Chi_Minh"