from __future__ import annotations

import logging
import re
from typing import Final


_HYSTERIA_SECRET_PATTERN: Final = re.compile(
    r"(?i)(hysteria_secret['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"
)
_BEARER_TOKEN_PATTERN: Final = re.compile(r"(?i)(bearer\s+)\S+")


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        message = _HYSTERIA_SECRET_PATTERN.sub(r"\1[REDACTED]", message)
        record.msg = _BEARER_TOKEN_PATTERN.sub(r"\1[REDACTED]", message)
        record.args = ()
        return True
