#!/usr/bin/env bash
# The test harness itself (lib.sh, fix review round 6): a command that never got to answer
# (script does not start, the command hangs, it exits 124) must never count as the expected
# refusal; expect_fail_with checks the exit code and the failure line. Each case runs in its
# own bash with fresh counters and a hard limit, and prints "counts <passed> <failed>".
# Run through run.sh.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
hcase() { # hcase <desc> <expected "passed failed"> <limit s>, body on stdin
  local got t0=$SECONDS
  { printf '%s\n' 'set -uo pipefail; . "$SRC/tests/lib.sh" > /dev/null 2>&1; pass=0 fail=0'; cat
    printf '%s\n' 'echo "counts $pass $fail"'; } > /tmp/hcase.sh
  got=$(timeout "$3" bash /tmp/hcase.sh 2> /dev/null | sed -n 's/^counts //p' | tail -1) || true
  check "$1 (counted: ${got:-nothing, the case hung})" test "${got:-hung}" = "$2"
  HCASE_SECONDS=$((SECONDS - t0))
}
mkdir -p /tmp/noscript
printf '#!/bin/bash\nexit 1\n' > /tmp/noscript/script; chmod +x /tmp/noscript/script

hcase "harness: script that does not start is no refusal" "0 1" 30 <<'EOF'
PATH=/tmp/noscript:$PATH expect_fail "refused" tty_run $'yes\n' bash -c 'exit 1'
EOF
hcase "harness: a hung command is stopped and is no refusal" "0 1" 60 <<'EOF'
TTY_TIMEOUT=3 expect_fail "refused" tty_run $'yes\n' bash -c 'sleep 300'
EOF
check "harness: the hung command was stopped within its deadline" test "$HCASE_SECONDS" -lt 30
check "harness: and nothing of it is left running" bash -c '! pgrep -f "^sleep 300$" > /dev/null'
hcase "harness: a command that exits 124 is no refusal" "0 1" 30 <<'EOF'
expect_fail "refused" tty_run $'yes\n' bash -c 'exit 124'
EOF
hcase "harness: a command that cannot be run (127) is no refusal" "0 1" 30 <<'EOF'
expect_fail "refused" no-such-command-td444
EOF
hcase "harness: expect_fail_with wants its exit code" "0 1" 30 <<'EOF'
expect_fail_with "refused" 7 'refused here' tty_run $'no\n' bash -c 'echo "refused here"; exit 3'
EOF
hcase "harness: expect_fail_with wants its failure line" "0 1" 30 <<'EOF'
expect_fail_with "refused" 7 'refused here' tty_run $'no\n' bash -c 'echo "something else"; exit 7'
EOF
hcase "harness control: a typed yes answers the prompt" "1 0" 30 <<'EOF'
expect_ok "answered" tty_run $'yes\n' bash -c 'printf "Type yes to continue: " > /dev/tty; read -r a < /dev/tty; test "$a" = yes'
EOF
hcase "harness control: a refusal with its code and line passes" "1 0" 30 <<'EOF'
expect_fail_with "refused" 7 'refused here' tty_run $'no\n' bash -c 'printf "Type yes to continue: " > /dev/tty; read -r a < /dev/tty; echo "refused here ($a)"; exit 7'
EOF
finish
