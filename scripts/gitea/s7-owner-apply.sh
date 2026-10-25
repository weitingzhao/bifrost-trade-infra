#!/usr/bin/env bash
# TD-432 S7, Owner only. Run with bash, never source into an interactive shell.
# Inventory -> both-name Role -> Tasks/Pipelines -> GitHub sync -> SA unlink.
# S8 is separate: drain old runs before narrowing Role or retiring credentials.
set +x +v
set -euo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
work=$(mktemp -d "${TMPDIR:-/tmp}/td432-s7.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
chmod 700 "$work"

inventory() {
  # Output only name and git annotations, not last-applied (which can embed values).
  kubectl -n cicd get secrets -o 'go-template={{range .items}}{{.metadata.name}}{{"\t"}}{{range $key, $value := .metadata.annotations}}{{if ge (len $key) 15}}{{if eq (slice $key 0 15) "tekton.dev/git-"}}{{$key}}={{$value}}{{"\t"}}{{end}}{{end}}{{end}}{{"\n"}}{{end}}' > "$work/secret-metadata.tsv"
  kubectl -n cicd get serviceaccounts -o json > "$work/accounts.json"
  python3 - "$work" <<'PY'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
names = {'gitea-ci-reader', 'gitea-git-credentials'}
for line in (root / 'secret-metadata.tsv').read_text().splitlines():
    name, *annotations = line.split('\t')
    if any(a.startswith('tekton.dev/git-') for a in annotations):
        names.add(name)
        print('Secret', name, 'annotations:', '\t'.join(annotations))
accounts = json.loads((root / 'accounts.json').read_text())['items']
for account in accounts:
    patch = []
    for field in ('secrets', 'imagePullSecrets'):
        for index, secret in reversed(list(enumerate(account.get(field, [])))):
            if secret['name'] in names:
                print('SA link:', account['metadata']['name'], field, secret['name'])
                path = f'/{field}/{index}'
                patch.extend([{'op': 'test', 'path': path + '/name', 'value': secret['name']},
                              {'op': 'remove', 'path': path}])
    if patch:
        (root / (account['metadata']['name'] + '.patch.json')).write_text(json.dumps(patch))
PY
}

# Step 1: read-only inventory, including previously unknown annotated Secrets.
inventory
# Pre-apply check: Gitea requires sign-in even for repository metadata.
# Keep the reader and curl config inside the private, trap-cleaned directory.
if ! kubectl -n cicd get secret gitea-ci-reader -o json > "$work/reader.json" 2>/dev/null; then
  printf '%s\n' 'STOP: cannot read Secret cicd/gitea-ci-reader' >&2
  exit 1
fi
python3 - "$work/reader.json" > "$work/reader.curl" <<'PY'
import base64
import json
import sys
try:
    with open(sys.argv[1]) as stream:
        data = json.load(stream)['data']
    user, password = (base64.b64decode(data[key], validate=True).decode()
                      for key in ('username', 'password'))
    if not user or not password or ':' in user or any(c in user + password for c in '\r\n\0'):
        raise ValueError()
except (KeyError, TypeError, ValueError, OSError):
    raise SystemExit('STOP: invalid Secret cicd/gitea-ci-reader') from None
auth = base64.b64encode((user + ':' + password).encode()).decode()
print('header = "Authorization: Basic ' + auth + '"')
PY
rm -f "$work/reader.json"
while IFS= read -r repo; do
  case "$repo" in ''|'#'*) continue ;; esac
  [[ "$repo" =~ ^bifrost-[a-z0-9-]+$ ]] || { printf '%s\n' 'STOP: invalid primary repository name' >&2; exit 1; }
  if ! status=$(curl -q --silent --noproxy '*' --max-redirs 0 --max-time 30 \
    --config - --output "$work/repo.json" --write-out '%{http_code}' \
    "http://192.168.10.73:30300/api/v1/repos/bifrost/$repo" < "$work/reader.curl"); then
    printf 'STOP: cannot read repository %s (HTTP %s; transport failure)\n' "$repo" "${status:-000}" >&2
    exit 1
  fi
  if [ "$status" != 200 ]; then
    printf 'STOP: cannot read repository %s (HTTP %s)\n' "$repo" "$status" >&2
    exit 1
  fi
  python3 - "$work/repo.json" "$repo" "$status" <<'PY'
import json
import sys
try:
    with open(sys.argv[1]) as stream:
        repo = json.load(stream)
    if not isinstance(repo, dict):
        raise ValueError()
except (ValueError, OSError):
    raise SystemExit('STOP: invalid repository metadata: ' + sys.argv[2] + ' (HTTP ' + sys.argv[3] + ')') from None
if repo.get('full_name') != 'bifrost/' + sys.argv[2] or repo.get('mirror') is not False:
    raise SystemExit('STOP: repository is not a confirmed Gitea primary: ' + sys.argv[2])
print(sys.argv[2] + ': mirror:false')
PY
done < agent-config/gitea-primary.txt
rm -f "$work/reader.curl"

# Step 2: widen only the read Role for the transition, not the other RBAC objects.
python3 - "$work/applier-read.yaml" <<'PY'
import sys
from pathlib import Path
import yaml
role = next(d for d in yaml.safe_load_all(Path('k8s/platform-rbac/30-applier.yaml').read_text())
            if d['kind'] == 'Role' and d['metadata']['name'] == 'bifrost-applier-read')
assert role['metadata']['namespace'] == 'cicd'
# S0's final manifest is reader-only. S7 still needs both during its staged
# migration; never put this temporary grant back in the generated manifest.
secret_rule = next(r for r in role['rules'] if r['resources'] == ['secrets'])
assert secret_rule['resourceNames'] == ['gitea-ci-reader']
secret_rule['resourceNames'] = ['gitea-ci-reader', 'gitea-git-credentials']
Path(sys.argv[1]).write_text(yaml.safe_dump(role))
PY
apply_file() {
  kubectl -n cicd apply --dry-run=server -f "$1"
  kubectl -n cicd apply -f "$1"
}
apply_file "$work/applier-read.yaml"

# Step 3: standalone Tasks, then Pipelines (including embedded Tasks).
for manifest in \
  task-code-health task-deliver-platform task-deliver-research task-deliver-stg \
  task-git-clone-gitea task-gitea-mirror-sync task-refresh-dockerfile-cms \
  task-research-lint-test task-verify-prod-deliver task-verify-stg-deliver \
  apply-manifest/pipeline pipeline-ci-python pipeline-deliver-platform-prod \
  pipeline-deliver-prod pipeline-deliver-research; do
  apply_file "k8s/cicd/tekton/$manifest.yaml"
done

# Step 4: scripts ConfigMap + sync Task/CronJob/TriggerTemplate, in cicd.
kubectl -n cicd apply --dry-run=server -k k8s/cicd/github-sync
kubectl -n cicd apply -k k8s/cicd/github-sync

# Step 5: rescan immediately before unlinking; do not reuse obsolete patches.
rm -f "$work"/*.patch.json
inventory
for patch in "$work"/*.patch.json; do
  [ -f "$patch" ] || continue
  account=$(basename "$patch" .patch.json)
  kubectl -n cicd patch serviceaccount "$account" --type=json --patch-file "$patch" --dry-run=server
  kubectl -n cicd patch serviceaccount "$account" --type=json --patch-file "$patch"
done
printf '%s\n' 'S7 applied. Verify real runs; S8 must drain old TaskRuns before narrowing the Role.'
