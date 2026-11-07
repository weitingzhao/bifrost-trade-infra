"""Exercise the fixed updater in an isolated filesystem with fake host commands."""
import hashlib
from pathlib import Path
import subprocess

HERE = Path(__file__).parent


def test_update_checksum_and_rollback(tmp_path):
    binary_dir = tmp_path / 'versions'
    binary_dir.mkdir()
    (binary_dir / 'agentd').write_text('old')
    (binary_dir / 'agentd').chmod(0o755)
    commands = tmp_path / 'bin'
    commands.mkdir()
    payload = b'new binary\n'
    digest = hashlib.sha256(payload).hexdigest()
    # Substitute fixed host paths only in the test copy. Production has no overrides.
    script = (HERE / 'agentd-update').read_text().replace(
        'export PATH=/usr/sbin:/usr/bin:/sbin:/bin', f'export PATH={commands}:/usr/bin:/bin'
    ).replace('[[ $EUID == 0 ]]', '[[ 0 == 0 ]]').replace(
        '/usr/local/libexec/bifrost', str(binary_dir)
    ).replace('/run/lock/bifrost-agentd-update.lock', str(tmp_path / 'lock'))
    updater = tmp_path / 'update'
    updater.write_text(script)
    # install's ownership switch needs root; retain actual modes and copy behavior.
    for name, body in {
        'install': 'args=(); for a in "$@"; do case "$a" in -o|-g) skip=1;; root) if [[ ${skip:-0} == 1 ]]; then skip=0; else args+=("$a"); fi;; *) args+=("$a");; esac; done; /usr/bin/install "${args[@]}"',
        'curl': 'while [[ $1 != --output ]]; do shift; done; printf "new binary\\n" > "$2"',
        'systemctl': 'exit 0',
    }.items():
        p = commands / name
        p.write_text('#!/bin/bash\n' + body + '\n')
        p.chmod(0o755)
    def run(*args):
        return subprocess.run(['bash', str(updater), *args], capture_output=True, text=True)
    bad = run('a' * 40, '0' * 64)
    assert bad.returncode != 0
    assert (binary_dir / 'agentd').read_text() == 'old'
    assert not (binary_dir / 'agentd.previous').exists()
    ok = run('a' * 40, digest)
    assert ok.returncode == 0, ok.stderr
    assert (binary_dir / 'agentd').is_symlink()
    assert (binary_dir / 'agentd').read_bytes() == payload
    assert (binary_dir / 'agentd.previous').read_text() == 'old'
    back = run('--rollback')
    assert back.returncode == 0, back.stderr
    assert (binary_dir / 'agentd').read_text() == 'old'
    assert (binary_dir / 'agentd.previous').read_bytes() == payload
    (commands / 'systemctl').write_text('#!/bin/bash\nexit 1\n')
    failed_restart = run('a' * 40, digest)
    assert failed_restart.returncode != 0
    assert (binary_dir / 'agentd').read_bytes() == payload
    assert (binary_dir / 'agentd.previous').read_text() == 'old'
    (commands / 'systemctl').write_text('#!/bin/bash\nexit 0\n')
    assert run('--rollback').returncode == 0
    assert (binary_dir / 'agentd').read_text() == 'old'


def test_rejects_arguments_before_host_actions():
    for args in [[], ['--rollback', 'extra'], ['../main', '0' * 64],
                 ['a' * 40, 'x' * 64], ['a' * 40, '0' * 64, 'sh']]:
        result = subprocess.run(['bash', str(HERE / 'agentd-update'), *args], capture_output=True, text=True)
        assert result.returncode != 0
        assert 'usage:' in result.stderr


def test_owner_update_is_retired_without_connecting():
    result = subprocess.run(['bash', str(HERE / 'agent-06-owner.sh'), 'update-agentd'], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'deploy_agentd card on the Console' in result.stderr
