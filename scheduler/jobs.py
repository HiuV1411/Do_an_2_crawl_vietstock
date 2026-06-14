"""
Định nghĩa các job crawl và lịch chạy.
Hỗ trợ cả Local (BlockingScheduler) và Cloud Run/GitHub Actions (BackgroundScheduler).
"""
import os
import time
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from crawler.cafef import crawl_new_articles
from storage.google_sheets import write_news_raw, write_crawl_log, update_daily_summary
from dedup.store import cleanup_old_records
from utils.logger import logger

TIMEZONE = "Asia/Ho_Chi_Minh"


def run_crawl_job(session: str) -> None:
    start_time = time.time()
    logger.info(f"{'='*60}")
    logger.info(f"[Job] BẮT ĐẦU phiên {session} lúc {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"{'='*60}")

    note = ""
    written = 0
    stats = {"total_found": 0, "new": 0, "duplicate": 0, "failed": 0}

    try:
        articles, stats = crawl_new_articles()

        if articles:
            written = write_news_raw(articles, stats, session)
            update_daily_summary(written, session)
        else:
            logger.info("[Job] Không có bài mới trong phiên này.")

        note = f"OK - {written} bài mới"

    except Exception as e:
        logger.error(f"[Job] LỖI NGHIÊM TRỌNG trong phiên {session}: {e}", exc_info=True)
        note = f"ERROR: {str(e)[:200]}"
        stats = {"total_found": 0, "new": 0, "duplicate": 0, "failed": 1}

    finally:
        duration = time.time() - start_time
        try:
            write_crawl_log(session, stats, duration, note)
        except Exception as log_err:
            logger.error(f"[Job] Không ghi được log: {log_err}")

        logger.info(
            f"[Job] KẾT THÚC phiên {session} — "
            f"Thời gian: {duration:.1f}s | Ghi: {written} bài | {note}"
        )
        logger.info(f"{'='*60}\n")


def morning_job():
    run_crawl_job("MORNING")


def evening_job():
    run_crawl_job("EVENING")


def start_scheduler() -> None:
    """Dùng cho local: BlockingScheduler giữ main thread sống."""
    morning_time = os.getenv("SCHEDULE_MORNING", "08:30")
    evening_time = os.getenv("SCHEDULE_EVENING", "18:30")
    morning_h, morning_m = morning_time.split(":")
    evening_h, evening_m = evening_time.split(":")

    scheduler = BlockingScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        morning_job,
        trigger=CronTrigger(hour=int(morning_h), minute=int(morning_m), timezone=TIMEZONE),
        id="morning_crawl",
        name=f"Crawl sáng {morning_time}",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        evening_job,
        trigger=CronTrigger(hour=int(evening_h), minute=int(evening_m), timezone=TIMEZONE),
        id="evening_crawl",
        name=f"Crawl chiều {evening_time}",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        lambda: cleanup_old_records(days=30),
        trigger=CronTrigger(hour=0, minute=1, timezone=TIMEZONE),
        id="cleanup_dedup",
        name="Dọn dedup DB",
    )

    logger.info(f"[Scheduler] Lịch: sáng {morning_time}, chiều {evening_time} (ICT)")
    logger.info("[Scheduler] Đang chờ... Nhấn Ctrl+C để dừng.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[Scheduler] Đã dừng.")


def start_scheduler_background() -> None:
    """Dùng cho Cloud Run: BackgroundScheduler chạy trong thread riêng."""
    morning_time = os.getenv("SCHEDULE_MORNING", "08:30")
    evening_time = os.getenv("SCHEDULE_EVENING", "18:30")
    morning_h, morning_m = morning_time.split(":")
    evening_h, evening_m = evening_time.split(":")

    scheduler = BackgroundScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        morning_job,
        trigger=CronTrigger(hour=int(morning_h), minute=int(morning_m), timezone=TIMEZONE),
        id="morning_crawl",
        name=f"Crawl sáng {morning_time}",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        evening_job,
        trigger=CronTrigger(hour=int(evening_h), minute=int(evening_m), timezone=TIMEZONE),
        id="evening_crawl",
        name=f"Crawl chiều {evening_time}",
        misfire_grace_time=300,
    )
    scheduler.add_job(
        lambda: cleanup_old_records(days=30),
        trigger=CronTrigger(hour=0, minute=1, timezone=TIMEZONE),
        id="cleanup_dedup",
        name="Dọn dedup DB",
    )

    scheduler.start()
    logger.info(f"[Scheduler] Background scheduler khởi động (sáng {morning_time}, chiều {evening_time})")

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("[Scheduler] Background scheduler đã dừng.")