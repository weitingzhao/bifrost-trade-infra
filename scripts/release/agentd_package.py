"""Publish an immutable agentd package after the ordinary STG delivery.

The build step has no upload credentials. This helper never starts CI or tests.
"""

import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

PACKAGE = "http://gitea.cicd.svc.cluster.local:3000/api/packages/bifrost-agentd-publisher/generic/agentd"
SHA = re.compile(r"[0-9a-f]{40}\Z")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("package redirect refused")


def publish(commit, binary, username, password, request=None):
    if not SHA.fullmatch(commit) or not username or not password:
        raise ValueError("commit and dedicated publisher credentials required")
    digest = hashlib.sha256(binary).hexdigest()
    auth = "Basic " + base64.b64encode((username + ":" + password).encode()).decode()
    opener = build_opener(NoRedirect())

    def http(method, name, body=None):
        req = Request(f"{PACKAGE}/{commit}/{name}", data=body, method=method,
                      headers={"Authorization": auth, "Content-Type": "application/octet-stream"})
        try:
            with opener.open(req, timeout=60) as response:
                return response.status, response.read()
        except HTTPError as error:
            # Never put a credential or an upstream response body in logs.
            return error.code, b""

    send = request or http
    # The checksum is the platform's discovery marker: publish it last.
    for name, body in (("agentd-linux-amd64", binary),
                       ("agentd.sha256", f"{digest}  agentd-linux-amd64\n".encode())):
        status, old = send("GET", name)
        if status == 404:
            status, _ = send("PUT", name, body)
            if status not in (200, 201, 409):
                raise ValueError(f"package upload failed: HTTP {status}")
            status, old = send("GET", name)
        if status != 200 or old != body:
            raise ValueError(f"package readback mismatch: {name}; existing content is never overwritten")
    return digest


def delivery_proof(proof, commit, ui, infra):
    if not all(SHA.fullmatch(x) for x in (commit, ui, infra)):
        raise ValueError("full input commits required")
    if not isinstance(proof, dict) or tuple(proof.get(k) for k in ("commit", "ui", "infra")) != (commit, ui, infra):
        raise ValueError("CI receipt does not match the exact delivery inputs")
    ci = proof.get("ci")
    if not isinstance(ci, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,252}", ci):
        raise ValueError("invalid CI run in delivery receipt")
    return {"commit": commit, "ui": ui, "infra": infra, "ci": ci}


def main():
    mode, directory = sys.argv[1:]
    out = Path(directory)
    if mode == "accept-evidence":
        commit, ui, infra = (os.environ[k] for k in ("PLATFORM_COMMIT", "UI_COMMIT", "INFRA_COMMIT"))
        proof = delivery_proof(json.loads(os.environ["CI_EVIDENCE"]), commit, ui, infra)
        out.mkdir(parents=True, exist_ok=True)
        (out / "evidence.json").write_text(json.dumps(proof))
        print(f"Reuse CI {proof['ci']} for agentd {commit}; no tests requested")
    elif mode == "publish":
        proof = json.loads((out / "evidence.json").read_text())
        digest = publish(proof["commit"], (out / "agentd-linux-amd64").read_bytes(),
                         os.environ["PUBLISH_USERNAME"], os.environ["PUBLISH_PASSWORD"])
        Path(os.environ["COMMIT_RESULT"]).write_text(proof["commit"])
        Path(os.environ["SHA256_RESULT"]).write_text(digest)
        print(f"Published agentd {proof['commit']} sha256 {digest} using CI {proof['ci']}")
    else:
        raise ValueError("unknown mode")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        sys.exit(f"agentd package refused: {type(error).__name__}: {error}")
