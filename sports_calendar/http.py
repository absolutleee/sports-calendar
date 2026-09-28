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
# URLs that already failed this run. Re-raised without retrying, so every rule
# that needs a failed URL fails alike: otherwise a main-calendar rule could lose
# a game that a later secondary-calendar rule then fetched and showed instead.
_failed: dict[str, "FetchError"] = {}
_sleep = time.sleep  # patched in tests


class FetchError(Exception):
    """A request failed after all retries."""


class NotFound(FetchError):
    """The server returned 404 (not retried; callers may treat as 'no data yet')."""


def clear_cache() -> None:
    _cache.clear()
    _failed.clear()


def get_json(url: str, params: dict | None = None, *, attempts: int = 3, timeout: int = 20) -> Any:
    key = url + ("?" + urlencode(params) if params else "")
    if key in _cache:
        return _cache[key]
    if key in _failed:
        raise _failed[key]

    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
            if resp.status_code == 404:
                raise NotFound(key)
            resp.raise_for_status()
            data = resp.json()
        except NotFound as exc:
            _failed[key] = exc
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

    _failed[key] = FetchError(f"{key}: {last_error}")
    raise _failed[key]
