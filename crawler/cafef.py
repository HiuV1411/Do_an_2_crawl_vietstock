"""
Orchestrator crawl Cafef mục Thị Trường.
Kết hợp Fetcher + Parser + Dedup để trả về danh sách bài mới.
"""
import os
import time
from datetime import datetime
from crawler.fetcher import fetch_html
from crawler.parser import parse_listing, parse_article_detail, ArticleRef, Article
from dedup.store import is_seen, mark_seen
from utils.logger import logger

BASE_URL = "https://cafef.vn/thi-truong.chn"
MAX_PAGES = int(os.getenv("MAX_PAGES", "5"))
DELAY = float(os.getenv("REQUEST_DELAY", "2"))
CATEGORY = "Thị trường"
SOURCE = "CafeF"


def build_page_url(page: int) -> str:
    """Tạo URL cho trang listing thứ N."""
    if page == 1:
        return BASE_URL
    return f"https://cafef.vn/thi-truong-p{page}.chn"


def crawl_new_articles() -> tuple[list[Article], dict]:
    """
    Crawl toàn bộ bài mới chưa seen trên Cafef Thị Trường.
    Áp dụng Early Stop: nếu >= 80% bài trên 1 trang đã seen thì dừng.

    Trả về:
        - list[Article]: danh sách bài mới
        - dict: thống kê (total_found, new, duplicate, failed)
    """
    stats = {"total_found": 0, "new": 0, "duplicate": 0, "failed": 0}
    new_articles: list[Article] = []

    for page in range(1, MAX_PAGES + 1):
        url = build_page_url(page)
        logger.info(f"[Cafef] Crawl trang {page}/{MAX_PAGES}: {url}")

        try:
            html = fetch_html(url)
        except Exception as e:
            logger.error(f"[Cafef] Không tải được trang {page}: {e}")
            stats["failed"] += 1
            break

        refs: list[ArticleRef] = parse_listing(html, url)
        if not refs:
            logger.warning(f"[Cafef] Trang {page} không có bài nào — dừng.")
            break

        stats["total_found"] += len(refs)
        new_on_page = 0

        for ref in refs:
            if is_seen(ref.url):
                stats["duplicate"] += 1
                continue

            # Tải trang chi tiết
            try:
                detail_html = fetch_html(ref.url)
                article = parse_article_detail(detail_html, ref)
                new_articles.append(article)
                new_on_page += 1
                stats["new"] += 1
                # Đánh dấu seen ngay sau khi lấy thành công
                mark_seen(ref.url)
                time.sleep(DELAY)
            except Exception as e:
                logger.error(f"[Cafef] Lỗi khi lấy bài {ref.url}: {e}")
                stats["failed"] += 1

        # Early stop: >= 80% bài trên trang này đã seen → không cần crawl sâu hơn
        seen_ratio = 1 - (new_on_page / len(refs))
        logger.info(
            f"[Cafef] Trang {page}: {new_on_page} mới, "
            f"{len(refs) - new_on_page} đã seen ({seen_ratio:.0%})"
        )
        if seen_ratio >= 0.8:
            logger.info("[Cafef] Early stop: phần lớn bài đã seen.")
            break

        time.sleep(DELAY)

    logger.info(
        f"[Cafef] Kết quả: "
        f"Tìm thấy={stats['total_found']}, "
        f"Mới={stats['new']}, "
        f"Trùng={stats['duplicate']}, "
        f"Lỗi={stats['failed']}"
    )
    return new_articles, stats