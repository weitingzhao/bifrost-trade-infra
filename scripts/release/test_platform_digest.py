"""The two platform kaniko Tasks record a registry digest and nothing else new.

Mainline task bodies are the expected documents. The live Task may add only
``spec.results`` named ``digest`` and one kaniko arg,
``--digest-file=$(results.digest.path)``, on ``build-and-push``. Any other
param, arg, step, or resource change fails the equality.

The deliver pipelines still call those Tasks the same way: task name,
``taskRef``, params, and workspaces.
"""

import copy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / "k8s/cicd/tekton"
DIGEST_ARG = "--digest-file=$(results.digest.path)"
DIGEST_RESULT = {
    "name": "digest",
    "description": "Registry digest (sha256:...) of the pushed image.",
}

# Mainline bodies, before the digest result and --digest-file arg.
# 2026-11-14: the api body's computeResources follow the task's (2 cores to 4:
# 124 of the build's seconds were one go build on 2 cores). The equality still
# holds every other line of the task to what it was.
# LAW-3 二 (2026-11-15; question, delete, simplify, then accelerate): of
# 172 s on the critical path of the STG delivery 54 s were pod starts of tasks doing 0–2 s
# of work. Each body gains the step stage-dockerfile, the copy that the pipeline task
# stage-<kind>-dockerfile made in a pod of its own; the STG pipeline's builds wait for the
# clones instead of for that task. The equality still holds every other line.
MAINLINE = {
    "api": """\
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: bifrost-kaniko-platform-api-stg
  namespace: cicd
  labels:
    bifrost.io/purpose: platform-deliver
spec:
  params:
  - name: image
    type: string
    default: registry.cicd.svc.cluster.local:5000/bifrost-platform-api:stg
  - name: dockerfile
    type: string
    default: Dockerfile.platform-api-prebuilt
  workspaces:
  - name: source
  volumes:
  - name: go-cache
    persistentVolumeClaim:
      claimName: deliver-build-cache
  steps:
  - name: stage-dockerfile
    image: alpine:3.20
    script: |
      #!/usr/bin/env sh
      set -eu
      cp "$(workspaces.source.path)/bifrost-trade-infra/k8s/cicd/docker/Dockerfile.platform-api-prebuilt" "$(workspaces.source.path)/Dockerfile.platform-api-prebuilt"
      echo "=== Dockerfile.platform-api-prebuilt from this run's infra clone ==="
      cat "$(workspaces.source.path)/Dockerfile.platform-api-prebuilt"
  - name: assert-context
    image: alpine:3.20
    script: |
      #!/usr/bin/env sh
      set -eu
      root="$(workspaces.source.path)"
      test -f "${root}/Dockerfile.platform-api-prebuilt"
      test -f "${root}/bifrost-platform/api/go.mod"
      echo "Platform API build context OK"
  - name: compile
    image: golang:1.25-alpine
    env:
    - name: CGO_ENABLED
      value: '0'
    - name: GOOS
      value: linux
    - name: GOARCH
      value: amd64
    - name: GOTOOLCHAIN
      value: auto
    volumeMounts:
    - name: go-cache
      mountPath: /go-cache
    computeResources:
      requests:
        cpu: '2'
        memory: 1Gi
      limits:
        cpu: '4'
        memory: 3Gi
    script: |
      #!/usr/bin/env sh
      set -eu
      root="$(workspaces.source.path)"
      month="$(date -u +%Y-%m)"
      export GOCACHE=/go-cache/build GOMODCACHE="/go-cache/mod/${month}"
      mkdir -p "${GOCACHE}" "${GOMODCACHE}" "${root}/platform-bin"
      # The module cache goes by month; a delivery deletes the months before last.
      year="${month%-*}" mon="${month#*-}"
      if [ "${mon}" = 01 ]; then last="$((year - 1))-12"; else last="$(printf '%s-%02d' "${year}" "$((${mon#0} - 1))")"; fi
      for old in /go-cache/mod/*; do
        case "${old##*/}" in "${month}"|"${last}") ;; *) chmod -R u+w "${old}" 2>/dev/null || true; rm -rf "${old}" ;; esac
      done
      cd "${root}/bifrost-platform/api"
      go build -o "${root}/platform-bin/platform-api" ./cmd/platform-api
      go build -o "${root}/platform-bin/owner-exec" ./cmd/owner-exec
      ls -l "${root}/platform-bin"
  - name: build-and-push
    image: gcr.io/kaniko-project/executor:v1.23.2
    args:
    - --dockerfile=$(params.dockerfile)
    - --context=$(workspaces.source.path)
    - --destination=$(params.image)
    - --custom-platform=linux/amd64
    - --insecure
    - --skip-tls-verify
    - --insecure-registry=registry.cicd.svc.cluster.local:5000
    computeResources:
      requests:
        cpu: '2'
        memory: 2560Mi
      limits:
        cpu: '4'
        memory: 3Gi
""",
    "console": """\
# Kaniko build bifrost-platform-console (requires bifrost-ui sibling).
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: bifrost-kaniko-platform-console-stg
  namespace: cicd
  labels:
    bifrost.io/purpose: platform-deliver
spec:
  params:
    - name: image
      type: string
      default: registry.cicd.svc.cluster.local:5000/bifrost-platform-console:stg
    - name: dockerfile
      type: string
      default: Dockerfile.platform-console-stg
  workspaces:
    - name: source
  steps:
    - name: stage-dockerfile
      image: alpine:3.20
      script: |
        #!/usr/bin/env sh
        set -eu
        cp "$(workspaces.source.path)/bifrost-trade-infra/k8s/cicd/docker/Dockerfile.platform-console-stg" "$(workspaces.source.path)/Dockerfile.platform-console-stg"
        echo "=== Dockerfile.platform-console-stg from this run's infra clone ==="
        cat "$(workspaces.source.path)/Dockerfile.platform-console-stg"
    - name: assert-context
      image: alpine:3.20
      script: |
        #!/usr/bin/env sh
        set -eu
        root="$(workspaces.source.path)"
        test -f "${root}/Dockerfile.platform-console-stg"
        test -f "${root}/bifrost-platform/console/package.json"
        test -f "${root}/bifrost-ui/package.json"
        echo "Platform console build context OK"
    - name: build-and-push
      image: gcr.io/kaniko-project/executor:v1.23.2
      args:
        - --dockerfile=$(params.dockerfile)
        - --context=$(workspaces.source.path)
        - --destination=$(params.image)
        - --custom-platform=linux/amd64
        - --insecure
        - --skip-tls-verify
        - --insecure-registry=registry.cicd.svc.cluster.local:5000
        - --cache=true
        - --cache-repo=registry.cicd.svc.cluster.local:5000/cache/bifrost-platform-console
        - --cache-ttl=168h
      computeResources:
        requests:
          cpu: 500m
          memory: 1Gi
        limits:
          cpu: "4"
          memory: 6Gi
""",
}

TASKS = {
    "api": TEKTON / "task-kaniko-platform-api-stg.yaml",
    "console": TEKTON / "task-kaniko-platform-console-stg.yaml",
}

# How the two deliver pipelines reference the Tasks. Both pipelines match.
PIPELINE_REFS = yaml.safe_load(
    """
build-platform-api:
  name: build-platform-api
  runAfter: [clone-platform, clone-infra]
  taskRef:
    name: bifrost-kaniko-platform-api-stg
  params:
    - name: image
      value: $(params.platformApiImage)
  workspaces:
    - name: source
      workspace: build-context
build-platform-console:
  name: build-platform-console
  runAfter: [clone-platform, clone-ui, clone-infra]
  taskRef:
    name: bifrost-kaniko-platform-console-stg
  params:
    - name: image
      value: $(params.platformConsoleImage)
  workspaces:
    - name: source
      workspace: build-context
"""
)

PIPELINES = (
    "pipeline-deliver-platform.yaml",
    "pipeline-deliver-platform-prod.yaml",
)


def load_one(path):
    docs = [doc for doc in yaml.safe_load_all(path.read_text()) if doc]
    assert len(docs) == 1
    return docs[0]


def build_step(doc):
    steps = [step for step in doc["spec"]["steps"] if step.get("name") == "build-and-push"]
    assert len(steps) == 1
    return steps[0]


def digest_file_args(doc):
    found = []
    for step in doc["spec"]["steps"]:
        for arg in step.get("args") or []:
            if "digest-file" in str(arg):
                found.append((step.get("name"), arg))
    return found


def without_digest(doc):
    """Drop the two allowed additions. Leave every other difference in place."""
    stripped = copy.deepcopy(doc)
    stripped["spec"].pop("results", None)
    step = build_step(stripped)
    step["args"] = [arg for arg in step["args"] if arg != DIGEST_ARG]
    return stripped


@pytest.mark.parametrize("name", ["api", "console"])
def test_task_declares_digest_result(name):
    doc = load_one(TASKS[name])
    assert doc["spec"]["results"] == [DIGEST_RESULT]


@pytest.mark.parametrize("name", ["api", "console"])
def test_build_step_has_one_digest_file_arg(name):
    doc = load_one(TASKS[name])
    assert digest_file_args(doc) == [("build-and-push", DIGEST_ARG)]
    assert build_step(doc)["args"].count(DIGEST_ARG) == 1


@pytest.mark.parametrize("name", ["api", "console"])
def test_task_matches_mainline_aside_from_digest(name):
    live = without_digest(load_one(TASKS[name]))
    mainline = yaml.safe_load(MAINLINE[name])
    assert live == mainline


# TD-411 (review 498 A1): each pipeline builds to its environment's candidate tag, never
# to the tag the Deployments run; promote-images moves that tag after the migration gate.
CANDIDATE_TAG = {"pipeline-deliver-platform.yaml": "stg-candidate", "pipeline-deliver-platform-prod.yaml": "prod-candidate"}


@pytest.mark.parametrize("pipeline", PIPELINES)
def test_deliver_pipeline_task_refs_unchanged(pipeline):
    doc = load_one(TEKTON / pipeline)
    names = [task["name"] for task in doc["spec"]["tasks"]]
    if pipeline == "pipeline-deliver-platform-prod.yaml":
        # TD-335 (W-31 3.4 ①): PROD builds nothing; it deploys the digests STG verified.
        assert not set(PIPELINE_REFS) & set(names)
        return
    for task_name, expected in PIPELINE_REFS.items():
        expected = copy.deepcopy(expected)
        repo = task_name.removeprefix("build-")
        expected["params"][0]["value"] = (
            "registry.cicd.svc.cluster.local:5000/bifrost-" + repo + ":" + CANDIDATE_TAG[pipeline]
        )
        assert names.count(task_name) == 1
        assert doc["spec"]["tasks"][names.index(task_name)] == expected
