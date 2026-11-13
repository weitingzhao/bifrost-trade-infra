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
