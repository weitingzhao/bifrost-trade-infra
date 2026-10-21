#!/usr/bin/env bash
# install-test-db-tools.sh — the programs agentd needs on ubt-k3s-06 to give
# each bifrost-platform attempt a throwaway Postgres and Redis of its own
# (TD-403; the Owner 2026-10-20 20:4x: 「每次尝试临时起一个 Postgres：在尝试自己的
# 临时目录里 initdb，写墙里、不联网，用完即删，没有共享状态；06 上要装 Postgres 的程序」).
#
# Run on 06 as root, by agent-06-owner.sh `test-db-tools`, which sends it on
# stdin:
#
#   sudo bash -s < install-test-db-tools.sh
#
# It installs Ubuntu's PostgreSQL 16 server (initdb and postgres, in
# /usr/lib/postgresql/16/bin, where agentd looks for them) and redis-server,
# from the Ubuntu archive (no other source), and starts nothing: while the
# packages install, policy-rc.d refuses every service start; PostgreSQL makes
# no cluster of its own (create_main_cluster = false, set before the server
# package is installed); afterwards both services are stopped and disabled.
# agentd starts its own Postgres and Redis per attempt, on unix sockets only,
# as the agent user, and stops them when the attempt ends (agentd testdb.go).
#
# It checks before it writes anything: root, this host, Ubuntu 24.04, no
# policy-rc.d of someone else's, no PostgreSQL cluster and no Redis service
# running. It stops at its first error. A second run installs nothing that is
# there and checks the same. It reads no credential and prints none.
set -euo pipefail

die() {
  echo "install-test-db-tools: $*" >&2
  exit 1
}
step() { echo "==> $*"; }

pg_major=16
pg_bin=/usr/lib/postgresql/$pg_major/bin
users="bifrost-agentd bifrost-agentd-stg"
policy=/usr/sbin/policy-rc.d
createcluster=/etc/postgresql-common/createcluster.conf

step "checks"
[ "$(id -u)" = 0 ] || die "run it as root (sudo bash -s)"
[ "$(hostname)" = ubt-k3s-06 ] || die "this is $(hostname), not ubt-k3s-06"
. /etc/os-release
[ "${ID:-}" = ubuntu ] && [ "${VERSION_ID:-}" = 24.04 ] || die "expected Ubuntu 24.04, found ${PRETTY_NAME:-unknown}"
for u in $users; do
  id "$u" > /dev/null 2>&1 || die "no user $u: run agent-06-owner.sh prepare first"
done
[ ! -e "$policy" ] || die "$policy is there already (someone else's): this step puts its own there while it installs, so it stops"
if command -v pg_lsclusters > /dev/null 2>&1 && [ -n "$(pg_lsclusters -h 2> /dev/null)" ]; then
  die "06 has a PostgreSQL cluster ($(pg_lsclusters -h | head -n 1)): this step installs programs only, and leaves it to you"
fi
! systemctl is-active --quiet redis-server.service 2> /dev/null || die "redis-server.service is running on 06: stop it first, or say why it runs"

# Every service start a package asks for is refused while this runs, and
# the refusal goes however the script ends.
trap 'rm -f "$policy"' EXIT
printf '#!/bin/sh\n# install-test-db-tools.sh: no service starts while it installs\nexit 101\n' > "$policy"
chmod 755 "$policy"

step "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends postgresql-common
[ -f "$createcluster" ] || die "postgresql-common left no $createcluster"
if grep -Eq '^[[:space:]]*#?[[:space:]]*create_main_cluster[[:space:]]*=' "$createcluster"; then
  sed -i -E 's/^[[:space:]]*#?[[:space:]]*create_main_cluster[[:space:]]*=.*/create_main_cluster = false/' "$createcluster"
else
  echo 'create_main_cluster = false' >> "$createcluster"
fi
grep -Eq '^create_main_cluster = false$' "$createcluster" || die "could not turn off the main cluster in $createcluster"
apt-get install -y -q --no-install-recommends "postgresql-$pg_major" redis-server

step "no service"
systemctl disable --now postgresql.service redis-server.service
rm -f "$policy"
trap - EXIT

step "check"
for p in "$pg_bin/initdb" "$pg_bin/postgres" /usr/bin/redis-server; do
  [ -x "$p" ] || die "$p is not there"
done
[ -z "$(pg_lsclusters -h 2> /dev/null)" ] || die "a PostgreSQL cluster was made: $(pg_lsclusters -h | head -n 1)"
for s in postgresql.service redis-server.service; do
  ! systemctl is-active --quiet "$s" || die "$s is running"
  ! systemctl is-enabled --quiet "$s" 2> /dev/null || die "$s starts at boot"
done
for u in $users; do
  runuser -u "$u" -- "$pg_bin/postgres" --version > /dev/null || die "$u cannot run $pg_bin/postgres"
  runuser -u "$u" -- /usr/bin/redis-server --version > /dev/null || die "$u cannot run redis-server"
done
echo "installed: $("$pg_bin/postgres" --version), $(/usr/bin/redis-server --version | cut -d' ' -f1-3); no cluster, no service running or enabled"
echo "agentd finds them when it starts: run agent-06-owner.sh update-agentd with the agentd that has TD-403, or restart both agentd services"
