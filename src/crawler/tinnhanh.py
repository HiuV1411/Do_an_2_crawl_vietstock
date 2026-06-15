"""
tinnhanh.py
===========
Crawler cho trang Tin nhanh chứng khoán (tinnhanhchungkhoan.vn).

Điểm khác biệt so với Vietstock:
  ✓ Trang render HTML tĩnh đầy đủ — requests + BeautifulSoup là đủ, không cần Selenium
  ✓ Mỗi bài có meta tags cực phong phú: article:published_time (ISO), article:tag,
    article:section, dable:item_id → lấy dữ liệu chính xác từ <meta> thay vì scrape text
  ✓ ID bài nằm trong URL dạng: /ten-bai-postNNNNNN.html → extract số sau "post"
  ✓ Phân trang category: ?page=2, ?page=3 (trang chủ không hỗ trợ phân trang)
"""

import logging
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.config import (
    BASE_URL,
    LISTING_URL,
    CATEGORIES,
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
# Helpers đặc thù tinnhanhchungkhoan.vn
# ---------------------------------------------------------------------------

def _get_meta(soup: BeautifulSoup, name: str = None, prop: str = None) -> str:
    """
    Lấy giá trị attribute 'content' của thẻ <meta>.
    Ưu tiên dùng meta tags vì chính xác hơn scrape text.
    """
    if name:
        tag = soup.find("meta", attrs={"name": name})
    elif prop:
        tag = soup.find("meta", attrs={"property": prop})
    else:
        return ""
    return tag["content"].strip() if tag and tag.get("content") else ""


def _extract_post_id(url: str) -> str:
    """
    Trích xuất ID bài từ URL tinnhanhchungkhoan.vn.
    Pattern: /ten-bai-viet-postNNNNNN.html → "NNNNNN"
    Ví dụ: /vn-index-va-nhung-tin-hieu-post391857.html → "391857"
    """
    m = re.search(r"-post(\d+)\.html", url)
    if m:
        return m.group(1)
    # Fallback: 8 ký tự hex từ hash URL
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:8].upper()


def _parse_tnck_date(raw: str) -> str:
    """
    Chuẩn hóa ngày từ tinnhanhchungkhoan.vn thành YYYY-MM-DD HH:MM:SS.

    Nguồn ưu tiên: meta[property='article:published_time'] → ISO 8601
      Ví dụ: "2026-06-09T06:37:12+0700" → "2026-06-09 06:37:12"

    Fallback: text "09/06/2026 06:37" → "2026-06-09 06:37:00"
    """
    if not raw:
        return today_str() + " 00:00:00"

    raw = raw.strip()

    # ISO 8601 (từ meta tag — chính xác nhất)
    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", raw)
    if m:
        return f"{m.group(1)} {m.group(2)}"

    # DD/MM/YYYY HH:MM (từ text hiển thị)
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}:\d{2})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)} {m.group(4)}:00"

    # Chỉ DD/MM/YYYY
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
    Crawl 1 trang danh sách tin tinnhanhchungkhoan.vn.

    Trang chủ:   https://www.tinnhanhchungkhoan.vn  (không hỗ trợ ?page=N)
    Chuyên mục:  https://www.tinnhanhchungkhoan.vn/chung-khoan/?page=2

    Returns: list[dict] mỗi dict gồm url, title, summary, raw_date
    """
    if category_url:
        url = category_url if page == 1 else f"{category_url.rstrip('/')}/?page={page}"
    else:
        url = LISTING_URL  # trang chủ — chỉ có 1 trang

    logger.info(f"  → Listing trang {page}: {url}")

    try:
        resp = safe_get(url, session)
    except Exception as e:
        logger.error(f"  ✗ Lỗi fetch listing trang {page}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    articles = []

    # -----------------------------------------------------------------------
    # Chiến lược parse listing tinnhanhchungkhoan.vn:
    # Tìm tất cả <a href="..."> có pattern URL bài viết (-postNNNNNN.html)
    # Đây là cách bền vững nhất, không bị vỡ khi đổi class CSS
    # -----------------------------------------------------------------------
    seen_in_page = set()
    all_links = soup.find_all("a", href=re.compile(r"-post\d+\.html$"))

    for a_tag in all_links:
        href = a_tag.get("href", "").strip()
        if not href:
            continue

        # Đảm bảo URL đầy đủ
        if href.startswith("/"):
            full_url = BASE_URL + href
        elif href.startswith("http"):
            full_url = href
        else:
            continue

        # Bỏ qua URL trùng trong cùng 1 trang
        norm = normalize_url(full_url)
        if norm in seen_in_page:
            continue
        seen_in_page.add(norm)

        title = a_tag.get_text(strip=True)
        if not title or len(title) < 5:   # bỏ link icon, ảnh không có text
            continue

        # Tìm ngày gần nhất trong parent elements
        raw_date = ""
        for parent in a_tag.parents:
            if parent.name in ["div", "article", "li", "section"]:
                time_tag = parent.find(
                    lambda t: t.name in ("time", "span") and
                    re.search(r"\d{2}/\d{2}/\d{4}", t.get_text())
                )
                if time_tag:
                    raw_date = time_tag.get("datetime", "") or time_tag.get_text(strip=True)
                    break
            if raw_date:
                break

        articles.append({
            "url":      full_url,
            "title":    title,
            "summary":  "",        # sẽ lấy từ meta description khi crawl detail
            "raw_date": raw_date,
        })

    logger.info(f"  ✓ Trang {page}: {len(articles)} bài")
    return articles


# ---------------------------------------------------------------------------
# Crawl bài chi tiết — khai thác tối đa meta tags
# ---------------------------------------------------------------------------

def crawl_detail(url: str, session: requests.Session = None) -> dict:
    """
    Crawl trang chi tiết 1 bài viết tinnhanhchungkhoan.vn.

    Ưu tiên lấy dữ liệu từ <meta> tags vì:
      - Chính xác (không bị ảnh hưởng bởi thay đổi CSS class)
      - Ngày giờ dạng ISO 8601 đầy đủ
      - Tags/keywords sẵn có, không cần scrape
    """
    logger.debug(f"    Detail: {url}")

    try:
        resp = safe_get(url, session)
    except Exception as e:
        logger.error(f"    ✗ Lỗi fetch detail {url}: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "lxml")

    # ---- ID bài (từ URL hoặc meta dable:item_id) ----
    article_id = _get_meta(soup, name="dable:item_id") or _extract_post_id(url)

    # ---- Title ----
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else _get_meta(soup, prop="og:title")

    # ---- Summary: từ meta description (đã chuẩn, có sẵn) ----
    summary = _get_meta(soup, name="description")
    # Bỏ tiền tố "(ĐTCK)" thường xuất hiện trong summary
    summary = re.sub(r"^\(ĐTCK\)\s*", "", summary).strip()

    # ---- Published date: ISO từ article:published_time ----
    raw_date = (
        _get_meta(soup, prop="article:published_time")
        or _get_meta(soup, name="dable:published_time")
    )
    # Fallback: tìm text ngày trong trang
    if not raw_date:
        date_pattern = re.compile(r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}")
        date_tag = soup.find(string=date_pattern)
        if date_tag:
            m = date_pattern.search(str(date_tag))
            raw_date = m.group(0) if m else ""

    # ---- Author ----
    author = _get_meta(soup, name="dable:author")
    if not author:
        author_tag = soup.find("a", href=re.compile(r"author-search"))
        author = author_tag.get_text(strip=True) if author_tag else ""

    # ---- Category: từ meta article:section ----
    # Giá trị: "Nhận định,Chứng khoán" → lấy phần tử đầu tiên
    section_raw = _get_meta(soup, prop="article:section")
    category = section_raw.split(",")[0].strip() if section_raw else ""

    # ---- Tags: từ meta article:tag / news_keywords ----
    tags_raw = _get_meta(soup, name="article:tag") or _get_meta(soup, name="news_keywords")
    # tags_raw: "SHS,VN-Index,Dòng tiền,Tháng năm"
    tags = tags_raw.strip() if tags_raw else ""

    # ---- Tickers: lọc từ tags (các từ viết hoa 2-4 ký tự) ----
    ticker_pattern = re.compile(r"^[A-Z]{2,4}$")
    EXCLUDE_TICKERS = {"SHS", "PMI", "GDP", "CPI", "ETF", "IPO"}
    tickers_list = [
        t.strip() for t in tags_raw.split(",")
        if ticker_pattern.match(t.strip()) and t.strip() not in EXCLUDE_TICKERS
    ] if tags_raw else []

    if not tickers_list:
        tickers_list = [
            t.strip() for t in extract_tickers_from_text(f"{title}").split(",")
            if t.strip()
        ]

    # ---- Content ----
    content = ""
    content_selectors = [
        "div.detail-content",
        "div.content-detail",
        "div.article-content",
        "div[class*='content']",
        "article",
    ]
    for sel in content_selectors:
        block = soup.select_one(sel)
        if block:
            for remove in block.select("script, style, .ads, .box-right, iframe, figure"):
                remove.decompose()
            content = block.get_text(separator="\n", strip=True)
            if len(content) > 100:   # đảm bảo lấy được nội dung thực
                break

    return {
        "article_id":    article_id,
        "title":         title,
        "summary":       summary[:500] if summary else "",
        "content":       content[:5000] if content else "",
        "raw_date":      raw_date,
        "author":        author,
        "category":      category,
        "tags":          tags,
        "tickers":       ", ".join(tickers_list[:10]),
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
    Crawl tất cả bài MỚI chưa có trong seen_urls.

    Returns:
        (new_articles, stats)
        new_articles: list[dict] — 18 cột sẵn sàng ghi vào NEWS_RAW
        stats:        {found, new, skipped_duplicate, failed}
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.tinnhanhchungkhoan.vn/",
    })

    stats = {"found": 0, "new": 0, "skipped_duplicate": 0, "failed": 0}
    new_articles = []

    logger.info(
        f"▶ Bắt đầu crawl "
        f"{'chuyên mục: ' + category_name if category_name else 'trang chủ'}"
    )

    for page in range(1, MAX_PAGES + 1):
        listing = crawl_listing_page(page, session, category_url)

        if not listing:
            logger.info(f"  Dừng tại trang {page} (không có bài hoặc hết trang)")
            break

        stats["found"] += len(listing)
        should_stop = False

        for item in listing:
            norm = normalize_url(item["url"])

            if norm in seen_urls:
                logger.debug(f"  ⟳ Trùng: {item['title'][:50]}...")
                stats["skipped_duplicate"] += 1
                should_stop = True
                break

            # Crawl chi tiết bài mới
            time.sleep(REQUEST_DELAY)
            detail = crawl_detail(item["url"], session)

            if not detail:
                stats["failed"] += 1
                # Ghi hàng lỗi để không bị crawl lại và có thể debug
                error_row = _build_row(
                    item=item,
                    detail={},
                    category_name=category_name,
                    crawl_status="failed",
                    error_message="Không thể crawl trang chi tiết",
                )
                new_articles.append(error_row)
                seen_urls.add(norm)
                continue

            row = _build_row(
                item=item,
                detail=detail,
                category_name=category_name,
                crawl_status="success",
            )
            new_articles.append(row)
            seen_urls.add(norm)
            stats["new"] += 1
            logger.info(f"  ✓ [{stats['new']}] {row['title'][:65]}...")

        if should_stop:
            logger.info(f"  ⏹ Early stop tại trang {page}")
            break

        time.sleep(REQUEST_DELAY)

    logger.info(
        f"◀ Kết thúc | Tìm: {stats['found']} | "
        f"Mới: {stats['new']} | Trùng: {stats['skipped_duplicate']} | "
        f"Lỗi: {stats['failed']}"
    )
    return new_articles, stats


# ---------------------------------------------------------------------------
# Helper: build 1 hàng NEWS_RAW (18 cột)
# ---------------------------------------------------------------------------

def _build_row(
    item: dict,
    detail: dict,
    category_name: Optional[str],
    crawl_status: str = "success",
    error_message: str = "",
) -> dict:
    """Merge dữ liệu listing + detail → dict 18 cột đúng schema NEWS_RAW."""
    url   = item["url"]
    title = detail.get("title") or item.get("title", "")

    # Ưu tiên ngày từ meta ISO (detail) > ngày text từ listing
    raw_date = detail.get("raw_date") or item.get("raw_date", "")
    published_date = _parse_tnck_date(raw_date)

    summary  = detail.get("summary") or item.get("summary", "")
    content  = detail.get("content", "")
    tags     = detail.get("tags", "")
    tickers  = detail.get("tickers", "")
    category = detail.get("category") or category_name or ""

    keywords, event_type = extract_keywords_and_event(title, summary, content)

    return {
        # 12 cột BẮT BUỘC
        "news_id":        make_news_id(url, published_date),
        "title":          title,
        "summary":        summary[:500],
        "content":        content[:5000],
        "published_date": published_date,
        "source":         SOURCE_NAME,
        "url":            url,
        "industry_group": INDUSTRY_GROUP,
        "tickers":        tickers,
        "keywords":       keywords,
        "event_type":     event_type,
        "crawl_time":     now_str(),
        # 6 cột NÊN CÓ
        "content_hash":   make_content_hash(title, content),
        "crawl_status":   crawl_status,
        "error_message":  error_message,
        "checked_by":     "",
        "checked_time":   "",
        "note":           f"{category} | tags: {tags[:100]}" if tags else category,
    }