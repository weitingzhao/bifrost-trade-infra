#!/usr/bin/env python3
"""Print a source-check-only PipelineRun for an Owner trial; never execute it."""

import argparse
import copy
import sys
import yaml
from embed_platform_prod_gate import PIPELINE


def trial_run(revision, ui_revision="main"):
    pipeline = yaml.safe_load(PIPELINE.read_text())["spec"]
    task = next(t for t in pipeline["tasks"] if t["name"] == "check-source")
    params = [
        {"name": name, "value": value}
        for name, value in (
            ("revision", revision),
            ("uiRevision", ui_revision),
            (
                "giteaBase",
                next(
                    p["default"] for p in pipeline["params"] if p["name"] == "giteaBase"
                ),
            ),
        )
    ]
    return {
        "apiVersion": "tekton.dev/v1",
        "kind": "PipelineRun",
        "metadata": {
            "generateName": "check-source-trial-",
            "namespace": "cicd",
            "labels": {"bifrost.io/purpose": "check-source-trial"},
        },
        "spec": {
            "params": params,
            "pipelineSpec": {
                "params": [{"name": p["name"], "type": "string"} for p in params],
                "tasks": [
                    {
                        "name": "check-source",
                        "params": copy.deepcopy(task["params"]),
                        "taskSpec": copy.deepcopy(task["taskSpec"]),
                    }
                ],
            },
            "taskRunSpecs": [
                {
                    "pipelineTaskName": "check-source",
                    "serviceAccountName": "tekton-deliver",
                }
            ],
            # The run the platform starts pins every task to amd64 nodes; a trial on an
            # arm64 node would test another variant of the image.
            "taskRunTemplate": {
                "podTemplate": {
                    "nodeSelector": {"kubernetes.io/arch": "amd64"},
                    "tolerations": [
                        {
                            "key": "node-role.kubernetes.io/control-plane",
                            "operator": "Exists",
                            "effect": "NoSchedule",
                        }
                    ],
                }
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision")
    parser.add_argument("--ui-revision", default="main")
    args = parser.parse_args()
    yaml.safe_dump(
        trial_run(args.revision, args.ui_revision), sys.stdout, sort_keys=False
    )


if __name__ == "__main__":
    main()
