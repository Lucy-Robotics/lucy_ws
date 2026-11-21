from __future__ import annotations

import subprocess
import time
from typing import Callable

RETRY_DELAYS_S = (10, 30)


def with_retries(
    what: str, attempt: Callable[[], object], log: Callable[[str], None], sleep: Callable[[float], None] = time.sleep
) -> None:
    for delay in RETRY_DELAYS_S:
        try:
            attempt()
            return
        except subprocess.CalledProcessError as error:
            log(f"{what} failed (exit code {error.returncode}), retrying in {delay}s")
            sleep(delay)
    attempt()
