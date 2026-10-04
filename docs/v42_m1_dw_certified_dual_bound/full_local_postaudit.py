"""Read-only original unreduced pricing-row audit after all heavy work ends."""
import sys
sys.path.insert(0,sys.argv[1])
from v42_dw_bound.common import *
from v42_dw_resume.audit import corrected_rows,pure_binary_equalities
from v42_dw_root.partition import axes
from v42_degen.identity import inputs
import numpy as np
gate('postterminal_full_local');assert (OUT/'DW_FINAL_RESULT.json').exists()
A,d,B,e,*_=inputs();owner,row_owner=axes();row_units=np.full(A.shape[0],-1,dtype=np.int8)
for i in range(A.shape[0]):
    deps=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
    if len(deps)==1 and -1 not in deps:row_units[i]=next(iter(deps))
models={}
for m in range(4):
    rr=np.flatnonzero(row_units==m);cc=np.flatnonzero(owner==m)
    attrs=dict(d,rhs=d['rhs'][rr],sense=d['sense'][rr],lower=d['lower'][cc],upper=d['upper'][cc],types=d['types'][cc],objective=d['objective'][cc],constant=np.array(0.))
    matrix=A[rr][:,cc];models[m]=(matrix,attrs,pure_binary_equalities(matrix,attrs),cc)
checks=[]
for price in ledger('DW_OPTIMAL_PRICING_LEDGER.csv',OUT):
    r=read(OUT/price['receipt'])
    if not r['point_file']:continue
    matrix,attrs,mask,cc=models[UNITS.index(price['MESS'])]
    with np.load(OUT/r['point_file']) as z:
        assert np.array_equal(cc,z['axis']);raw=corrected_rows(matrix,attrs,z['x'],True,mask)
    if price['valid_bound']=='True':assert raw['PASS'],price['call']
    checks.append(dict(call=int(price['call']),MESS=price['MESS'],bound_was_certified=price['valid_bound']=='True',PASS=raw['PASS'],full_original_local_rows=matrix.shape[0],max_violation=raw['max_constraint_violation'],point_SHA=sha(OUT/r['point_file'])))
write('FULL_ORIGINAL_LOCAL_PRICING_POSTAUDIT.json',dict(PASS=all(c['PASS'] for c in checks if c['bound_was_certified']),checks=checks,optimization_calls=0,repair_calls=0,affine_tolerance=POST,bounds_route_tolerance=EPS))
for name,prefix in [('DW_RMP_WARMSTART_AUDIT.json','RMP'),('DW_PRICING_WARMSTART_AUDIT.json','PRICE')]:
    audit=read(OUT/name)
    for hint in audit['hints']:
        identifier=hint['iteration'] if prefix=='RMP' else hint['call']
        files=list((OUT/'logs').glob(f'{prefix}_{identifier:04d}*.log'))
        log=files[0].read_text(encoding='utf8',errors='replace') if files else ''
        evidence=[line for line in log.splitlines() if 'warm-start' in line.lower() or 'mip start' in line.lower()]
        hint['native_log_start_evidence']=evidence
        hint['native_basis_acceptance']='CONFIRMED_USE_BASIS' if any('use basis' in x.lower() for x in evidence) else 'EXPLICITLY_DISCARDED' if any('discard basis' in x.lower() for x in evidence) else 'NO_HINT_SUPPLIED' if prefix=='RMP' and not hint['basis_supplied'] else 'NOT_EXPLICITLY_REPORTED'
        if prefix=='PRICE':hint['native_MIP_start_solution_confirmed']=any('loaded user mip start' in x.lower() or 'produced solution' in x.lower() for x in evidence)
    audit['postterminal_log_evidence_readonly']=True;write(name,audit)
print('FULL_ORIGINAL_LOCAL_PRICING_PASS',len(checks))
