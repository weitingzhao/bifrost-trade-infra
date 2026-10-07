#!/usr/bin/env python3
"""Every Tekton pipeline that clones bifrost-ui pins it on its own param (debt TD-234).

bifrost-ui is its own repo, consumed by the Trade frontend and the Ops Console as
file:../../bifrost-ui. When a pipeline cloned it at `$(params.revision)` the ui ref
could only be the same branch name as the app's, so a PROD run took whatever ui main
was at the time and could not be pinned to the ui commit STG had tested.

Rules, over the Pipelines, TriggerTemplates and EventListeners in k8s/cicd/tekton:
  1. A Pipeline task that clones bifrost-ui (a url param naming bifrost-ui, or a task
     named clone-ui) takes its revision from `$(params.uiRevision)`, and the Pipeline
     declares a `uiRevision` param.
  2. Every bifrost-ci-* Pipeline that clones bifrost-ui is run on a bifrost-ui push:
     some EventListener trigger filters on repository.name == 'bifrost-ui', binds a
     TriggerBinding that sets uiRevision from $(body.after), and uses a TriggerTemplate
     whose PipelineRun runs that Pipeline and passes uiRevision from $(tt.params.uiRevision).

Usage: python3 scripts/check_ui_revision.py [DIR ...]   (default: k8s/cicd/tekton; exit 1 on any problem)
       python3 scripts/check_ui_revision.py --self-test
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
UI_REPO = "bifrost-ui"
UI_PARAM = "uiRevision"
UI_REF = f"$(params.{UI_PARAM})"


def load_docs(paths: list[Path]) -> list[tuple[Path, dict]]:
    out: list[tuple[Path, dict]] = []
    for base in paths:
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.suffix in (".yaml", ".yml"))
        for f in files:
            try:
                docs = list(yaml.safe_load_all(f.read_text()))
            except yaml.YAMLError:
                continue
            out.extend((f, d) for d in docs if isinstance(d, dict))
    return out


def params_of(obj: dict) -> dict[str, str]:
    return {p.get("name"): str(p.get("value", "")) for p in obj.get("params") or [] if isinstance(p, dict)}


def pipeline_param_defaults(spec: dict) -> dict[str, str]:
    return {p.get("name"): str(p.get("default", "")) for p in spec.get("params") or [] if isinstance(p, dict)}


def clones_ui(task: dict, defaults: dict[str, str]) -> bool:
    if task.get("name") == "clone-ui":
        return True
    url = params_of(task).get("url", "")
    for name, default in defaults.items():
        url = url.replace(f"$(params.{name})", default)
    return f"/{UI_REPO}.git" in url or url.rstrip("/").endswith(f"/{UI_REPO}")


def ui_push_runs(docs: list[tuple[Path, dict]]) -> set[str]:
    """Pipelines that a bifrost-ui push runs with uiRevision = the pushed SHA."""
    ui_bindings = set()
    templates: dict[str, set[str]] = {}
    for _, d in docs:
        kind, name = d.get("kind"), (d.get("metadata") or {}).get("name")
        spec = d.get("spec") or {}
        if kind == "TriggerBinding" and params_of(spec).get(UI_PARAM) == "$(body.after)":
            ui_bindings.add(name)
        elif kind == "TriggerTemplate":
            runs = set()
            for rt in spec.get("resourcetemplates") or []:
                rspec = (rt or {}).get("spec") or {}
                if params_of(rspec).get(UI_PARAM) == f"$(tt.params.{UI_PARAM})":
                    runs.add(((rspec.get("pipelineRef") or {}).get("name")) or "")
            templates[name] = runs
    out: set[str] = set()
    for _, d in docs:
        if d.get("kind") != "EventListener":
            continue
        for trig in (d.get("spec") or {}).get("triggers") or []:
            filters = " ".join(
                str(p.get("value", ""))
                for i in trig.get("interceptors") or []
                for p in i.get("params") or []
                if p.get("name") == "filter"
            )
            if f"'{UI_REPO}'" not in filters:
                continue
            if not any(b.get("ref") in ui_bindings for b in trig.get("bindings") or []):
                continue
            out |= templates.get(((trig.get("template") or {}).get("ref")) or "", set())
    return out


def check(paths: list[Path]) -> list[str]:
    docs = load_docs(paths)
    pushed = ui_push_runs(docs)
    problems: list[str] = []
    for f, d in docs:
        if d.get("kind") != "Pipeline":
            continue
        name = (d.get("metadata") or {}).get("name")
        spec = d.get("spec") or {}
        defaults = pipeline_param_defaults(spec)
        try:
            where = f.relative_to(ROOT)
        except ValueError:
            where = f
        ui_tasks = [t for t in (spec.get("tasks") or []) + (spec.get("finally") or []) if clones_ui(t, defaults)]
        if not ui_tasks:
            continue
        if UI_PARAM not in defaults:
            problems.append(f"{where}: Pipeline/{name} clones {UI_REPO} but declares no '{UI_PARAM}' param")
        for t in ui_tasks:
            rev = params_of(t).get("revision", "")
            if rev != UI_REF:
                problems.append(
                    f"{where}: Pipeline/{name} task {t.get('name')} clones {UI_REPO} at {rev!r}, want {UI_REF!r}"
                )
        if name.startswith("bifrost-ci-") and name not in pushed:
            problems.append(
                f"{where}: Pipeline/{name} clones {UI_REPO} but no EventListener trigger runs it on a "
                f"{UI_REPO} push with {UI_PARAM}=$(body.after)"
            )
    return problems


SELF_TEST = """
apiVersion: tekton.dev/v1
kind: Pipeline
metadata: {name: bifrost-deliver-good}
spec:
  params: [{name: revision, default: main}, {name: uiRevision, default: main}]
  tasks:
    - name: clone-ui
      params: [{name: url, value: http://g/bifrost-ui.git}, {name: revision, value: $(params.uiRevision)}]
---
apiVersion: tekton.dev/v1
kind: Pipeline
metadata: {name: bifrost-deliver-shared-ref}
spec:
  params: [{name: revision, default: main}]
  tasks:
    - name: fetch-ui
      params: [{name: url, value: http://g/bifrost-ui.git}, {name: revision, value: $(params.revision)}]
---
apiVersion: tekton.dev/v1
kind: Pipeline
metadata: {name: bifrost-build-param-url}
spec:
  params: [{name: uiRepo, default: http://g/bifrost-ui.git}, {name: uiRevision, default: main}]
  tasks:
    - name: get-ui
      params: [{name: url, value: $(params.uiRepo)}, {name: revision, value: $(params.revision)}]
---
apiVersion: tekton.dev/v1
kind: Pipeline
metadata: {name: bifrost-ci-triggered}
spec:
  params: [{name: uiRevision, default: main}]
  tasks:
    - name: clone-ui
      params: [{name: url, value: http://g/bifrost-ui.git}, {name: revision, value: $(params.uiRevision)}]
---
apiVersion: tekton.dev/v1
kind: Pipeline
metadata: {name: bifrost-ci-orphan}
spec:
  params: [{name: uiRevision, default: main}]
  tasks:
    - name: clone-ui
      params: [{name: url, value: http://g/bifrost-ui.git}, {name: revision, value: $(params.uiRevision)}]
---
apiVersion: tekton.dev/v1
kind: Pipeline
metadata: {name: bifrost-ci-no-ui}
spec:
  tasks:
    - name: clone
      params: [{name: url, value: http://g/bifrost-platform.git}, {name: revision, value: $(params.revision)}]
---
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerBinding
metadata: {name: push-ui}
spec:
  params: [{name: revision, value: main}, {name: uiRevision, value: $(body.after)}]
---
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata: {name: tpl-triggered}
spec:
  resourcetemplates:
    - kind: PipelineRun
      spec:
        pipelineRef: {name: bifrost-ci-triggered}
        params: [{name: uiRevision, value: $(tt.params.uiRevision)}]
---
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata: {name: tpl-orphan-drops-ui}
spec:
  resourcetemplates:
    - kind: PipelineRun
      spec:
        pipelineRef: {name: bifrost-ci-orphan}
        params: [{name: revision, value: $(tt.params.revision)}]
---
apiVersion: triggers.tekton.dev/v1beta1
kind: EventListener
metadata: {name: el}
spec:
  triggers:
    - name: triggered-ui
      interceptors: [{params: [{name: filter, value: "body.repository.name == 'bifrost-ui'"}]}]
      bindings: [{ref: push-ui}]
      template: {ref: tpl-triggered}
    - name: orphan-ui
      interceptors: [{params: [{name: filter, value: "body.repository.name == 'bifrost-ui'"}]}]
      bindings: [{ref: push-ui}]
      template: {ref: tpl-orphan-drops-ui}
"""


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "m.yaml"
        p.write_text(SELF_TEST)
        got = sorted(line.split(": ", 1)[1].split(" ", 1)[0] for line in check([p]))
    want = [
        "Pipeline/bifrost-build-param-url",
        "Pipeline/bifrost-ci-orphan",
        "Pipeline/bifrost-deliver-shared-ref",
        "Pipeline/bifrost-deliver-shared-ref",
    ]
    if got != want:
        print(f"self-test FAILED: flagged {got}, want {want}")
        return 1
    print("self-test ok")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--self-test"]:
        return self_test()
    paths = [Path(a).resolve() for a in argv] or [ROOT / "k8s" / "cicd" / "tekton"]
    problems = check(paths)
    for p in problems:
        print(p)
    if problems:
        print(f"{len(problems)} bifrost-ui clone(s) not pinned on their own param (TD-234)")
        return 1
    print("ui-revision: every bifrost-ui clone takes uiRevision, and every ui-cloning CI gate runs on a ui push")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
