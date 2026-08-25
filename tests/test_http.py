import pytest
import requests

from sports_calendar import http


class FakeResponse:
    def __init__(self, status, payload=None, bad_json=False):
        self.status_code = status
        self._payload = payload
        self._bad_json = bad_json

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code}")
            err.response = self
            raise err

    def json(self):
        if self._bad_json:
            raise ValueError("bad json")
        return self._payload


@pytest.fixture(autouse=True)
def no_sleep_and_clear_cache(monkeypatch):
    monkeypatch.setattr(http, "_sleep", lambda s: None)
    http.clear_cache()


def test_returns_json(monkeypatch):
    monkeypatch.setattr(http.requests, "get", lambda *a, **k: FakeResponse(200, {"ok": 1}))
    assert http.get_json("https://x/y", {"a": 1}) == {"ok": 1}


def test_caches_by_url_and_params(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, tuple(sorted((kwargs.get("params") or {}).items()))))
        return FakeResponse(200, {"n": len(calls)})

    monkeypatch.setattr(http.requests, "get", fake_get)
    assert http.get_json("https://x/y", {"a": 1}) == {"n": 1}
    assert http.get_json("https://x/y", {"a": 1}) == {"n": 1}
    assert http.get_json("https://x/y", {"a": 2}) == {"n": 2}
    assert len(calls) == 2


def test_retries_then_succeeds(monkeypatch):
    responses = [FakeResponse(500), FakeResponse(200, bad_json=True), FakeResponse(200, {"ok": 1})]
    monkeypatch.setattr(http.requests, "get", lambda *a, **k: responses.pop(0))
    assert http.get_json("https://x/y") == {"ok": 1}


def test_raises_fetch_error_after_attempts(monkeypatch):
    monkeypatch.setattr(http.requests, "get", lambda *a, **k: FakeResponse(500))
    with pytest.raises(http.FetchError):
        http.get_json("https://x/y")


def test_404_raises_not_found_without_retry(monkeypatch):
    calls = []

    def fake_get(*a, **k):
        calls.append(1)
        return FakeResponse(404)

    monkeypatch.setattr(http.requests, "get", fake_get)
    with pytest.raises(http.NotFound):
        http.get_json("https://x/missing")
    assert len(calls) == 1


def test_connection_error_retries(monkeypatch):
    attempts = []

    def fake_get(*a, **k):
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.ConnectionError("boom")
        return FakeResponse(200, {"ok": 1})

    monkeypatch.setattr(http.requests, "get", fake_get)
    assert http.get_json("https://x/y") == {"ok": 1}
    assert len(attempts) == 3
