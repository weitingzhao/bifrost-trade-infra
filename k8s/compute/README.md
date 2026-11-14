# Compute cluster records

## Block 1 — applied on 2026-11-14 (UTC)

Execution card #544 created the five PriorityClasses in
`priority-classes/priority-classes.yaml`; card #545 added `bifrost.io/batch=deny`
to `ubt-k3s-01`, `ubt-k3s-02`, and `ubt-k3s-04`. All classes explicitly set
`globalDefault: false`. The first three allow lower-priority preemption; the
two batch classes never preempt. This record enrolls no workloads.

The shared compute notes contain the executed command bodies
`compute/block1-classes-cmd.v2.sh` and `compute/block1-labels-cmd.v3.apply.sh`,
and the receipts `compute/block1-classes-receipt.json` (18:32:51Z) and
`compute/block1-labels-receipt.json` (18:45:21Z). The class manifest matches
the #544 command's names, values, globalDefault, preemptionPolicy and
description fields exactly; API bookkeeping is not copied into Git.

The priority-classes directory is an independent Kustomization, deliberately
not referenced by `k8s/compute/kustomization.yaml` or any existing overlay.
Its Kustomization adds no labels or annotations. The seven Applications read
on 2026-11-14 have no ownerReferences and none points here; the four infra
Applications point only to existing overlays. ApplicationSet was not readable;
this describes the readable scope, not a guarantee about unseen controllers.
Merging this record does not enroll the directory into an existing Argo app.

### Node label procedure record

No standalone label script is retained: the actual operation used execution
card #545. Future node rebuilding or label repair must use a reviewed execution
card again. The execution admission policy permits only this one label key on
Node updates; it is not permission to modify other labels or taints.

The applied procedure targeted exactly the three nodes above. It checked each
UID against the approved node identity, rejected a conflicting value, and
skipped nodes already labelled `deny`. Each write used the freshly read
resourceVersion as a concurrency condition. It added only `bifrost.io/batch`,
then verified the entire labels map, UID and spec against the pre-state with
only that one label added. No taints were modified. Partial or uncertain
responses require read-only reconciliation before any retry. For a rebuilt
node, its new UID must be reviewed explicitly; never reuse the old receipt as
authorization for a different object.

### Rollback and future cluster objects

Reverting this Git commit removes the repository record only. Cluster rollback
is a separate execution-card operation. Before deleting a class, verify that
no Pod in any phase references it, and restrict removal to the reviewed
creation receipt and matching object identity. Before removing the node label,
the CI lane must first withdraw its dependency on that label. Check the
receipt, UID and fresh resourceVersion, remove only that key, and verify all
other labels and spec remain unchanged. Never roll back uncertain writes
automatically.

Before introducing new kinds or scopes of cluster-level objects, update and
verify the execution admission policy through its authorized process first.
This manifest record does not broaden that policy.
