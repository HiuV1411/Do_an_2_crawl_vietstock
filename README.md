# CafeF News Crawler

Hệ thống tự động crawl tin tức mục **Thị Trường** từ CafeF.vn và lưu vào Google Sheets.
Chạy tự động lúc **08:30** và **18:30** mỗi ngày, không cần thao tác thủ công.

---

## Cấu trúc thư mục

```
cafef_crawler/
├── main.py                    # Entry point
├── .env                       # Biến cấu hình (tự tạo, không commit)
├── requirements.txt
├── crawler/
│   ├── cafef.py               # Orchestrator crawl
│   ├── fetcher.py             # HTTP + retry
│   └── parser.py              # BeautifulSoup parser
├── dedup/
│   └── store.py               # SQLite dedup store
├── storage/
│   └── google_sheets.py       # Ghi Google Sheets
├── scheduler/
│   └── jobs.py                # APScheduler jobs
├── utils/
│   ├── logger.py
│   └── hash.py
├── data/                      # Tự tạo khi chạy (seen_urls.db)
├── logs/                      # Tự tạo khi chạy
└── credentials/               # Đặt file service_account.json vào đây
```

---

## Hướng dẫn cài đặt

### Bước 1 — Tạo môi trường ảo trong VS Code

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
```

### Bước 2 — Tạo Google Service Account

1. Vào [Google Cloud Console](https://console.cloud.google.com/)
2. Tạo project mới → Enable **Google Sheets API** và **Google Drive API**
3. Tạo **Service Account** → tải file JSON → đổi tên thành `service_account.json`
4. Đặt file vào thư mục `credentials/`
5. Mở Google Spreadsheet → **Share** với email của Service Account (quyền Editor)

### Bước 3 — Tạo file .env

Sao chép file `.env` (đã có trong dự án) và điền thông tin thực tế:

```
GOOGLE_SERVICE_ACCOUNT_PATH=credentials/service_account.json
SPREADSHEET_ID=<ID lấy từ URL Google Sheets>
GROUP_ID=G5
GROUP_NAME=Nhóm 5
INDUSTRY_GROUP=Năng lượng-Điện-Dầu khí-Cảng biển-Logistics
SOURCE_ID=CAFEF
SCHEDULE_MORNING=08:30
SCHEDULE_EVENING=18:30
MAX_PAGES=5
REQUEST_DELAY=2
REQUEST_TIMEOUT=30
MAX_RETRIES=3
```

**Lấy SPREADSHEET_ID từ URL:**
```
https://docs.google.com/spreadsheets/d/[SPREADSHEET_ID]/edit
```

### Bước 4 — Test thủ công trước khi chạy tự động

```bash
# Crawl ngay lập tức để kiểm tra
python main.py --run-now
```

Kiểm tra:
- File `logs/crawler_YYYYMMDD.log` có ghi không?
- Sheet `NEWS_RAW` có dữ liệu không?
- Sheet `CRAWL_LOG` có dòng log không?

### Bước 5 — Chạy tự động 24/7

```bash
python main.py
```

Chương trình sẽ chạy liên tục và tự crawl đúng 08:30 và 18:30.

---

## Yêu cầu để chạy 100% tự động (không cần mở máy)

Cần giữ máy tính **luôn bật và không sleep**. Hoặc deploy lên:

- **PythonAnywhere** (miễn phí cho sinh viên): upload code, chạy `python main.py` trong tab Console Always-On
- **Google Cloud Run** (free tier): build Docker image, deploy
- **VPS/Server** bất kỳ: chạy bằng `nohup python main.py &`

---

## Các sheet trong Google Spreadsheet

| Sheet | Mô tả |
|---|---|
| `NEWS_RAW` | Toàn bộ tin tức đã crawl |
| `CRAWL_LOG` | Log mỗi lần chạy (sáng/chiều) |
| `DAILY_SUMMARY` | Tổng hợp số bài theo ngày |