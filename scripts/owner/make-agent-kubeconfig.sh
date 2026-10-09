#!/usr/bin/env bash
# Owner only. An Agent must not run this script.
#
# Write a kubeconfig that authenticates only as bifrost-access/bifrost-agent.
# The token is read from the long-lived Secret and is not printed, and it is
# not placed on a command line.
#
#   make-agent-kubeconfig.sh <output-path> [admin-kubeconfig]
#
# The admin kubeconfig is OWNER_KUBECONFIG, or the second argument.
# Before the two kubeconfig files are swapped, pass ~/.kube/bifrost-k3s.yaml.
# The server address matches the admin file. The output file is mode 600.
set -euo pipefail

if [ $# -lt 1 ] || [ $# -gt 2 ] || [ -z "${1:-}" ]; then
  echo "usage: make-agent-kubeconfig.sh <output-path> [admin-kubeconfig]" >&2
  exit 2
fi

out="$1"
admin="${2:-${OWNER_KUBECONFIG:-${HOME}/.bifrost-owner/kube/admin.yaml}}"
if [ ! -f "$admin" ]; then
  echo "REFUSED: admin kubeconfig is missing" >&2
  exit 1
fi

secret_json="$(mktemp)"
chmod 600 "$secret_json"
trap 'rm -f "$secret_json"' EXIT

server="$(kubectl --kubeconfig "$admin" config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
if [ -z "$server" ]; then
  echo "REFUSED: admin kubeconfig has no server" >&2
  exit 1
fi
kubectl --kubeconfig "$admin" -n bifrost-access get secret bifrost-agent-token -o json >"$secret_json"

mkdir -p "$(dirname "$out")"
python3 - "$secret_json" "$server" "$out" <<'PY'
import base64, json, os, sys
secret_path, server, out = sys.argv[1:]
doc = json.load(open(secret_path, encoding="utf-8"))
data = doc.get("data") or {}
token_b64 = data.get("token") or ""
ca_b64 = data.get("ca.crt") or ""
if not token_b64 or not ca_b64:
    sys.stderr.write("REFUSED: token secret is missing token or ca.crt\n")
    sys.exit(1)
token = base64.b64decode(token_b64).decode()
if not token or "\n" in token or "\r" in token:
    sys.stderr.write("REFUSED: token is empty or not a single line\n")
    sys.exit(1)
text = (
    "apiVersion: v1\n"
    "kind: Config\n"
    "clusters:\n"
    "- name: bifrost\n"
    "  cluster:\n"
    f"    server: {server}\n"
    f"    certificate-authority-data: {ca_b64}\n"
    "contexts:\n"
    "- name: bifrost-agent\n"
    "  context:\n"
    "    cluster: bifrost\n"
    "    user: bifrost-agent\n"
    "current-context: bifrost-agent\n"
    "users:\n"
    "- name: bifrost-agent\n"
    "  user:\n"
    f"    token: {token}\n"
)
with open(out, "w", encoding="utf-8") as fh:
    fh.write(text)
os.chmod(out, 0o600)
PY

echo "wrote ${out} mode 600"
