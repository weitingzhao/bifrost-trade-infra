"""A fake Gitea API for the cicd script tests: answers from a routing table,
records each request (method, path, Authorization header). Local only."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeGitea:
    def __init__(self, routes: dict[str, tuple[int, str]]) -> None:
        self.routes = routes
        self.requests: list[tuple[str, str, str]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
                outer.requests.append((self.command, self.path, self.headers.get("Authorization", "")))
                code, body = outer.routes.get(f"{self.command} {self.path}", (404, "{}"))
                data = body.encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = _answer

            def log_message(self, *args) -> None:  # quiet
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self) -> "FakeGitea":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

    def calls(self, method: str | None = None) -> list[str]:
        return [f"{m} {p}" for m, p, _ in self.requests if method is None or m == method]


def repo(name: str, body: str) -> dict[str, tuple[int, str]]:
    return {f"GET /api/v1/repos/bifrost/{name}": (200, body)}
