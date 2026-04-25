import logging
from logging.handlers import TimedRotatingFileHandler

from src.utils import LOGS_DIR


def setup_logger(console_logging = False):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt='[%(asctime)s] %(name)-12s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    if not logger.handlers:
        file_handler = TimedRotatingFileHandler(
            filename=LOGS_DIR / 'log', 
            when='midnight', 
            interval=1, 
            backupCount=30,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        if console_logging:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)