#!/usr/bin/env python3
"""Print a verify-only STG PipelineRun for the Owner; never contact the cluster."""

import argparse
import copy
import sys

import yaml
from embed_platform_digest_verify import TASK


def trial_run(api_digest, console_digest):
    spec = yaml.safe_load(TASK.read_text())["spec"]
    spec = copy.deepcopy(spec)
    spec["steps"] = [s for s in spec["steps"] if s["name"] == "verify-digests"]
    params = [
        {"name": k, "value": v}
        for k, v in (
            ("namespace", "bifrost-platform-stg"),
            ("apiDigest", api_digest),
            ("consoleDigest", console_digest),
            ("requireSpecDigest", "false"),
            ("recordApplication", "none"),
        )
    ]
    return {
        "apiVersion": "tekton.dev/v1",
        "kind": "PipelineRun",
        "metadata": {
            "generateName": "platform-digest-trial-",
            "namespace": "cicd",
            "labels": {"bifrost.io/purpose": "platform-digest-trial"},
        },
        "spec": {
            "pipelineSpec": {
                "tasks": [
                    {"name": "verify-digests", "params": params, "taskSpec": spec}
                ]
            },
            "taskRunSpecs": [
                {
                    "pipelineTaskName": "verify-digests",
                    "serviceAccountName": "tekton-deliver",
                }
            ],
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
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Owner only, after applying the STG Role and new Task, before the STG Pipeline.\n"
            "Generate one run with measured digests and one with an incorrect digest:\n"
            "  python3 scripts/release/platform_digest_verify_trial.py <api-digest> <console-digest> > trial.yaml\n"
            "  kubectl create -f trial.yaml\n"
            "This uses tekton-deliver and only reads STG Deployments, Pods and ReplicaSets.\n"
            "It never restarts workloads or records Application annotations."
        ),
    )
    parser.add_argument("api_digest")
    parser.add_argument("console_digest")
    args = parser.parse_args()
    yaml.safe_dump(
        trial_run(args.api_digest, args.console_digest), sys.stdout, sort_keys=False
    )


if __name__ == "__main__":
    main()
