"""CLI-only contracts: real children and planted transport failures/bad inputs."""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

LANE = Path(__file__).with_name('lane.py')
REC = LANE.with_name('rec.py')


def cli(root, *args, expected=0, lane=LANE, env=None):
    proc = subprocess.run([sys.executable, str(lane), '--root', str(root), *args],
                          capture_output=True, text=True, timeout=12, env=env)
    assert proc.returncode == expected, proc.stdout + proc.stderr
    return proc


def dispatch(root, name='job', code='pass', usual=None):
    args = ['start', '--work', 'w1', '--title', 'Work', '--name', name,
            '--kind', 'other', '--who', 'Cursor']
    if usual is not None:
        args += ['--usual-min', str(usual)]
    proc = cli(root, *args, '--', sys.executable, '-c', code)
    assert len(proc.stdout.splitlines()) == 1
    row = json.loads(proc.stdout)
    assert set(row) == {'work', 'step_id', 'output_dir', 'wrapper_pid', 'recorded'}
    assert row['recorded'] is True
    return row


def status(root):
    return json.loads(cli(root, 'status', '--json').stdout)


def events(root):
    return [json.loads(line.split(" ", 1)[1]) for line in (root / 'w1/events.jsonl').read_text().splitlines()]


def wait_for(predicate):
    deadline = time.monotonic() + 6
    while True:
        result = predicate()
        if result:
            return result
        assert time.monotonic() < deadline
        time.sleep(.03)


def finished(root, row):
    return next((e for e in events(root) if e['type'] == 'step_finished'
                 and e['step_id'] == row['step_id']), None)


def recording(root, result='done', quote='Reviewed'):
    return cli(root, 'record', '--work', 'w1', '--name', 'Review', '--kind', 'review',
               '--who', 'Reviewer', '--result', result, '--quote', quote)


def owner_open(root):
    return json.loads(cli(root, 'owner-open', '--work', 'w1', '--title', 'Sign off',
                          '--can-act', 'yes', '--where', 'terminal', '--command', 'echo ok').stdout)


def proxy(tmp_path, body):
    """Transport fault fixture; all other calls exec the unchanged real recorder."""
    directory = tmp_path / 'proxy'
    directory.mkdir()
    shutil.copyfile(LANE, directory / 'lane.py')
    (directory / 'rec.py').write_text('import os,sys,time\n' + body + '\n'
        + f'os.execv(sys.executable, [sys.executable, {str(REC)!r}, *sys.argv[1:]])\n')
    return directory / 'lane.py'


def test_end_to_end(tmp_path):
    root = tmp_path / 'root'
    for name, code in (('ok', 0), ('bad', 3)):
        row = dispatch(root, name, f'raise SystemExit({code})')
        assert wait_for(lambda: finished(root, row))['exit'] == {'code': code}
        assert not status(root)['steps']
    row = dispatch(root, 'long', 'import time; time.sleep(30)')
    try:
        assert status(root)['steps'][0]['state'] == 'running'
    finally:
        cli(root, 'stop', '--step', row['step_id'])
        assert wait_for(lambda: finished(root, row))['exit'] == {'signal': 'SIGTERM'}
    assert not status(root)['steps']
    cli(root, 'stop', '--step', row['step_id'], expected=4)
    recording(root)
    assert events(root)[-1]['reported'] == 'finished'
    assert events(root)[-1]['quote'] == 'Reviewed'
    assert not status(root)['steps']
    owner = owner_open(root)
    assert status(root)['owners'][0]['since'] == owner['at']
    cli(root, 'owner-close', '--work', 'w1', '--wait', owner['wait_id'], '--how', 'done')
    assert status(root) == {'steps': [], 'owners': [], 'unrecorded': []}


def test_start_detached_verbatim_and_open_unchanged(tmp_path):
    root = tmp_path / 'root'
    marker = tmp_path / 'result'
    argv = ['space words', '$(echo BAD)', '--root', 'a; b', '']
    code = ('import os,signal,sys,time,json; from pathlib import Path; '
            'assert os.getsid(os.getpid()) == os.getpid(); '
            'assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN; '
            "assert sys.stdin.read() == ''; time.sleep(.7); "
            f'Path({str(marker)!r}).write_text(json.dumps(sys.argv[1:]))')
    row = json.loads(cli(root, 'start', '--work', 'w1', '--title', 'Original', '--name', 'job',
                        '--kind', 'other', '--who', 'Cursor', '--usual-min', '2', '--',
                        sys.executable, '-c', code, *argv).stdout)
    assert not marker.exists()
    wait_for(marker.exists)
    assert json.loads(marker.read_text()) == argv
    assert wait_for(lambda: finished(root, row))['exit'] == {'code': 0}
    second = dispatch(root, 'second')
    wait_for(lambda: finished(root, second))
    opened = [e for e in events(root) if e['type'] == 'work_opened']
    assert len(opened) == 1 and opened[0]['title'] == 'Original'
    saved = json.loads((root / 'lanes.json').read_text())[row['step_id']]
    assert saved['wrapper_pid'] == row['wrapper_pid']
    assert saved['name'] == 'job' and saved['who'] == 'Cursor'
    assert saved['usual_min'] == 2 and saved['wrapper_start'] is not None


def test_child_survives_death_of_start_caller_and_hup(tmp_path):
    root = tmp_path / 'root'
    marker = tmp_path / 'survived'
    response = tmp_path / 'response'
    command = [sys.executable, str(LANE), '--root', str(root), 'start', '--work', 'w1',
               '--title', 'Work', '--name', 'survivor', '--kind', 'other', '--who', 'Cursor',
               '--', sys.executable, '-c',
               f'import time; from pathlib import Path; time.sleep(1.5); Path({str(marker)!r}).write_text("ok")']
    caller_code = (f'import subprocess,time; from pathlib import Path; '
                   f'p=subprocess.run({command!r}, capture_output=True, text=True); '
                   f'Path({str(response)!r}).write_text(p.stdout); time.sleep(30)')
    caller = subprocess.Popen([sys.executable, '-c', caller_code], start_new_session=True)
    try:
        wait_for(response.exists)
        caller.terminate()
        caller.wait(timeout=3)
        row = json.loads(response.read_text())
        os.kill(row['wrapper_pid'], signal.SIGHUP)
        wait_for(marker.exists)
        assert wait_for(lambda: finished(root, row))['exit'] == {'code': 0}
        assert not status(root)['steps']
    finally:
        if caller.poll() is None:
            caller.terminate()
            caller.wait(timeout=3)


def test_start_timeout_does_not_stop_command(tmp_path):
    root = tmp_path / 'root'
    marker = tmp_path / 'late'
    # The fake recorder says nothing for 8.5 s; start gives up after its 5 s and must be back well before that.
    lane = proxy(tmp_path, "if sys.argv[3] == 'run': time.sleep(8.5)")
    begin = time.monotonic()
    proc = cli(root, 'start', '--work', 'w1', '--title', 'Work', '--name', 'late',
               '--kind', 'other', '--who', 'Cursor', '--', sys.executable, '-c',
               f'from pathlib import Path; Path({str(marker)!r}).write_text("ok")', expected=3, lane=lane)
    assert time.monotonic() - begin < 8
    row = json.loads(proc.stdout)
    assert row['step_id'] is None and row['output_dir'] is None and row['wrapper_pid'] > 0
    wait_for(marker.exists)
    assert json.loads((root / 'lanes.json').read_text())[f'pending:{row["wrapper_pid"]}']['name'] == 'late'
    wait_for(lambda: any(e['type'] == 'step_finished' for e in events(root)))
    assert not status(root)['steps']


@pytest.mark.parametrize('failure', ['declare', 'start', 'finish'])
def test_record_reports_each_failed_stage(tmp_path, failure):
    root = tmp_path / 'root'
    row = dispatch(root)
    wait_for(lambda: finished(root, row))
    trace = tmp_path / 'trace'
    lane = proxy(tmp_path, f'from pathlib import Path\n'
                 f'with Path({str(trace)!r}).open("a") as f: f.write(sys.argv[3] + "\\n")\n'
                 f'if sys.argv[3] == {failure!r}:\n    print("planted failure", file=sys.stderr)\n    sys.exit(7)')
    proc = cli(root, 'record', '--work', 'w1', '--name', 'Review', '--kind', 'review',
               '--who', 'Reviewer', '--result', 'done', lane=lane, expected=2)
    assert f'{failure} failed (7)' in proc.stderr and proc.stdout == ''
    order = ['declare', 'start', 'finish']
    assert trace.read_text().splitlines() == order[:order.index(failure) + 1]
    if failure != 'declare':
        step = events(root)[-1]['step_id']
        assert f'step {step} left behind' in proc.stderr
    else:
        assert 'left behind' not in proc.stderr
    assert not any(e['type'] == 'step_finished' and e.get('reported') == 'finished' for e in events(root))


def test_record_failed_verdict_and_invalid_result(tmp_path):
    row = dispatch(tmp_path)
    wait_for(lambda: finished(tmp_path, row))
    recording(tmp_path, 'failed', 'Changes required')
    assert [e['type'] for e in events(tmp_path)[-3:]] == ['step_declared', 'step_started', 'step_finished']
    assert events(tmp_path)[-1]['reported'] == 'failed'
    before = (tmp_path / 'w1/events.jsonl').read_bytes()
    cli(tmp_path, 'record', '--work', 'w1', '--name', 'Review', '--kind', 'review',
        '--who', 'Reviewer', '--result', 'approved', expected=2)
    assert (tmp_path / 'w1/events.jsonl').read_bytes() == before


def test_stop_stale_pid_does_not_signal_live_innocent(tmp_path):
    marker = tmp_path / 'innocent'
    child = subprocess.Popen([sys.executable, '-c',
                              f'import time; from pathlib import Path; time.sleep(.6); Path({str(marker)!r}).write_text("alive")'])
    (tmp_path / 'lanes.json').write_text(json.dumps({'stale': {'wrapper_pid': child.pid,
                                                              'wrapper_start': 'wrong start time'}}))
    try:
        assert 'wrapper is gone' in cli(tmp_path, 'stop', '--step', 'stale', expected=4).stderr
        assert 'wrapper is gone' in cli(tmp_path, 'stop', '--step', 'missing', expected=4).stderr
        assert child.wait(timeout=3) == 0 and marker.read_text() == 'alive'
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=3)


def test_status_over_owner_since_and_only_observe_writes(tmp_path):
    root = tmp_path / 'root'
    row = dispatch(root, code='import time; time.sleep(30)', usual=.00001)
    try:
        owner = owner_open(root)
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
        doc = status(root)
        step = doc['steps'][0]
        assert step['title'] == 'Work' and step['name'] == 'job' and step['who'] == 'Cursor'
        assert step['state'] == 'running' and step['elapsed_s'] > 0
        assert step['usual_min'] == .00001 and step['over']
        assert doc['owners'][0]['since'] == owner['at']
        text = cli(root, 'status').stdout
        assert 'Work | job | Cursor | running' in text and 'OVER' in text
        assert f'since {owner["at"]}' in text
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
        assert all(after[p] == value for p, value in before.items() if '_observer' not in p.parts)
        assert all('_observer' in p.parts for p in after.keys() - before.keys())
    finally:
        cli(root, 'stop', '--step', row['step_id'])
        wait_for(lambda: finished(root, row))


def test_status_observes_before_folding_dead_wrapper(tmp_path):
    pidfile = tmp_path / 'child-pid'
    row = dispatch(tmp_path, usual=.00001, code=f'import os,time; from pathlib import Path; Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)')
    try:
        wait_for(pidfile.exists)
        # Plant wrapper death without finish; observe must turn running into dead.
        os.kill(row['wrapper_pid'], signal.SIGKILL)
        wait_for(lambda: status(tmp_path)['steps'][0]['state'] == 'dead')
        folded = subprocess.run([sys.executable, str(REC), '--root', str(tmp_path), 'fold'],
                                capture_output=True, text=True, check=True, timeout=12)
        since = json.loads(folded.stdout)['works'][0]['steps'][0]['since']
        step = status(tmp_path)['steps'][0]
        assert step['since'] == since and not step['over']
        text = cli(tmp_path, 'status').stdout
        assert f'| dead | since {since}' in text and 'OVER' not in text
        assert not finished(tmp_path, row)
    finally:
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass


def test_status_does_not_hide_observe_failure(tmp_path):
    row = dispatch(tmp_path)
    wait_for(lambda: finished(tmp_path, row))
    lane = proxy(tmp_path, "if sys.argv[3] == 'observe':\n    print('planted observe failure', file=sys.stderr)\n    sys.exit(8)")
    proc = cli(tmp_path, 'status', '--json', lane=lane, expected=2)
    assert 'observe failed (8)' in proc.stderr and proc.stdout == ''


def test_root_precedence_and_owner_validation(tmp_path):
    env = os.environ.copy()
    env['HOME'] = str(tmp_path / 'home')
    env['BIFROST_RECORDER_ROOT'] = str(tmp_path / 'env')
    args = ['start', '--work', 'w1', '--title', 'Work', '--name', 'job', '--kind', 'other',
            '--who', 'Cursor', '--', sys.executable, '-c', 'pass']
    for root in (tmp_path / 'env', tmp_path / 'home/agent-work/recorder-root'):
        proc = subprocess.run([sys.executable, str(LANE), *args], env=env, capture_output=True, text=True, timeout=10)
        assert proc.returncode == 0, proc.stderr
        assert (root / 'lanes.json').exists()
        wait_for(lambda: finished(root, json.loads(proc.stdout)))
        env.pop('BIFROST_RECORDER_ROOT', None)
    env['BIFROST_RECORDER_ROOT'] = str(tmp_path / 'ignored')
    explicit = tmp_path / 'explicit'
    proc = cli(explicit, *args, env=env)
    wait_for(lambda: finished(explicit, json.loads(proc.stdout)))
    assert (explicit / 'lanes.json').exists() and not (tmp_path / 'ignored').exists()
    assert 'required' in cli(explicit, 'owner-open', '--work', 'w1', expected=2).stderr
    cli(explicit, 'owner-close', '--work', 'w1', '--wait', 'ffffffff', '--how', 'done', expected=1)


@pytest.mark.parametrize('usual', ['0', '-1', 'nan', 'inf'])
def test_invalid_usual_does_not_dispatch(tmp_path, usual):
    marker = tmp_path / 'unexpected'
    cli(tmp_path, 'start', '--work', 'w1', '--title', 'Work', '--name', 'job',
        '--kind', 'other', '--who', 'Cursor', '--usual-min', usual, '--', sys.executable,
        '-c', f'from pathlib import Path; Path({str(marker)!r}).touch()', expected=2)
    assert not marker.exists() and not (tmp_path / 'lanes.json').exists()


def test_status_under_usual_and_missing_metadata(tmp_path):
    row = dispatch(tmp_path, code='import time; time.sleep(30)', usual=10)
    try:
        step = status(tmp_path)['steps'][0]
        assert not step['over'] and step['usual_min'] == 10
        assert 'OVER' not in cli(tmp_path, 'status').stdout
        metadata = (tmp_path / 'lanes.json').read_bytes()
        (tmp_path / 'lanes.json').unlink()
        doc = status(tmp_path)
        assert doc['steps'][0]['usual_min'] is None and not doc['steps'][0]['over']
        assert not (tmp_path / 'lanes.json').exists()
        (tmp_path / 'lanes.json').write_bytes(metadata)
    finally:
        cli(tmp_path, 'stop', '--step', row['step_id'])
        wait_for(lambda: finished(tmp_path, row))


@pytest.mark.parametrize('argument,value,reason', [
    ('kind', 'fix', 'must be'), ('kind', 'ci', 'must be'), ('kind', 'release', 'must be'),
    ('name', 'n' * 81, '80'), ('who', 'w' * 81, '80'),
    ('name', 'bad\nname', 'control'), ('who', 'bad\twho', 'control'),
    ('name', 'bad\x7fname', 'control'), ('who', 'bad\u202ewho', 'control'),
    ('who', 'bad\x80who', 'control'),
])
def test_start_invalid_metadata_starts_nothing(tmp_path, argument, value, reason):
    root = tmp_path / 'root'
    marker = tmp_path / 'unexpected'
    args = dict(work='w1', title='Work', name='job', kind='other', who='Cursor')
    args[argument] = value
    tokens = [token for key, val in args.items() for token in ('--' + key, val)]
    proc = cli(root, 'start', *tokens, '--', sys.executable, '-c',
               f'from pathlib import Path; Path({str(marker)!r}).touch()', expected=2)
    assert proc.stdout == '' and len(proc.stderr.splitlines()) == 1
    assert f'--{argument}' in proc.stderr and reason in proc.stderr
    assert not root.exists() and not marker.exists()


def test_start_unrecorded_is_reported_and_command_runs(tmp_path):
    root = tmp_path / 'root'
    marker = tmp_path / 'ran'
    # Plant recorder rejection after lane's valid input; the real wrapper still runs the child.
    lane = proxy(tmp_path, "if sys.argv[3] == 'run':\n    sys.argv[sys.argv.index('--kind') + 1] = 'fix'")
    proc = subprocess.run([sys.executable, str(lane), '--root', str(root), 'start',
                           '--work', 'w1', '--title', 'Work', '--name', 'job',
                           '--kind', 'other', '--who', 'Cursor', '--', sys.executable, '-c',
                           f'import time; from pathlib import Path; Path({str(marker)!r}).touch(); time.sleep(30)'],
                          capture_output=True, text=True, timeout=12)
    row = json.loads(proc.stdout)
    try:
        assert proc.returncode == 3, proc.stdout + proc.stderr
        assert row['recorded'] is False and row['step_id'] and row['output_dir']
        wait_for(marker.exists)
        doc = status(root)
        assert doc['steps'] == []
        assert doc['unrecorded'] == [dict(work='w1', title='Work', unrecorded_runs=1)]
        assert 'Work | work w1 | unrecorded runs 1' in cli(root, 'status').stdout
    finally:
        cli(root, 'stop', '--step', row['step_id'])
        wait_for(lambda: not status(root)['unrecorded'])


@pytest.mark.parametrize('quote,clean', [
    ('q' * 201, 'q' * 200),
    ('First\nSecond', 'First'),
    ('A\tB\x1bC\x7fD\u202eE\x80F\nIgnored', 'ABCDEF'),
    ('', ''),
])
def test_record_cleans_quote_before_writing(tmp_path, quote, clean):
    row = dispatch(tmp_path)
    wait_for(lambda: finished(tmp_path, row))
    trace = tmp_path / 'quote-at-declare'
    lane = proxy(tmp_path, f'from pathlib import Path\n'
                 f'if sys.argv[3] == "declare":\n    Path({str(trace)!r}).touch()')
    recording_args = ['record', '--work', 'w1', '--name', 'Review', '--kind', 'review',
                      '--who', 'Reviewer', '--result', 'done', '--quote', quote]
    cli(tmp_path, *recording_args, lane=lane)
    assert trace.exists()
    assert [e['type'] for e in events(tmp_path)[-3:]] == ['step_declared', 'step_started', 'step_finished']
    assert events(tmp_path)[-1]['quote'] == clean
    assert not status(tmp_path)['steps']
