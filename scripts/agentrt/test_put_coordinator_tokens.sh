#!/usr/bin/env bash
# Offline only: PATH fixtures replace kubectl/openssl before setup can run.
set -euo pipefail
script=$(cd "$(dirname "$0")" && pwd)/put-coordinator-tokens.sh
python3 - "$script" <<'PY'
import json, os, stat, subprocess, sys, tempfile
from pathlib import Path

script = Path(sys.argv[1]).resolve()
tokens = ['a' * 64, 'b' * 64]
old_value = 'EXISTING_SECRET_VALUE'

with tempfile.TemporaryDirectory(prefix='coordinator-tokens-test-') as tmp:
    root = Path(tmp).resolve()
    bin_dir = root / 'bin'
    bin_dir.mkdir()
    # Observe every subprocess that could carry a generated value. The real
    # Python executable is fixed before adding these wrappers to PATH.
    common = '''import json, os, sys
from pathlib import Path
root = Path(os.environ['TEST_CASE'])
with (root / 'argv').open('a') as f:
    f.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')
assert 'proposer_token' not in os.environ and 'agentd_token' not in os.environ
'''
    (bin_dir / 'python3').write_text('#!' + sys.executable + '\n' + common + '''
assert sys.argv[1] == '-I'
os.execv(os.environ['TEST_PYTHON'], [os.environ['TEST_PYTHON'], *sys.argv[1:]])
''')
    (bin_dir / 'openssl').write_text('#!' + sys.executable + '\n' + common + '''
assert sys.argv[1:] == ['rand', '-hex', '32']
counter = root / 'generated'
n = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(n + 1))
print(('a' if n == 0 else 'b') * 64)
''')
    (bin_dir / 'kubectl').write_text('#!' + sys.executable + '\n' + common + '''
args = sys.argv[1:]
env = os.environ['TEST_ENV']
assert args[:2] == ['-n', 'bifrost-platform-' + env]
keys = (['PLATFORM_SEAT_COORDINATOR_STG_TOKEN', 'PLATFORM_AGENTD_COORDINATOR_MBP_STG_TOKEN']
        if env == 'stg' else ['PLATFORM_PROD_SEAT_COORDINATOR_TOKEN', 'PLATFORM_PROD_AGENTD_COORDINATOR_MBP_TOKEN'])
mode = os.environ.get('TEST_MODE', '')
if args[2] == 'get':
    assert args[3:] == ['secret', 'bifrost-platform-role-tokens', '-o', 'json']
    if mode == 'get-fail':
        print('EXISTING_SECRET_VALUE', file=sys.stderr)
        sys.exit(1)
    data = {'UNRELATED_TOKEN': 'EXISTING_SECRET_VALUE'}
    if (root / 'patched').exists() and mode != 'missing-readback':
        data.update({k: 'EXISTING_SECRET_VALUE' for k in keys})
    if mode == 'existing-secret':
        data[keys[1]] = 'EXISTING_SECRET_VALUE'
    print(json.dumps({'data': data}))
elif args[2] == 'patch':
    assert args[3:9] == ['secret', 'bifrost-platform-role-tokens', '--type', 'merge', '--patch-file', '/dev/stdin']
    payload = json.load(sys.stdin)
    assert payload == {'stringData': dict(zip(keys, ['a' * 64, 'b' * 64]))}
    # Exercise tools that echo payloads, including failures; neither stream
    # may escape the script. No value is persisted by the fake cluster.
    print(json.dumps(payload))
    print(json.dumps(payload), file=sys.stderr)
    if args[9:] == ['--dry-run=server']:
        (root / 'dry-run').touch()
        if mode == 'dry-fail': sys.exit(1)
    else:
        assert args[9:] == [] and (root / 'dry-run').exists()
        if mode == 'patch-fail': sys.exit(1)
        (root / 'patched').touch()
else:
    raise AssertionError('unexpected kubectl operation')
''')
    for path in bin_dir.iterdir():
        path.chmod(0o755)

    def case(name, environment='stg', mode='', replace=False, setup=None, trace=False):
        current = root / name
        current.mkdir()
        fixture_home = current / 'home'
        fixture_home.mkdir()
        suffix = '-stg' if environment == 'stg' else ''
        files = [fixture_home / '.config/bifrost' / (f'coordinator-{kind}{suffix}.token')
                 for kind in ('proposer', 'agentd')]
        if setup:
            setup(current, files)
        # Child-only fixture home: never inspect the operator's home or kubeconfig.
        env = dict(os.environ)
        env.update({'HOME': str(fixture_home), 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
                    'TEST_CASE': str(current), 'TEST_ENV': environment, 'TEST_MODE': mode,
                    'TEST_PYTHON': sys.executable, 'PUT_TOKEN_KUBECONFIG': str(current / 'unused-kubeconfig')})
        command = ['bash'] + (['-x'] if trace else []) + [str(script), environment] + (['replace'] if replace else [])
        p = subprocess.run(command, env=env, capture_output=True, text=True, timeout=45)
        argv = (current / 'argv').read_text() if (current / 'argv').exists() else ''
        assert not any(v in p.stdout + p.stderr + argv for v in [*tokens, old_value]), name
        success = not trace and (mode == '' or mode == 'existing-secret' and replace) and (setup is None or replace)
        if name in ('symlink', 'parent-symlink', 'hardlink', 'directory'):
            success = False
        assert (p.returncode == 0) == success, (name, p.returncode, p.stdout, p.stderr)
        if success:
            expected_keys = (['PLATFORM_SEAT_COORDINATOR_STG_TOKEN', 'PLATFORM_AGENTD_COORDINATOR_MBP_STG_TOKEN']
                             if environment == 'stg' else ['PLATFORM_PROD_SEAT_COORDINATOR_TOKEN', 'PLATFORM_PROD_AGENTD_COORDINATOR_MBP_TOKEN'])
            assert p.stdout.splitlines() == expected_keys + list(map(str, files))
            assert not p.stderr
            assert (current / 'patched').exists()
            for path, token in zip(files, tokens):
                assert path.read_text() == token + '\n'
                assert stat.S_IMODE(path.stat().st_mode) == 0o600
                assert path.stat().st_uid == os.getuid() and not path.is_symlink()
        else:
            assert 'refused' in p.stderr
            if mode != 'missing-readback':
                assert not (current / 'patched').exists()
            if setup is None:
                assert not any(path.exists() for path in files)
            if mode == 'dry-fail':
                assert (current / 'dry-run').exists()
            if setup or trace or mode in ('existing-secret', 'get-fail'):
                assert not (current / 'generated').exists()
        print('PASS', name)
        return current

    def existing(current, files):
        files[0].parent.mkdir(parents=True)
        files[0].write_text('old local fixture\n')
        files[0].chmod(0o644)

    case('stg-create')
    case('prod-create', environment='prod')
    case('dry-run-failure', mode='dry-fail')
    case('patch-failure', mode='patch-fail')
    case('read-failure', mode='get-fail')
    case('readback-missing', mode='missing-readback')
    # One key/file alone is enough to refuse the whole operation.
    c = case('local-exists', setup=existing)
    assert (c / 'home/.config/bifrost/coordinator-proposer-stg.token').read_text() == 'old local fixture\n'
    case('secret-exists', mode='existing-secret')
    case('secret-replace', mode='existing-secret', replace=True)
    case('local-replace', setup=existing, replace=True)
    case('xtrace', trace=True)

    def link(current, files):
        files[0].parent.mkdir(parents=True)
        target = current / 'untouched'
        target.write_text('unchanged')
        files[0].symlink_to(target)
    c = case('symlink', setup=link, replace=True)
    assert (c / 'untouched').read_text() == 'unchanged'

    def parent_link(current, files):
        (current / 'home/.config').mkdir()
        target = current / 'untouched'
        target.mkdir()
        files[0].parent.symlink_to(target, target_is_directory=True)
    c = case('parent-symlink', setup=parent_link, replace=True)
    assert not list((c / 'untouched').iterdir())

    def hardlink(current, files):
        existing(current, files)
        os.link(files[0], current / 'untouched')
    c = case('hardlink', setup=hardlink, replace=True)
    assert (c / 'untouched').read_text() == 'old local fixture\n'

    def directory(current, files):
        files[0].mkdir(parents=True)
    case('directory', setup=directory, replace=True)

print('All coordinator token tests passed (offline fixtures only).')
PY
