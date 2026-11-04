# shellcheck shell=bash
# Shared setup for the NAS script tests (runs inside debian:12, see run.sh): packages, shims
# for btrfs / exportfs / docker / curl / getfacl / stat / mv / rsync / python3, a kill double for BASH_ENV,
# the fake SSD hwmon tree, and assertions. Shims read their behaviour from files under
# /tmp/fake so a test can switch a failure on; the scripts under test carry no test hooks.
export DEBIAN_FRONTEND=noninteractive
if ! command -v rsync > /dev/null; then
  apt-get update -qq > /dev/null && apt-get install -y -qq rsync acl attr util-linux bsdutils procps python3 > /dev/null
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
tty_run() { # tty_run <answer> <command...>: on a pty, typing <answer> each time the command asks
  # "Type yes to continue"; returns the command's own exit code. Typed only after the prompt shows:
  # input sent earlier can be lost before the command opens /dev/tty, and script -e reports 0
  # once its stdin ends first, so the command writes its own status.
  local a=$1 n=0 c sp w; shift
  rm -f /tmp/tty.rc /tmp/tty.in /tmp/tty.out; mkfifo /tmp/tty.in
  script -qc "$(printf '%q ' "$@"); echo \$? > /tmp/tty.rc" /dev/null < /tmp/tty.in > /tmp/tty.out 2>&1 &
  sp=$!
  exec {w}> /tmp/tty.in
  while kill -0 "$sp" 2> /dev/null; do
    c=$(grep -c 'Type yes to continue' /tmp/tty.out || true)
    if ((c > n)); then printf '%s' "$a" >&"$w"; n=$c; fi
    sleep 0.2
  done
  exec {w}>&-
  wait "$sp" || true
  cat /tmp/tty.out
  return "$(cat /tmp/tty.rc 2> /dev/null || echo 99)"
}

mkdir -p /shim /tmp/fake
cat > /shim/btrfs <<'EOF'
#!/bin/bash
# subvolume roots are the paths listed in /tmp/fake/subvols (one per line)
is_sub() { grep -Fxq "$1" /tmp/fake/subvols 2>/dev/null; }
case "$1 $2" in
  "subvolume show") if [[ -d $3 ]] && { is_sub "$3" || [[ $3 == */td444-snap/* || $3 == */rollup-snap/* ]]; }; then
                      echo "$3"; echo "	UUID: 	$(cat "$3/.fake-uuid" 2>/dev/null || echo uuid-"$(basename "$3")")"; else exit 1; fi ;;
  "subvolume snapshot") shift 2; rw=1; [[ $1 == -r ]] && { rw=0; shift; }
                        cp -a "$1" "$2" && echo "uuid-$(basename "$2")" > "$2/.fake-uuid" || exit 1
                        if ((rw)); then echo "$2" >> /tmp/fake/rw_snaps; fi ;;
  "subvolume delete") [[ -e /tmp/fake/btrfs_delete_fail ]] && exit 1; rm -rf "$3" ;;
  "property get") if [[ -e /tmp/fake/snap_rw ]] || grep -Fxq "$4" /tmp/fake/rw_snaps 2>/dev/null; then echo "ro=false"; else echo "ro=true"; fi ;;
  "inspect-internal rootid") echo 5 ;;
  *) echo "shim btrfs: $*" >&2; exit 1 ;;
esac
EOF
cat > /shim/exportfs <<'EOF'
#!/bin/bash
cat /tmp/exports.txt
EOF
cat > /shim/rsync <<'EOF'
#!/bin/bash
# with /tmp/fake/rsync_no_acls: an rsync built without ACLs (UGOS 1.18): -V says "no ACLs", -A is refused
if [[ -f /tmp/fake/rsync_no_acls ]]; then
  # -V line by line, as the real rsync writes it: a reader that stops early (grep -q) ends it by SIGPIPE
  if [[ $1 == -V ]]; then /usr/bin/rsync -V > /tmp/fake/rsync-V.txt; while IFS= read -r l; do printf '%s\n' "${l/ACLs,/no ACLs,}"; done < /tmp/fake/rsync-V.txt; exit 0; fi
  for a in "$@"; do
    if [[ $a == -A || $a =~ ^-[a-zA-Z]*A[a-zA-Z]*$ ]]; then echo 'rsync: ACLs are not supported on this client' >&2; exit 1; fi
  done
fi
# with /tmp/fake/rsync_ugos: UGOS 1.18's rsync as the NAS showed it (11-04): a copy leaves owner
# and mode unset (what it writes under the target ends up 0:0, mode 000, no error; inodes of a
# --link-dest directory it links to keep theirs), and UGOS's own ug.* xattrs differ on the
# target, so a comparison with -X lists the target directory unless the ug.* xattr filter is
# given. Every call is logged to /tmp/fake/rsync.log.
if [[ -f /tmp/fake/rsync_ugos && $1 != -V ]]; then
  echo "$*" >> /tmp/fake/rsync.log
  dry=0 xat=0 filt=0 ld=""
  for a in "$@"; do
    case $a in -n|--dry-run) dry=1 ;; --filter='-x ug.*') filt=1 ;; --link-dest=*) ld=${a#--link-dest=} ;; esac
    if [[ $a =~ ^-[a-zA-Z]*X[a-zA-Z]*$ ]]; then xat=1; fi
  done
  : > /tmp/fake/ld.inodes; if [[ -n $ld && -d $ld ]]; then find "$ld" -printf '%i\n' | sort -u > /tmp/fake/ld.inodes; fi
  rc=0; /usr/bin/rsync "$@" || rc=$?
  if ((dry)); then
    if ((rc == 0 && xat && !filt)); then echo '.d........x ./'; fi
  else
    t=${!#}; t=${t%/}
    find "$t" -depth -printf '%i %p\n' | while read -r ino q; do
      grep -qx "$ino" /tmp/fake/ld.inodes && continue
      chown -h 0:0 "$q"; [[ -L $q ]] || chmod 000 "$q"
    done
  fi
  exit "$rc"
fi
exec /usr/bin/rsync "$@"
EOF
# python3: with /tmp/fake/python_no_chown it runs without CAP_CHOWN, so every chown that changes
# an owner fails as a refused chown would
cat > /shim/python3 <<'EOF'
#!/bin/bash
if [[ -f /tmp/fake/python_no_chown ]]; then exec setpriv --bounding-set -chown --inh-caps -chown /usr/bin/python3 "$@"; fi
exec /usr/bin/python3 "$@"
EOF
cat > /shim/getfattr <<'EOF'
#!/bin/bash
# prints /tmp/fake/xattr/<path with / as _> as the path's xattrs when that file exists
for a in "$@"; do [[ $a == /* ]] && p=$a; done
f=/tmp/fake/xattr/${p//\//_}
if [[ -n $p && -f $f ]]; then printf '# file: %s\n' "$p"; cat "$f"; echo; exit 0; fi
exec /usr/bin/getfattr "$@"
EOF
cat > /shim/getfacl <<'EOF'
#!/bin/bash
# fails for every path listed in /tmp/fake/getfacl_fail ("*" = all)
for a in "$@"; do [[ $a == /* ]] && p=$a; done
if [[ -f /tmp/fake/getfacl_fail ]] && { grep -Fxq '*' /tmp/fake/getfacl_fail || grep -Fxq "$p" /tmp/fake/getfacl_fail; }; then
  echo "getfacl: $p: Operation not supported" >&2; exit 1
fi
if [[ -f /tmp/fake/extended_acl && " $* " == *' --skip-base '* ]]; then   # a line "*": one under any path
  while read -r q; do
    if [[ $q == '*' ]]; then q=$p/acl-file; fi
    [[ $q == "$p"* ]] && printf '# file: %s\nuser:4242:rwx\n\n' "$q"
  done < /tmp/fake/extended_acl; exit 0
fi
exec /usr/bin/getfacl "$@"
EOF
# docker: the td444 container record under /tmp/fake/dk (exists, running, id, netmode, ports,
# networks). The roll-up's throwaway containers live under /tmp/fake/run/<id>/ (name, labels,
# running, mount, envfile, own filesystem fs/); they are found by ID or name; docker exec runs
# the command here with the --env-file loaded literally, FAKE_DATA = the mounted directory and
# /tmp/rollup-mc mapped into fs/. Flags: run_conflict (run fails as on a name clash),
# run_fail_after_create (run creates the container, then fails), run_stop_fail, run_rm_fail.
cat > /shim/docker <<'EOF'
#!/bin/bash
S=/tmp/fake/dk; R=/tmp/fake/run; mkdir -p "$S" "$R"
echo "docker $*" >> "$S/log"
get() { cat "$S/$1" 2>/dev/null; }
cid_of() { local d; [[ -n $1 ]] || return 1; [[ -d $R/$1 ]] && { echo "$1"; return 0; }
  for d in "$R"/*/; do [[ -d $d && $(cat "$d/name" 2>/dev/null) == "$1" ]] && { basename "$d"; return 0; }; done; return 1; }
rmode=0; case $1 in run|ps|image) rmode=1 ;; esac
for a in "${@:2}"; do if [[ $a == bifrost-rollup-* ]] || cid_of "$a" > /dev/null; then rmode=1; fi; done
if ((rmode)); then
  last=${!#}
  case $1 in
    run) shift; nv=0; pub=0; net=""; envf=""; mnt=""; name=""; labels=()
      while (($#)); do case $1 in
        -d) shift ;; --name) name=$2; shift 2 ;; --network) net=$2; shift 2 ;; --env-file) envf=$2; shift 2 ;;
        -v|--volume) mnt=${2%%:*}; nv=$((nv + 1)); shift 2 ;; -p|--publish) pub=1; shift 2 ;; -P) pub=1; shift ;;
        --label) labels+=("$2"); shift 2 ;; --pull|--memory) shift 2 ;; -*) echo "shim docker run: $1" >&2; exit 125 ;; *) break ;; esac; done
      [[ -e /tmp/fake/no_image ]] && { echo "Unable to find image" >&2; exit 125; }
      if [[ -e /tmp/fake/run_conflict ]] || cid_of "$name" > /dev/null; then echo "Conflict. The container name $name is already in use" >&2; exit 125; fi
      id=$(printf '%s %s %s' "$name" "$RANDOM" "$$" | sha256sum | cut -c1-64)
      mkdir -p "$R/$id/fs"; echo "$name" > "$R/$id/name"; echo true > "$R/$id/running"; printf '%s\n' "${labels[@]}" > "$R/$id/labels"
      printf '%s\n' "$net" > "$R/$id/net"; echo "$pub" > "$R/$id/pub"; echo "$nv" > "$R/$id/nvol"
      printf '%s\n' "$mnt" > "$R/$id/mount"; printf '%s\n' "$envf" > "$R/$id/envfile"; printf '%s\n' "$*" > "$R/$id/cmd"
      [[ -e /tmp/fake/run_fail_after_create ]] && { echo "context deadline exceeded" >&2; exit 125; }
      echo "$id" ;;
    image) [[ $2 == inspect && ! -e /tmp/fake/no_image ]] ;;
    ps) shift; fid=""; flab=""; fname=""; fmt=""
      while (($#)); do case $1 in
        --filter) case $2 in id=*) fid=${2#id=} ;; label=*) flab=${2#label=} ;; name=*) fname=${2#name=^}; fname=${fname%\$} ;; esac; shift 2 ;;
        --format) fmt=$2; shift 2 ;; *) shift ;; esac; done
      for d in "$R"/*/; do
        [[ -d $d ]] || continue; id=$(basename "$d")
        [[ -z $fid || $id == "$fid"* ]] || continue
        [[ -z $flab ]] || grep -Fxq "$flab" "$d/labels" || continue
        [[ -z $fname || $(cat "$d/name") == "$fname" ]] || continue
        if [[ $fmt == *Names* ]]; then cat "$d/name"; else echo "$id"; fi
      done; exit 0 ;;
    stop) c=$(cid_of "$last") || exit 1; [[ -e /tmp/fake/run_stop_fail ]] && exit 1; echo false > "$R/$c/running" ;;
    rm) c=$(cid_of "$last") || exit 1; [[ ! -e /tmp/fake/run_rm_fail && $(cat "$R/$c/running") == false ]] || exit 1; rm -rf "${R:?}/$c" ;;
    inspect) c=$(cid_of "$last") || { echo "Error: No such object: $last" >&2; exit 1; }
      fmt=""; prev=""; for a in "$@"; do [[ $prev == -f || $prev == --format ]] && fmt=$a; prev=$a; done
      case $fmt in
        *State.Running*) cat "$R/$c/running" ;;
        *Config.Labels*) l=${fmt#*\"}; l=${l%%\"*}; sed -n "s/^$l=//p" "$R/$c/labels" ;;
        *) echo "$c" ;;
      esac ;;
    exec) shift; while [[ $1 == -* ]]; do shift; done
      c=$(cid_of "$1") && [[ $(cat "$R/$c/running") == true ]] || { echo "container not running" >&2; exit 1; }
      shift
      args=(); for a in "$@"; do args+=("${a//\/tmp\/rollup-mc/$R/$c/fs/tmp/rollup-mc}"); done
      # --env-file as docker reads it: KEY=VALUE taken literally, quotes included
      ( while IFS= read -r l; do if [[ $l == [A-Za-z_]*=* ]]; then export "$l"; fi; done < "$(cat "$R/$c/envfile")"
        FAKE_DATA=$(cat "$R/$c/mount"); export FAKE_DATA; exec "${args[@]}" ) ;;
    *) echo "shim docker: $*" >&2; exit 1 ;;
  esac
  exit
fi
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
if [[ -n ${FAKE_DATA:-} ]]; then [[ ! -e /tmp/fake/run_unhealthy ]]; exit; fi
[[ -e /tmp/fake/dk/healthy ]]
EOF
# mc (inside a throwaway container): cat rb/<object> prints <FAKE_DATA>/<object>/xl.meta (plain
# text in the fixtures); an object listed in /tmp/fake/unreadable fails as a bitrot error would
cat > /shim/mc <<'EOF'
#!/bin/bash
cfg=""; while [[ $1 == --config-dir || $1 == -C ]]; do cfg=$2; shift 2; done
[[ $1 == cat ]] || { echo "shim mc: $*" >&2; exit 1; }
grep -q '"secretKey":"..*"' "$cfg/config.json" 2>/dev/null || { echo "mc: alias rb has no credentials" >&2; exit 1; }
obj=${2#rb/}
if [[ -f /tmp/fake/unreadable ]] && grep -Fxq "$obj" /tmp/fake/unreadable; then echo "mc: <ERROR> bitrot hash mismatch: $obj" >&2; exit 1; fi
[[ -f $FAKE_DATA/$obj/xl.meta ]] || { echo "mc: <ERROR> Object does not exist: $obj" >&2; exit 1; }
cat "$FAKE_DATA/$obj/xl.meta"
EOF
# stat: fails for every path listed in /tmp/fake/stat_fail
cat > /shim/stat <<'EOF'
#!/bin/bash
p=""; for a in "$@"; do [[ $a == /* ]] && p=$a; done
if [[ -n $p && -f /tmp/fake/stat_fail ]] && grep -Fxq "$p" /tmp/fake/stat_fail; then echo "stat: cannot stat '$p'" >&2; exit 1; fi
exec /usr/bin/stat "$@"
EOF
# mv: the n-th publish rename (.partial-<stamp> -> <stamp>) fails while /tmp/fake/mv_fail_at holds n
cat > /shim/mv <<'EOF'
#!/bin/bash
if [[ -f /tmp/fake/mv_fail_at && $# -eq 2 && ${1##*/} == .partial-* && ${2##*/} =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
  n=$(( $(cat /tmp/fake/mv_count 2> /dev/null || echo 0) + 1 )); echo "$n" > /tmp/fake/mv_count
  if ((n == $(cat /tmp/fake/mv_fail_at))); then echo "mv: injected failure of publish rename $n" >&2; exit 1; fi
fi
exec /usr/bin/mv "$@"
EOF
chmod +x /shim/*
# kill (test double, loaded through BASH_ENV into the script under test): the copy group
# swallows TERM and KILL, so it is still alive after stop_group gave up
cat > /tmp/stuck-kill.sh <<'EOF'
kill() {
  if [[ $# -eq 3 && $2 == -- && $3 == -[0-9]* && ( $1 == -TERM || $1 == -KILL ) ]]; then return 0; fi
  builtin kill "$@"
}
EOF
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
