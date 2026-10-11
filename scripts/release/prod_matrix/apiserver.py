"""A fake apiserver. It records every request and enforces the continue token it issued.

The collector talks to this object in process. kubectl is not involved. A next page
that does not carry the token from the previous response is rejected.
"""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit

Handler = Callable[[str, str, dict[str, str], Any], dict]


def split_target(raw: str) -> tuple[str, dict[str, str]]:
    parsed = urlsplit(raw)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return parsed.path or raw, query


class FakeApiserver:
    def __init__(self, handler: Handler, scripts: dict[str, list[int]] | None = None) -> None:
        self.handler = handler
        self.scripts = {path: list(codes) for path, codes in (scripts or {}).items()}
        self.received: list[dict] = []
        self.issued: dict[str, str] = {}
        self._script_at: dict[str, int] = {}

    def __call__(self, method: str, raw: str, body: str | None) -> tuple[int, str, str]:
        path, query = split_target(raw)
        parsed = json.loads(body) if body else None
        self.received.append({"method": method, "path": path, "query": dict(query), "raw": raw, "body": body})
        scripted = self._scripted(path)
        if scripted is not None:
            return scripted
        expected = self.issued.get(path)
        if expected is not None and query.get("continue", "") != expected:
            return 1, "", "Error from server (BadRequest): continue"
        payload = self.handler(method, path, query, parsed)
        self._remember(path, payload)
        return 0, json.dumps(payload), ""

    def _scripted(self, path: str) -> tuple[int, str, str] | None:
        script = self.scripts.get(path) or []
        index = self._script_at.get(path, 0)
        if index >= len(script):
            return None
        self._script_at[path] = index + 1
        status = script[index]
        if status == 200:
            return None
        if status == 503:
            stderr = "Error from server (Service Unavailable): no"
        else:
            stderr = f"Error from server ({status}): no"
        return 1, json.dumps({"kind": "Status", "message": "unavailable", "code": status}), stderr

    def _remember(self, path: str, payload: dict) -> None:
        meta = payload.get("metadata") if isinstance(payload, dict) else None
        token = meta.get("continue") if isinstance(meta, dict) else None
        if isinstance(token, str) and token:
            self.issued[path] = token
        else:
            self.issued.pop(path, None)
