#!/usr/bin/env bash
# Disk guard for a machine that runs agents (TD-415; W-31 round 4, 4.6 S1).
#
#   disk-guard.sh check            free space: exit 0 at or above WARN_GB (30), 1 below it (no
#                                  new review, npm ci or worktree), 2 below STOP_GB (15) or
#                                  when it cannot be read
#   disk-guard.sh sweep            report only: what would be removed and why the rest stays,
#                                  in $AGENT_WORK/status/lifecycle.json
#   disk-guard.sh sweep --apply    remove registered cache roots whose owner has ended, after
#                                  checking the whole tree twice under the machine lock
#   disk-guard.sh status           check, then the ten largest entries under AGENT_WORK
#
# The rules, the registry format and the environment are in disk_guard.py beside this file.
# Scheduled by install-disk-guard.sh: LaunchAgent com.bifrost.disk-guard on macOS, the
# bifrost-disk-guard@<user>.timer on Linux. Run `check` before each dispatch.
set -u
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec "${DISK_GUARD_PYTHON:-python3}" "$here/disk_guard.py" "$@"
