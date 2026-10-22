#!/usr/bin/env python3
"""Embed the pin-and-sync script in its Task; --check detects drift."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "k8s/cicd/tekton/task-argocd-pin-sync-platform.yaml"
BEGIN = "      # BEGIN GENERATED PIN SYNC\n      script: |\n"
END = "      # END GENERATED PIN SYNC\n"


def embedded_script():
    return "#!/usr/bin/env python3\n" + (ROOT / "scripts/release/platform_pin_sync.py").read_text()


def generated_task(text):
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    body = "".join(("        " + line if line.strip() else "") + "\n" for line in embedded_script().splitlines())
    return head + BEGIN + body + END + tail


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    original = TASK.read_text()
    generated = generated_task(original)
    if args.check:
        if generated != original:
            print("Embedded platform pin-and-sync script is stale")
            return 1
    else:
        TASK.write_text(generated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
