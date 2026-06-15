"""
Parser dành riêng cho trang Cafef mục Thị Trường.
Trích xuất danh sách bài viết từ trang listing
và nội dung chi tiết từ trang bài viết.
"""
import re
from dataclasses import dataclass, field
from typing import Optional
from bs4 import BeautifulSoup
from utils.logger import logger


@dataclass
class ArticleRef:
    """Thông tin cơ bản từ trang listing."""
    url: str
    title: str
    summary: str = ""
    published_date: str = ""


@dataclass
class Article:
    """Thông tin đầy đủ sau khi vào trang bài viết."""
    url: str
    title: str
    summary: str
    content: str
    published_date: str
    author: str = ""
    tags: list = field(default_factory=list)


# ---------------------------------------------------------------
# LISTING PAGE PARSER
# ---------------------------------------------------------------

def parse_listing(html: str, page_url: str) -> list[ArticleRef]:
    """
    Parse trang danh sách bài viết Cafef.
    Trả về list ArticleRef.
    """
    soup = BeautifulSoup(html, "lxml")
    articles: list[ArticleRef] = []

    # Selector chính: các thẻ h3, h2 chứa link bài viết trong khu vực tin tức
    # Cafef dùng cấu trúc: <h3><a href="...chn">Tiêu đề</a></h3>
    # Kết hợp nhiều selector để bắt hết các dạng layout
    selectors = [
        "h3 > a[href*='.chn']",
        "h2 > a[href*='.chn']",
        ".list-news h3 a[href*='.chn']",
        ".featured-news h2 a[href*='.chn']",
        "article h3 a[href*='.chn']",
    ]

    seen_urls: set[str] = set()

    for selector in selectors:
        for a_tag in soup.select(selector):
            href = a_tag.get("href", "")
            if not href or href in seen_urls:
                continue

            # Đảm bảo URL đầy đủ
            if href.startswith("/"):
                href = "https://cafef.vn" + href
            if not href.startswith("http"):
                continue

            # Lọc chỉ bài thuộc cafef.vn và có đuôi .chn
            if "cafef.vn" not in href or not href.endswith(".chn"):
                continue

            title = a_tag.get_text(strip=True)
            if len(title) < 10:
                continue

            # Tìm summary: thường là thẻ p hoặc span gần nhất
            summary = ""
            parent = a_tag.find_parent(["article", "div", "li"])
            if parent:
                p_tag = parent.find("p")
                if p_tag:
                    summary = p_tag.get_text(strip=True)

            # Tìm thời gian đăng
            published_date = ""
            if parent:
                time_tag = parent.find("time")
                if time_tag:
                    published_date = (
                        time_tag.get("datetime", "") or time_tag.get_text(strip=True)
                    )

            seen_urls.add(href)
            articles.append(
                ArticleRef(
                    url=href,
                    title=title,
                    summary=summary,
                    published_date=_normalize_date(published_date),
                )
            )

    logger.info(f"[Parser] Listing {page_url} → {len(articles)} bài")
    return articles


# ---------------------------------------------------------------
# DETAIL PAGE PARSER
# ---------------------------------------------------------------

def parse_article_detail(html: str, ref: ArticleRef) -> Article:
    """
    Parse trang bài viết chi tiết.
    Trích xuất nội dung đầy đủ, tác giả, tags.
    """
    soup = BeautifulSoup(html, "lxml")

    # Tiêu đề
    title = ref.title
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True) or title

    # Sapo / summary
    summary = ref.summary
    sapo_selectors = [".sapo", ".summary", ".article-sapo", 'p[class*="sapo"]']
    for sel in sapo_selectors:
        tag = soup.select_one(sel)
        if tag:
            summary = tag.get_text(strip=True)
            break

    # Ngày đăng
    published_date = ref.published_date
    date_selectors = [
        "time[datetime]",
        ".time",
        ".date",
        ".article-time",
        'span[class*="time"]',
    ]
    for sel in date_selectors:
        tag = soup.select_one(sel)
        if tag:
            dt = tag.get("datetime", "") or tag.get_text(strip=True)
            if dt:
                published_date = _normalize_date(dt)
                break

    # Tác giả
    author = ""
    author_selectors = [".author", ".article-author", 'span[class*="author"]', ".by-author"]
    for sel in author_selectors:
        tag = soup.select_one(sel)
        if tag:
            author = tag.get_text(strip=True).replace("Tác giả:", "").strip()
            break

    # Nội dung bài viết
    content = ""
    content_selectors = [
        ".detail-content",
        ".article-body",
        ".content-detail",
        "#main-detail-body",
        'div[class*="detail"]',
    ]
    for sel in content_selectors:
        tag = soup.select_one(sel)
        if tag:
            # Xoá các phần tử không cần: quảng cáo, script, related
            for remove in tag.select("script, style, .related, .ads, .advertisement, iframe"):
                remove.decompose()
            content = tag.get_text(separator="\n", strip=True)
            # Giới hạn độ dài để không vượt quá giới hạn ô Google Sheets (50000 chars)
            content = content[:45000]
            break

    # Tags
    tags: list[str] = []
    tag_selectors = [".tags a", ".tag-list a", 'a[class*="tag"]']
    for sel in tag_selectors:
        found = [t.get_text(strip=True) for t in soup.select(sel)]
        if found:
            tags = found
            break

    return Article(
        url=ref.url,
        title=title,
        summary=summary,
        content=content,
        published_date=published_date,
        author=author,
        tags=tags,
    )


# ---------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------

def _normalize_date(raw: str) -> str:
    """Cố gắng chuẩn hoá chuỗi ngày về YYYY-MM-DD HH:MM:SS."""
    if not raw:
        return ""
    raw = raw.strip()

    # ISO format: 2026-06-07T09:10:00
    m = re.search(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", raw)
    if m:
        return f"{m.group(1)} {m.group(2)}:00"

    # DD/MM/YYYY HH:MM
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s*[–-]?\s*(\d{2}:\d{2})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)} {m.group(4)}:00"

    # DD/MM/YYYY
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)} 00:00:00"

    return raw