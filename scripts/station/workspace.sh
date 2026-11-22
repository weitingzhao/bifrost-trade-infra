#!/usr/bin/env bash
# workspace.sh — a throwaway workspace root around one infra checkout, so the governance check
# (agent-config/scripts/check-governance-consistency.sh) can judge that checkout (Station, 2026-11-22).
#
# Usage: workspace.sh <infra checkout> [<empty dir>]   prints the root; then: bash <root>/scripts/check-governance-consistency.sh
#
# Why: the check needs a whole workspace root (bifrost-platform beside infra, the root links), and the real
# root is the checkout every session shares. A visitor working in its own clone could not run it (Crew's
# 11-22 visit stopped there), nor could a seat whose branch only the Owner may push.
# What it builds: the governance files come from the checkout given (the root links point into it); every
# other repository is a link to the shared workspace's checkout, read only. CLAUDE.md §7: governance files
# linked to the shared checkout prove nothing about a change; here they are the candidate's own.
# Known and not hidden: the Codex install item reports drift ("project <root> is not trusted", "~/.codex/AGENTS.md
# does not point to <root>/AGENTS.md"), because it checks this machine's Codex against the root it runs in.
# That item is about the machine, not the change; read the rest of the report.
set -euo pipefail
cand="$(cd "${1:?usage: workspace.sh <infra checkout> [<empty dir>]}" && pwd)"
real="$(cd "$(dirname "$0")/../../.." && pwd)"   # the workspace this script's infra sits in, when it sits in one
[[ -f "$real/bifrost-platform/config/ops-context.yaml" ]] || real="${BIFROST_WORKSPACE:-$HOME/Desktop/stocks}"
[[ -f "$real/bifrost-platform/config/ops-context.yaml" ]] || { echo "no workspace with bifrost-platform beside it at $real; set BIFROST_WORKSPACE" >&2; exit 2; }
root="${2:-$(mktemp -d "${TMPDIR:-/tmp}/station-ws.XXXXXX")}"
mkdir -p "$root"
[[ -z "$(ls -A "$root")" ]] || { echo "$root is not empty" >&2; exit 2; }
for repo in "$real"/bifrost-*; do
  name="$(basename "$repo")"
  [[ "$name" == bifrost-trade-infra ]] || ln -s "$repo" "$root/$name"
done
ln -s "$cand" "$root/bifrost-trade-infra"
for link in .claude .mcp.json AGENTS.md AGENT_FACTS.md CLAUDE.md DESIGN_CONTRACTS.md scripts; do
  target="$(readlink "$real/$link" 2>/dev/null || true)"
  [[ -n "$target" ]] && ln -s "$target" "$root/$link"
done
echo "$root"
