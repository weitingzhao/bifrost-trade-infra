"""Review/build-time contract generator. No runtime trust from ConfigMaps/R."""

import argparse
import importlib.util
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "registry.cicd.svc.cluster.local:5000/bifrost-s5-checker@"
ZERO_IMAGE = "sha256:" + "0" * 64
IMAGE_DIGEST = "docker/s5-checker/IMAGE_DIGEST"
# `s5check --ci-materials` output of the pinned image (reported by
# bifrost-build-s5-checker as result "materials"); all zeros while UNBUILT.
MATERIALS = "docker/s5-checker/MATERIALS.json"
TASKS = ("fetch", "check")


def _verify_module(root):
    spec = importlib.util.spec_from_file_location(
        "s5_verify_materials", root / "docker/s5-checker/verify_materials.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_materials(raw, verify, placeholder):
    raw = raw.strip()
    value = json.loads(raw)
    if verify.canonical(value).decode() != raw:
        raise ValueError("S5 materials are not canonical JSON")
    return verify.check_materials(value, placeholder=placeholder)


def contract(root=ROOT, ready=True):
    tekton = root / "k8s/cicd/tekton"
    pin = (root / IMAGE_DIGEST).read_text().strip()
    if not re.fullmatch("sha256:[0-9a-f]{64}", pin) or ready and pin == ZERO_IMAGE:
        raise ValueError("UNBUILT: pin the reviewed S5 image before installation")
    image = REPOSITORY + pin
    tasks = {
        s: yaml.safe_load((tekton / ("task-s5-" + s + ".yaml")).read_text())["spec"]
        for s in TASKS
    }
    for task in tasks.values():
        if any(step["image"] != image for step in task["steps"]):
            raise ValueError("S5 image pin mismatch")
    # Materials come from the same build as the image: an UNBUILT image keeps
    # the all-zero placeholder, a built image must carry its real materials.
    materials = _canonical_materials(
        (root / MATERIALS).read_text(), _verify_module(root), pin == ZERO_IMAGE
    )
    return {
        "schema": 1,
        "image": image,
        "tasks": tasks,
        "pipeline": yaml.safe_load((tekton / "pipeline-ci-s5.yaml").read_text())[
            "spec"
        ],
        "runTemplate": json.loads((tekton / "s5-run-template.json").read_text()),
        "materials": materials,
    }


def backfill(root, digest, materials_raw):
    """Record one build's image digest and materials together, then re-check.

    Both values are the bifrost-build-s5-checker results of the same run
    (image-digest, materials). Nothing is written unless both are valid, and
    the previous files are restored if the resulting contract is not ready.
    """
    if not re.fullmatch("sha256:[0-9a-f]{64}", digest) or digest == ZERO_IMAGE:
        raise ValueError("UNBUILT: backfill needs the built image digest")
    verify = _verify_module(root)
    materials = _canonical_materials(materials_raw, verify, False)
    old = (root / IMAGE_DIGEST).read_text().strip()
    paths = [root / IMAGE_DIGEST, root / MATERIALS] + [
        root / "k8s/cicd/tekton" / ("task-s5-" + s + ".yaml") for s in TASKS
    ]
    before = {p: p.read_text() for p in paths}
    after = {
        root / IMAGE_DIGEST: digest + "\n",
        root / MATERIALS: verify.canonical(materials).decode() + "\n",
    }
    for p in paths[2:]:
        if REPOSITORY + old not in before[p]:
            raise ValueError("S5 task is not pinned to the current image: " + p.name)
        after[p] = before[p].replace(REPOSITORY + old, REPOSITORY + digest)
    try:
        for p, text in after.items():
            p.write_text(text)
        return contract(root, ready=True)
    except Exception:
        for p, text in before.items():
            p.write_text(text)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-platform", type=Path)
    parser.add_argument("--backfill-digest", help="build result image-digest")
    parser.add_argument(
        "--backfill-materials", type=Path, help="file holding build result materials"
    )
    args = parser.parse_args()
    if bool(args.backfill_digest) != bool(args.backfill_materials):
        parser.error("--backfill-digest and --backfill-materials go together")
    if args.backfill_digest:
        backfill(ROOT, args.backfill_digest, args.backfill_materials.read_text())
    value = contract(ready=args.ready)
    if args.check_platform and json.loads(args.check_platform.read_text()) != value:
        raise ValueError("platform embedded S5 contract differs from infra manifests")
    if args.output:
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
