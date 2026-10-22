"""Exercise startup reporting without touching the developer's tmux server."""

import subprocess
from pathlib import Path


def run_start(alive: bool):
    source = Path(__file__).with_name("bdev").read_text()
    functions = "cmd_start() {" + source.split("cmd_start() {", 1)[1].split("\nensure_watchdog() {", 1)[0]
    stubs = r'''
require_tmux() { :; }
die() { echo "ERROR: $*" >&2; exit 1; }
require_config() { :; }
ensure_dirs() { :; }
clear_stop_flag() { :; }
clear_crash_flag() { :; }
trim_log_file() { :; }
ensure_watchdog() { :; }
session_exists() { return 0; }
window_exists() { return 1; }
get_session() { echo trade-ui; }
parse_sessions() { echo 'trade-ui|Trade|/tmp|false|5173||trade|on-failure|1|30|10|30|3'; }
build_run_cmd() { echo false; }
sleep() { :; }
tmux() {
  if [[ "$1" == capture-pane ]]; then
    echo 'bdev-supervise: Operation not permitted'
  fi
}
LOG_TEE=$(command -v bash)
SUPERVISE=$LOG_TEE
TMUX_SESSION=test
LOG_DIR=/tmp
'''
    script = functions + stubs
    script += f"\npane_is_alive() {{ return {0 if alive else 1}; }}\ncmd_start trade-ui\n"
    return subprocess.run(["bash", "-c", script], text=True, capture_output=True)


def test_exited_supervisor_fails_without_success_message():
    result = run_start(False)
    assert result.returncode != 0
    assert "— started" not in result.stdout
    assert "Operation not permitted" in result.stderr
    assert "exited during startup" in result.stderr


def test_live_pane_reports_started():
    result = run_start(True)
    assert result.returncode == 0, result.stderr
    assert "trade-ui — started" in result.stdout
