# Apply ownership and one-time bootstrap

The applier plans every object with ownership `ssa` or `migrate`. Migration is
limited to the policy's cicd_resources in namespace `cicd`: Pipeline, Task,
TriggerTemplate, TriggerBinding and EventListener. Only conflicts owned by
`kubectl-client-side-apply`, `kubectl-last-applied`, or `kubectl` with operation
`Update` and a last-applied-configuration annotation qualify. Other conflicting
managers fail the plan by name. Apply rechecks migration conflicts immediately,
forces only those objects with field manager `bifrost-applier`, and removes their
last-applied annotation. Prune stays off.

If the applier itself was installed client-side, first use one
`owner_run_command` card for this exact bootstrap command:

```sh
kubectl apply --server-side --force-conflicts --field-manager=bifrost-applier -f k8s/cicd/tekton/apply-manifest/pipeline.yaml
```

This repository defines the apply-manifest Task inline in that Pipeline file;
there is no separate apply-manifest Task file to bootstrap. The ownership helper
is embedded in the Pipeline, so no ConfigMap update is
needed for this bootstrap. After bootstrap, every cicd definition change
uses `plan_manifest` followed by `apply_manifest`.
