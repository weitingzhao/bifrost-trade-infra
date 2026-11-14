# owner-exec (PROD)

Runs an `owner_run_command` card the Owner approves in the Console with a
one-time code from his authenticator app, so an approved command no longer
waits for a terminal (Owner 2026-11-13: nothing may require him back at the
computer). Program: `bifrost-platform` `api/internal/ownerexec`, `api/cmd/owner-exec`.
STG's copy is `k8s/overlays/platform-stg/owner-exec.yaml` (no identity, throwaway seed).

**Not under Argo.** Applied once by the Owner:

```bash
bash scripts/owner-exec/enroll.sh
```

Read the header of that script first: it lists the seven steps, what it
creates, and what it leaves behind if it stops.

## What must be true for a command to run

1. the card is approved (the runner approves a pending card with the admin
   sign-in of the page, on the Owner's click);
2. the command on the card hashes to the fingerprint the page showed;
3. the 6-digit code is valid and has not been used.

The admin sign-in is readable on the Owner's Mac by anything running there,
so it is not the lock. The code is. A caller without an admin sign-in is
refused before the code is looked at.

## Who can read the seed (measured 2026-11-13)

Secret `bifrost-owner-exec/owner-exec-seed`. Agents and both platform
identities cannot read Secrets. These can, cluster-wide, as they can read
every other Secret: the admin identity, Argo CD (3 ServiceAccounts),
CloudNativePG, the Tekton controller, the monitoring stack (Grafana,
kube-state-metrics, the operator, Loki), Traefik, and the daily
`cluster-state-backup` (so the seed is in every daily state backup, which is
encrypted to a recipient key). Accepted by the Owner's coordinator 2026-11-13.

## What the carve-out does not stop

The admission policy refuses the runner's identity any write, delete, exec or
port-forward in the three Trade namespaces, on a Deployment named `daemon`,
and on `redis-ib` / the IB gateway in `data`; the NetworkPolicy lets the Pod
reach only DNS, the API server and platform-api. That stops a command that
goes at Trade directly, however it is worded. It does not stop:

- a command built to go around it in steps (create another identity, or a Pod
  elsewhere, and use that; delete the policy itself). The Owner reads the
  command on the card; that is the control for this.
- reads: admission sees writes only, so the identity can read Secrets,
  Trade's included, and a command can print what it reads onto the card.
- a command printing its own 10-minute cluster token onto the card.
  platform-api redacts token shapes from stored output; an encoded token
  would pass.

For cluster-scoped writes, the no-trade policy permits only these operations,
without a subresource (coordinator 2026-11-14 tightened scope; compute-13 review):

- PriorityClass CREATE/DELETE with a name starting with `bifrost-`. CREATE
  requires `globalDefault` false or absent. UPDATE is refused. CREATE checks
  `object.metadata.name`, since `request.name` may be absent; DELETE checks
  `oldObject.metadata.name`, since DELETE has no new object. Missing oldObject
  fails closed. Value, description and preemptionPolicy have no extra restriction.
- Node UPDATE with identical spec and user metadata except labels. Name,
  generateName, namespace, annotations, finalizers, ownerReferences, selfLink,
  deletionTimestamp and deletionGracePeriodSeconds are compared with presence
  guards. Other label keys and values must be identical in both directions.
  Only `bifrost.io/batch=deny` may be added or removed. Both old and new values,
  if present, must be `deny`: even removal of an existing non-deny value is
  refused. An unchanged deny value is allowed. Absent labels mean an empty map.

Taints, cordon, other labels, annotations, Node CREATE/DELETE and nodes/status
are refused. Other cluster-scoped writes are denied where Kubernetes evaluates
this policy. Namespaced requests keep all three original Trade protections.
Match scope, failure policy and bindings are unchanged.

Server bookkeeping is not compared: managedFields may change when the field
manager processes a label/JSON Patch; resourceVersion is concurrency/storage
bookkeeping. The update path restores generation and creationTimestamp, fills
an omitted UID and validates UID immutability. Node's main endpoint restores
old status before validation. See Kubernetes v1.35
[patch handling](https://github.com/kubernetes/kubernetes/blob/v1.35.0/staging/src/k8s.io/apiserver/pkg/endpoints/handlers/patch.go),
[update normalization](https://github.com/kubernetes/kubernetes/blob/v1.35.0/staging/src/k8s.io/apiserver/pkg/registry/rest/update.go),
[metadata validation](https://github.com/kubernetes/kubernetes/blob/v1.35.0/staging/src/k8s.io/apimachinery/pkg/api/validation/objectmeta.go),
[Node strategy](https://github.com/kubernetes/kubernetes/blob/v1.35.0/pkg/registry/core/node/strategy.go), and
[AdmissionRequest](https://github.com/kubernetes/kubernetes/blob/v1.35.0/staging/src/k8s.io/api/admission/v1/types.go).
This is source reasoning, not a captured live admission request.

Kubernetes exempts admission policies and their bindings from these checks;
the runner's existing RBAC still lets it patch/update its own policy. This is
the known, accepted risk of the current design, not fixed here. To allow a new
cluster-scoped kind later, change this policy and its probes and submit the
repository change through the landing channel on a ready/ branch. If the
channel refuses it, record the refusal and rule location for the coordinator;
do not bypass it or turn it into an Owner merge in Gitea. Live policy updates
use an execution card approved by the Owner with an authenticator code.
Do not broaden RBAC or re-enroll to bypass this process.

Step 4 of enrollment tests these boundaries with server dry-runs. It discovers
an existing Node without the batch label and an existing PV; missing fixtures fail verification rather than treating
NotFound as a policy refusal. The new cluster refusal probes require both the
no-trade policy's name, denied-request text and the full validation message;
RBAC, NotFound, duplicate-object and CEL errors do not count. Existing Trade
probes now use those same checks. If verification fails, the newly applied
policy remains in place, and a runner from an earlier enrollment keeps running.
Re-enrollment keeps the seed when the Owner presses Enter at its prompt, but
step 6 still restarts the runner. There is no delete/recreate policy gap.
If step 6 fails it removes the namespace guard binding, leaving that protection
absent. Policy-only upgrades therefore use an execution card, not a rerun of
enrollment. Repository reconciliation goes through the landing channel.
Step 4 stays synchronized for future enrollments.

The two label-map traversals are linear in the number of labels. Kubernetes
v1.35 defines a per-expression cost limit of 1,000,000 and a policy runtime
budget of 10,000,000 in
[CEL configuration](https://github.com/kubernetes/kubernetes/blob/v1.35.0/staging/src/k8s.io/apiserver/pkg/apis/cel/config.go).
Execution card #543 verified v3 with 17 server dry-runs on November 14 (below).
This does not exhaustively measure CEL cost or every possible request.
YAML rendering alone does not prove policy acceptance.

## Namespace object correction: #541 and #543

#541 applied v2, but creating a Namespace was incorrectly allowed: the API
sets request.namespace to the Namespace's own name, so variables.namespaced
was true even for this cluster-scoped object. The card's self-check detected
the failure and automatically restored the old policy. v3 changes only
spec.validations[3].expression: the namespaced bypass explicitly excludes the
core group's namespaces resource. A Trade Namespace object still returns
validation 1's message; an ordinary Namespace returns validation 4's message.

#543 executed on 2026-11-14 at 18:28:12.534–18:28:16.667 UTC, exit 0:
COUNTS pass=17 fail=0 untested=0; RESULT=PASS; FINAL_SPEC=new;
ACTIVE=new-probe; ROLLBACK=not-needed; NO_PV=0. Its 17 cases cover Namespace
creation, a Trade Namespace annotation, ClusterRole annotation, the protected
Deployment, the protected data prefix, a Trade ConfigMap, PV deletion, an
ordinary ConfigMap, three PriorityClass cases and six Node cases.
Step 4 includes those 17 cases and retains four existing extra probes
(the other two Trade namespaces, Deployment scale, and the gateway prefix).
All behavioral probes use server dry-run and persist nothing. This repository
change does not run enrollment or repeat those server requests.

The expression strings match the live policy exactly. Multiline expressions
use literal YAML blocks to preserve their newlines through kustomize; this
changes serialization only, not the other validation strings. The executor's
ability to update the policy governing itself remains a known, accepted risk;
this correction does not fix it.

## Namespace guard incident, 2026-11-14

All times here are America/Chicago (CST, UTC-6). The policy and binding were
created on November 13 at 10:41:44 (their live creationTimestamp). Until the
repair on November 14 around 12:00, cluster-scoped writes by identities outside
the policy's allowlist were rejected. This was not every identity: the Owner,
runner and listed cluster controllers were exempt. Request #540 records that
namespaceSelector did not exclude cluster-scoped resources, so those requests
reached the namespace-only identity validation. The old second policy did not
read request.namespace; the initial report attributing this incident to a
missing-field evaluation error conflated it with the separate #537 issue.
failurePolicy remains Fail; missing-field evaluation errors would also fail closed.

According to the coordinator's incident account recorded in #540, Tekton's
webhook could not write its renewed certificate's signing authority back to
its cluster-scoped registration, and all pipeline creation stopped from
November 14 at 11:43. That start time and the full outage extent were not
independently established from historical webhook logs in this change.
#540 ran at 12:00:12.083 and finished at 12:00:32.638 with exit 0, RESULT=PATCHED,
an empty typeChecking result and zero matching denials in the last 15 seconds
of webhook logs. These bound the repair; they are not an independently timed
end-to-end pipeline recovery check.

#540 first added the live in-the-namespace matchCondition. This commit copies
its expression exactly into the repository; it restricts the guard to requests
in bifrost-owner-exec and the Namespace object itself. The remaining spec and
binding match live after API-default normalization. This directory is not
managed by Argo, so merging does not change the cluster. The separate no-trade
policy was subsequently updated by execution card #543 as recorded above.

Guard optional request.namespace and request.name with has() before reading
them, and include a cluster-scoped request in every new policy's probes.
Enrollment step 6 now server-dry-runs an annotation on the existing
applications.argoproj.io CRD as system:serviceaccount:cicd:argocd-application-controller.
Read-only inspection on November 14 confirmed that account, CRD, and its
ClusterRoleBinding to a ClusterRole granting all API groups/resources/verbs.
The positive control requires exit 0; RBAC Forbidden is a failure, not proof
of admission acceptance. The existing same-identity ConfigMap creation probe
inside bifrost-owner-exec is retained and tightened to require this policy's
name and exact rejection message. Neither probe persists an object. These
probes were not executed for this repository-only change.

## Not verified by an agent

- Both admission policies: server dry-run needs an admin identity. `enroll.sh`
  dry-runs them, then proves each refusal by impersonating the runner, with
  one write that must pass as the positive control.
- The NetworkPolicy in force: the runner dials Grafana's Service (not allowed)
  30 seconds after start and refuses every request if it connects.
- `expirationSeconds: 600` is the API's documented minimum; the dry-run in
  step 5 is where it is first checked here.

## Upgrading the runner

It runs the image digest PROD's platform-api ran when `enroll.sh` last ran.
To move it: an `owner_run_command` card that sets the new digest on
`deploy/owner-exec` (the runner may write its own namespace), approved with a
code like any other. Or run `enroll.sh` again and keep the seed.

## If the cluster or the Console is down

The runner is down with it. `scripts/owner/owner-run.sh <id>` from the
Owner's terminal still works for a card approved without a code; that is the
one remaining case that needs the computer.
