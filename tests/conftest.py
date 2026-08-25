import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def fixture():
    return load_fixture


@pytest.fixture
def fake_fetch(monkeypatch):
    """Replace http.get_json with a lookup table.

    mapping: list of (needles, payload). needles is a str or tuple of str; every
    needle must appear in the full URL (url + '?' + encoded params). payload is a
    fixture filename (str) or a dict. First match wins. Unmatched URLs raise.
    """
    from sports_calendar import http

    def install(mapping):
        calls = []

        def _get(url, params=None, **kwargs):
            full = url + ("?" + urlencode(params) if params else "")
            calls.append(full)
            for needles, payload in mapping:
                if isinstance(needles, str):
                    needles = (needles,)
                if all(n in full for n in needles):
                    return load_fixture(payload) if isinstance(payload, str) else payload
            raise AssertionError(f"unexpected fetch: {full}")

        monkeypatch.setattr(http, "get_json", _get)
        return calls

    return install
