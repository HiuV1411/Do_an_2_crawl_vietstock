"""
Entry point của hệ thống Cafef News Crawler.

Cách dùng:
    python main.py                  → Khởi động scheduler tự động (chạy liên tục)
    python main.py --run-now        → Chạy crawl ngay lập tức (test nhanh)
    python main.py --session MORNING → Chạy đúng một phiên cụ thể

Khi deploy lên Cloud Run:
    Container tự nhận biết môi trường Cloud Run qua biến K_SERVICE.
    Scheduler chạy trong background thread.
    HTTP server nhỏ lắng nghe PORT để Cloud Run health check.
"""
import sys
import os
import threading

# Đảm bảo thư mục gốc dự án luôn nằm trong sys.path
# Fix lỗi ModuleNotFoundError khi chạy từ bất kỳ thư mục nào
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv

# Load biến môi trường từ file .env TRƯỚC KHI import các module khác
# Trên Cloud Run, biến env được set qua Cloud Console → load_dotenv sẽ không ghi đè
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

from utils.logger import logger
from scheduler.jobs import start_scheduler_background, run_crawl_job


def run_health_server():
    """
    HTTP server tối giản để Cloud Run health check.
    Chỉ chạy khi deploy trên Cloud Run (biến K_SERVICE được tự động set bởi Cloud Run).
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK - CafeF Crawler is running")

        def log_message(self, format, *args):
            pass  # Tắt log mặc định của HTTPServer để không lộn với crawler log

    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"[Health] HTTP server lắng nghe port {port}")
    server.serve_forever()


def main():
    args = sys.argv[1:]

    logger.info("╔══════════════════════════════════════╗")
    logger.info("║    CafeF News Crawler — Starting     ║")
    logger.info("╚══════════════════════════════════════╝")

    if "--run-now" in args:
        # Chạy ngay lập tức để test thủ công
        logger.info("[Main] Chế độ: RUN NOW (test thủ công)")
        run_crawl_job("MANUAL")

    elif "--session" in args:
        idx = args.index("--session")
        session = args[idx + 1].upper() if idx + 1 < len(args) else "MANUAL"
        logger.info(f"[Main] Chế độ: Chạy phiên {session}")
        run_crawl_job(session)

    else:
        # Chế độ mặc định: scheduler tự động
        is_cloud_run = bool(os.getenv("K_SERVICE"))  # Cloud Run tự set biến này

        if is_cloud_run:
            # ── Cloud Run mode ──────────────────────────────────────
            # Scheduler chạy trong background thread
            # Main thread chạy HTTP server để Cloud Run không kill container
            logger.info("[Main] Chế độ: CLOUD RUN — Scheduler + HTTP health server")
            scheduler_thread = threading.Thread(
                target=start_scheduler_background, daemon=True
            )
            scheduler_thread.start()
            run_health_server()  # Block main thread
        else:
            # ── Local mode ───────────────────────────────────────────
            # BlockingScheduler giữ main thread sống
            logger.info("[Main] Chế độ: LOCAL SCHEDULER (tự động 24/7)")
            from scheduler.jobs import start_scheduler
            start_scheduler()


if __name__ == "__main__":
    main()