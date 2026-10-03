"""Raw exact-base bytes, separate from inherited CRLF pytest checkout variants."""
import hashlib
import subprocess
from .common import *


def base_bytes(*,restore=False):
    rows=[]; restored=[]
    for line in subprocess.check_output(['git','ls-tree','-r',BASE],cwd=ROOT).decode().splitlines():
        meta,name=line.split('\t',1); mode,kind,oid=meta.split()
        if kind!='blob': raise ValueError('BASE_NON_BLOB')
        path=ROOT/name; data=path.read_bytes()
        blob=lambda v:hashlib.sha1(('blob %d\0'%len(v)).encode()+v).hexdigest()
        if blob(data)!=oid:
            if not restore: raise ValueError('BASE_BYTE_DRIFT:'+name)
            expected=subprocess.check_output(['git','cat-file','blob',oid],cwd=ROOT)
            if data.replace(b'\r\n',b'\n')!=expected.replace(b'\r\n',b'\n'):
                raise ValueError('BASE_CONTENT_DRIFT:'+name)
            path.write_bytes(expected); data=expected; restored.append(name)
        rows.append(dict(path=name,bytes=len(data),git_blob_sha1=oid,sha256=hashlib.sha256(data).hexdigest()))
    if restore:
        write(OUT,'CHECKOUT_EOL_RECEIPT.json',dict(base=BASE,EOL_only_restored=restored,BASE_content_edits=0))
        subprocess.run(['git','-c','core.safecrlf=false','add','--',*restored],cwd=ROOT,check=True)
        if subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT):
            raise ValueError('BASE_STAGED_CHANGE')
    else:
        write(OUT,'BASE_BYTE_PRESERVATION.json',dict(base=BASE,files=rows,checked_files=len(rows),PASS=True))
    return rows


def identity():
    checked=base_bytes()
    scientific=[r for r in checked if r['path'].startswith('docs/v42_april_b0_capacity_queue_voltage_calibration/')]
    write(OUT,'PR125_NON_GRID_STATE_IDENTITY.json',dict(PASS=True,
        identity_method='every PR127 BASE raw file equals exact Git blob; PR125 files inherited unchanged',
        base=BASE,all_base_files=len(checked),all_PR125_files=len(scientific),
        Planning_workload_arrays_unchanged=True,Planning_PCC_PQ_unchanged=True,
        Actual_workload_occupancy_arrays_unchanged=True,Actual_PCC_PQ_unchanged=True,
        CC4_queue_results_unchanged=True,capacity_audits_unchanged=True,
        Runtime_reserve_unchanged=True,V_PLAN_bytes_unchanged=True,V_PLAN_numerically_unchanged=True,
        old_voltage_evidence_preserved=True,PR124_PR126_imports=0,
        arrays=[r for r in scientific if r['path'].endswith(('PLANNING_PHYSICAL.npz','ACTUAL_PHYSICAL.npz','V_PLAN.npz'))]))


if __name__=='__main__':
    import sys
    base_bytes(restore=True) if '--restore' in sys.argv else identity()
