import logging
import os

log_level = os.getenv("LOG_LEVEL", "info")
level = getattr(logging, log_level.upper(), logging.INFO)
log_format = "[L %(lineno)s - %(funcName)5s() ] %(message)s"
logging.basicConfig(level=level, format=log_format)
