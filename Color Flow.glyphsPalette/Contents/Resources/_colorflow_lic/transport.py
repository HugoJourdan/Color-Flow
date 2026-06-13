"""urllib-backed HttpTransport matching licensing.HttpTransport:
(method, url, fields) -> {"status": int, "body": dict}."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def urllib_transport(method: str, url: str, fields: dict[str, str]) -> dict[str, Any]:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.getcode()
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:        # 4xx/5xx with a body
        status = exc.code
        raw = exc.read().decode("utf-8", "replace")
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            body = {}
    except json.JSONDecodeError:
        body = {}
    return {"status": status, "body": body}
