#!/usr/bin/env python3
"""Print a verify-only STG or PROD PipelineRun; never contact the cluster."""

import argparse
import copy
import sys

import yaml
from embed_platform_digest_verify import TASK


def trial_run(api_digest, console_digest, namespace="bifrost-platform-stg"):
    if namespace not in ("bifrost-platform-stg", "bifrost-platform-prod"):
        raise ValueError("only STG or PROD verification without recording is supported")
    spec = yaml.safe_load(TASK.read_text())["spec"]
    spec = copy.deepcopy(spec)
    spec["steps"] = [s for s in spec["steps"] if s["name"] == "verify-digests"]
    params = [
        {"name": k, "value": v}
        for k, v in (
            ("namespace", namespace),
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
            "Owner only, after applying the target Role and new Task, before the target Pipeline.\n"
            "Generate one run with measured digests and one with an incorrect digest:\n"
            "  python3 scripts/release/platform_digest_verify_trial.py <api-digest> <console-digest> > trial.yaml\n"
            "  kubectl create -f trial.yaml\n"
            "Use --namespace bifrost-platform-prod for PROD (default: bifrost-platform-stg).\n"
            "This uses tekton-deliver and only reads target Deployments, Pods and ReplicaSets.\n"
            "It never restarts workloads or records Application annotations."
        ),
    )
    parser.add_argument("api_digest")
    parser.add_argument("console_digest")
    parser.add_argument("--namespace", choices=("bifrost-platform-stg", "bifrost-platform-prod"), default="bifrost-platform-stg")
    args = parser.parse_args()
    yaml.safe_dump(
        trial_run(args.api_digest, args.console_digest, args.namespace), sys.stdout, sort_keys=False
    )


if __name__ == "__main__":
    main()
