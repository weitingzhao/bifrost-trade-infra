#!/usr/bin/env bash
# TD-432 S7, Owner only. Run with bash, never source into an interactive shell.
# Inventory -> both-name Role -> Tasks/Pipelines -> GitHub sync -> SA unlink.
# S8 is separate: drain old runs before narrowing Role or retiring credentials.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
work=$(mktemp -d "${TMPDIR:-/tmp}/td432-s7.XXXXXXXX")
trap 'rm -rf "$work"' EXIT

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
# Pre-apply check: all 11 public Gitea repositories must be primaries.
# This anonymous metadata GET reads no Secret and sends no credential.
while IFS= read -r repo; do
  case "$repo" in ''|'#'*) continue ;; esac
  curl --fail --silent --show-error --noproxy '*' --max-redirs 0 \
    "http://192.168.10.73:30300/api/v1/repos/bifrost/$repo" > "$work/repo.json"
  python3 - "$work/repo.json" "$repo" <<'PY'
import json
import sys
with open(sys.argv[1]) as stream:
    repo = json.load(stream)
if repo.get('full_name') != 'bifrost/' + sys.argv[2] or repo.get('mirror') is not False:
    raise SystemExit('STOP: repository is not a confirmed Gitea primary: ' + sys.argv[2])
print(sys.argv[2] + ': mirror:false')
PY
done < agent-config/gitea-primary.txt

# Step 2: widen only the read Role for the transition, not the other RBAC objects.
python3 - "$work/applier-read.yaml" <<'PY'
import sys
from pathlib import Path
import yaml
role = next(d for d in yaml.safe_load_all(Path('k8s/platform-rbac/30-applier.yaml').read_text())
            if d['kind'] == 'Role' and d['metadata']['name'] == 'bifrost-applier-read')
assert role['metadata']['namespace'] == 'cicd'
assert next(r['resourceNames'] for r in role['rules'] if r['resources'] == ['secrets']) == [
    'gitea-ci-reader', 'gitea-git-credentials']
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
