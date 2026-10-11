# PROD write matrix

`prod_write_matrix.py` reports who can change the platform's PROD. It reads
either the repository manifests (`--from-repo`) or a directory of JSON objects
(`--from-dump`). It does not call the cluster, and it does not read Secret
data, env files, token files or kubeconfigs.

Rows from `--from-repo` are marked `repo`. Rows from `--from-dump` are marked
`measured`.

## Dump commands

From a kubeconfig that can `get` these objects, write one JSON file per
command into an empty directory and pass that directory to `--from-dump`:

```sh
kubectl get clusterroles -o json > clusterroles.json
kubectl get clusterrolebindings -o json > clusterrolebindings.json
kubectl get roles -A -o json > roles.json
kubectl get rolebindings -A -o json > rolebindings.json
kubectl get validatingadmissionpolicies.admissionregistration.k8s.io -o json > validatingadmissionpolicies.json
kubectl get validatingadmissionpolicybindings.admissionregistration.k8s.io -o json > validatingadmissionpolicybindings.json
kubectl get serviceaccounts -A -o json > serviceaccounts.json
kubectl get pipelines.tekton.dev -n cicd -o json > pipelines.json
kubectl get tasks.tekton.dev -n cicd -o json > tasks.json
kubectl get applications.argoproj.io -n cicd bifrost-platform-prod -o json > application-bifrost-platform-prod.json
```

Each file may be a List or a single object. The program accepts only `.json`
in that directory.
