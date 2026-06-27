# Tin Nhanh Chứng Khoán — Daily News Crawler

> **Đồ án Web Crawling** | Hệ thống tự động thu thập tin tức tài chính từ [tinnhanhchungkhoan.vn](https://www.tinnhanhchungkhoan.vn), lưu vào Google Sheets — **100% tự động, không cần thao tác thủ công**.

---

## Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Cấu trúc thư mục](#2-cấu-trúc-thư-mục)
3. [Cài đặt local (VS Code + môi trường ảo)](#3-cài-đặt-local-vs-code--môi-trường-ảo)
4. [Cấu hình Google Service Account](#4-cấu-hình-google-service-account)
5. [Cấu hình biến môi trường](#5-cấu-hình-biến-môi-trường)
6. [Cấu trúc Google Spreadsheet](#6-cấu-trúc-google-spreadsheet)
7. [Triển khai tự động với GitHub Actions](#7-triển-khai-tự-động-với-github-actions)
8. [Chạy thủ công để test](#8-chạy-thủ-công-để-test)
9. [Chạy Unit Test](#9-chạy-unit-test)
10. [Quy tắc chống trùng lặp (Dedup)](#10-quy-tắc-chống-trùng-lặp-dedup)
11. [Xử lý sự cố thường gặp](#11-xử-lý-sự-cố-thường-gặp)
12. [Mở rộng thêm nguồn tin](#12-mở-rộng-thêm-nguồn-tin)

---

## 1. Tổng quan hệ thống

### Nguồn dữ liệu

| Thông tin | Giá trị |
|---|---|
| Tên trang | Tin nhanh chứng khoán |
| URL | https://www.tinnhanhchungkhoan.vn |
| Cơ quan | Báo Tài chính – Đầu tư (Bộ Tài chính) |
| Loại trang | HTML tĩnh — không cần Selenium |
| Pattern URL bài | `/ten-bai-postNNNNNN.html` |

### Lịch chạy tự động

| Phiên | Giờ Việt Nam | Cron (UTC) |
|---|---|---|
| Sáng | 10:00 | `0 3 * * *` |
| Chiều | 20:30 | `30 13 * * *` |

### Tech stack

```
Python 3.11 + requests + BeautifulSoup4
    ↓ crawl HTML tĩnh
gspread + google-auth
    ↓ ghi Google Sheets
GitHub Actions
    ↓ chạy tự động theo cron
```

### Luồng hoạt động

```
GitHub Actions (cron)
    │
    ▼
[1] Kết nối Google Sheets API
    │
    ▼
[2] Load cột URL từ NEWS_RAW → tạo seen_urls set (dedup cache)
    │
    ▼
[3] Crawl trang chủ tinnhanhchungkhoan.vn
    │  ├─ Tìm tất cả link có pattern -postNNNNNN.html
    │  ├─ Nếu URL đã có trong seen_urls → DỪNG SỚM (early stop)
    │  └─ Nếu URL mới → crawl trang chi tiết
    │         ├─ Lấy từ <meta> tags: ngày ISO, tags, category, author, ID
    │         └─ Lấy nội dung bài từ div.detail-content
    │
    ▼
[4] Ghi batch vào NEWS_RAW (tối đa 20 hàng/lần gọi API)
    │
    ▼
[5] Ghi CRAWL_LOG (thống kê phiên crawl)
    │
    ▼
[6] Cập nhật DAILY_SUMMARY
```

---

## 2. Cấu trúc thư mục

```
tinnhanh-crawler/
│
├── .github/
│       └── crawl.yml              ← GitHub Actions
│
├── src/
│   ├── __init__.py
│   ├── config.py                  ← Cấu hình tập trung (URL, selector, sheet name...)
│   │
│   ├── crawler/
│   │   ├── __init__.py
│   │   ├── tinnhanh.py            ← Logic crawl chính cho tinnhanhchungkhoan.vn
│   │   └── utils.py               ← Hàm dùng chung: dedup, hash, parse date, retry...
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   └── sheets.py              ← Kết nối & ghi Google Sheets API
│   │
│   └── pipeline/
│       ├── __init__.py
│       └── runner.py              ← Entry point: orchestrate toàn bộ pipeline
│
├── tests/
│   ├── test_utils.py              ← Unit test hàm tiện ích (16 tests)
│   └── test_tinnhanh.py           ← Unit + integration test crawler (9 tests)
│
├── logs/                          ← Log local (không commit lên Git)
│
├── requirements.txt               ← Danh sách thư viện Python
├── .env.example                   ← Mẫu biến môi trường (commit được)
├── .env                           ← Biến môi trường thực (KHÔNG commit — trong .gitignore)
├── .gitignore
└── README.md
```

---

## 3. Cài đặt local (VS Code + môi trường ảo)

### Bước 1 — Clone repository

```bash
git clone https://github.com/HiuV1411/Do_an_2_crawl_vietstock.git
```

### Bước 2 — Tạo và kích hoạt môi trường ảo

```bash
# Tạo môi trường ảo
python -m venv .venv

# Kích hoạt trên Windows
.venv\Scripts\activate

# Kích hoạt trên macOS / Linux
source .venv/bin/activate
```

> **VS Code**: Nhấn `Ctrl + Shift + P` → `Python: Select Interpreter` → chọn `.venv`.

### Bước 3 — Cài thư viện

```bash
pip install -r requirements.txt
```

Các thư viện được cài:

| Thư viện | Phiên bản | Vai trò |
|---|---|---|
| `requests` | 2.32.3 | HTTP client — tải HTML từ trang báo |
| `beautifulsoup4` | 4.12.3 | Parse HTML — tìm thẻ, trích xuất dữ liệu |
| `lxml` | 5.2.2 | Parser nhanh cho BeautifulSoup |
| `gspread` | 6.1.2 | Client Google Sheets API |
| `google-auth` | 2.29.0 | Xác thực Service Account |
| `python-dotenv` | 1.0.1 | Load file `.env` |
| `tenacity` | 8.3.0 | Retry tự động khi request lỗi |
| `pytz` | 2024.1 | Xử lý múi giờ Việt Nam (UTC+7) |

---

## 4. Cấu hình Google Service Account

### Bước 1 — Tạo Google Cloud Project

1. Vào [Google Cloud Console](https://console.cloud.google.com/)
2. Nhấn **New Project** → đặt tên → **Create**

### Bước 2 — Bật API

Vào **APIs & Services → Library**, tìm và bật 2 API:
- ✅ **Google Sheets API**
- ✅ **Google Drive API**

### Bước 3 — Tạo Service Account

1. Vào **IAM & Admin → Service Accounts → Create Service Account**
2. Đặt tên (ví dụ: `crawler-bot`) → **Create and Continue → Done**
3. Click vào Service Account vừa tạo → tab **Keys → Add Key → Create new key → JSON**
4. File JSON sẽ được tải về máy — **bảo mật, không commit lên GitHub**

### Bước 4 — Cấp quyền vào Spreadsheet

1. Mở file Google Spreadsheet cần ghi dữ liệu
2. Nhấn **Share** (nút chia sẻ góc trên phải)
3. Dán email của Service Account (dạng `crawler-bot@project-id.iam.gserviceaccount.com`)
4. Chọn quyền **Editor** → **Send**

---

## 5. Cấu hình biến môi trường

```bash
# Copy file mẫu
cp .env.example .env
```

M�� file `.env` và điền:

```env
# Nội dung JSON của file Service Account key (dán toàn bộ JSON thành 1 dòng)
GSPREAD_CREDS={"type":"service_account","project_id":"your-project","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"crawler-bot@your-project.iam.gserviceaccount.com","client_id":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token"}

# ID của Google Spreadsheet (lấy từ URL)
SPREADSHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms

# Thông tin nhóm
INDUSTRY_GROUP=Ngân hàng - Chứng khoán - Bảo hiểm
GROUP_ID=G1
```

> **Tìm SPREADSHEET_ID**: Mở Google Sheets → nhìn URL:
> `https://docs.google.com/spreadsheets/d/`**`1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms`**`/edit`

---

## 6. Cấu trúc Google Spreadsheet

Spreadsheet cần có **7 sheets** với tên chính xác như sau:

| Sheet | Mô tả |
|---|---|
| `README` | Thông tin nhóm, mô tả bộ dữ liệu |
| `CONFIG_SOURCES` | Cấu hình nguồn tin (SOURCE_ID, URL...) |
| `CONFIG_KEYWORDS` | Từ khóa và mã cổ phiếu theo nhóm ngành |
| `NEWS_RAW` | **Toàn bộ dữ liệu crawl được** |
| `CRAWL_LOG` | Lịch sử từng lần crawl |
| `DAILY_SUMMARY` | Tóm tắt tiến độ theo ngày |
| `DATA_QUALITY_CHECK` | Kiểm tra chất lượng dữ liệu |

### Sheet NEWS_RAW — 18 cột

**12 cột bắt buộc (A → L):**

| Cột | Tên cột | Nguồn lấy dữ liệu | Ví dụ |
|---|---|---|---|
| A | `news_id` | `TINNHANH_YYYYMMDD_XXXXXX` | `TINNHANH_20260609_1B2C3D` |
| B | `title` | `<h1>` trong trang chi tiết | `VN-Index và những tín hiệu trái chiều` |
| C | `summary` | `<meta name="description">` | `Sau giai đoạn VN-Index tăng mạnh...` |
| D | `content` | `div.detail-content` (tối đa 5000 ký tự) | Nội dung đầy đủ bài viết |
| E | `published_date` | `<meta property="article:published_time">` (ISO) | `2026-06-09 06:37:12` |
| F | `source` | Cố định: `Tin nhanh chứng khoán` | `Tin nhanh chứng khoán` |
| G | `url` | URL đầy đủ bài viết — **dùng làm khóa dedup** | `https://www.tinnhanhchungkhoan.vn/...-post391857.html` |
| H | `industry_group` | Biến môi trường `INDUSTRY_GROUP` | `Ngân hàng - Chứng khoán - Bảo hiểm` |
| I | `tickers` | `<meta name="article:tag">` lọc mã CK 2-4 chữ hoa | `VCB, BID, CTG` |
| J | `keywords` | Quét title + summary theo `KEYWORDS_MAP` | `vn-index, lãi suất` |
| K | `event_type` | Phân loại tự động từ keywords | `thị trường chứng khoán` |
| L | `crawl_time` | Thời điểm hệ thống crawl (UTC+7) | `2026-06-09 08:31:05` |

**6 cột nên có (M → R):**

| Cột | Tên cột | Mô tả | Ví dụ |
|---|---|---|---|
| M | `content_hash` | MD5(title + content) — phát hiện nội dung trùng | `a1b2c3d4...` |
| N | `crawl_status` | Trạng thái crawl | `success` / `failed` |
| O | `error_message` | Mô tả lỗi nếu crawl thất bại | `Connection timeout` |
| P | `checked_by` | Người kiểm tra dữ liệu | `Nguyễn Văn A` |
| Q | `checked_time` | Thời điểm kiểm tra | `2026-06-09 10:00:00` |
| R | `note` | Chuyên mục + tags bài viết | `Nhận định \| tags: VN-Index, SHS` |

### Quy tắc tạo `news_id`

```
Format:  TINNHANH_YYYYMMDD_XXXXXX
Ví dụ:  TINNHANH_20260609_1B2C3D

Trong đó:
  TINNHANH  = SOURCE_ID cố định
  YYYYMMDD  = Ngày đăng bài (từ published_date)
  XXXXXX    = 6 ký tự cuối MD5(URL) viết hoa
```

---

## 7. Triển khai tự động với GitHub Actions

### Bước 1 — Push code lên GitHub

```bash
git add .
git commit -m "feat: tinnhanh crawler"
git push origin main
```

### Bước 2 — Thêm GitHub Secrets

Vào **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**:

| Tên Secret | Giá trị |
|---|---|
| `GSPREAD_CREDS` | Toàn bộ nội dung JSON file Service Account (1 dòng) |
| `SPREADSHEET_ID` | ID của Google Spreadsheet |
| `INDUSTRY_GROUP` | Ví dụ: `Ngân hàng - Chứng khoán - Bảo hiểm` |
| `GROUP_ID` | Ví dụ: `G1` |

### Bước 3 — Kiểm tra workflow

1. Vào tab **Actions** trên GitHub repo
2. Chọn workflow **Tin Nhanh Chứng Khoán Daily Crawler**
3. Nhấn **Run workflow** → **Run workflow** để kích hoạt thủ công ngay
4. Theo dõi log từng bước — mỗi bước có `✓` hoặc `✗` rõ ràng

### Lịch cron

```yaml
schedule:
  - cron: "30 1 * * *"    # 08:30 sáng giờ Việt Nam (ICT = UTC+7)
  - cron: "30 11 * * *"   # 18:30 chiều giờ Việt Nam
```

> GitHub Actions dùng múi giờ UTC. Để chạy lúc 08:30 ICT (UTC+7), cần đặt cron là 01:30 UTC.

---

## 8. Chạy thủ công để test

```bash
# Kích hoạt môi trường ảo trước
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

# Chạy toàn bộ pipeline
python -m src.pipeline.runner

# Hoặc
python src/pipeline/runner.py
```

**Output mẫu khi chạy thành công:**

```
============================================================
🚀 BẮT ĐẦU CRAWL | Phiên: morning | 2026-06-09 08:31:00
============================================================
✓ Kết nối Spreadsheet: 'Đồ án Web Crawling - Nhóm G1'
✓ Đã load 150 URL từ NEWS_RAW (dedup cache)
▶ Bắt đầu crawl trang chủ
  → Listing trang 1: https://www.tinnhanhchungkhoan.vn
  ✓ Trang 1: 42 bài
  ✓ [1] VN-Index và những tín hiệu trái chiều...
  ✓ [2] Chuyển nhượng vốn không còn dễ né thuế...
  ⏹ Early stop tại trang 1 (gặp bài đã crawl)
◀ Kết thúc | Tìm: 42 | Mới: 12 | Trùng: 30 | Lỗi: 0
✓ Đã ghi batch 1: 12 hàng
✓ Tổng cộng đã ghi 12 hàng vào NEWS_RAW
✓ Đã ghi CRAWL_LOG
✓ Đã cập nhật DAILY_SUMMARY ngày 2026-06-09
============================================================
  Tổng tìm thấy : 42
  Bài mới       : 12
  Bài trùng     : 30
  Lỗi           : 0
  Đã ghi Sheets : 12 hàng
============================================================
✅ Pipeline hoàn thành thành công
```

---

## 9. Chạy Unit Test

```bash
# Test hàm tiện ích (không cần mạng)
python tests/test_utils.py

# Test crawler tinnhanhchungkhoan.vn (có integration test cần mạng)
python tests/test_tinnhanh.py

# Chạy tất cả bằng pytest
pip install pytest
pytest tests/ -v
```

**Kết quả mong đợi:**

```
── Unit tests ──
  ✓ test_extract_post_id_normal
  ✓ test_extract_post_id_short
  ✓ test_extract_post_id_fallback
  ✓ test_parse_iso_date
  ✓ test_parse_text_date_with_time
  ✓ test_parse_text_date_only
  ✓ test_parse_empty_date

── Integration tests (cần mạng) ──
  ✓ test_crawl_listing_homepage     → tìm thấy 40+ bài
  ✓ test_crawl_detail_real          → đầy đủ title, date, tags, author
```

---

## 10. Quy tắc chống trùng lặp (Dedup)

Hệ thống dùng **URL chuẩn hóa** làm khóa dedup — đơn giản, chính xác, không cần database riêng.

### Cơ chế hoạt động

```python
# Bước 1: Đầu mỗi phiên crawl — đọc 1 lần duy nhất
seen_urls = load_seen_urls(spreadsheet)
# → set{"https://tinnhanhchungkhoan.vn/bai-a-post123.html", ...}

# Bước 2: Với mỗi bài tìm được
norm_url = normalize_url(article_url)
if norm_url in seen_urls:
    DỪNG SỚM  # tin cũ nhất cũng đã có → không cần crawl thêm
else:
    crawl_detail(url)
    seen_urls.add(norm_url)  # cập nhật ngay để dedup trong cùng phiên
```

### Quy tắc normalize URL

```
Input:  "https://www.tinnhanhchungkhoan.vn/bai-post123.html?ref=home"
Output: "https://www.tinnhanhchungkhoan.vn/bai-post123.html"

Thao tác:
  ✓ Lowercase toàn bộ
  ✓ Bỏ query params (?ref=, ?utm_source=...)
  ✓ Bỏ fragment (#section)
  ✓ Bỏ trailing slash
```

### Tại sao không dùng database?

Google Sheets **chính là** source of truth. Load 1 lần lúc đầu phiên → set trong memory → O(1) mỗi lần kiểm tra. Với vài nghìn bài/tháng, hoàn toàn đủ nhanh.

### Đảm bảo không trùng giữa buổi sáng và buổi chiều

```
08:30 → load seen_urls (ví dụ: 200 URL) → crawl 15 bài mới → ghi vào Sheets
18:30 → load seen_urls (215 URL, bao gồm 15 bài buổi sáng) → chỉ crawl bài sau 08:30
```

---

## 11. Xử lý sự cố thường gặp

| Vấn đề | Nguyên nhân | Giải pháp |
|---|---|---|
| `EnvironmentError: Thiếu GSPREAD_CREDS` | Chưa set biến môi trường | Kiểm tra file `.env` (local) hoặc GitHub Secrets (Actions) |
| `SpreadsheetNotFound` | `SPREADSHEET_ID` sai | Kiểm tra lại URL Google Sheets, copy đúng ID |
| `403 Forbidden` từ Sheets API | Service Account chưa được share | Share Sheets với email của Service Account (quyền Editor) |
| `429 Too Many Requests` | Vượt quota Sheets API | Hệ thống tự retry sau 60 giây — không cần can thiệp |
| Crawl được 0 bài | Trang thay đổi HTML | Cập nhật selector trong `src/config.py` |
| GitHub Actions không chạy | Repo bị inactive >60 ngày | Vào Actions → enable workflow |
| `ModuleNotFoundError` | Chưa kích hoạt venv | Chạy `.venv\Scripts\activate` trước |

### Khi trang tinnhanhchungkhoan.vn thay đổi HTML

Chỉ cần cập nhật các selector trong **`src/config.py`** — không cần sửa code logic:

```python
# Ví dụ: trang đổi class content từ "detail-content" sang "article-body"
DETAIL_SELECTORS = {
    "content": "div.article-body",   ← chỉ sửa dòng này
    ...
}
```

---

## 12. Mở rộng thêm nguồn tin

Kiến trúc được thiết kế để dễ mở rộng. Để thêm nguồn mới (ví dụ CafeF):

### Bước 1 — Tạo crawler mới

```bash
# Tạo file mới, kế thừa cùng interface
touch src/crawler/cafef.py
```

Implement 2 hàm bắt buộc:
```python
def crawl_listing_page(page, session, category_url) -> list[dict]: ...
def crawl_new_articles(seen_urls, category_url, category_name) -> tuple[list, dict]: ...
```

### Bước 2 — Thêm vào pipeline

M�� `src/pipeline/runner.py`, thêm:
```python
from src.crawler.cafef import crawl_new_articles as crawl_cafef

# Trong hàm run_pipeline():
articles, stats = crawl_cafef(seen_urls=seen_urls, ...)
```

### Bước 3 — Cập nhật config

Thêm cấu hình nguồn mới vào `src/config.py` (URL, selector, SOURCE_ID).

> Không cần sửa `sheets.py`, `utils.py`, hay `crawl.yml` — các module này hoàn toàn độc lập với nguồn tin.

---

## Thông tin dự án

| | |
|---|---|
| **Tên đồ án** | Crawl dữ liệu tin tức tài chính tự động |
| **Nguồn dữ liệu** | tinnhanhchungkhoan.vn |
| **Tự động hóa** | GitHub Actions (100%, không cần server riêng) |
| **Lưu trữ** | Google Sheets (NEWS_RAW + CRAWL_LOG + DAILY_SUMMARY) |
| **Ngôn ngữ** | Python 3.11 |
| **License** | MIT |
