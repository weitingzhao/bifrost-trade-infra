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
MAINLINE = {
    "api": """\
# Kaniko build bifrost-platform-api from Gitea clone workspace.
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
      default: Dockerfile.platform-api-stg
  workspaces:
    - name: source
  steps:
    - name: assert-context
      image: alpine:3.20
      script: |
        #!/usr/bin/env sh
        set -eu
        root="$(workspaces.source.path)"
        test -f "${root}/Dockerfile.platform-api-stg"
        test -f "${root}/bifrost-platform/api/go.mod"
        echo "Platform API build context OK"
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
          cpu: 250m
          memory: 512Mi
        limits:
          cpu: "2"
          memory: 2Gi
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
  runAfter: [stage-api-dockerfile]
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
  runAfter: [stage-console-dockerfile]
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


@pytest.mark.parametrize("pipeline", PIPELINES)
def test_deliver_pipeline_task_refs_unchanged(pipeline):
    doc = load_one(TEKTON / pipeline)
    names = [task["name"] for task in doc["spec"]["tasks"]]
    for task_name, expected in PIPELINE_REFS.items():
        assert names.count(task_name) == 1
        assert doc["spec"]["tasks"][names.index(task_name)] == expected
