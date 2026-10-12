#!/usr/bin/env python3
"""Generate the source gate embedded in the platform PROD Pipeline."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml"


def embedded_script():
    helper = (
        (ROOT / "scripts/release/ci_gate.py")
        .read_text()
        .split("\ndef gate(")[0]
        .replace("from __future__ import annotations\n", "")
    )
    gate = (ROOT / "scripts/release/platform_prod_gate.py").read_text()
    return "#!/usr/bin/env python3\n" + gate.replace(
        "from ci_gate import classify, _pipeline_name, _succeeded", helper
    )


def generated_pipeline(text):
    head, rest = text.split(
        "            script: |\n              #!/usr/bin/env python3\n", 1
    )
    _, tail = rest.split("\n    - name: clone-platform\n", 1)
    body = "".join(
        (" " * 14 + line if line.strip() else "") + "\n"
        for line in embedded_script().splitlines()
    )
    return (
        head
        + "            script: |\n"
        + body
        + "\n    - name: clone-platform\n"
        + tail
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    original = PIPELINE.read_text()
    generated = generated_pipeline(original)
    if args.check:
        if original != generated:
            print("Embedded platform PROD gate is stale")
            return 1
    else:
        PIPELINE.write_text(generated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
