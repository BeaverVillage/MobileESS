"""Exact user-authorized code successor, never a blanket preservation bypass."""
import subprocess,hashlib
from .common import *

CHANGES=frozenset(('v42_bootstrap/grid.py','v42_boundary/model.py','v42_capacity/electrical.py',
    'v42_compact/native.py','v42_holdout/planning.py','v42_m1_sparse/grid.py','v42_may01/prepare.py',
    'v42_native/actual.py','v42_native/grid.py','v42_regcontrol/authority.py','v42_regcontrol/runner.py',
    'v42_temporal/native.py','v42_voltage/grid.py','v42_voltage/preservation.py'))

def assert_successor(path,current_sha,previous_sha=None):
    p=OUT/'AUTHORIZED_THERMAL_SUPERSESSION.json'
    if path not in CHANGES or not p.is_file():return False
    manifest=read(p)
    assert manifest['exact_base']==BASE and manifest['schema']==SCHEMA
    assert manifest['scientific_model_changed'] and manifest['old_M1_certificates_superseded']
    assert not manifest['M1_production_execution_authorized']
    row=next(r for r in manifest['files'] if r['path']==path)
    assert current_sha==row['current_sha256'],'UNSEALED_THERMAL_SUCCESSOR:'+path
    original=subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)
    assert hashlib.sha256(original).hexdigest()==row['base_sha256'],'THERMAL_BASE_SHA:'+path
    if previous_sha is not None:assert previous_sha in row['historical_sha256'],'THERMAL_HISTORICAL_SHA:'+path
    return True

def seal():
    rows=[]
    for name in sorted(CHANGES):
        base=subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT)
        # Bind inherited checkout hashes to actual ancestor Git blobs and their
        # exact LF/CRLF variants. Do not grant unverified historical digests.
        commits=subprocess.check_output(['git','log','--format=%H',BASE,'--',name],cwd=ROOT,text=True).splitlines()
        history=set()
        for ref in commits:
            data=subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT)
            lf=data.replace(b'\r\n',b'\n')
            history.update(hashlib.sha256(v).hexdigest() for v in (data,lf,lf.replace(b'\n',b'\r\n')))
        lf=base.replace(b'\r\n',b'\n');history.update(hashlib.sha256(v).hexdigest() for v in (base,lf,lf.replace(b'\n',b'\r\n')))
        rows.append(dict(path=name,base_sha256=hashlib.sha256(base).hexdigest(),current_sha256=sha(ROOT/name),
            historical_sha256=sorted(history),history_source='exact ancestor Git blobs, LF/CRLF variants'))
    write(OUT,'AUTHORIZED_THERMAL_SUPERSESSION.json',dict(exact_base=BASE,schema=SCHEMA,
        authorization='Explicit user attachment 53d84771-cfc3-4b7c-ae5a-f7b396182599, sections 1/3/7/12',
        scientific_model_changed=True,old_M1_certificates_superseded=True,M1_production_execution_authorized=False,
        preserved_evidence_requires_exact_parent_bytes=True,files=rows))
    print('Sealed exact thermal successor code',len(rows),flush=True)

if __name__=='__main__':seal()
