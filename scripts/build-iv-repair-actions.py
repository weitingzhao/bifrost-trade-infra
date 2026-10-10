#!/usr/bin/env python3
"""Build private run_probe_pod payloads; do not submit or read credentials.

These run reviewed source as one-shot domain actions in existing images, without
release/rollout. Source and exact manifests are embedded; never mount a DB dump.
"""
import argparse
import hashlib
import json
from pathlib import Path

REUSE = {
    'reuse-goog': 'd9ead4c40e8125ce73c465050c123f611a232680a5f86f853b1e3764e33cd76c',
    'reuse-spx': '91fd5e9c777e0bd6b1eb7d2507231fad87b80bd616584c12bd87d85ec074b95b',
    'reuse-other': 'bb7eba2ae35a07e41dc6e80be67f50ee2b13f475f0c268c4fdcfb357042844be',
    'pilot-feature-keys': '4bf222572f710f875d7e5602bca8df7664049824f487d227c2982bfa0fea0094',
}
PILOT_DIGEST = '07abffb6f27ccdff7588c4c962fc8451968df314ec6ba0b70dda9799f342f789'


def capsule(modules):
    return f'''import importlib,sys,types
for fullname, source in {modules!r}:
    importlib.import_module(fullname.rsplit('.',1)[0])
    module=types.ModuleType(fullname)
    module.__file__='/tmp/'+fullname+'.py'
    sys.modules[fullname]=module
    exec(compile(source,module.__file__,'exec'),module.__dict__)
'''


def manifest(root, name, digest):
    content = (root/(name+'.csv')).read_bytes().decode('utf-8')
    if hashlib.sha256((root/(name+'.csv')).read_bytes()).hexdigest() != digest:
        raise ValueError('approved manifest changed: '+name)
    return content


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--research', type=Path, required=True)
    p.add_argument('--market-data', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    a = p.parse_args()
    modules = [(f'bifrost_research.{name}', (a.research/'src/bifrost_research'/path).read_text())
               for name,path in [('pricing.rates','pricing/rates.py'),
                                 ('engines.volatility.atm_repair','engines/volatility/atm_repair.py')]]
    for name,digest in REUSE.items():
        body = manifest(a.evidence, name, digest)
        code = capsule(modules) + f'''
import json
from pathlib import Path
from bifrost_research.db.conn import connect
from bifrost_research.engines.volatility.atm_repair import load_manifest,repair
path=Path('/tmp/approved.csv');path.write_text({body!r},newline='')
conn=connect()
try:
    report=repair(conn,load_manifest(path,{digest!r}),execute=True)
    conn.commit()
    report.pop('rows')
    print(json.dumps({{'status':'committed','manifest_sha256':{digest!r},**report}}))
finally:
    if not conn.closed:
        conn.rollback()
    conn.close()
'''
        packet = {'action':'run_probe_pod','reason':'TD-172 TD-142 approved exact '+name,
                  'params':{'namespace':'research','image':'192.168.10.73:30500/bifrost-research:0.205.0',
                            'env_from':'research-api','timeout_seconds':900,'command':['python','-c',code]}}
        (a.evidence/(name+'-action.json')).write_text(json.dumps(packet,indent=2))
    body = manifest(a.evidence,'approved-pilot-82',PILOT_DIGEST)
    source = (a.market_data/'src/bifrost_market_data/ingest/long_pilot.py').read_text()
    code = capsule([('bifrost_market_data.ingest.long_pilot',source)]) + f'''
import asyncio,json,os
from pathlib import Path
import psycopg2
from bifrost_market_data.config import load_config,postgres_connect_kwargs
from bifrost_market_data.ingest.long_pilot import PilotClient,load_pilot,run_pilot
# Probe env copies the writer, but does not mount its ConfigMap. Its known
# cluster port is 5432, not the LAN example's NodePort 30432.
os.environ['POSTGRES_PORT']='5432'
p=Path('/tmp/approved.csv');p.write_text({body!r},newline='')
requests=load_pilot(p,{PILOT_DIGEST!r})
cfg=load_config();conn=psycopg2.connect(**postgres_connect_kwargs(cfg,statement_timeout='20s'))
receipt=Path('/tmp/pilot-receipt.json')
async def run():
    key=os.environ.get('POLYGON_API_KEY') or os.environ.get('MASSIVE_API_KEY')
    async with PilotClient(key,tier='starter') as client:
        await run_pilot(conn,client,requests,receipt=receipt,lock=Path('/tmp/pilot.lock'))
try:
    asyncio.run(run())
finally:
    conn.close()
    if receipt.exists(): print(receipt.read_text())
'''
    packet = {'action':'run_probe_pod','reason':'TD-172 TD-142 approved 82 ranges / 120 target days',
              'params':{'namespace':'plugin-market-data','image':'192.168.10.73:30500/bifrost-market-data:0.87.1',
                        'env_from':'polygon-worker-options','timeout_seconds':900,'command':['python','-c',code]}}
    (a.evidence/'pilot-82-action.json').write_text(json.dumps(packet,indent=2))
    print('Prepared five private actions. Not submitted. Run reuse GOOG → SPX → other, reconcile, then pilot → pilot ATM keys.')


if __name__ == '__main__':
    main()
