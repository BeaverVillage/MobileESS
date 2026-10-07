"""Stored witness and 27-date compatibility; no optimizer or reruns."""
import gzip,pickle
import numpy as np,scipy.sparse as sp
from .common import *

def verify():
    from v42_pr134_b1.common import verify_freeze,valid_receipt,identity,STAGES
    freeze=read(PRODUCTION/'B1_PRODUCTION_FREEZE_MANIFEST.json');verify_freeze(freeze)
    old=read(CASE/'ORIGINAL_PRODUCTION_BYTE_MANIFEST.json');changed=[]
    for r in old['files']:
        p=Path(r['path'])
        if not p.exists() or sha(p)!=r['sha256']:changed.append(str(p))
    if changed:raise ValueError('OLD_PRODUCTION_BYTES_CHANGED:'+str(changed[:5]))
    checkpoint=read(PRODUCTION/'CHECKPOINT.json');passdays=[d for d,r in checkpoint['dates'].items() if r['status']=='PASS']
    if len(passdays)!=27:raise ValueError('EXACT_27_PASS_REQUIRED')
    receipts=[]
    for day in passdays:
        for stage in STAGES:
            saved=checkpoint['stages'][day+'/'+stage];path=Path(saved['receipt'])
            if sha(path)!=saved['sha256']:raise ValueError('CHECKPOINT_RECEIPT_SHA')
            r=read(path)
            if not valid_receipt(r,identity(freeze,day,stage),PRODUCTION):raise ValueError('CAUSAL_RECEIPT_SHA:'+day+':'+stage)
            receipts.append(dict(day=day,stage=stage,PASS=True,receipt=record(path)))
    # Raw accepted PR134 May01 witness and stored May01 production witness
    # are read-only regression evidence, not new solves.
    from v42_pr134_sc.build import replay
    source=ROOT/'.pr134_sc_local';a=sp.load_npz(source/'A0_MATRIX.npz');z=dict(np.load(source/'A0_ATTRIBUTES_CODED.npz'))
    point=dict(np.load(source/'ACCEPTED_POINT.npz'));x=point[next(iter(point))]
    accepted=replay(a,z,x)
    if not accepted['PASS']:raise ValueError('PR134_ACCEPTED_WITNESS_REGRESSION')
    del a,z,x
    day='2025-05-01';folder=PRODUCTION/'stages'/day/'A1'/'1'/'output'
    a=sp.load_npz(folder/'A0_MATRIX.npz');z=dict(np.load(folder/'A0_ATTRIBUTES_CODED.npz'))
    proof=dict(np.load(folder/'A2SC_PROOF.npz'));mapping=proof['mapping'] if 'mapping' in proof else np.cumsum(proof['mapping_delta'],dtype=np.int64)
    raw=dict(np.load(folder/'PASS_4_RAW_POINT.npz'))['values'];x=np.zeros(len(mapping));kept=mapping>=0;x[kept]=raw[mapping[kept]]
    current=replay(a,z,x)
    if not current['PASS']:raise ValueError('REPRESENTATIVE_CURRENT_PASS_REGRESSION')
    write('PASS27_REUSE_COMPATIBILITY.json',dict(PASS=True,dates=passdays,receipts=receipts,causal_PASS_receipts=len(receipts),
        preserved_manifest=record(CASE/'ORIGINAL_PRODUCTION_BYTE_MANIFEST.json'),old_files_verified=len(old['files']),old_files_changed=changed,
        existing_results_valid_under_unchanged_scientific_source=True,days_rerun=0,scientific_code_changed=False,
        source_commit=freeze['Git_SHA'],source_freeze=record(PRODUCTION/'B1_PRODUCTION_FREEZE_MANIFEST.json'),
        PR134_accepted_witness=accepted,representative_current_PASS_witness=current,
        raw_accepted_point=record(source/'ACCEPTED_POINT.npz'),raw_current_point=record(folder/'PASS_4_RAW_POINT.npz'),
        optimizer_calls=0,FreshAC_not_rerun=True,checkpoint_bytes_preserved=True))
    print('27 dates / 135 causal receipts bytes and PR134 + current witness replay PASS',flush=True)
if __name__=='__main__':verify()
