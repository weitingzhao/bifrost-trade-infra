#!/usr/bin/env bash
# Offline behavioral regressions for review 691. Real temporary Git repositories;
# curl is replaced before any invocation, with fixture-only credentials.
set -euo pipefail
script=${HANDIN_SCRIPT:-$(cd "$(dirname "$0")" && pwd)/handin.sh}
python3 - "$script" "${1:-all}" <<'PY'
import hashlib, json, os, signal, subprocess, sys, tempfile, time
from pathlib import Path
script, group = Path(sys.argv[1]).resolve(), sys.argv[2]
task = 't_' + '0'*25 + '1'
realgit = subprocess.check_output(['which','git'], text=True).strip()

def stop_fixtures(root):
    # Only PIDs written by our own offline child fixtures; no system process
    # enumeration or process-group signaling (restricted on macOS sandboxes).
    for name in ('sleep-pids', 'heartbeat-pids', 'curl-pids'):
        f=root/name
        for pid in f.read_text().splitlines() if f.exists() else []:
            try: os.kill(int(pid), signal.SIGKILL)
            except ProcessLookupError: pass

def invoke(args, cwd, env, success=True):
    child = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = child.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        child.kill()
        stop_fixtures(Path(env['TEST_ROOT']))
        stdout, stderr = child.communicate()
        raise AssertionError(('process or inherited output pipe remained open', args, stdout, stderr))
    p = subprocess.CompletedProcess(args, child.returncode, stdout, stderr)
    if success is not None and (p.returncode == 0) != success:
        raise AssertionError((args, p.returncode, p.stdout, p.stderr))
    return p

def test(name, fn):
    if group not in ('all', name): return
    with tempfile.TemporaryDirectory(prefix='handin-test-') as d:
        root=Path(d); repo=root/'repo'; repo.mkdir(); bin=root/'bin'; bin.mkdir()
        env=dict(os.environ, PATH=str(bin)+os.pathsep+os.environ['PATH'], PLATFORM_AGENTRT_URL='http://offline.invalid',
            AGENTRT_COORDINATOR_AGENTD_TOKEN='SENTINEL_AGENTD', AGENTRT_COORDINATOR_PROPOSER_TOKEN='SENTINEL_PROPOSER',
            TEST_ROOT=str(root), TEST_TASK=task, TEST_REAL_GIT=realgit)
        def git(*a): return invoke([realgit,*a],repo,env).stdout.strip()
        git('init','-q','-b','work-unit'); git('config','user.name','Fixture'); git('config','user.email','fixture@example.invalid')
        (repo/'base').write_text('base\n'); git('add','base'); git('commit','-qm','base'); base=git('rev-parse','HEAD')
        env['TEST_BASE']=base
        (repo/'mine').write_text('mine\n'); git('add','mine'); git('commit','-qm','Mine\n\nAgentrt-Task: '+task+'\nChange-Id: I'+'c'*40)
        commit=git('rev-parse','HEAD'); env['TEST_COMMIT']=commit
        (root/'report').write_text('fixture report\n')
        (root/'state.json').write_text(json.dumps(dict(state='leased',task_id=task,host_id='coordinator-mbp',lease_epoch=1)))
        (bin/'curl').write_text(r'''#!/usr/bin/env python3
import hashlib,json,os,sys,time
from pathlib import Path
root=Path(os.environ['TEST_ROOT']); args=sys.argv[1:]; url=args[-1]; route=url.split('/api/v1/agentrt')[-1]
with (root/'calls').open('a') as f: f.write(json.dumps(args)+'\n')
with (root/'curl-pids').open('a') as f: f.write(str(os.getpid())+'\n')
# Sentinels must be supplied through a header file, never the argv on fixed code.
method=args[args.index('-X')+1]; payload={}
if '--data-binary' in args:
    data=args[args.index('--data-binary')+1]
    if not data.startswith('@'): payload=json.loads(data)
s=json.loads((root/'state.json').read_text()); doc={'ok':True}; code=os.environ.get('TEST_CODE','200')
action=route.rsplit('/',1)[-1]
if route.startswith('/tasks/'): doc={'base_commit':os.environ['TEST_BASE'],'state':os.environ.get('TEST_TASK_STATE','ready')}
elif route=='/claim/pinned': doc={'attempt_id':'a_fixture','lease_epoch':1,'pushed_ref':'refs/heads/agent/'+os.environ['TEST_TASK']+'/a1'}
elif route=='/attempts/a_fixture': doc=s
elif route.startswith('/missions/'): doc={'tasks':[{'task_id':os.environ['TEST_TASK']}]}
elif route=='/landing/refresh':
    assert payload=={'task':os.environ['TEST_TASK'],'op':'land:'+os.environ['TEST_TASK']+':1'}
    doc={'refreshed':True,**payload}
elif route.startswith('/landing/operations/'): doc={'phase':'awaiting_grant','main_known':True,'main_changed':True}
elif action=='heartbeat':
    doc={'stop':os.environ.get('TEST_BEAT')=='stop'}
    if os.environ.get('TEST_BEAT')=='reject': code='409'
elif action in ('start','computed','persist','submit'):
    if action=='start': s.update(started_at='now',state='running')
    if action=='computed': s['computed_at']='now'
    if action=='persist': s.update(persisted_at='now',pushed_commit=payload['pushed_commit'],pushed_ref=payload['pushed_ref'],report_artifact_id=payload['report'])
    if action=='submit': s['state']='submitted'
    (root/'state.json').write_text(json.dumps(s))
if os.environ.get('TEST_BLOCK')==action:
    (root/'blocked').write_text(str(os.getpid())); time.sleep(20)
Path(args[args.index('-o')+1]).write_text(json.dumps(doc))
if os.environ.get('TEST_TIMEOUT')=='1' or action==os.environ.get('TEST_LOST'):
    sys.exit(28)
print(code,end='')
''')
        (bin/'sleep').write_text(r'''#!/usr/bin/env python3
import os,sys,time
from pathlib import Path
if sys.argv[1]=='60':
    root=Path(os.environ['TEST_ROOT'])
    with (root/'sleep-pids').open('a') as f: f.write(str(os.getpid())+'\n')
    with (root/'heartbeat-pids').open('a') as f: f.write(str(os.getppid())+'\n')
    time.sleep(.02 if os.environ.get('TEST_BEAT') else 20)
else: time.sleep(.01)
''')
        (bin/'git').write_text(r'''#!/usr/bin/env python3
import os,sys
from pathlib import Path
root=Path(os.environ['TEST_ROOT'])
if sys.argv[1]=='push':
    with (root/'pushes').open('a') as f: f.write(' '.join(sys.argv[2:])+'\n')
    sys.exit(1 if os.environ.get('TEST_PUSH_FAIL') else 0)
if sys.argv[1]=='commit-tree' and os.environ.get('TEST_COMMIT_FAIL'): sys.exit(1)
os.execv(os.environ['TEST_REAL_GIT'],[os.environ['TEST_REAL_GIT'],*sys.argv[1:]])
''')
        for f in bin.iterdir(): f.chmod(0o755)
        def run(*a, success=True, extra=None): return invoke(['bash',str(script),*a], repo, dict(env,**(extra or {})),success)
        args=['run','--task',task,'--report',str(root/'report'),'--remote','fixture','--key','same']
        try:
            fn(root,repo,env,git,run,args,base,commit)
            print('PASS',name)
        finally:
            stop_fixtures(root)

def http(root,repo,env,git,run,args,base,commit):
    assert 'leased' in run('status','--attempt','a_fixture').stdout
    assert task in run('propose','--mission','M-1','--title','unit','--repo','bifrost-platform','--base',base).stdout
    assert 'HTTP 403' in run('status','--attempt','a_fixture',success=False,extra={'TEST_CODE':'403'}).stderr
    assert 'HTTP 000' in run('status','--attempt','a_fixture',success=False,extra={'TEST_TIMEOUT':'1'}).stderr

def squash(root,repo,env,git,run,args,base,commit):
    # A prepared single commit is an identity, not a request for a new SHA.
    assert run('squash','--task',task,'--base',base).stdout.strip()==commit
    assert git('rev-parse','HEAD')==commit
    (repo/'other').write_text('foreign\n'); git('add','other'); git('commit','-qm','Other work')
    other=git('rev-parse','HEAD')
    run('squash','--task',task,'--base',base,success=False)
    run('squash','--task',task,'--base',base,'--commit',commit,success=False)
    assert git('rev-parse','HEAD')==other
    run('squash','--task',task,'--base',base,'--commit',commit,'--commit',other,success=False,extra={'TEST_COMMIT_FAIL':'1'})
    assert git('rev-parse','HEAD')==other
    msg=repo/'.git/handin/squash'/task/'message'; saved=msg.read_text()
    result=run('squash','--task',task,'--base',base,'--commit',commit,'--commit',other).stdout.strip()
    assert git('rev-parse','HEAD')==result and saved==msg.read_text()
    assert run('squash','--task',task,'--base',base).stdout.strip()==result
    git('branch','main'); git('checkout','-q','main')
    run('squash','--task',task,'--base',base,success=False)

def recovery(root,repo,env,git,run,args,base,commit):
    # A lost submit response is already complete before this invocation.
    submitted=dict(state='submitted', task_id=task, host_id='coordinator-mbp', lease_epoch=1,
        started_at='now', computed_at='now', persisted_at='now', pushed_commit=commit,
        pushed_ref='refs/heads/agent/'+task+'/a1', report_artifact_id='sha256:'+hashlib.sha256((root/'report').read_bytes()).hexdigest())
    (root/'state.json').write_text(json.dumps(submitted))
    assert 'a_fixture' in run(*args).stdout
    submitted['state']='finished'; (root/'state.json').write_text(json.dumps(submitted))
    assert 'a_fixture' in run(*args).stdout
    for stage in ('start','computed','persist','submit'):
        (root/'state.json').write_text(json.dumps(dict(state='leased',task_id=task,host_id='coordinator-mbp',lease_epoch=1)))
        assert 'a_fixture' in run(*args,extra={'TEST_LOST':stage}).stdout
        # A replay must not push again after persistence.
        pushes=(root/'pushes').read_text()
        assert 'a_fixture' in run(*args).stdout
        assert pushes==(root/'pushes').read_text()
    (repo/'later').write_text('later\n'); git('add','later'); git('commit','-qm','Later work')
    assert 'a_fixture' in run(*args).stdout
    run(*args,'--commit','HEAD',success=False)
    (root/'report').write_text('different\n'); run(*args,success=False)
    (root/'report').write_text('fixture report\n')
    s=json.loads((root/'state.json').read_text()); s['pushed_commit']='e'*40; (root/'state.json').write_text(json.dumps(s))
    run(*args,success=False)

def dead_pids(root):
    for name in ('sleep-pids','heartbeat-pids','curl-pids'):
        p=root/name
        for pid in p.read_text().splitlines() if p.exists() else []:
            try: os.kill(int(pid),0)
            except ProcessLookupError: continue
            raise AssertionError('heartbeat/request process remains: '+pid)

def cleanup(root,repo,env,git,run,args,base,commit):
    run(*args); dead_pids(root)
    for extra in ({'TEST_PUSH_FAIL':'1'}, {'TEST_BEAT':'stop','TEST_BLOCK':'start'}, {'TEST_BEAT':'reject','TEST_BLOCK':'start'}):
        (root/'state.json').write_text(json.dumps(dict(state='leased',task_id=task,host_id='coordinator-mbp',lease_epoch=1)))
        run(*args,success=False,extra=extra); dead_pids(root)
    for sig in (signal.SIGINT,signal.SIGTERM):
        (root/'state.json').write_text(json.dumps(dict(state='leased',task_id=task,host_id='coordinator-mbp',lease_epoch=1)))
        (root/'blocked').unlink(missing_ok=True)
        p=subprocess.Popen(['bash',str(script),*args],cwd=repo,env=dict(env,TEST_BLOCK='start'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        for _ in range(500):
            if (root/'blocked').exists(): break
            time.sleep(.01)
        else: p.kill(); raise AssertionError('no blocked start')
        p.send_signal(sig); p.communicate(timeout=5)
        assert p.returncode!=0; dead_pids(root)

def tokens(root,repo,env,git,run,args,base,commit):
    p=run('status','--attempt','a_fixture'); assert 'SENTINEL' not in p.stdout+p.stderr
    p=invoke(['bash','-x',str(script),'status','--attempt','a_fixture'],repo,env,None)
    assert 'SENTINEL' not in p.stdout+p.stderr, 'tracing exposed a credential'
    assert p.returncode!=0
    trace=root/'trace'
    with trace.open('w') as fd:
        e=dict(env,BASH_XTRACEFD=str(fd.fileno()))
        p=subprocess.run(['bash','-x',str(script),'status','--attempt','a_fixture'],cwd=repo,env=e,pass_fds=(fd.fileno(),),capture_output=True,text=True)
    assert p.returncode!=0 and 'SENTINEL' not in trace.read_text()+p.stdout+p.stderr
    assert 'SENTINEL' not in (root/'calls').read_text()
    token=root/'token'; token.write_text('SENTINEL_FILE'); token.chmod(0o600)
    run('status','--attempt','a_fixture',extra={'AGENTRT_COORDINATOR_AGENTD_TOKEN':'','HANDIN_AGENTD_TOKEN_FILE':str(token)})
    token.chmod(0o644)
    run('status','--attempt','a_fixture',success=False,extra={'AGENTRT_COORDINATOR_AGENTD_TOKEN':'','HANDIN_AGENTD_TOKEN_FILE':str(token)})

def refresh(root,repo,env,git,run,args,base,commit):
    op='land:'+task+':1'
    assert 'awaiting_grant' in run('status','--attempt','a_fixture','--task',task,'--op',op).stdout
    assert 'main_changed' in run('refresh','--task',task,'--op',op).stdout
    run('refresh','--task',task,'--op',op,success=False,extra={'TEST_CODE':'403'})

for name,fn in [('B-03',http),('R-03',squash),('R-04',recovery),('R-05',cleanup),('N-01',tokens),('N-02',refresh)]: test(name,fn)
PY
