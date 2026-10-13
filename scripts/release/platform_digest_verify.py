"""Bounded STG running-image check, embedded verbatim in the rollout Task."""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
REVISION = "deployment.kubernetes.io/revision"
ATTEMPTS = 3
INTERVAL = 3
TOTAL_BUDGET = 55
QUERY_BUDGET = 5
TARGETS = (
    ("platform-api", "platform-api", "API_DIGEST"),
    ("platform-workers", "platform-api", "API_DIGEST"),
    ("platform-console", "platform-console", "CONSOLE_DIGEST"),
)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_json(namespace, args, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("verification deadline exceeded")
    # No connection flags: they disable kubectl's in-cluster identity fallback.
    try:
        output = subprocess.run(
            ["kubectl", "-n", namespace, "get", *args, "-o", "json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=min(QUERY_BUDGET, remaining),
        ).stdout
    except subprocess.TimeoutExpired:
        raise ValueError("cluster read timed out") from None
    except subprocess.CalledProcessError as exc:
        error = exc.stderr.lower() if isinstance(exc.stderr, str) else ""
        if "forbidden" in error or "unauthorized" in error:
            raise ValueError(
                "identity cannot read Deployments/Pods/ReplicaSets"
            ) from None
        raise ValueError("cluster read failed") from None
    try:
        doc = json.loads(output, object_pairs_hook=unique_object)
    except json.JSONDecodeError:
        raise ValueError("malformed cluster JSON") from None
    if not isinstance(doc, dict):
        raise ValueError("malformed cluster object")
    return doc


def controller(metadata, kind):
    owners = metadata["ownerReferences"]
    if not isinstance(owners, list):
        raise ValueError("invalid controller reference")
    refs = [r for r in owners if r.get("controller") is True]
    if len(refs) != 1:
        raise ValueError("missing or ambiguous controller reference")
    ref = refs[0]
    if ref["apiVersion"] != "apps/v1" or ref["kind"] != kind:
        raise ValueError("wrong controller kind or API version")
    if (
        not isinstance(ref["name"], str)
        or not ref["name"]
        or not isinstance(ref["uid"], str)
        or not ref["uid"]
    ):
        raise ValueError("invalid controller identity")
    return ref


def object_identity(doc, name, namespace):
    metadata = doc["metadata"]
    if (
        metadata["name"] != name
        or metadata["namespace"] != namespace
        or not isinstance(metadata["uid"], str)
        or not metadata["uid"]
    ):
        raise ValueError("cluster object identity mismatch")
    return metadata


def verify(namespace, api_digest, console_digest, require_spec, deadline):
    digests = {"API_DIGEST": api_digest, "CONSOLE_DIGEST": console_digest}
    for name, container_name, digest_key in TARGETS:
        expected = digests[digest_key]
        dep = read_json(namespace, ["deployment", name], deadline)
        metadata = object_identity(dep, name, namespace)
        spec, status = dep["spec"], dep["status"]
        replicas = spec["replicas"]
        if type(replicas) is not int or replicas < 1:
            raise ValueError("Deployment has no positive replica count")
        generation = metadata["generation"]
        if (
            type(generation) is not int
            or generation < 1
            or type(status["observedGeneration"]) is not int
            or status["observedGeneration"] != generation
        ):
            raise ValueError("Deployment generation is not observed")
        if any(
            type(status[k]) is not int or status[k] != replicas
            for k in (
                "replicas",
                "updatedReplicas",
                "readyReplicas",
                "availableReplicas",
            )
        ):
            raise ValueError("Deployment replicas are not fully rolled out")
        labels = spec["selector"]["matchLabels"]
        if (
            not isinstance(labels, dict)
            or not labels
            or spec["selector"].get("matchExpressions")
        ):
            raise ValueError("unsupported Deployment selector")
        if any(
            not isinstance(k, str)
            or not k
            or not isinstance(v, str)
            or any(c in k + v for c in ",=\n")
            for k, v in labels.items()
        ):
            raise ValueError("unsupported Deployment selector")
        selection = ",".join(k + "=" + v for k, v in sorted(labels.items()))
        pods = read_json(namespace, ["pods", "-l", selection], deadline)
        if not isinstance(pods["items"], list) or pods.get("metadata", {}).get(
            "continue"
        ):
            raise ValueError("malformed or incomplete Pod list")
        active = [p for p in pods["items"] if "deletionTimestamp" not in p["metadata"]]
        if len(active) != replicas:
            raise ValueError("active Pod count differs from replicas")
        seen = set()
        for pod in active:
            pm = object_identity(pod, pod["metadata"]["name"], namespace)
            if pm["uid"] in seen or any(
                pm["labels"].get(k) != v for k, v in labels.items()
            ):
                raise ValueError("Pod list identity or selector mismatch")
            seen.add(pm["uid"])
            pr = controller(pm, "ReplicaSet")
            rs = read_json(namespace, ["replicaset", pr["name"]], deadline)
            rm = object_identity(rs, pr["name"], namespace)
            if rm["uid"] != pr["uid"]:
                raise ValueError("Pod ReplicaSet UID mismatch")
            dr = controller(rm, "Deployment")
            if dr["name"] != name or dr["uid"] != metadata["uid"]:
                raise ValueError("ReplicaSet Deployment identity mismatch")
            revision = metadata["annotations"][REVISION]
            if (
                not isinstance(revision, str)
                or not revision
                or rm["annotations"][REVISION] != revision
            ):
                raise ValueError("ReplicaSet is not the current revision")
            ps, state = pod["spec"], pod["status"]
            if state["phase"] != "Running":
                raise ValueError("Pod is not Running")
            containers = ps["containers"]
            if len(containers) != 1 or containers[0]["name"] != container_name:
                raise ValueError("unexpected Pod containers")
            extra_containers = (
                state.get("initContainerStatuses", []),
                state.get("ephemeralContainerStatuses", []),
                ps.get("initContainers", []),
                ps.get("ephemeralContainers", []),
            )
            if any(not isinstance(extra, list) or extra for extra in extra_containers):
                raise ValueError("init or ephemeral containers are not supported")
            statuses = state["containerStatuses"]
            if len(statuses) != 1 or statuses[0]["name"] != container_name:
                raise ValueError("missing or ambiguous container status")
            cs = statuses[0]
            if (
                set(cs["state"]) != {"running"}
                or not isinstance(cs["state"]["running"], dict)
                or cs["ready"] is not True
            ):
                raise ValueError("container is not running and ready")
            image_id = cs["imageID"]
            digest = image_id.rsplit("@", 1)[-1] if isinstance(image_id, str) else ""
            if not DIGEST_RE.fullmatch(digest) or digest != expected:
                raise ValueError("container imageID digest differs or is invalid")
        if require_spec:
            containers = spec["template"]["spec"]["containers"]
            if (
                len(containers) != 1
                or containers[0]["name"] != container_name
                or not containers[0]["image"].endswith("@" + expected)
            ):
                raise ValueError("Deployment spec image is not the expected digest")


def main():
    try:
        namespace = os.environ["NAMESPACE"]
        api_digest, console_digest = (
            os.environ["API_DIGEST"],
            os.environ["CONSOLE_DIGEST"],
        )
        if not DIGEST_RE.fullmatch(api_digest) or not DIGEST_RE.fullmatch(
            console_digest
        ):
            raise ValueError("invalid expected digest")
        if (
            namespace != "bifrost-platform-stg"
            or os.environ["RECORD_APPLICATION"] != "none"
        ):
            raise ValueError("only STG verification without recording is supported")
        mode = os.environ["REQUIRE_SPEC_DIGEST"]
        if mode not in ("true", "false"):
            raise ValueError("invalid spec digest mode")
        deadline = time.monotonic() + TOTAL_BUDGET
        for attempt in range(ATTEMPTS):
            try:
                verify(namespace, api_digest, console_digest, mode == "true", deadline)
                break
            except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
                if attempt == ATTEMPTS - 1 or time.monotonic() + INTERVAL >= deadline:
                    raise exc
                time.sleep(INTERVAL)
        if time.monotonic() >= deadline:
            raise ValueError("verification deadline exceeded")
        verified_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for key, value in (
            ("API_DIGEST_PATH", api_digest),
            ("CONSOLE_DIGEST_PATH", console_digest),
            ("VERIFIED_AT_PATH", verified_at),
        ):
            Path(os.environ[key]).write_text(value)
        print("Platform running image digests verified")
        return 0
    except Exception as exc:
        reason = (
            str(exc)
            if isinstance(exc, ValueError)
            else "missing or malformed verification evidence"
        )
        # Only our fixed phrases; subprocess output and object fields never enter logs.
        print("REFUSED: platform digest verification: " + reason)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
