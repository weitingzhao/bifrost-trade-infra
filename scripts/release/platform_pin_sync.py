"""Pin a platform Argo application to two image digests and sync it; embedded in the gitops-sync Task.

TD-335, TD-419 (W-31 3.4 ①): a platform delivery deploys the digests it built (STG) or
the digests STG verified (PROD), not a tag. The application's kustomize image override
names them, so Argo renders the Deployments with image@digest; a tag that moves later
changes nothing that runs, and a restart pulls the same bytes. One merge patch writes
the override and the sync request together, so the sync Argo runs is of the new spec.
The wait recognises this run's own sync by the name it signs the request with, never by
timestamps. The rollout's verifier (requireSpecDigest) is what proves the Deployments
and Pods; this only orders the pin before it.
"""

import json
import os
import re
import subprocess
import time

DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
RUN_RE = re.compile(r"[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?\Z")
NAMESPACE = "cicd"
# application -> (overlay path, destination namespace)
APPLICATIONS = {
    "bifrost-platform-stg": ("k8s/overlays/platform-stg", "bifrost-platform-stg"),
    "bifrost-platform-prod": ("k8s/overlays/platform-prod", "bifrost-platform-prod"),
}
# The overlays' image entries name the base image; the override keeps their new name.
SOURCE = "registry.cicd.svc.cluster.local:5000/bifrost-platform-%s"
TARGET = "192.168.10.73:30500/bifrost-platform-%s"
# The whole step's time and one call's at most; the tests shorten them.
WAIT_S = int(os.environ.get("PIN_SYNC_WAIT_S", "180"))
CALL_S = int(os.environ.get("PIN_SYNC_CALL_S", "20"))
POLL_S = float(os.environ.get("PIN_SYNC_POLL_S", "2"))


class Refused(ValueError):
    """A refusal with a fixed, task-owned log message."""


class OutOfTime(Refused):
    """The step's deadline, not a slow cluster, ended a call."""


def kubectl(args, deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise OutOfTime("the step's time ran out")
    # No connection flags: with any of them kubectl in a pod stops using its
    # in-cluster identity (the deliver gate's trial run, 2026-10-12).
    try:
        return subprocess.run(
            ["kubectl", "-n", NAMESPACE, *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=min(CALL_S, left),
        ).stdout
    except subprocess.TimeoutExpired:
        if left < CALL_S:
            raise OutOfTime("the step's time ran out") from None
        raise Refused("a cluster call did not answer in time") from None
    except subprocess.CalledProcessError as exc:
        text = exc.stderr.lower() if isinstance(exc.stderr, str) else ""
        if "forbidden" in text or "unauthorized" in text:
            raise Refused("this identity cannot read or patch the application") from None
        raise Refused("a cluster call failed") from None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refused("duplicate JSON key")
        result[key] = value
    return result


def read_app(app, deadline):
    try:
        doc = json.loads(
            kubectl(["get", "application", app, "-o", "json"], deadline),
            object_pairs_hook=unique_object,
        )
    except json.JSONDecodeError:
        raise Refused("malformed application JSON") from None
    if not isinstance(doc, dict) or doc.get("metadata", {}).get("name") != app:
        raise Refused("the application read is not " + app)
    return doc


def pinned(doc, digests):
    """Whether the application reports both pinned images among its images."""
    images = doc.get("status", {}).get("summary", {}).get("images") or []
    if not isinstance(images, list):
        return False
    return all(
        any(
            isinstance(i, str) and i.startswith(TARGET % kind) and i.endswith("@" + digest)
            for i in images
        )
        for kind, digest in digests.items()
    )


def main():
    written = False
    try:
        app = os.environ["APPLICATION"]
        digests = {"api": os.environ["API_DIGEST"], "console": os.environ["CONSOLE_DIGEST"]}
        run = os.environ["DELIVER_RUN"]
        if app not in APPLICATIONS:
            raise Refused("not a platform application")
        if not all(DIGEST_RE.fullmatch(d) for d in digests.values()):
            raise Refused("invalid image digest")
        if not RUN_RE.fullmatch(run):
            raise Refused("invalid pipeline run name")
        path, destination = APPLICATIONS[app]
        deadline = time.monotonic() + WAIT_S
        doc = read_app(app, deadline)
        spec = doc["spec"]
        if spec["source"]["path"] != path or spec["destination"]["namespace"] != destination:
            raise Refused("the application does not deploy " + path + " to " + destination)
        # A sync already queued or running finishes first: one operation at a time.
        while "operation" in doc:
            if time.monotonic() + POLL_S >= deadline:
                raise Refused("another sync of the application did not finish in time")
            time.sleep(POLL_S)
            try:
                doc = read_app(app, deadline)
            except OutOfTime:
                raise Refused("another sync of the application did not finish in time") from None
        who = "tekton-deliver-platform:" + run
        patch = {
            "spec": {"source": {"kustomize": {"images": [
                SOURCE % kind + "=" + TARGET % kind + "@" + digests[kind] for kind in ("api", "console")
            ]}}},
            "operation": {"initiatedBy": {"username": who}, "sync": {"revision": "HEAD"}},
        }
        written = True  # from here the application may be pinned, the patch's answer lost or not
        kubectl(["patch", "application", app, "--type", "merge", "-p", json.dumps(patch)], deadline)
        print("pinned %s to api %s and console %s; sync requested as %s" % (app, digests["api"], digests["console"], who))
        late = "this run's sync did not finish with the pinned images in %d s" % WAIT_S
        while True:
            try:
                doc = read_app(app, deadline)
            except OutOfTime:
                raise Refused(late) from None
            state = doc.get("status", {}).get("operationState") or {}
            mine = (state.get("operation") or {}).get("initiatedBy", {}).get("username") == who
            phase = state.get("phase")
            if mine and phase in ("Failed", "Error"):
                raise Refused("this run's sync ended " + phase)
            if mine and phase == "Succeeded" and "operation" not in doc and pinned(doc, digests):
                break
            if time.monotonic() + POLL_S >= deadline:
                raise Refused(late)
            time.sleep(POLL_S)
        print("synced %s with the pinned images" % app)
        return 0
    except Exception as exc:
        reason = str(exc) if isinstance(exc, Refused) else "missing or malformed application fields"
        # Only fixed phrases: object fields and kubectl output never enter the log.
        said = (
            "; the application may be pinned to this run's digests and syncing to them"
            if written
            else "; the application is left as it was"
        )
        print("REFUSED: pin and sync of the platform application: " + reason + said)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
