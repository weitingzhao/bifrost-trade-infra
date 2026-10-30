#!/usr/bin/env bash
# Offline behavioral regressions for review 691 and TD-458. Real temporary Git repositories;
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
    for name in ('sleep-pids', 'heartbeat-pids', 'curl-pids', 'git-pids'):
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
elif route=='/claim/pinned':
    doc={'attempt_id':'a_fixture','lease_epoch':1,'pushed_ref':'refs/heads/agent/'+os.environ['TEST_TASK']+'/a'+os.environ.get('TEST_ATTEMPT','1')}
    if os.environ.get('TEST_CLAIM_ERROR'):
        code='409'; doc={'error':'no_lease','message':'executor quota reached quota_stop_percent'}
    if os.environ.get('TEST_CLAIMS'):
        counter=root/'claim-count'; n=int(counter.read_text()) if counter.exists() else 0
        counter.write_text(str(n+1))
        replies=json.loads(os.environ['TEST_CLAIMS']); reply=replies[min(n,len(replies)-1)]
        if reply.get('timeout'):
            time.sleep(float(args[args.index('--max-time')+1])); sys.exit(28)
        code=str(reply['code'])
        if 'message' in reply: doc={'error':'state','message':reply['message']}
elif route=='/attempts/a_fixture': doc=s
elif route.startswith('/missions/'): doc={'tasks':[{'task_id':os.environ['TEST_TASK']}]}
elif route=='/landing/refresh':
    assert payload=={'task':os.environ['TEST_TASK'],'op':'land:'+os.environ['TEST_TASK']+':1'}
    doc={'refreshed':True,**payload}
elif route.startswith('/landing/operations/'): doc={'phase':'awaiting_grant','main_known':True,'main_changed':True}
elif '/material?' in route:
    assert method=='GET'
    assert Path(args[args.index('-H')+1][1:]).read_text()=='Authorization: Bearer SENTINEL_AGENTD\n'
    stg=route.rsplit('=',1)[-1]=='true'
    core=os.environ.get('TEST_CORE')=='1'
    candidate={'env':'prod','repo':'bifrost-platform','task':os.environ['TEST_TASK'],
        'op':'land:'+os.environ['TEST_TASK']+':1','R':'f'*40,'stg_release':stg,
        'hard_core_paths':[{'path':'api/internal/agentrt/store/x.go'}] if core else [],
        'decision_chain':core,'trust_review':core}
    doc={'material':{'candidate':candidate,'material_digest':'sha256:'+'d'*64,
        'action':'approve_core_landing' if core else 'approve_guardrail_landing',
        'problems':['review_missing'] if os.environ.get('TEST_PROBLEMS') else [],
        'soft_at_request':['core'] if core else ['floor_soft']},
        'main_is_M0':not bool(os.environ.get('TEST_STALE_MAIN'))}
    if os.environ.get('TEST_MATERIAL_BAD'): del doc['material']['candidate']['R']
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
if route=='/claim/pinned' and os.environ.get('TEST_CLAIM_RAW'):
    code='502'; Path(args[args.index('-o')+1]).write_text('<html>gateway unavailable</html>')
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
else:
    root=Path(os.environ['TEST_ROOT'])
    with (root/'waits').open('a') as f: f.write(sys.argv[1]+'\n')
    time.sleep(float(sys.argv[1]) if os.environ.get('TEST_REAL_WAIT') else .01)
''')
        (bin/'git').write_text(r'''#!/usr/bin/env python3
import os,sys
from pathlib import Path
root=Path(os.environ['TEST_ROOT'])
if sys.argv[1]=='push':
    with (root/'pushes').open('a') as f: f.write(' '.join(sys.argv[2:])+'\n')
    if not os.environ.get('TEST_PUSH_FAIL'):
        (root/'remote-ref').write_text(sys.argv[-1].replace(':','\t')+'\n')
    sys.exit(1 if os.environ.get('TEST_PUSH_FAIL') else 0)
if sys.argv[1]=='ls-remote':
    with (root/'readbacks').open('a') as f: f.write(' '.join(sys.argv[2:])+'\n')
    if os.environ.get('TEST_READ_FAIL'): sys.exit(1)
    if (root/'remote-ref').exists(): print((root/'remote-ref').read_text(),end='')
    sys.exit(0)
if sys.argv[1]=='commit-tree' and os.environ.get('TEST_COMMIT_FAIL'): sys.exit(1)
os.execv(os.environ['TEST_REAL_GIT'],[os.environ['TEST_REAL_GIT'],*sys.argv[1:]])
''')
        for f in bin.iterdir(): f.chmod(0o755)
        def run(*a, success=True, extra=None):
            p=invoke(['bash',str(script),*a], repo, dict(env,**(extra or {})),success)
            assert 'SENTINEL' not in p.stdout+p.stderr
            if (root/'calls').exists(): assert 'SENTINEL' not in (root/'calls').read_text()
            return p
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

def squash_attempts(root,repo,env,git,run,args,base,commit):
    def edit(name):
        (repo/name).write_text(name+'\n'); git('add',name); git('commit','-qm',name)
        return git('rev-parse','HEAD')
    def selection(*commits, attempt='1'):
        return ['squash','--task',task,'--base',base,'--attempt',attempt,
                *[arg for c in commits for arg in ('--commit',c)]]
    def change(c):
        return [line for line in git('show','-s','--format=%B',c).splitlines() if line.startswith('Change-Id:')]
    other=edit('first-round')
    first=run(*selection(commit,other)).stdout.strip()
    state_dir=repo/'.git/handin/squash'/task
    original={p.name:p.read_bytes() for p in state_dir.iterdir() if p.is_file()}
    backup=git('rev-parse','refs/handin/backups/'+task)
    assert 'a_fixture' in run(*args).stdout
    assert json.loads((root/'state.json').read_text())['state']=='submitted'
    assert (root/'remote-ref').read_text()==first+'\trefs/heads/agent/'+task+'/a1\n'
    later=edit('second-round')
    # Default/explicit attempt 1 must still refuse a changed source, even
    # after delivery. Selecting attempt 2 must leave all old recovery intact.
    p=run(*selection(first,later),success=False)
    assert 'recovery state differs' in p.stderr and git('rev-parse','HEAD')==later
    second_args=selection(first,later,attempt='2')
    run(*second_args,success=False,extra={'TEST_COMMIT_FAIL':'1'})
    second_dir=state_dir/'attempts/2'
    second_saved={p.name:p.read_bytes() for p in second_dir.iterdir()}
    assert git('rev-parse','HEAD')==later
    git('checkout','-q','-b','interrupted-drift')
    drift=edit('unexpected-change')
    p=run(*selection(first,later,drift,attempt='2'),success=False)
    assert 'recovery state differs' in p.stderr and git('rev-parse','HEAD')==drift
    assert all((second_dir/name).read_bytes()==data for name,data in second_saved.items())
    git('checkout','-q','work-unit')
    second=run(*second_args).stdout.strip()
    assert git('rev-parse','HEAD')==second and second!=first
    assert git('rev-parse',second+'^')==base
    assert git('rev-parse',second+'^{tree}')==git('rev-parse',later+'^{tree}')
    assert change(first)==change(second) and len(change(second))==1
    assert all((second_dir/name).read_bytes()==data for name,data in second_saved.items())
    assert run(*second_args).stdout.strip()==second
    assert all((state_dir/name).read_bytes()==data for name,data in original.items())
    assert git('rev-parse','refs/handin/backups/'+task)==backup
    assert git('rev-parse','refs/handin/attempt-backups/'+task+'/a2')==later
    # The second attempt is a separate run binding and a2 push, using the
    # same fixture API but no real remote or credentials.
    (root/'state.json').write_text(json.dumps(dict(state='leased',task_id=task,host_id='coordinator-mbp',lease_epoch=1)))
    (root/'remote-ref').unlink()
    assert 'a_fixture' in run(*args,'--key',task+':2',extra={'TEST_ATTEMPT':'2'}).stdout
    assert (root/'remote-ref').read_text()==second+'\trefs/heads/agent/'+task+'/a2\n'
    third_tip=edit('third-round')
    third=run(*selection(second,third_tip,attempt='3')).stdout.strip()
    assert change(third)==change(first)
    for invalid in ('0','-1','01','../2','2/3','abc'):
        run(*selection(third,attempt=invalid),success=False)
    # A prepared commit with a different identity must not skip the lineage
    # check on the idempotent fast path. Keep the good branch unchanged.
    git('checkout','-q','-b','wrong-identity',commit)
    p=run('squash','--task',task,'--base',base,'--attempt','4',success=False)
    assert 'Change-Id differs from first attempt' in p.stderr
    assert git('rev-parse','HEAD')==commit

def squash_prepared(root,repo,env,git,run,args,base,commit):
    # Prepared attempt 1 has no recovery message, but its identity remains
    # available in the explicitly selected history for a later attempt.
    assert run('squash','--task',task,'--base',base).stdout.strip()==commit
    (repo/'rework').write_text('rework\n'); git('add','rework'); git('commit','-qm','Rework')
    tip=git('rev-parse','HEAD')
    result=run('squash','--task',task,'--base',base,'--attempt','2','--commit',commit,'--commit',tip).stdout.strip()
    assert 'Change-Id: I'+'c'*40 in git('show','-s','--format=%B',result)
    assert not (root/'calls').exists(), 'squash must remain offline'

def dead_pids(root):
    for name in ('sleep-pids','heartbeat-pids','curl-pids','git-pids'):
        p=root/name
        for pid in p.read_text().splitlines() if p.exists() else []:
            try: os.kill(int(pid),0)
            except ProcessLookupError: continue
            raise AssertionError('heartbeat/request process remains: '+pid)

def cleanup(root,repo,env,git,run,args,base,commit):
    run(*args); dead_pids(root)
    for extra in ({'TEST_PUSH_FAIL':'1'}, {'TEST_BEAT':'stop','TEST_BLOCK':'start'}, {'TEST_BEAT':'reject','TEST_BLOCK':'start'}):
        (root/'remote-ref').unlink(missing_ok=True)
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

def push_cleanup(root,repo,env,git,run,args,base,commit):
    # A real child/grandchild tree stands in for Git's credential/transport
    # helpers. The marker is emitted by the deepest child, after all exist.
    helper=root/'helper.py'
    helper.write_text(r'''import os,signal,subprocess,sys,time
from pathlib import Path
root=Path(os.environ['TEST_ROOT'])
with (root/'git-pids').open('a') as f: f.write(str(os.getpid())+'\n')
if sys.argv[1]=='leaf':
    (root/'push-started').write_text('ready')
    time.sleep(3)
else:
    p=subprocess.Popen([sys.executable,__file__,'leaf'])
    def stop(sig,frame):
        p.wait()
        sys.exit(128+sig)
    signal.signal(signal.SIGTERM,stop)
    p.wait()
''')
    wrapper=root/'bin/git'
    code=wrapper.read_text().replace('import os,sys', 'import os,sys,signal,subprocess')
    code=code.replace("if sys.argv[1]=='push':", r'''if sys.argv[1]=='push' and os.environ.get('TEST_PUSH_BLOCK'):
    with (root/'git-pids').open('a') as f: f.write(str(os.getpid())+'\n')
    if os.environ.get('TEST_PUSH_LANDED'):
        (root/'remote-ref').write_text(sys.argv[-1].replace(':','\t')+'\n')
    p=subprocess.Popen([sys.executable,str(root/'helper.py'),'parent'])
    def stop(sig,frame):
        p.wait()
        sys.exit(128+sig)
    signal.signal(signal.SIGTERM,stop)
    p.wait()
    (root/'push-completed').write_text('done')
if sys.argv[1]=='push':''')
    wrapper.write_text(code)
    sleeper=root/'bin/sleep'
    sleeper.write_text(sleeper.read_text().replace("time.sleep(.02 if os.environ.get('TEST_BEAT') else 20)", """if os.environ.get('TEST_BEAT'):
        for _ in range(600):
            if (root/'push-started').exists(): break
            time.sleep(.01)
    else: time.sleep(20)"""))
    for mode in ('control','stop','reject','term','int','landed'):
        if os.environ.get('HANDIN_PUSH_CASE') and mode not in ('control',os.environ['HANDIN_PUSH_CASE']): continue
        for f in ('push-started','push-completed','remote-ref'):
            (root/f).unlink(missing_ok=True)
        (root/'state.json').write_text(json.dumps(dict(state='leased',task_id=task,host_id='coordinator-mbp',lease_epoch=1)))
        e=dict(env,TEST_PUSH_BLOCK='1',TEST_BEAT=mode if mode in ('stop','reject') else '')
        if mode=='landed': e['TEST_PUSH_LANDED']='1'
        p=subprocess.Popen(['bash',str(script),*args],cwd=repo,env=e,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+6
            while not (root/'push-started').exists():
                assert p.poll() is None and time.monotonic()<deadline, 'push never started'
                time.sleep(.01)
            if mode in ('term','landed'): p.send_signal(signal.SIGTERM)
            if mode=='int': p.send_signal(signal.SIGINT)
            out,err=p.communicate(timeout=6 if mode=='control' else 1.5)
            assert p.returncode==({'control':0,'term':143,'landed':143,'int':130}.get(mode,1)), (mode,p.returncode,err)
            assert (root/'push-completed').exists()==(mode=='control'), mode
            state=json.loads((root/'state.json').read_text())
            assert ('persisted_at' in state)==(mode=='control'), (mode,state)
            dead_pids(root)
            assert not list((repo/'.git/handin/runs').glob('*.lock'))
            print('PASS blocked push',mode)
        finally:
            if p.poll() is None:
                p.kill(); stop_fixtures(root); p.communicate(timeout=5)
        if mode=='landed':
            # Advance HEAD after cancellation; the saved key must still
            # recover the original result without issuing a second push.
            (repo/'later').write_text('later\n'); git('add','later'); git('commit','-qm','Later work')
            before=(root/'pushes').read_text()
            (root/'remote-ref').write_text('e'*40+'\trefs/heads/agent/'+task+'/a1\n')
            run(*args,success=False)
            (root/'remote-ref').write_text(commit+'\trefs/heads/agent/'+task+'/a1\n')
            run(*args,success=False,extra={'TEST_READ_FAIL':'1'})
            assert 'persisted_at' not in json.loads((root/'state.json').read_text())
            assert 'a_fixture' in run(*args).stdout
            assert (root/'pushes').read_text()==before
            assert json.loads((root/'state.json').read_text())['pushed_commit']==commit
            dead_pids(root)

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

def claim_error(root,repo,env,git,run,args,base,commit):
    p=run(*args,success=False,extra={'TEST_CLAIM_ERROR':'1'})
    assert 'HTTP 409' in p.stderr and 'no_lease' in p.stderr and 'quota_stop_percent' in p.stderr
    assert 'retry with the same key' in p.stderr
    p=run(*args,success=False,extra={'TEST_CLAIM_RAW':'1'})
    assert 'HTTP 502' in p.stderr and 'gateway unavailable' not in p.stderr
    calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
    assert all(c[-1].endswith(('/tasks/'+task,'/claim/pinned')) for c in calls)
    assert not (root/'pushes').exists()

def claim_ready(root,repo,env,git,run,args,base,commit):
    proposed={'code':409,'message':'task '+task+' is proposed, not ready'}
    def claims():
        return [json.loads(line) for line in (root/'calls').read_text().splitlines()
                if json.loads(line)[-1].endswith('/claim/pinned')]
    def reset():
        for name in ('calls','claim-count','waits'): (root/name).unlink(missing_ok=True)
    p=run(*args,extra={'TEST_TASK_STATE':'proposed','TEST_CLAIMS':json.dumps([proposed]*5+[{'code':200}])})
    assert 'a_fixture' in p.stdout and 'retrying claim/pinned' in p.stderr
    requests=claims()
    assert len(requests)==6
    bodies=[c[c.index('--data-binary')+1] for c in requests]
    assert len(set(bodies))==1 and json.loads(bodies[0])['idempotency_key']=='same'
    assert (root/'waits').read_text().splitlines()[:5]==['1','2','4','8','10']
    assert json.loads((root/'state.json').read_text())['state']=='submitted'
    dead_pids(root)
    # Both a persistent proposed response and a transport timeout after one
    # must respect the total deadline. Curl gets only the remaining budget.
    for replies in ([proposed], [proposed,{'code':200,'timeout':True}]):
        reset(); started=time.monotonic()
        p=run(*args,success=False,extra={'TEST_CLAIMS':json.dumps(replies),
            'HANDIN_READY_TIMEOUT_SECONDS':'2','TEST_REAL_WAIT':'1' if len(replies)==1 else ''})
        elapsed=time.monotonic()-started
        # Bash SECONDS has one-second granularity; the deadline may be
        # reached up to one second earlier than a monotonic stopwatch.
        assert .8<elapsed<3.5, elapsed
        if len(replies)>1: assert len(claims())>=2
        assert 'timed out after 2s' in p.stderr and task in p.stderr and 'is proposed, not ready' in p.stderr
        assert 'retry with the same key' in p.stderr
        assert all(0<float(c[c.index('--max-time')+1])<=2 for c in claims())
        assert all(c[-1].endswith(('/tasks/'+task,'/claim/pinned'))
                   for c in map(json.loads,(root/'calls').read_text().splitlines()))
        dead_pids(root)
        assert not list((repo/'.git/handin/runs').glob('*.lock'))
    # Other 409s and the same text under another status stop immediately;
    # a quota response after proposed must also stop the readiness loop.
    for code,message in ((409,'quota_stop_percent'),(409,'task is running, not ready'),
                         (403,proposed['message']),(409,None),(409,['is proposed, not ready'])):
        reset()
        p=run(*args,success=False,extra={'TEST_CLAIMS':json.dumps([{'code':code,'message':message}])})
        assert len(claims())==1 and 'HTTP '+str(code) in p.stderr
        assert not (root/'waits').exists()
    reset()
    p=run(*args,success=False,extra={'TEST_CLAIMS':json.dumps([proposed,{'code':409,'message':'quota_stop_percent'}])})
    assert len(claims())==2 and 'quota_stop_percent' in p.stderr and 'timed out' not in p.stderr
    assert (root/'waits').read_text().splitlines()==['1']

def material(root,repo,env,git,run,args,base,commit):
    op='land:'+task+':1'
    for options,core,stg in (([],False,True),(['--stg-release','false'],False,False),(['--stg-release','true'],True,True)):
        p=run('material','--op',op,*options,extra={'TEST_CORE':'1' if core else ''})
        doc=json.loads(p.stdout)
        assert doc['action']==('approve_core_landing' if core else 'approve_guardrail_landing')
        assert doc['params']=={'env':'prod','repo':'bifrost-platform','task':task,'op':op,'R':'f'*40,
                              'material_digest':'sha256:'+'d'*64,'stg_release':stg}
        assert doc['problems']==[] and doc['main_is_M0'] is True
        assert doc['soft_at_request']==(['core'] if core else ['floor_soft'])
        assert bool(doc['hard_core_paths'])==core
        assert doc['decision_chain']==core and doc['trust_review']==core
    for extra in ({'TEST_PROBLEMS':'1'}, {'TEST_STALE_MAIN':'1'}):
        p=run('material','--op',op,success=False,extra=extra)
        assert 'do not request_action' in p.stderr
        assert json.loads(p.stdout)['problems'] or not json.loads(p.stdout)['main_is_M0']
    for extra in ({'TEST_CODE':'403'}, {'TEST_MATERIAL_BAD':'1'}):
        p=run('material','--op',op,success=False,extra=extra)
        assert not p.stdout
    before=(root/'calls').read_text()
    for bad in ([],['--op'],['--op','land:x:0'],['--op',op+'?extra=1'],['--op',op,'--stg-release','yes'],['--op',op,'--stg-release']):
        run('material',*bad,success=False)
    assert before==(root/'calls').read_text(), 'invalid input made an HTTP request'
    calls=[json.loads(line) for line in before.splitlines()]
    assert all(c[c.index('-X')+1]=='GET' and '/material?stg_release=' in c[-1] for c in calls)
    assert 'SENTINEL' not in before

for name,fn in [('B-03',http),('R-03',squash),('TD-458-squash',squash_attempts),('TD-458-prepared',squash_prepared),('R-04',recovery),('R-05',cleanup),('R-01-push',push_cleanup),('N-01',tokens),('N-02',refresh),('C-7-claim',claim_error),('TD-458-ready',claim_ready),('C-7-material',material)]: test(name,fn)
PY
