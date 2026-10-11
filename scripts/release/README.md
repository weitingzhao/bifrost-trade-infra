# PROD write matrix

`prod_write_matrix.py` reports who can change the platform's PROD. It reads
either the repository manifests (`--from-repo`) or a directory of JSON objects
(`--from-dump`). It does not call the cluster, and it does not read Secret
data, env files, token files or kubeconfigs.

Rows from `--from-repo` are marked `repo`. Rows from `--from-dump` are marked
`measured`.

## Dump commands

From a kubeconfig that can `get` these objects, write one JSON file per
command into an empty directory. Then write `MANIFEST.json` and pass the
directory to `--from-dump`. The program refuses the directory when a file is
missing, a kind is missing, a count does not match, or a binding's `roleRef`
does not resolve.

```sh
kubectl get clusterroles -o json > clusterroles.json
kubectl get clusterrolebindings -o json > clusterrolebindings.json
kubectl get roles -A -o json > roles.json
kubectl get rolebindings -A -o json > rolebindings.json
kubectl get validatingadmissionpolicies.admissionregistration.k8s.io -o json > validatingadmissionpolicies.json
kubectl get validatingadmissionpolicybindings.admissionregistration.k8s.io -o json > validatingadmissionpolicybindings.json
kubectl get mutatingwebhookconfigurations.admissionregistration.k8s.io -o json > mutatingwebhookconfigurations.json
kubectl get validatingwebhookconfigurations.admissionregistration.k8s.io -o json > validatingwebhookconfigurations.json
kubectl get serviceaccounts -A -o json > serviceaccounts.json
kubectl get namespaces -o json > namespaces.json
kubectl get pipelines.tekton.dev -n cicd -o json > pipelines.json
kubectl get tasks.tekton.dev -n cicd -o json > tasks.json
kubectl get pipelineruns.tekton.dev -n cicd -o json > pipelineruns.json
kubectl get applications.argoproj.io -n cicd -o json > applications.json
kubectl get appprojects.argoproj.io -n cicd -o json > appprojects.json
python3 - <<'PY'
import json
from pathlib import Path
specs = [
    ("clusterroles.json", "ClusterRole"),
    ("clusterrolebindings.json", "ClusterRoleBinding"),
    ("roles.json", "Role"),
    ("rolebindings.json", "RoleBinding"),
    ("validatingadmissionpolicies.json", "ValidatingAdmissionPolicy"),
    ("validatingadmissionpolicybindings.json", "ValidatingAdmissionPolicyBinding"),
    ("mutatingwebhookconfigurations.json", "MutatingWebhookConfiguration"),
    ("validatingwebhookconfigurations.json", "ValidatingWebhookConfiguration"),
    ("serviceaccounts.json", "ServiceAccount"),
    ("namespaces.json", "Namespace"),
    ("pipelines.json", "Pipeline"),
    ("tasks.json", "Task"),
    ("pipelineruns.json", "PipelineRun"),
    ("applications.json", "Application"),
    ("appprojects.json", "AppProject"),
]
files = []
for name, kind in specs:
    loaded = json.loads(Path(name).read_text())
    items = loaded.get("items") if loaded.get("kind") == "List" else [loaded]
    files.append({"name": name, "kind": kind, "count": len(items)})
Path("MANIFEST.json").write_text(json.dumps({"files": files}, indent=2) + "\n")
PY
```

Each kubectl file is a List. The program reads `.json` files named by the
manifest and does not read Secret data.
