from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

LOGGER = logging.getLogger(__name__)


def with_retry(fn: Callable[[], T], attempts: int = 3, base_delay: float = 1.5) -> T:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == attempts:
                break
            delay = base_delay * attempt
            LOGGER.warning("Retrying after error on attempt %s/%s: %s", attempt, attempts, exc)
            time.sleep(delay)
    assert last_error is not None
    raise last_error
