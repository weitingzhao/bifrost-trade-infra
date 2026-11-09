"""Exercise ownership migration with kubectl responses, without a cluster."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'k8s/cicd/tekton/apply-manifest/apply-manifest-ownership.sh'
FAKE = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
a=sys.argv[1:]
p=Path(os.environ['PROBE'])
with (p/'calls').open('a') as f: f.write(json.dumps(a)+'\\n')
if a[0]=='get':
 print(json.dumps({'metadata':{'managedFields':[{'manager':m,'operation':os.environ['OP']} for m in os.environ['MANAGER'].split(',')], 'annotations':json.loads(os.environ['ANNOTATIONS'])}}))
elif '--dry-run=server' in a:
 n=int((p/'n').read_text()) if (p/'n').exists() else 0
 (p/'n').write_text(str(n+1))
 m=os.environ['MANAGER'] if n==0 else os.environ.get('LATER', os.environ['MANAGER'])
 if m:
  for manager in m.split(','): print(os.environ.get('CONFLICT_PREFIX', 'conflict with')+' "'+manager+'": .spec',file=sys.stderr)
  sys.exit(1)
'''

class Ownership(unittest.TestCase):
    def run_case(self, manager, ns='cicd', kind='Task', op='Update', annotation=True, later=None, plural=False, mode='apply'):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'kubectl').write_text(FAKE)
            (p/'kubectl').chmod(0o755)
            (p/'render').write_text(json.dumps({'kind':'List','items':[{'apiVersion':'tekton.dev/v1','kind':kind,'metadata':{'name':'probe','namespace':ns}}]}))
            (p/'objects').write_text(json.dumps([{'namespace':ns,'kind':kind,'name':'probe','tier':'C'}]))
            env=dict(os.environ, PROBE=d, MANAGER=manager, OP=op, ANNOTATIONS=json.dumps({'kubectl.kubernetes.io/last-applied-configuration':'{}'} if annotation else {}), KUBECTL=str(p/'kubectl'))
            if later is not None: env['LATER']=later
            if plural: env['CONFLICT_PREFIX']='error: Apply failed with 2 conflicts: conflicts with'
            r=subprocess.run(['sh',str(HELPER),mode,str(p/'render'),str(p/'objects')],env=env,capture_output=True,text=True)
            calls=[json.loads(s) for s in (p/'calls').read_text().splitlines()]
            return r, calls, json.loads((p/'objects').read_text())

    def test_embedded_helper_matches(self):
        import yaml
        pipeline = yaml.safe_load((HELPER.parent / 'pipeline.yaml').read_text())
        script = pipeline['spec']['tasks'][1]['taskSpec']['steps'][0]['script']
        embedded = script.split("<<'OWNERSHIP'\n", 1)[1].split('\nOWNERSHIP\n', 1)[0]
        self.assertEqual(embedded + '\n', HELPER.read_text())

    def test_migrate(self):
        for m in ('kubectl-client-side-apply','kubectl-last-applied','kubectl','kubectl-client-side-apply,kubectl-last-applied'):
            r,c,o=self.run_case(m)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(o[0]['ownership'],'migrate')
            self.assertTrue(any('--force-conflicts' in a for a in c))
            self.assertTrue(any(a[0]=='annotate' for a in c))

    def test_ssa(self):
        r,c,o=self.run_case('')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(o[0]['ownership'],'ssa')
        self.assertFalse(any('--force-conflicts' in a for a in c))

    def test_refuse(self):
        for kwargs in ({'manager':'foreign'}, {'manager':'kubectl-client-side-apply,foreign'}, {'manager':'kubectl','op':'Apply'}, {'manager':'kubectl','annotation':False}, {'manager':'kubectl-client-side-apply','ns':'other'}, {'manager':'kubectl-client-side-apply','kind':'ConfigMap'}, {'manager':'kubectl-client-side-apply','later':'foreign'}):
            r,c,_=self.run_case(**kwargs)
            self.assertNotEqual(r.returncode,0)
            self.assertFalse(any(a[0]=='apply' and '--dry-run=server' not in a for a in c))
            self.assertFalse(any('--force-conflicts' in a for a in c))

    def test_plural_conflict_from_real_kubectl(self):
        r, calls, objects = self.run_case('kubectl-client-side-apply', plural=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(objects[0]['ownership'], 'migrate')
        self.assertTrue(any('--force-conflicts' in call for call in calls))

    def test_plural_conflict_still_refuses_foreign_manager(self):
        for manager in ('foreign', 'kubectl-client-side-apply,foreign'):
            r, calls, _ = self.run_case(manager, plural=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse(any('--force-conflicts' in call for call in calls))
            self.assertFalse(any(call[0] == 'apply' and '--dry-run=server' not in call for call in calls))

    def test_plural_plan_is_read_only(self):
        r, calls, objects = self.run_case('kubectl-client-side-apply', plural=True, mode='plan')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(objects[0]['ownership'], 'migrate')
        self.assertTrue(any(call[0] == 'diff' and '--force-conflicts' in call for call in calls))
        self.assertFalse(any(call[0] == 'annotate' for call in calls))
        self.assertFalse(any(call[0] == 'apply' and '--dry-run=server' not in call for call in calls))
