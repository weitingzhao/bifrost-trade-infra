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
`http://192.168.10.73:30300/api/packages/bifrost-agentd-publisher/generic/agentd/<commit>/agentd-linux-amd64`,
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

## One CI, ordinary CD publication

The STG delivery's `agentd-package` task runs after its rollout succeeds. It
requires a successful platform CI whose platform, UI and infra results match
the three actual delivery clones. It does not start CI or repeat tests. The
cloned platform must still be main when publication preparation begins; a moved
main fails explicitly instead of silently publishing another commit or starting CI.

The task builds linux/amd64 with `CGO_ENABLED=0`, `-trimpath` and `-buildvcs=true`.
Only the upload step receives the dedicated `cicd/gitea-agentd-publisher` Secret
(`username`, `password`). The existing `gitea-ci-reader` stays read-only. The
package contains `agentd-linux-amd64` and `agentd.sha256`, the name the existing
platform discovery reader uses. The checksum is published last. Both files are
read back; an existing version is reused only when its bytes match. Different
content is never overwritten. The delivery exposes `agentd-commit` and
`agentd-sha256` results; landing CI itself publishes nothing.

## First activation (Owner, once)

Prepare all of these before landing the PROD mount patch or applying the CD task:

1. Create the dedicated non-admin Gitea user `bifrost-agentd-publisher`, with
   public package visibility and no organization/team membership. Publish only
   in its own package namespace; do not grant it access to the bifrost organization.
   Issue a `write:package` token and store its credentials in
   `cicd/gitea-agentd-publisher`. Do not reuse the admin bootstrap Secret or
   expand `gitea-ci-reader` to write. Create a separate `read:package` token
   in the same isolated identity, used by the host and by the PROD
   `agentd-package-reader` Secret (username/password). API and workers mount
   it at `AGENTD_PACKAGE_READER_DIR`; the repository reader is unchanged.
   Verify the dedicated reader can read the package checksum.
2. Create the `deploy` account on 06, without other sudo grants. Generate a
   dedicated SSH key, install its public key with forwarding/PTY disabled, and
   independently verify 06's SSH host key. Do not use `StrictHostKeyChecking=no`.
3. Install the existing fixed helper with `agent-06-owner.sh install-update-helper`.
   Store the dedicated private key and verified host key as `id_ed25519` and
   `known_hosts` in `bifrost-platform-prod/agentd-deploy-ssh`. The PROD API and
   workers mount it read-only with mode 0400. STG and model executors do not
   receive it. The runtime image includes the client already required by
   `deploy_agentd`; the only target is `agent-06=deploy@192.168.10.79`.
4. Apply the pinned task and pipeline via the platform manifest action, after
   the infra validation. Do not start an extra platform CI for packaging.
   Allow the ordinary STG/CD run to publish the tested commit. Only then request
   the normal PROD/deploy_agentd cards. The Owner approves in PROD Console.

Record the actual package digest, host-reported version, update card and rollback
result. Local publication tests do not prove credentials or host installation.
Rejecting the deploy card keeps the old host binary. After activation, normal
updates do not require the Owner to run another local installation command.
