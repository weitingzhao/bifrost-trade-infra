"""promote() against a fake Docker Registry v2. No real registry."""

import hashlib
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import sys

sys.path.insert(0, os.path.dirname(__file__))

from registry_retag import RegistryError, digest_of, pod_digest, promote  # noqa: E402

DOCKER = "application/vnd.docker.distribution.manifest.v2+json"
INDEX = "application/vnd.oci.image.index.v1+json"
REPO = "bifrost-platform-api"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        item = self._item()
        if item is None:
            self._send(404, b"not found", "text/plain")
            return
        body, media = item
        accept = self.headers.get("Accept", "")
        if media not in accept:
            self._send(406, b"accept", "text/plain")
            return
        self._send(200, body, media, digest_of(body))

    def do_PUT(self):
        parsed = self._parse()
        if parsed is None:
            self._send(404, b"not found", "text/plain")
            return
        repo, ref = parsed
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        media = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        self.server.puts.append((repo, ref, media, body))
        self.server.store[(repo, ref)] = (body, media)
        self.server.store[(repo, digest_of(body))] = (body, media)
        self._send(201, b"", media, digest_of(body))

    def _item(self):
        parsed = self._parse()
        if parsed is None:
            return None
        return self.server.store.get(parsed)

    def _parse(self):
        path = self.path.split("?", 1)[0]
        marker = "/manifests/"
        prefix = "/v2/"
        if not path.startswith(prefix) or marker not in path:
            return None
        repo, ref = path[len(prefix):].split(marker, 1)
        return repo, ref

    def _send(self, code, body, media, digest=None):
        self.send_response(code)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(body)))
        if digest:
            self.send_header("Docker-Content-Digest", digest)
        self.end_headers()
        if body:
            self.wfile.write(body)


@pytest.fixture
def registry():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.store = {}
    httpd.puts = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()


def _url(httpd) -> str:
    return f"http://127.0.0.1:{httpd.server_address[1]}"


def _seed(httpd, ref, body, media):
    httpd.store[(REPO, ref)] = (body, media)
    httpd.store[(REPO, digest_of(body))] = (body, media)


def _manifest(media, marker):
    # Exact bytes, including the space after the colon, so a re-encode would fail.
    return (
        '{"schemaVersion":2, "mediaType":"%s", "marker":"%s"}\n' % (media, marker)
    ).encode()


def test_single_manifest_put_is_byte_identical(registry) -> None:
    src = _manifest(DOCKER, "from-stg")
    old = _manifest(DOCKER, "previous-prod")
    _seed(registry, "stg", src, DOCKER)
    _seed(registry, "prod", old, DOCKER)
    got = promote(REPO, digest_of(src), "prod", "prod-prev", base_url=_url(registry))
    assert got == digest_of(src)
    assert got == "sha256:" + hashlib.sha256(src).hexdigest()
    assert registry.store[(REPO, "prod")] == (src, DOCKER)
    assert registry.store[(REPO, "prod-prev")] == (old, DOCKER)
    assert registry.puts == [
        (REPO, "prod-prev", DOCKER, old),
        (REPO, "prod", DOCKER, src),
    ]


def test_index(registry) -> None:
    src = _manifest(INDEX, "index")
    old = _manifest(INDEX, "old-index")
    _seed(registry, "stg", src, INDEX)
    _seed(registry, "prod", old, INDEX)
    got = promote(REPO, "stg", "prod", "prod-prev", base_url=_url(registry))
    assert got == digest_of(src)
    assert registry.puts[0] == (REPO, "prod-prev", INDEX, old)
    assert registry.puts[1] == (REPO, "prod", INDEX, src)
    assert registry.store[(REPO, "prod")][0] == src


def test_missing_source_changes_nothing(registry) -> None:
    old = _manifest(DOCKER, "keep")
    _seed(registry, "prod", old, DOCKER)
    before = dict(registry.store)
    with pytest.raises(RegistryError, match="not found"):
        promote(REPO, "missing", "prod", "prod-prev", base_url=_url(registry))
    assert registry.puts == []
    assert registry.store == before


def test_target_absent_the_first_time(registry) -> None:
    src = _manifest(DOCKER, "first")
    _seed(registry, "stg", src, DOCKER)
    got = promote(REPO, "stg", "prod", "prod-prev", base_url=_url(registry))
    assert got == digest_of(src)
    assert registry.store[(REPO, "prod")] == (src, DOCKER)
    assert (REPO, "prod-prev") not in registry.store
    assert registry.puts == [(REPO, "prod", DOCKER, src)]


def test_rerun_is_a_noop(registry) -> None:
    src = _manifest(DOCKER, "from-stg")
    old = _manifest(DOCKER, "previous-prod")
    _seed(registry, "stg", src, DOCKER)
    _seed(registry, "prod", old, DOCKER)
    promote(REPO, "stg", "prod", "prod-prev", base_url=_url(registry))
    puts = list(registry.puts)
    prev = registry.store[(REPO, "prod-prev")]
    again = promote(REPO, "stg", "prod", "prod-prev", base_url=_url(registry))
    assert again == digest_of(src)
    assert registry.puts == puts
    assert registry.store[(REPO, "prod-prev")] == prev
    assert registry.store[(REPO, "prod")][0] == src


def test_pod_digest_from_image_id() -> None:
    digest = "sha256:" + "ab" * 32
    pods = {"items": [
        {
            "metadata": {"name": "platform-api-a"},
            "status": {"containerStatuses": [{
                "name": "platform-api",
                "ready": True,
                "imageID": f"docker-pullable://192.168.10.73:30500/bifrost-platform-api@{digest}",
            }]},
        },
        {
            "metadata": {"name": "platform-api-b", "deletionTimestamp": "2026-10-10T12:00:00Z"},
            "status": {"containerStatuses": [{
                "name": "platform-api",
                "ready": True,
                "imageID": "sha256:" + "cd" * 32,
            }]},
        },
    ]}
    assert pod_digest(pods, "platform-api") == digest
    pods["items"].append({
        "metadata": {"name": "platform-api-c"},
        "status": {"containerStatuses": [{
            "name": "platform-api",
            "ready": True,
            "imageID": "sha256:" + "ef" * 32,
        }]},
    })
    with pytest.raises(RegistryError, match="disagree"):
        pod_digest(pods, "platform-api")
