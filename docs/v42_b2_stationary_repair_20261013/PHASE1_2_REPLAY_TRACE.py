"""Archived-case binding regression and native readback; no Optimize or UB adoption."""
from pathlib import Path
from types import SimpleNamespace
import json,sys,gc
import numpy as np
from scipy import sparse
from v42_pr134_b1.common import read,atomic,record,sha
from v42_may_final.pr221 import current_axes,pcs_context,rebound
from v42_bootstrap.m1 import native_inputs

ROOT=Path('D:/v42_b2_stationary_diagnosis_20261013')
ROOT.mkdir(exist_ok=True)
day=sys.argv[1]
old=Path('D:/v42_may_joint_repair_campaign_20261013')
folder=old/'dates/B2'/day/'attempts/attempt_01/output'
out=ROOT/'binding_regression'/day;out.mkdir(parents=True,exist_ok=True)
def arrays(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
d=arrays(folder/'DENSE_RESPONSE_DATA.npz');original=arrays(folder/'FULL_DATA.npz')
A=sparse.load_npz(folder/'DENSE_RESPONSE_A.npz').tocsr();full=sparse.load_npz(folder/'FULL_A.npz').tocsr()
bundle=read(old/'inputs/B2'/day/'NATIVE_INPUT.json')
sites,initial,routes,battery,receipt=native_inputs(bundle)
graph=(sites,initial,[(s,t,s,t+1,None) for s in sites for t in range(96)]+
    [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)],battery,receipt)
identity=read(folder/'SCIENTIFIC_CASE_IDENTITY.json')
aliases=read(folder/'CURRENT_C2_ALIASES.json')
with np.load(folder/'CURRENT_C2_AXES.npz') as z:columns=z['columns'].copy()
n=max(full.shape[1],max(map(int,columns))+1,max(p['column'] for p in aliases)+1)
def lift(point):
    x=np.zeros(n);x[columns]=point[:len(columns)]
    for p in reversed(aliases):x[p['column']]=p['constant']+sum(w*x[int(k)] for k,w in p['terms'].items())
    return x[:full.shape[1]].copy()
case=SimpleNamespace(A=A,d=d,original_A=full,original_d=original,graph=graph,
    case_sha=identity['case_sha'],identity=identity,aliases=aliases,selected_columns=columns,lift=lift)
with np.load(folder/'PR221/INITIAL_POINT.npz') as z:point=z['point'].copy()
axes=current_axes(case);context=pcs_context(case)
atomic(out/'CURRENT_CASE_AXES.json',axes);atomic(out/'SIGNED_SELECTION_CONTEXT.json',context)

from v42_m1_hybrid.final_verify import _strict_ub
warm=ROOT/'PR220/calls/008_R2_LATE_SMALL/native/FINAL_RAW.npz'
assert sha(warm)=='3f3314b0ca9235ffeff02e3d4bdaab97477f4390992fddbd486a047ebd62d686'
from unittest.mock import patch
import v42_m1_hybrid.final_verify as fv
with patch.object(fv,'ROOT',ROOT):verified=_strict_ub(case,warm,{})
assert verified['PASS'] and verified['Global_UB']==0.5398310226338695
atomic(ROOT/'PR220_CURRENT_MAY01_FULL_REPLAY.json',verified)
from tools.minimax_beam1800.adapter import current_paths
from tools.global_local_multistart1800.joint import path_signature
with np.load(warm) as z:wp=z['point'].copy()
paths=current_paths(case,wp)
winning=paths['MESS03'];sig=path_signature(winning)
rows=[]
for filename in ['ADAPTIVE_BEAM_EPOCH_00.json','BEAM_RESERVOIR.json']:
 q=read(folder/'PR221'/filename)
 source=q['all_generated_candidates']['MESS03'] if 'all_generated_candidates' in q else q['units']['MESS03']
 rows.append(dict(stage=filename,exists=sig in source,count=len(source)))
for p in sorted((folder/'PR221').glob('ADAPTIVE_POOL_*.json')):
 q=read(p);rows.append(dict(stage=p.name,exists=winning in q['pools']['MESS03'],count=len(q['pools']['MESS03'])))
atomic(ROOT/'PR220_PATH_PRODUCTION_TRACE.json',dict(PASS=True,signature=sig,path=winning,paths=paths,stages=rows,
 production_RAW_REL_replaced_with_initial_STAY=True,legacy_May01_pool_removed=True,Native_optimize_calls=0))
print('FULL_REPLAY',verified['PASS'],verified['Global_UB']);print('WINNING_PATH_TRACE',rows)
