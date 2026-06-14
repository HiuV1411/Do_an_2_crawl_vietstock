"""
Cấu hình logging tập trung cho toàn dự án.
Ghi log ra cả file và console.
"""
import logging
import os
from datetime import datetime


def setup_logger(name: str = "cafef_crawler") -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    os.makedirs("logs", exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    log_file = f"logs/crawler_{today}.log"

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()