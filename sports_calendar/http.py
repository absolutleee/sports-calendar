"""Single network seam. Everything that talks to the internet goes through get_json."""
from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)

USER_AGENT = "sports-calendar/1.0 (+https://github.com)"
_cache: dict[str, Any] = {}
_sleep = time.sleep  # patched in tests


class FetchError(Exception):
    """A request failed after all retries."""


class NotFound(FetchError):
    """The server returned 404 (not retried; callers may treat as 'no data yet')."""


def clear_cache() -> None:
    _cache.clear()


def get_json(url: str, params: dict | None = None, *, attempts: int = 3, timeout: int = 20) -> Any:
    key = url + ("?" + urlencode(params) if params else "")
    if key in _cache:
        return _cache[key]

    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
            if resp.status_code == 404:
                raise NotFound(key)
            resp.raise_for_status()
            data = resp.json()
        except NotFound:
            raise
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            log.warning("fetch failed (attempt %d/%d) %s: %s", attempt, attempts, key, exc)
            if attempt < attempts:
                _sleep(delay)
                delay *= 2
            continue
        _cache[key] = data
        return data

    raise FetchError(f"{key}: {last_error}")
