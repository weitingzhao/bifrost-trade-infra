# shellcheck shell=bash
# Shared setup for the NAS script tests (runs inside debian:12, see run.sh): packages, shims
# for btrfs / exportfs / docker / curl / getfacl, the fake SSD hwmon tree, and assertions.
# Shims read their behaviour from files under /tmp/fake so a test can switch a failure on.
export DEBIAN_FRONTEND=noninteractive
if ! command -v rsync > /dev/null; then
  apt-get update -qq > /dev/null && apt-get install -y -qq rsync acl attr util-linux bsdutils procps > /dev/null
fi
SRC=${SRC:-/src}
# shellcheck disable=SC2034  # used by the test files that source this one
MOVE=$SRC/td444-move.sh ROLL=$SRC/backup-rollup/rollup.sh
pass=0 fail=0
ok() { pass=$((pass + 1)); echo "PASS: $*"; }
bad() { fail=$((fail + 1)); echo "FAIL: $*"; }
expect_ok() { local d=$1; shift; if "$@" > /tmp/out 2>&1; then ok "$d"; else bad "$d"; tail -15 /tmp/out; fi; }
expect_fail() { local d=$1; shift; if "$@" > /tmp/out 2>&1; then bad "$d (succeeded)"; tail -15 /tmp/out; else ok "$d"; fi; }
check() { local d=$1; shift; if "$@"; then ok "$d"; else bad "$d"; fi; }
finish() { echo; echo "passed $pass, failed $fail"; ((fail == 0)); }

mkdir -p /shim /tmp/fake
cat > /shim/btrfs <<'EOF'
#!/bin/bash
# subvolume roots are the paths listed in /tmp/fake/subvols (one per line)
is_sub() { grep -Fxq "$1" /tmp/fake/subvols 2>/dev/null; }
case "$1 $2" in
  "subvolume show") if [[ -d $3 ]] && { is_sub "$3" || [[ $3 == */td444-snap/* || $3 == */rollup-snap/* ]]; }; then
                      echo "$3"; echo "	UUID: 	$(cat "$3/.fake-uuid" 2>/dev/null || echo uuid-"$(basename "$3")")"; else exit 1; fi ;;
  "subvolume snapshot") shift 2; [[ $1 == -r ]] && shift; cp -a "$1" "$2" && echo "uuid-$(basename "$2")" > "$2/.fake-uuid" ;;
  "subvolume delete") [[ -e /tmp/fake/btrfs_delete_fail ]] && exit 1; rm -rf "$3" ;;
  "property get") [[ -e /tmp/fake/snap_rw ]] && echo "ro=false" || echo "ro=true" ;;
  "inspect-internal rootid") echo 5 ;;
  *) echo "shim btrfs: $*" >&2; exit 1 ;;
esac
EOF
cat > /shim/exportfs <<'EOF'
#!/bin/bash
cat /tmp/exports.txt
EOF
cat > /shim/getfacl <<'EOF'
#!/bin/bash
# fails for every path listed in /tmp/fake/getfacl_fail ("*" = all)
for a in "$@"; do [[ $a == /* ]] && p=$a; done
if [[ -f /tmp/fake/getfacl_fail ]] && { grep -Fxq '*' /tmp/fake/getfacl_fail || grep -Fxq "$p" /tmp/fake/getfacl_fail; }; then
  echo "getfacl: $p: Operation not supported" >&2; exit 1
fi
exec /usr/bin/getfacl "$@"
EOF
# docker: a container record under /tmp/fake/dk (exists, running, id, netmode, ports, networks)
cat > /shim/docker <<'EOF'
#!/bin/bash
S=/tmp/fake/dk; mkdir -p "$S"
echo "docker $*" >> "$S/log"
get() { cat "$S/$1" 2>/dev/null; }
newc() { # newc <compose file>
  echo 1 > "$S/exists"; echo "cid-$RANDOM$RANDOM" > "$S/id"
  if grep -q 'network_mode: none' "$1" && [[ ! -e $S/force_network ]]; then
    echo none > "$S/netmode"; echo '{}' > "$S/ports"; echo 'none ' > "$S/networks"
  else
    echo minio-backup_default > "$S/netmode"; echo '{"9000/tcp":[{"HostIp":"127.0.0.1","HostPort":"9000"}]}' > "$S/ports"; echo 'minio-backup_default ' > "$S/networks"
  fi
}
case $1 in
  version) echo 29.0.0 ;;
  inspect)
    [[ -e $S/inspect_fail || $(get exists) != 1 ]] && { echo "Error: No such object" >&2; exit 1; }
    fmt=""; prev=""
    for a in "$@"; do [[ $prev == -f || $prev == --format ]] && fmt=$a; prev=$a; done
    case $fmt in
      *State.Running*) get running ;;
      *'{{.Id}}'*) get id ;;
      *'HostConfig.NetworkMode}}|'*) printf '%s|%s|%s\n' "$(get netmode)" "$(get ports)" "$(get networks)" ;;
      *'json .NetworkSettings.Networks'*) echo '{}' ;;
      *'range $k, $v := .NetworkSettings.Networks'*) get networks ;;
      *'9000/tcp'*) echo 127.0.0.1 ;;
      *) echo "?" ;;
    esac ;;
  network) echo "$3: " ;;
  exec) [[ $(get running) == true && -e $S/healthy ]] ;;
  compose)
    shift; file=""
    while [[ $1 == -* ]]; do case $1 in -f) file=$2; shift 2 ;; --project-directory) shift 2 ;; *) shift ;; esac; done
    case $1 in
      config) exit 0 ;;
      stop) [[ -e $S/stop_fail ]] && exit 1; echo false > "$S/running" ;;
      create) newc "$file"; echo false > "$S/running" ;;
      start) echo true > "$S/running" ;;
      up) newc "$file"; echo true > "$S/running" ;;
      *) echo "shim compose: $*" >&2; exit 1 ;;
    esac ;;
  *) echo "shim docker: $*" >&2; exit 1 ;;
esac
EOF
cat > /shim/curl <<'EOF'
#!/bin/bash
[[ -e /tmp/fake/dk/healthy ]]
EOF
chmod +x /shim/*
export PATH=/shim:$PATH
mkdir -p /hwmon/hwmon0 /hwmon/hwmon1
for h in 0 1; do echo nvme > /hwmon/hwmon$h/name; echo 50000 > /hwmon/hwmon$h/temp1_input; done
export TD444_HWMON=/hwmon

pkg_setup() { # a package root with the scripts, and its SHA256SUMS (runbook §3.2)
  rm -rf /pkg && mkdir -p /pkg/scripts/nas /pkg/k8s/data/minio/nas
  cp -a "$SRC"/. /pkg/scripts/nas/
  printf 'name: minio-backup\nservices:\n  minio:\n    volumes:\n      - /volume2/minio-backup/data:/data\n' > /pkg/k8s/data/minio/nas/compose.yaml
  cp /pkg/k8s/data/minio/nas/compose.yaml /pkg/k8s/data/minio/nas/compose.isolated.yaml
  echo 'network_mode: none' >> /pkg/k8s/data/minio/nas/compose.isolated.yaml
  cp /pkg/k8s/data/minio/nas/compose.yaml /pkg/k8s/data/minio/nas/compose.recovery.yaml
  (cd /pkg && find . -type f -exec sha256sum {} + > /sums)
  # shellcheck disable=SC2034
  PMOVE=/pkg/scripts/nas/td444-move.sh
}
