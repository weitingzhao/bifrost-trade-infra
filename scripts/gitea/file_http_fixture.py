"""File transport for existing HTTP handlers, following agent-host's fixture.

No listening sockets. Child urllib still runs its real redirect/error handlers;
curl is a small test executable. Any URL outside registered fixtures fails.
"""
import atexit
from email.message import Message
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

SHIM = '''import io, json, os, time, urllib.error, urllib.parse, urllib.request, uuid
from email.message import Message
from pathlib import Path
from urllib.response import addinfourl

def fixture_http_open(self, req):
    parsed = urllib.parse.urlsplit(req.full_url)
    destination = urllib.parse.urlsplit("http://" + req.host)
    root = Path(os.environ["GITEA_TEST_HTTP_DIR"])
    if destination.hostname != "127.0.0.1" or not (root / str(destination.port)).exists():
        raise urllib.error.URLError("unregistered fixture URL; network disabled")
    path = root / str(destination.port) / (uuid.uuid4().hex + ".request")
    body = (req.data or b"").decode()
    headers = dict(req.header_items())
    headers["Content-Length"] = str(len(body.encode()))
    data = {"method": req.get_method(), "path": req.selector,
            "headers": headers, "body": body}
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data)); temp.rename(path)
    answer = path.with_suffix(".response")
    deadline = time.monotonic() + 15
    while not answer.exists():
        if time.monotonic() > deadline: raise urllib.error.URLError("fixture timed out")
        time.sleep(0.005)
    result = json.loads(answer.read_text()); answer.unlink()
    headers = Message()
    for k, v in result["headers"]: headers[k] = v
    response = addinfourl(io.BytesIO(result["body"].encode()), headers, req.full_url, result["code"])
    response.msg = "fixture response"
    return response
urllib.request.HTTPHandler.http_open = fixture_http_open
urllib.request.HTTPSHandler.https_open = fixture_http_open
'''

CURL = '''import base64, json, sys, urllib.error, urllib.request
from pathlib import Path
args = iter(sys.argv[1:])
output = header_output = config = fmt = None
headers = {}; url = None; fail = False
for arg in args:
    if arg in ("-K", "--config"): config = next(args)
    elif arg in ("-o", "--output"): output = next(args)
    elif arg in ("-D", "--dump-header"): header_output = next(args)
    elif arg in ("-w", "--write-out"): fmt = next(args)
    elif arg in ("--noproxy", "--max-time", "--max-redirs"): next(args)
    elif arg.startswith("--"): assert arg in ("--silent", "--show-error", "--fail"); fail |= arg == "--fail"
    elif arg.startswith("-"): assert set(arg[1:]) <= set("qsfS"); fail |= "f" in arg
    else: url = arg
if config:
    text = sys.stdin.read() if config == "-" else Path(config).read_text()
    for line in text.splitlines():
        key, value = line.split("=", 1); value = json.loads(value.strip())
        if key.strip() == "header":
            name, value = value.split(":", 1); headers[name] = value.strip()
        elif key.strip() == "user":
            headers["Authorization"] = "Basic " + base64.b64encode(value.encode()).decode()
        else: raise AssertionError("unexpected curl config")
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args): return None
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
try:
    response = opener.open(urllib.request.Request(url, headers=headers))
except urllib.error.HTTPError as error:
    response = error
body = response.read()
if header_output:
    Path(header_output).write_text("".join(k + ": " + v + "\\r\\n" for k, v in response.headers.items()))
if not (fail and response.code >= 400):
    if output: Path(output).write_bytes(body)
    else: sys.stdout.buffer.write(body)
if fmt: sys.stdout.write(fmt.replace("%{http_code}", str(response.code)))
sys.exit(22 if fail and response.code >= 400 else 0)
'''

_transport = None
_next_port = 62000


def _prepare():
    global _transport
    if _transport is None:
        _transport = tempfile.TemporaryDirectory(prefix="gitea-file-http-")
        atexit.register(_transport.cleanup)
        root = Path(_transport.name)
        (root / "sitecustomize.py").write_text(SHIM)
        (root / "curl").write_text("#!" + sys.executable + "\n" + CURL)
        (root / "curl").chmod(0o755)
        os.environ["GITEA_TEST_HTTP_DIR"] = str(root)
        os.environ["PYTHONPATH"] = str(root) + os.pathsep + os.environ.get("PYTHONPATH", "")
        os.environ["PATH"] = str(root) + os.pathsep + os.environ["PATH"]
    return Path(_transport.name)


class ThreadingHTTPServer:
    """The server API used by the existing tests, backed by request/response files."""

    def __init__(self, address, handler):
        global _next_port
        self.server_address = ("127.0.0.1", _next_port)
        _next_port += 1
        self.directory = _prepare() / str(self.server_address[1])
        self.directory.mkdir()
        self.handler = handler
        self.stopping = threading.Event()
        self.finished = threading.Event()

    def serve_forever(self):
        try:
            while not self.stopping.wait(0.005):
                for path in self.directory.glob("*.request"):
                    request = json.loads(path.read_text())
                    handler = self.handler.__new__(self.handler)
                    handler.command, handler.path = request["method"], request["path"]
                    handler.headers = Message()
                    for key, value in request["headers"].items():
                        handler.headers[key] = value
                    handler.rfile, handler.wfile = io.BytesIO(request["body"].encode()), io.BytesIO()
                    headers = []
                    handler.send_response = lambda code: setattr(handler, "code", code)
                    handler.send_header = lambda k, v: headers.append((k, str(v)))
                    handler.end_headers = lambda: None
                    getattr(handler, "do_" + handler.command)()
                    response = {"code": handler.code, "body": handler.wfile.getvalue().decode(), "headers": headers}
                    temp = path.with_suffix(".tmp")
                    temp.write_text(json.dumps(response))
                    temp.rename(path.with_suffix(".response"))
                    path.unlink()
        finally:
            self.finished.set()

    def shutdown(self):
        self.stopping.set()
        self.finished.wait(5)

    def server_close(self):
        self.shutdown()
