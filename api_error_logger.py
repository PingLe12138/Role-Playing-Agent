"""Global API error logger.

/ 全局 API 错误日志记录器。

Logs all unhandled exceptions from route handlers to `logs/api_errors.log`
with rotation at 5 MB per file (3 backups).
/ 将路由处理函数中所有未捕获的异常记录到 `logs/api_errors.log`,
   单文件 5 MB 轮转, 最多保留 3 个备份。
"""

import logging
from logging.handlers import RotatingFileHandler
import traceback

import paths

_log_dir = paths.LOGS_DIR
_log_dir.mkdir(exist_ok=True)
_handler = RotatingFileHandler(
    _log_dir / "api_errors.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

_logger = logging.getLogger("api_error")
_logger.addHandler(_handler)
_logger.setLevel(logging.ERROR)


def log_exception(method: str, path: str, exc: Exception):
    _logger.error(
        f"{method} {path}\n"
        f"  {type(exc).__name__}: {exc}\n"
        f"{traceback.format_exc().rstrip()}"
    )
