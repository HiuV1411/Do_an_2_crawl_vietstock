"""
runner.py
=========
Pipeline orchestrator — điểm vào (entry point) của toàn bộ hệ thống.

Luồng:
  1. Kết nối Google Sheets
  2. Load seen_urls (dedup cache)
  3. Crawl từng chuyên mục → lấy bài mới
  4. Ghi NEWS_RAW (batch)
  5. Ghi CRAWL_LOG
  6. Cập nhật DAILY_SUMMARY
  7. In tóm tắt kết quả

Chạy:
  python -m src.pipeline.runner
  # hoặc
  python src/pipeline/runner.py
"""

import logging
import sys
import traceback

from src.crawler.utils import setup_logging, now_str, crawl_session_label
from src.crawler.tinnhanh import crawl_new_articles   # ← ĐÃ ĐỔI import
from src.storage.sheets import (
    get_client,
    get_spreadsheet,
    load_seen_urls,
    write_news_raw,
    write_crawl_log,
    update_daily_summary,
)
from src.config import CATEGORIES, LISTING_URL

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    """
    Hàm pipeline chính. Được gọi bởi GitHub Actions 2 lần mỗi ngày.
    """
    setup_logging()
    session_label = crawl_session_label()

    logger.info("=" * 60)
    logger.info(f"🚀 BẮT ĐẦU CRAWL | Phiên: {session_label} | {now_str()}")
    logger.info("=" * 60)

    # --- Bước 1: Kết nối Google Sheets ---
    try:
        client = get_client()
        spreadsheet = get_spreadsheet(client)
        logger.info(f"✓ Kết nối Spreadsheet: '{spreadsheet.title}'")
    except Exception as e:
        logger.critical(f"✗ KHÔNG THỂ KẾT NỐI GOOGLE SHEETS: {e}")
        sys.exit(1)  # Thoát với exit code 1 → GitHub Actions đánh dấu FAILED

    # --- Bước 2: Load seen_urls ---
    seen_urls = load_seen_urls(spreadsheet)

    # --- Bước 3: Crawl ---
    all_new_articles = []
    total_stats = {"found": 0, "new": 0, "skipped_duplicate": 0, "failed": 0}
    global_error = ""

    # Crawl trang "Tin mới nhất" trước (bắt buộc)
    try:
        articles, stats = crawl_new_articles(
            seen_urls=seen_urls,
            category_url=LISTING_URL,
            category_name="Tin mới nhất",
        )
        all_new_articles.extend(articles)
        for k in total_stats:
            total_stats[k] += stats.get(k, 0)

    except Exception as e:
        global_error = str(e)
        logger.error(f"✗ Lỗi crawl trang tin mới nhất: {e}")
        traceback.print_exc()

    # Crawl thêm các chuyên mục (tùy chọn — bỏ comment để bật)
    # for cat_name, cat_url in CATEGORIES.items():
    #     try:
    #         articles, stats = crawl_new_articles(
    #             seen_urls=seen_urls,
    #             category_url=cat_url,
    #             category_name=cat_name,
    #         )
    #         all_new_articles.extend(articles)
    #         for k in total_stats:
    #             total_stats[k] += stats.get(k, 0)
    #     except Exception as e:
    #         logger.error(f"✗ Lỗi crawl chuyên mục '{cat_name}': {e}")

    # --- Bước 4: Ghi NEWS_RAW ---
    written = 0
    if all_new_articles:
        try:
            written = write_news_raw(spreadsheet, all_new_articles)
        except Exception as e:
            global_error = str(e)
            logger.error(f"✗ Lỗi ghi NEWS_RAW: {e}")
            traceback.print_exc()
    else:
        logger.info("ℹ Không có bài mới — bỏ qua bước ghi NEWS_RAW")

    # --- Bước 5: Ghi CRAWL_LOG ---
    try:
        write_crawl_log(
            spreadsheet,
            stats=total_stats,
            session_label=session_label,
            error_note=global_error,
        )
    except Exception as e:
        logger.error(f"✗ Lỗi ghi CRAWL_LOG: {e}")

    # --- Bước 6: Cập nhật DAILY_SUMMARY ---
    try:
        update_daily_summary(
            spreadsheet,
            new_count=total_stats["new"],
            duplicate_count=total_stats["skipped_duplicate"],
        )
    except Exception as e:
        logger.error(f"✗ Lỗi cập nhật DAILY_SUMMARY: {e}")

    # --- Bước 7: Tóm tắt ---
    logger.info("=" * 60)
    logger.info("📊 KẾT QUẢ CRAWL:")
    logger.info(f"   Tổng tìm thấy  : {total_stats['found']}")
    logger.info(f"   Bài mới        : {total_stats['new']}")
    logger.info(f"   Bài trùng bỏ qua: {total_stats['skipped_duplicate']}")
    logger.info(f"   Lỗi            : {total_stats['failed']}")
    logger.info(f"   Đã ghi Sheets  : {written} hàng")
    logger.info(f"   Phiên          : {session_label}")
    logger.info("=" * 60)

    # Exit code: 0 = thành công, 1 = có lỗi nghiêm trọng
    if global_error and total_stats["new"] == 0:
        logger.error("✗ Pipeline kết thúc với LỖI")
        sys.exit(1)
    else:
        logger.info("✅ Pipeline hoàn thành thành công")


if __name__ == "__main__":
    run_pipeline()