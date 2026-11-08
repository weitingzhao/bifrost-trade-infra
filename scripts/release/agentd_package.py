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


def values(run, section):
    result = {}
    for item in run.get(section, []):
        key = item["name"]
        if key in result:
            raise ValueError("duplicate evidence field")
        result[key] = item["value"]
    return result


def evidence(runs, commit, ui, infra):
    """Require an actual successful CI of the exact three cloned inputs."""
    if not all(SHA.fullmatch(x) for x in (commit, ui, infra)):
        raise ValueError("full input commits required")
    for run in runs:
        spec, status = run.get("spec", {}), run.get("status", {})
        if spec.get("pipelineRef", {}).get("name") != "bifrost-ci-platform":
            continue
        if not any(c.get("type") == "Succeeded" and c.get("status") == "True"
                   for c in status.get("conditions", [])):
            continue
        params, results = values(spec, "params"), values(status, "results")
        if (params.get("repo-url") != "http://gitea.cicd.svc.cluster.local:3000/bifrost/bifrost-platform.git"
                or params.get("revision") != commit or results.get("platform-commit") != commit
                or results.get("ui-commit") != ui or results.get("infra-commit") != infra):
            continue
        # Reuse/skip protocols are deliberately not extended by this closeout.
        if results.get("tested-by") or results.get("api-scope") not in ("full", "incremental"):
            continue
        return run["metadata"]["name"]
    raise ValueError("no successful CI for the exact delivery inputs; do not start another CI here")


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


def main():
    mode, directory = sys.argv[1:]
    out = Path(directory)
    if mode == "evidence":
        commit, ui, infra = (os.environ[k] for k in ("PLATFORM_COMMIT", "UI_COMMIT", "INFRA_COMMIT"))
        ci = evidence(json.load(sys.stdin)["items"], commit, ui, infra)
        out.mkdir(parents=True, exist_ok=True)
        (out / "evidence.json").write_text(json.dumps({"commit": commit, "ci": ci}))
        print(f"Reuse CI {ci} for agentd {commit}; no tests requested")
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
