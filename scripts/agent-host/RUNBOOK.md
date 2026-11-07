# Pinned agentd updates

The Owner runs `bash scripts/agent-host/agent-06-owner.sh install-update-helper`
once from the Owner checkout. It sends the checked-in installer and helper to
06, installs `/usr/local/sbin/agentd-update` as root:root 0755, and installs
`/etc/sudoers.d/bifrost-agentd-update` as root:root 0440 after `visudo` checks.
The fixed login is `deploy`; it must already exist and have no other sudo
permissions. This step grants only the helper, with its arguments validated
inside the helper. It does not create an account or remove existing sudo grants.
The binary directory and its parents must remain root-owned and unwritable by
deploy or agent users.

Use a `deploy_agentd` card on the Console for updates. The old Owner
`update-agentd` command now refuses locally. The card's host invocation is:

```
sudo -n /usr/local/sbin/agentd-update <40-lowercase-hex-commit> <64-lowercase-hex-sha256>
sudo -n /usr/local/sbin/agentd-update --rollback
```

The helper downloads only
`http://192.168.10.73:30300/api/packages/bifrost/generic/agentd/<commit>/agentd-linux-amd64`,
verifies the supplied digest, installs a root-owned version beside the current
binary, atomically changes the `agentd` link, restarts `bifrost-agentd.service`,
and waits up to 60 seconds for active state after restart returns. Active state
is a systemd check, not an application health probe. The existing regular binary
is preserved on the first update. `agentd.previous` retains the previous version;
rollback exchanges current and previous and restarts the same unit. A failed
restart leaves the previous version available for explicit rollback. Updates are
serialized with a root-owned lock. Version files are retained; cleanup is an
Owner operation. The STG unit shares the binary path but is not restarted by this
helper; its running process keeps its current build until its next restart.

The installer creates an empty root-only `/etc/bifrost/agentd-update.curl`.
For private packages the Owner must put a package-read credential there using
curl config syntax (for example `user = "account:token"`), retain root:root 0600,
and never give deploy write access. The helper accepts no URL, credential,
configuration path, unit name, or executable from the caller.

## CI publishing blocked by the current credential

`bifrost-ci-platform` uses Secret `cicd/gitea-ci-reader`. Its provisioning script
`scripts/gitea/put-reader-token.sh ci` deliberately requires a read-only forge
identity; `k8s/cicd/gitea/secret.yaml.example` documents the same restriction.
There is no existing CI package-write credential declared in this repository.
The admin Secret is explicitly Owner-only and forbidden to workloads. Per the
task's stop condition, this change does not add a Secret, broaden credentials,
or wire an unusable publisher into the pipeline.

Publishing and pipeline results `agentd-commit` / `agentd-sha256` remain blocked
until an existing CI credential is confirmed to have package-write permission.
The intended contract is a main-only linux/amd64 build from the cloned commit
with `CGO_ENABLED=0`, `-trimpath`, and `-buildvcs=true`; publish the binary and
`agentd-linux-amd64.sha256` to the generic package version named by that commit.
Landing runs must not publish; runs without a build must succeed with optional
agentd results. No live registry permission check or host installation was
performed by this repository change.
