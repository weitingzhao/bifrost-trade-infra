#!/usr/bin/env bash
# Docker rehearsal for the Gitea backup. No cluster access.
# One container set at a time; containers and volumes are removed on exit.
# Prints one line per check and exits non-zero if any check fails.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="${IMAGE:-gitea/gitea:1.21.11}"
suffix="$$"
name="gitea-rehearse-$suffix"
vol="gitea-rehearse-data-$suffix"
bak="gitea-rehearse-bak-$suffix"
workvol="gitea-rehearse-work-$suffix"
port="${REHEARSE_PORT:-30331}"
failed=0
push_pid=""

say() { printf '%s\n' "$*"; }

cleanup() {
  if [[ -n "$push_pid" ]]; then
    kill "$push_pid" 2>/dev/null || true
    wait "$push_pid" 2>/dev/null || true
  fi
  if [[ -n "${name:-}" ]]; then docker rm -f "$name" >/dev/null 2>&1 || true; fi
  docker rm -f gitea-probe >/dev/null 2>&1 || true
  docker volume rm "$vol" "$bak" "$workvol" gitea-probe-data >/dev/null 2>&1 || true
  rm -rf "${seed_dir:-}"
}
trap cleanup EXIT

check() {
  local title="$1" rc="$2"
  if [[ "$rc" -eq 0 ]]; then
    say "PASS $title"
  else
    say "FAIL $title"
    failed=1
  fi
}

run_backup() {
  docker run --rm --user 1000:1000 --network none --entrypoint /bin/bash \
    -v "$vol":/data:ro -v "$bak":/backup \
    -v "$HERE":/scripts:ro \
    "$IMAGE" "$@"
}

run_drill() {
  docker run --rm --user 1000:1000 --network none --entrypoint /bin/bash \
    -v "$bak":/backup -v "$workvol":/data \
    -v "$HERE":/scripts:ro \
    "$IMAGE" "$@"
}

docker rm -f gitea-probe "$name" >/dev/null 2>&1 || true
docker volume rm gitea-probe-data >/dev/null 2>&1 || true

tools_rc=0
docker run --rm --entrypoint /bin/bash "$IMAGE" -c \
  'command -v sqlite3 && command -v git && command -v tar && command -v sha256sum && command -v bash && command -v curl' \
  >/dev/null || tools_rc=1
check "image has sqlite3 git tar sha256sum bash curl" "$tools_rc"
[[ "$tools_rc" -eq 0 ]] || exit 1

docker volume create "$vol" >/dev/null
docker volume create "$bak" >/dev/null
docker volume create "$workvol" >/dev/null
docker run --rm --entrypoint /bin/sh -v "$bak":/backup -v "$workvol":/data "$IMAGE" -c \
  'chown 1000:1000 /backup /data && chmod 0700 /backup /data'

docker run -d --name "$name" \
  -p "127.0.0.1:${port}:3000" \
  -v "$vol":/data \
  -e USER_UID=1000 -e USER_GID=1000 \
  -e SECRET_KEY=rehearse-secret-key-0123456789abcdef \
  -e GITEA__database__DB_TYPE=sqlite3 \
  -e GITEA__security__INSTALL_LOCK=true \
  -e GITEA__security__SECRET_KEY=rehearse-secret-key-0123456789abcdef \
  -e GITEA__server__DOMAIN=127.0.0.1 \
  -e GITEA__server__ROOT_URL="http://127.0.0.1:${port}/" \
  -e GITEA__server__HTTP_PORT=3000 \
  -e GITEA__service__DISABLE_REGISTRATION=true \
  "$IMAGE" >/dev/null

ready=0
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null "http://127.0.0.1:${port}/"; then ready=1; break; fi
  sleep 1
done
check "gitea ready" "$([[ $ready -eq 1 ]] && echo 0 || echo 1)"
[[ "$ready" -eq 1 ]] || { docker logs "$name" 2>&1 | tail -30; exit 1; }

seed_rc=0
docker exec -u git "$name" gitea admin user create \
  --config /data/gitea/conf/app.ini \
  --username giteaadmin --password 'Rehearse-pass-1' \
  --email giteaadmin@example.com --admin --must-change-password=false \
  >/dev/null || seed_rc=1
for repo in alpha beta gamma; do
  curl -sf -u 'giteaadmin:Rehearse-pass-1' -H 'Content-Type: application/json' \
    -X POST "http://127.0.0.1:${port}/api/v1/user/repos" \
    -d "{\"name\":\"${repo}\",\"auto_init\":false}" >/dev/null || seed_rc=1
done
seed_dir="$(mktemp -d)"
for repo in alpha beta gamma; do
  dir="$seed_dir/$repo"
  git init -q -b main "$dir"
  git -C "$dir" config user.email rehearse@example.com
  git -C "$dir" config user.name rehearse
  echo "seed $repo" >"$dir/README"
  if [[ "$repo" == gamma ]]; then
    dd if=/dev/urandom of="$dir/blob.bin" bs=1048576 count=24 >/dev/null 2>&1
  fi
  git -C "$dir" add -A
  git -C "$dir" commit -q -m "seed $repo"
  git -C "$dir" remote add origin "http://giteaadmin:Rehearse-pass-1@127.0.0.1:${port}/giteaadmin/${repo}.git"
  git -C "$dir" push -q -u origin main >/dev/null 2>&1 || seed_rc=1
done
check "seeded admin and three repositories" "$seed_rc"
[[ "$seed_rc" -eq 0 ]] || exit 1

dump_out="$(docker run --rm --user 1000:1000 --entrypoint /bin/bash \
  -v "$vol":/data:ro "$IMAGE" -c '
    set +e
    before=$(sha256sum /data/gitea/gitea.db)
    if touch /data/gitea/probe-write 2>/dev/null; then write=yes; else write=no; fi
    mkdir -p /tmp/dump /tmp/dump-tmp
    gitea dump --config /data/gitea/conf/app.ini --work-path /data/gitea --custom-path /data/gitea \
      --tempdir /tmp/dump-tmp --file /tmp/dump/out.zip --type zip -q >/tmp/dump.log 2>&1
    echo "exit=$?"
    after=$(sha256sum /data/gitea/gitea.db)
    if [[ "$before" == "$after" ]]; then echo db_unchanged=yes; else echo db_unchanged=no; fi
    echo "live_write=$write"
  ')"
say "INFO gitea-dump-readonly: ${dump_out//$'\n'/ }"

push_log="$seed_dir/pushes"
: >"$push_log"
(
  while true; do
    start=$(date +%s)
    echo "tick $start" >>"$seed_dir/alpha/overlap.txt"
    git -C "$seed_dir/alpha" add overlap.txt
    git -C "$seed_dir/alpha" commit -q -m "overlap $start" || { sleep 0.2; continue; }
    if git -C "$seed_dir/alpha" push -q origin main; then
      end=$(date +%s)
      printf '%s %s\n' "$start" "$end" >>"$push_log"
    fi
    sleep 2
  done
) >"$seed_dir/push-loop.err" 2>&1 &
push_pid=$!

for _ in $(seq 1 50); do
  [[ -s "$push_log" ]] && break
  sleep 0.2
done

backup_start=$(date +%s)
backup_rc=0
backup_log="$(run_backup -c 'bash /scripts/backup.sh' 2>&1)" || backup_rc=$?
backup_end=$(date +%s)
say "$backup_log" | tail -n 20
check "backup.sh exit 0" "$backup_rc"
say "TIME backup $((backup_end - backup_start))s"

kill "$push_pid" 2>/dev/null || true
wait "$push_pid" 2>/dev/null || true
push_pid=""

overlap=1
while read -r pstart pend; do
  if (( pstart <= backup_end && pend >= backup_start )); then overlap=0; break; fi
done <"$push_log"
check "a push overlapped the backup" "$overlap"

status_rc=1
size_line=""
if [[ "$backup_rc" -eq 0 ]]; then
  size_line="$(docker run --rm --user 1000:1000 --network none --entrypoint /bin/bash \
    -v "$bak":/backup:ro "$IMAGE" -c '
      latest=$(cat /backup/LATEST)
      echo "LATEST=$latest"
      echo "STATUS=$(cat /backup/$latest/STATUS)"
      cat "/backup/$latest/SIZES.tsv"
      echo "MODE=$(stat -c %a /backup/$latest) $(stat -c %a /backup/$latest/gitea.db) $(stat -c %a /backup/$latest/data.tar)"
    ')"
  say "$size_line"
  printf '%s\n' "$size_line" | grep -q 'STATUS=OK' && status_rc=0
fi
check "LATEST run STATUS is OK" "$status_rc"

docker rm -f "$name" >/dev/null
name=""

drill_rc=0
drill_start=$(date +%s)
drill_log="$(run_drill -c 'bash /scripts/drill.sh latest' 2>&1)" || drill_rc=$?
drill_end=$(date +%s)
say "$drill_log" | tail -n 30
check "drill.sh PASS" "$(printf '%s\n' "$drill_log" | grep -q 'VERDICT: PASS' && [[ $drill_rc -eq 0 ]] && echo 0 || echo 1)"
say "TIME drill $((drill_end - drill_start))s"

plant() {
  docker run --rm --user 1000:1000 --network none --entrypoint /bin/bash \
    -v "$bak":/backup "$IMAGE" -c "$1"
}

latest="$(printf '%s\n' "$size_line" | sed -n 's/^LATEST=//p' | head -1)"
trunc_rc=0
if [[ -n "$latest" ]]; then
  plant "
    set -e
    rm -rf /backup/fault-trunc
    cp -a /backup/$latest /backup/fault-trunc
    head -c 64 /backup/fault-trunc/gitea.db > /tmp/short
    cat /tmp/short > /backup/fault-trunc/gitea.db
    cd /backup/fault-trunc
    sha256sum gitea.db data.tar MANIFEST.tsv SIZES.tsv > SHA256SUMS
    printf 'OK\n' > STATUS
    chmod 0600 SHA256SUMS STATUS gitea.db data.tar MANIFEST.tsv SIZES.tsv
  " || trunc_rc=1
fi
trunc_drill=0
trunc_log="$(run_drill -c 'bash /scripts/drill.sh fault-trunc' 2>&1)" || trunc_drill=$?
say "$trunc_log" | tail -n 15
if [[ "$trunc_rc" -eq 0 && "$trunc_drill" -ne 0 ]] \
   && printf '%s\n' "$trunc_log" | grep -q 'integrity_check:' \
   && ! printf '%s\n' "$trunc_log" | grep -q 'integrity_check: ok'; then
  check "fault truncated database fails the drill" 0
else
  check "fault truncated database fails the drill" 1
fi

man_rc=0
if [[ -n "$latest" ]]; then
  plant "$(cat <<EOF
set -e
rm -rf /backup/fault-manifest
cp -a /backup/${latest} /backup/fault-manifest
cd /backup/fault-manifest
awk -F '\t' -v OFS='\t' 'NR==1 { print; next } { gsub(/=[0-9a-f]+/, "=0000000000000000000000000000000000000000"); print }' MANIFEST.tsv > MANIFEST.tsv.new
mv MANIFEST.tsv.new MANIFEST.tsv
sha256sum gitea.db data.tar MANIFEST.tsv SIZES.tsv > SHA256SUMS
printf 'OK\n' > STATUS
chmod 0600 SHA256SUMS STATUS gitea.db data.tar MANIFEST.tsv SIZES.tsv
EOF
)" || man_rc=1
fi
man_drill=0
man_log="$(run_drill -c 'bash /scripts/drill.sh fault-manifest' 2>&1)" || man_drill=$?
say "$man_log" | tail -n 20
if [[ "$man_rc" -eq 0 && "$man_drill" -ne 0 ]] && printf '%s\n' "$man_log" | grep -q 'ref mismatch'; then
  check "fault manifest ref fails the drill" 0
else
  check "fault manifest ref fails the drill" 1
fi

corrupt_rc=0
docker run --rm --user 1000:1000 --entrypoint /bin/bash -v "$vol":/data "$IMAGE" -c '
  set -e
  repo=/data/git/repositories/giteaadmin/alpha.git
  sha=$(git --git-dir="$repo" rev-parse HEAD)
  mkdir -p /tmp/packs
  if ls "$repo/objects/pack/"*.pack >/dev/null 2>&1; then
    for pack in "$repo/objects/pack/"*.pack; do
      git --git-dir="$repo" unpack-objects < "$pack"
    done
    rm -f "$repo/objects/pack/"*
  fi
  rm -f "$repo/objects/${sha:0:2}/${sha:2}"
  if git --git-dir="$repo" fsck --connectivity-only >/dev/null 2>&1; then
    echo "still consistent" >&2
    exit 1
  fi
' || corrupt_rc=1
check "planted a missing object" "$corrupt_rc"

miss_rc=0
miss_log="$(run_backup -c 'bash /scripts/backup.sh' 2>&1)" || miss_rc=$?
say "$miss_log" | tail -n 20
latest_after="$(docker run --rm --user 1000:1000 --network none --entrypoint /bin/bash \
  -v "$bak":/backup:ro "$IMAGE" -c 'cat /backup/LATEST')"
if [[ "$corrupt_rc" -eq 0 && "$miss_rc" -ne 0 && "$latest_after" == "$latest" ]] \
   && printf '%s\n' "$miss_log" | grep -q 'failed git fsck after 3 copies'; then
  check "fault missing object fails the backup and keeps LATEST" 0
else
  check "fault missing object fails the backup and keeps LATEST" 1
fi

exit "$failed"
