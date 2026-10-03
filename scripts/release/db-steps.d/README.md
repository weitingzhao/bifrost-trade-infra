# One-off database steps of a release

`release.sh <env>` never runs `psql` against `bifrost_stg`, `bifrost_prod` or `bifrost_golden_source`
(the auto mode rules keep database writes with the Owner). A release that needs a one-off step — a
migration script, an `ALTER … OWNER`, a backfill — registers it here, and `release.sh` **stops** before
the deliver run of every env where the step is still pending, printing the commands for the Owner to
run in their own terminal.

One file per step: `db-steps.d/<date>-<name>.md` (this README is ignored).

```markdown
---
id: 2026-10-03-td77-ops-feedback-owner   # unique; what `release.sh db-done` records
envs: dev stg prod                       # the envs it applies to
when: before                             # before = must run before this env's deliver run
                                         # after  = printed as the next step once the run passed
done: dev                                # envs where it is already done (committed state)
---
# TD-77: ops_feedback objects owned by bifrost

## dev
dry-run: kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -c "SET default_transaction_read_only=on;" -c "SELECT …"
commit:  kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_dev -X -f /path/to/td77.sql
verify:  …

## stg
…

## prod
…  (rollback: …)
```

`release.sh` prints the `## <env>` section (or the whole body when there is none). A step is done
for an env when `done:` lists the env, or when `~/.bifrost-release/db-steps.done` has a line
`<env> <id> …`. After the Owner reports a step done:

```bash
scripts/release/release.sh db-done prod 2026-10-03-td77-ops-feedback-owner   # local record (who/when)
scripts/release/release.sh db-steps prod                                     # list every step and its state
```

and add the env to the file's `done:` line in the next infra commit, so other machines and sessions see
it too. Write the commands without placeholders (zsh reads `<…>` as a redirection) and keep each env's
dry-run before its commit.
