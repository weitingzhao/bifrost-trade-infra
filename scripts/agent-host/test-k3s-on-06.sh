#!/bin/bash
# test-k3s-on-06.sh — the gone() check of k3s-on-06.sh against ten fake
# /proc trees (reviews 233 and 234): a live process whose exe or name cannot
# be read is "cannot tell" (2); one that ended, a zombie or a kernel thread
# is skipped; k3s is found by its path, a deleted binary or its name. Runs
# anywhere (macOS included); exits non-zero on any mismatch.
#
#   bash scripts/agent-host/test-k3s-on-06.sh
here=$(cd "$(dirname "$0")" && pwd -P)
T=$(mktemp -d)
cases="clean unreadable-exe k3s-shim kthread zombie k3s-elsewhere k3s-elsewhere-noname normal-noname kthread-oddname k3s-binary-deleted"
mk() { # mk <set> <pid> <exe target or -> <comm or -> <state> <flags> [stat name]
  local d=$T/$1/$2
  mkdir -p "$d"
  [ "$3" = - ] || ln -s "$3" "$d/exe"
  [ "$4" = - ] || echo "$4" > "$d/comm"
  echo "$2 (${7:-$4}) $5 1 1 1 0 -1 $6 0 0" > "$d/stat"
}
for c in $cases; do for i in $(seq 100 111); do mk "$c" "$i" /usr/bin/bash bash S 4194560; done; done
mk unreadable-exe 200 - containerd S 4194560
mk k3s-shim 200 /var/lib/rancher/k3s/data/abc/bin/containerd-shim-runc-v2 containerd-shim S 4194560
mk kthread 200 - kworker/0:1 I 69238880
mk zombie 200 - k3sdead Z 4194560
mk k3s-elsewhere 200 "/tmp/k3s (deleted)" k3s S 4194560
mk k3s-elsewhere-noname 200 "/tmp/k3s (deleted)" - S 4194560 k3s
mk normal-noname 200 /usr/bin/python3 - S 4194560 python3
mk kthread-oddname 200 - - I 69238880 "kw (a) b) c"
mk k3s-binary-deleted 200 "/usr/local/bin/k3s (deleted)" k3s-agent S 4194560
cat > "$T/drive.sh" << EOF
systemctl() { echo not-found; }
sleep() { :; }
eval "\$(sed -n '/^PROC=/,/^case "\\\${1:-}" in/p' "$here/k3s-on-06.sh" | sed '\$d')"
gone
echo "exit=\$?"
EOF
fails=0
for c in $cases; do
  case $c in
    clean | kthread | zombie | kthread-oddname) want=0 ;;
    k3s-shim | k3s-elsewhere | k3s-binary-deleted) want=1 ;;
    *) want=2 ;;
  esac
  out=$(K3S_ON_06_PROC=$T/$c /bin/bash "$T/drive.sh" 2>&1)
  got=$(echo "$out" | sed -n 's/^exit=//p')
  [ "$want" = "$got" ] && r=ok || { r=MISMATCH; fails=$((fails + 1)); }
  printf '%-22s want=%s got=%s %-8s | %s\n' "$c" "$want" "$got" "$r" "$(echo "$out" | grep -v '^exit=' | head -1)"
done
echo "mismatches: $fails"
rm -rf -- "$T"
[ "$fails" = 0 ]
