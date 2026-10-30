"""Review/build-time contract generator. No runtime trust from ConfigMaps/R."""

import argparse
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]


def contract(root=ROOT, ready=True):
    tekton = root / "k8s/cicd/tekton"
    pin = (root / "docker/s5-checker/IMAGE_DIGEST").read_text().strip()
    if (
        not re.fullmatch("sha256:[0-9a-f]{64}", pin)
        or ready
        and pin == "sha256:" + "0" * 64
    ):
        raise ValueError("UNBUILT: pin the reviewed S5 image before installation")
    image = "registry.cicd.svc.cluster.local:5000/bifrost-s5-checker@" + pin
    tasks = {
        s: yaml.safe_load((tekton / ("task-s5-" + s + ".yaml")).read_text())["spec"]
        for s in ["fetch", "check"]
    }
    for task in tasks.values():
        if any(step["image"] != image for step in task["steps"]):
            raise ValueError("S5 image pin mismatch")
    return {
        "schema": 1,
        "image": image,
        "tasks": tasks,
        "pipeline": yaml.safe_load((tekton / "pipeline-ci-s5.yaml").read_text())[
            "spec"
        ],
        "runTemplate": json.loads((tekton / "s5-run-template.json").read_text()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-platform", type=Path)
    args = parser.parse_args()
    value = contract(ready=args.ready)
    if args.check_platform and json.loads(args.check_platform.read_text()) != value:
        raise ValueError("platform embedded S5 contract differs from infra manifests")
    if args.output:
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
