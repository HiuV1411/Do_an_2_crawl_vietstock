"""
vietstock.py
============
Crawler chính cho trang Vietstock.vn.

Luồng hoạt động:
  1. crawl_listing()  → danh sách bài từ trang listing (URL, title, date thô)
  2. crawl_detail()   → nội dung đầy đủ 1 bài
  3. crawl_new_articles() → kết hợp cả hai, lọc bài đã crawl qua seen_urls
"""

import logging
import time
import re
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.config import (
    BASE_URL,
    LISTING_URL,
    CATEGORIES,
    LISTING_SELECTORS,
    DETAIL_SELECTORS,
    REQUEST_DELAY,
    MAX_PAGES,
    SOURCE_ID,
    SOURCE_NAME,
    INDUSTRY_GROUP,
)
from src.crawler.utils import (
    safe_get,
    normalize_url,
    make_news_id,
    make_content_hash,
    extract_keywords_and_event,
    extract_tickers_from_text,
    now_str,
    today_str,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parse ngày từ chuỗi text Vietstock
# ---------------------------------------------------------------------------

def _parse_vietstock_date(raw: str) -> str:
    """
    Chuyển các định dạng ngày Vietstock thành YYYY-MM-DD HH:MM:SS.

    Vietstock dùng nhiều format:
      - "15/06/2025 08:30"
      - "15/06/2025"
      - "08:30 15/06/2025"
      - ISO "2025-06-15T08:30:00"
    """
    if not raw:
        return today_str()

    raw = raw.strip()

    # ISO format
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    # DD/MM/YYYY HH:MM hoặc DD/MM/YYYY
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(raw[:16], fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    # Chỉ lấy phần có dạng DD/MM/YYYY bằng regex
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)} 00:00:00"

    return today_str() + " 00:00:00"


# ---------------------------------------------------------------------------
# Crawl trang listing
# ---------------------------------------------------------------------------

def crawl_listing_page(
    page: int = 1,
    session: requests.Session = None,
    category_url: Optional[str] = None,
) -> list[dict]:
    """
    Crawl 1 trang danh sách tin Vietstock.

    Args:
        page:         Số trang (bắt đầu từ 1)
        session:      requests.Session dùng chung (tối ưu connection pool)
        category_url: Nếu None → dùng trang "Tin mới nhất"

    Returns:
        Danh sách dict, mỗi dict chứa: url, title, summary, published_date (thô), thumbnail
    """
    # Xây URL phân trang — Vietstock dùng query param ?page=N hoặc /pageN
    base = category_url or LISTING_URL
    url = f"{base}?page={page}" if page > 1 else base

    logger.info(f"  → Crawl listing trang {page}: {url}")

    try:
        resp = safe_get(url, session)
    except Exception as e:
        logger.error(f"  ✗ Lỗi fetch listing trang {page}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    articles = []

    # ---- Thử nhiều selector để tìm các bài báo ----
    # Vietstock dùng nhiều class khác nhau tuỳ chuyên mục
    item_selectors = [
        "div.news-item",
        "article.item-news",
        "div.item-news",
        "li.item-news",
        "div.box-item-news",
    ]

    items = []
    for sel in item_selectors:
        items = soup.select(sel)
        if items:
            logger.debug(f"    Selector '{sel}' tìm thấy {len(items)} bài")
            break

    if not items:
        logger.warning(f"  ⚠ Không tìm thấy bài nào trang {page} — HTML có thể đã thay đổi")
        return []

    for item in items:
        try:
            art = _parse_listing_item(item)
            if art and art.get("url"):
                articles.append(art)
        except Exception as e:
            logger.debug(f"  Bỏ qua 1 item lỗi: {e}")
            continue

    logger.info(f"  ✓ Trang {page}: {len(articles)} bài")
    return articles


def _parse_listing_item(item: BeautifulSoup) -> Optional[dict]:
    """Parse 1 thẻ bài trong trang listing."""
    # Lấy link + tiêu đề
    link_tag = item.select_one("h2 a, h3 a, h4 a, .title a, a.news-title, a[href*='.htm']")
    if not link_tag:
        return None

    raw_url = link_tag.get("href", "").strip()
    if not raw_url:
        return None

    # Đảm bảo URL đầy đủ
    if raw_url.startswith("/"):
        raw_url = BASE_URL + raw_url
    elif not raw_url.startswith("http"):
        raw_url = BASE_URL + "/" + raw_url

    title = link_tag.get_text(strip=True)

    # Tóm tắt
    summary_tag = item.select_one("p.sapo, .summary, p.brief, p.intro, p")
    summary = summary_tag.get_text(strip=True) if summary_tag else ""

    # Ngày đăng (text thô)
    date_tag = item.select_one("span.time, time, .date, .post-time, span[class*='time']")
    raw_date = ""
    if date_tag:
        raw_date = date_tag.get("datetime", "") or date_tag.get_text(strip=True)

    # Thumbnail
    img_tag = item.select_one("img[data-src], img[src]")
    thumbnail = ""
    if img_tag:
        thumbnail = img_tag.get("data-src") or img_tag.get("src", "")

    return {
        "url":            raw_url,
        "title":          title,
        "summary":        summary[:500] if summary else "",
        "raw_date":       raw_date,
        "thumbnail":      thumbnail,
    }


# ---------------------------------------------------------------------------
# Crawl bài chi tiết
# ---------------------------------------------------------------------------

def crawl_detail(url: str, session: requests.Session = None) -> dict:
    """
    Crawl trang chi tiết 1 bài viết Vietstock.

    Returns:
        dict với tất cả các trường cần thiết cho NEWS_RAW.
        Trả về dict rỗng nếu lỗi.
    """
    logger.debug(f"    Crawl detail: {url}")

    try:
        resp = safe_get(url, session)
    except Exception as e:
        logger.error(f"    ✗ Lỗi fetch detail {url}: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "lxml")

    # ---- Title ----
    title = ""
    for sel in ["h1.article-title", "h1.title", "h1.post-title", "h1"]:
        tag = soup.select_one(sel)
        if tag:
            title = tag.get_text(strip=True)
            break

    # ---- Summary / sapo ----
    summary = ""
    for sel in ["p.sapo", "p.summary", ".article-sapo", "h2.sapo", ".sapo"]:
        tag = soup.select_one(sel)
        if tag:
            summary = tag.get_text(strip=True)
            break

    # ---- Content ----
    content = ""
    for sel in ["div.article-content", "div.content-detail", "div#article-body",
                "div.post-content", "div.entry-content", "div.content"]:
        tag = soup.select_one(sel)
        if tag:
            # Xoá script, style, quảng cáo
            for remove in tag.select("script, style, .ads, .advertisement, iframe"):
                remove.decompose()
            content = tag.get_text(separator="\n", strip=True)
            break

    # ---- Published date ----
    raw_date = ""
    for sel in ["time[datetime]", "span.time", "span.date", ".article-time",
                "span[class*='time']", "span[class*='date']"]:
        tag = soup.select_one(sel)
        if tag:
            raw_date = tag.get("datetime", "") or tag.get_text(strip=True)
            if raw_date:
                break

    # ---- Author ----
    author = ""
    for sel in [".author-name", "span.author", ".by-author", ".writer"]:
        tag = soup.select_one(sel)
        if tag:
            author = tag.get_text(strip=True)
            break

    # ---- Category (từ breadcrumb) ----
    category = ""
    breadcrumb = soup.select("div.breadcrumb a, nav.breadcrumb a, ol.breadcrumb li a")
    if len(breadcrumb) >= 2:
        category = breadcrumb[-1].get_text(strip=True)

    # ---- Tags ----
    tag_els = soup.select("div.tags a, .article-tags a, .tag-list a, .hashtag a")
    tags = ", ".join(t.get_text(strip=True) for t in tag_els[:10])

    # ---- Tickers: từ link finance.vietstock.vn ----
    ticker_links = soup.select("a[href*='finance.vietstock.vn']")
    tickers_from_links = []
    for a in ticker_links:
        href = a.get("href", "")
        # Dạng: finance.vietstock.vn/VCB-...
        m = re.search(r"/([A-Z]{2,4})-", href)
        if m:
            tickers_from_links.append(m.group(1))

    # Bổ sung: quét text tìm mã CK
    tickers_from_text = extract_tickers_from_text(f"{title} {content[:1000]}")
    all_tickers = list(dict.fromkeys(tickers_from_links))  # giữ thứ tự, unique
    if not all_tickers:
        all_tickers = [t.strip() for t in tickers_from_text.split(",") if t.strip()]

    return {
        "title":          title,
        "summary":        summary[:500] if summary else "",
        "content":        content[:5000] if content else "",   # giới hạn 5000 ký tự
        "raw_date":       raw_date,
        "author":         author,
        "category":       category,
        "tags":           tags,
        "tickers":        ", ".join(all_tickers[:10]),
    }


# ---------------------------------------------------------------------------
# Hàm chính: crawl toàn bộ bài mới
# ---------------------------------------------------------------------------

def crawl_new_articles(
    seen_urls: set[str],
    category_url: Optional[str] = None,
    category_name: Optional[str] = None,
) -> tuple[list[dict], dict]:
    """
    Crawl tất cả bài MỚI (chưa có trong seen_urls).

    Args:
        seen_urls:     Set các URL đã được normalize, đã có trong Sheets
        category_url:  URL chuyên mục cần crawl (None = trang tin mới nhất)
        category_name: Tên chuyên mục (để điền vào trường category)

    Returns:
        (new_articles, stats)
        new_articles: Danh sách dict sẵn sàng ghi vào NEWS_RAW (18 cột)
        stats: {found, new, skipped_duplicate, failed}
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    stats = {"found": 0, "new": 0, "skipped_duplicate": 0, "failed": 0}
    new_articles = []

    logger.info(f"▶ Bắt đầu crawl {'chuyên mục: ' + category_name if category_name else 'tin mới nhất'}")

    for page in range(1, MAX_PAGES + 1):
        # -- Crawl trang listing --
        listing = crawl_listing_page(page, session, category_url)
        if not listing:
            logger.info(f"  Dừng tại trang {page} (không có bài)")
            break

        stats["found"] += len(listing)
        should_stop = False

        for item in listing:
            norm = normalize_url(item["url"])

            # Kiểm tra trùng
            if norm in seen_urls:
                logger.debug(f"  ⟳ Đã có: {item['title'][:50]}...")
                stats["skipped_duplicate"] += 1
                should_stop = True   # Vietstock sắp theo mới → dừng sớm
                break                # Không cần crawl tiếp trang này

            # -- Crawl chi tiết bài mới --
            time.sleep(REQUEST_DELAY)
            detail = crawl_detail(item["url"], session)

            if not detail:
                stats["failed"] += 1
                continue

            # Merge dữ liệu listing + detail
            title         = detail.get("title") or item["title"]
            summary       = detail.get("summary") or item["summary"]
            content       = detail.get("content", "")
            raw_date      = detail.get("raw_date") or item.get("raw_date", "")
            published_date = _parse_vietstock_date(raw_date)

            keywords, event_type = extract_keywords_and_event(title, summary, content)

            row = {
                # 12 cột BẮT BUỘC
                "news_id":        make_news_id(item["url"], published_date),
                "title":          title,
                "summary":        summary,
                "content":        content,
                "published_date": published_date,
                "source":         SOURCE_NAME,
                "url":            item["url"],
                "industry_group": INDUSTRY_GROUP,
                "tickers":        detail.get("tickers", ""),
                "keywords":       keywords,
                "event_type":     event_type,
                "crawl_time":     now_str(),
                # 6 cột NÊN CÓ
                "content_hash":   make_content_hash(title, content),
                "crawl_status":   "success",
                "error_message":  "",
                "checked_by":     "",
                "checked_time":   "",
                "note":           detail.get("category", category_name or ""),
            }

            new_articles.append(row)
            seen_urls.add(norm)       # Cập nhật set ngay để dedup trong cùng phiên
            stats["new"] += 1
            logger.info(f"  ✓ [{stats['new']}] {title[:60]}...")

        if should_stop:
            logger.info(f"  ⏹ Early stop tại trang {page} (gặp bài đã crawl)")
            break

        time.sleep(REQUEST_DELAY)

    logger.info(
        f"◀ Kết thúc crawl | "
        f"Tìm thấy: {stats['found']} | "
        f"Mới: {stats['new']} | "
        f"Trùng: {stats['skipped_duplicate']} | "
        f"Lỗi: {stats['failed']}"
    )
    return new_articles, stats