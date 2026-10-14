"""Independent CSR/Fraction certificate replay; no Gurobi or producer imports."""
from collections import defaultdict
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import re

import numpy as np
from scipy import sparse

from tools.verify_physical_global_lb import OriginalGeometry, compare_sparse

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/v42_b2_global_lb_alternative_research_20261014'
OLD=ROOT/'docs/v42_physical_global_lb_pilot'


def require(ok,why):
    if not ok:raise ValueError(why)


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))


def npz(p):
    with np.load(p,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def terms_dot(terms,x):return sum((F(a)*F(float(x[int(j)])) for j,a in terms.items()),F(0))


def local_bound(folder,original_exact,maximize,unit):
    """Only the solver global bound is trusted numerically; transport is exact."""
    folder=Path(folder);r=read(folder/'RESULT.json');d=npz(folder/'DATA.npz')
    old=npz(OLD/f'UNIT_{unit}_DATA.npz');axes=npz(OLD/f'UNIT_{unit}_AXES.npz')
    A=sparse.load_npz(folder/'A.npz').tocsr();B=sparse.load_npz(OLD/f'UNIT_{unit}_A.npz').tocsr()
    compare_sparse(A,B)
    require(np.array_equal(d['rhs'],old['rhs']) and np.array_equal(d['senses'],old['sense']) and
            np.array_equal(d['lb'],old['lower']) and np.array_equal(d['ub'],old['upper']) and
            np.array_equal(d['vtypes'],old['types']),'INDEPENDENT_LOCAL_DOMAIN_DRIFT')
    lookup={int(j):k for k,j in enumerate(axes['columns'])}
    exact={lookup[j]:a for j,a in original_exact.items() if j in lookup}
    require(np.array_equal(d['c'],np.array([float(exact.get(j,0)) for j in range(len(d['c']))])),
            'INDEPENDENT_OBJECTIVE_COEFFICIENT_DRIFT')
    require(r['status'] in (2,9,11) and read(folder/'READBACK.json')['PASS'],'NATIVE_STATUS_OR_READBACK')
    params=read(folder/'READBACK.json')['parameters']
    require(params['Threads']==1 and params['TimeLimit']<=30 and params['FeasibilityTol']==1e-9 and
            params['IntFeasTol']==1e-8,'ORIGINAL_PRECISION_OR_THREAD_DRIFT')
    correction=F(0)
    for j in set(exact)|set(map(int,np.flatnonzero(d['c']))):
        delta=exact.get(j,F(0))-F(float(d['c'][j]))
        lo,hi=delta*F(float(d['lb'][j])),delta*F(float(d['ub'][j]))
        correction+=(max if maximize else min)(lo,hi)
    require(str(correction)==r['rounding_correction'],'INDEPENDENT_OBJECTIVE_OUTWARD_ERROR')
    result=F(float(r['Global_Bound']))+correction
    require(str(result)==r['exact_corrected_bound'],'INDEPENDENT_GLOBAL_BOUND_TRANSPORT')
    # Existing local incumbent validates a witness, not the universal theorem.
    if (folder/'POINT.npz').exists():
        x=npz(folder/'POINT.npz')['point'];residual=A@x-d['rhs']
        violation=np.where(d['senses']=='=',abs(residual),np.where(d['senses']=='<',residual,-residual))
        require(max(violation)<=1e-6 and np.all(x>=d['lb']-1e-8) and np.all(x<=d['ub']+1e-8),'LOCAL_WITNESS_REPLAY')
        require(np.max(abs(x[d['vtypes']=='B']-np.rint(x[d['vtypes']=='B'])))<=1e-8,'LOCAL_INTEGER_WITNESS_REPLAY')
    return result


def verify():
    audit=read(OUT/'SOURCE_CASE_MATRIX_IDENTITY_AUDIT.json');require(audit['PASS'],'SOURCE_CASE_GATE')
    for record in audit['protected_files']:require(sha(record['path'])==record['sha256'],'PROTECTED_FILE_DRIFT')
    current=Path(audit['protected_files'][0]['path']).parent
    A=sparse.load_npz(current/'FULL_A.npz').tocsr();d=npz(current/'FULL_DATA.npz')
    geometry=OriginalGeometry(A,d);rho=list(d['names']).index('rho_max')
    catalog=read(OUT/'ORIGINAL_AFFINE_ROW_CATALOG.json')['rows'];original={}
    for k,p in catalog.items():
        i=int(k)
        if p['thermal']:
            constant,terms=geometry.thermal(i,rho)
        else:
            constant=-F(float(d['rhs'][i]));terms=defaultdict(F)
            sign=F(1 if d['sense'][i]=='<' else -1)
            constant*=sign
            begin,end=A.indptr[i:i+2]
            for j,a in zip(A.indices[begin:end],A.data[begin:end]):
                offset,leaves=geometry.expand(int(j));weight=sign*F(float(a));constant+=weight*offset
                for c,v in leaves.items():terms[c]+=weight*v
            terms={c:v for c,v in terms.items() if v}
        require(str(constant)==p['constant'] and {str(j):str(v) for j,v in terms.items()}==p['terms'],
                'THIRD_INDEPENDENT_ORIGINAL_ROW_DERIVATION')
        original[i]=(constant,terms)
    history=read(OUT/'LAGRANGIAN_LOCAL_SUBPROBLEM_CERTIFICATES.json')['evaluations'];evaluations=[]
    for p in history:
        w={int(k):F(v) for k,v in p['weights'].items()};mu={int(k):F(v) for k,v in p['mu'].items()}
        require(sum(w.values())==1 and all(v>=0 for v in w.values()) and all(v>=0 for v in mu.values()),'WEIGHT_CONE')
        exact=defaultdict(F);constant=F(0)
        for k,v in list(w.items())+list(mu.items()):
            require(catalog[str(k)]['thermal']==(k in w),'WEIGHT_FAMILY_MIX')
            c,t=original[k];constant+=v*c
            for j,a in t.items():exact[j]+=v*a
        exact={j:a for j,a in exact.items() if a}
        lower=constant
        for local in p['local']:
            if 'cached_from' in local:
                require(sha(local['cached_from'])==local['cached_sha'],'CACHED_BOUND_SHA')
                r=read(local['cached_from']);value=F(r['certified_LB_exact'])
                require(read(OLD/'INDEPENDENT_CERTIFICATE.json')['PASS'],'CACHED_INDEPENDENT_CERTIFICATE')
            else:
                require(sha(Path(local['path'])/'RESULT.json')==local['result_sha'],'LOCAL_RECEIPT_SHA')
                value=local_bound(local['path'],exact,False,local['unit'])
            require(str(value)==local['exact_LB'],'LOCAL_CERTIFICATE_RECALCULATION')
            lower+=value
        require(str(lower)==p['exact_LB'] and str(constant)==p['constant'],'LAGRANGIAN_INDEPENDENT_AGGREGATION')
        evaluations.append(dict(evaluation=p['evaluation'],exact_LB=str(lower),PASS=True))
    cuts=read(OUT/'MULTIPERIOD_HULL_CUT_CERTIFICATES.json')['certificates'];cut_checks=[]
    point=npz(OUT/'ORIGINAL_ROOT_POINT.npz')['point']
    from tools.critical_grid_cg.verify import CompactMap
    base=ROOT/'docs/v42_b2_root_lp_tightening/base';bd=npz(base/'LP_DATA.npz')
    mapping=CompactMap(current,npz(base/'LP_AXES.npz')['columns'],bd['names'])
    for ordinal,p in enumerate(cuts):
        terms=defaultdict(F)
        # Derive objective from signed original rows, not the exported candidate.
        for k,row in catalog.items():
            if row['thermal'] and row['slot'] in p['window'] and re.match(r'line_thermal_face\[\d+,26,1\]',row['name']):
                for j,v in original[int(k)][1].items():
                    name=str(d['names'][j])
                    if name.split('[',1)[1].split(',',1)[0]==p['unit']:terms[j]-=v/F(p['size'])
        terms={j:a for j,a in terms.items() if a}
        require({str(j):str(a) for j,a in terms.items()}==p['terms'],'SUPPORT_WINDOW_ORIGINAL_OBJECTIVE')
        folder=OUT/'B'/f'SUPPORT_{ordinal}_{p["unit"]}'
        upper=local_bound(folder,terms,True,p['unit'])
        require(str(upper)==p['Global_Upper_Bound'],'SUPPORT_UPPER_CERTIFICATE')
        violation=terms_dot(terms,point)-upper
        require(str(violation)==p['root_violation_exact'],'INDEPENDENT_ROOT_VIOLATION')
        cut=p['transport'];rhs,_,compact=mapping.row(upper,F(0),terms)
        error=F(0)
        for j,a in compact.items():
            delta=F(float(a))-a
            error+=max(delta*F(float(bd['lb'][j])),delta*F(float(bd['ub'][j])))
        require(str(rhs)==cut['compact_rhs'] and str(error)==cut['coefficient_error_upper'] and
                F(cut['native_rhs'])>=rhs+error,'CUT_ALIAS_OUTWARD_TRANSPORT')
        for inc in read(OUT/'CURRENT_FULL_INCUMBENT_REPLAY.json')['incumbents']:
            require(terms_dot(terms,npz(inc['original_path'])['point'])<=upper,'FULL_MOVING_INCUMBENT_REPLAY')
        cut_checks.append(dict(ordinal=ordinal,PASS=True,accepted=p['accepted'],root_violation_exact=str(violation)))
    final=read(OUT/'FINAL_GLOBAL_LB_REGISTRY.json');ub=read(OUT/'B2_CURRENT_UB_LB_REGISTRY.json')
    require(F(final['exact_LB'])<=F(ub['exact_UB']),'FINAL_LB_ABOVE_UB')
    ledger=read(OUT/'NATIVE_RUNTIME_BUDGET_LEDGER.json')
    require(ledger['inflight'] is None and not ledger['STOP'],'LEDGER_INFLIGHT_OR_STOP')
    total=sum(F(float(c['Native_Runtime'])) for c in ledger['calls'])
    require(float(total)==ledger['research_Native_Runtime'] and float(total)+ledger['prefix_Native_Runtime']<=1800 and total<=600,
            'CUMULATIVE_MEASURED_RUNTIME')
    for algorithm,cap in (('A',360),('B',240)):
        require(sum(F(float(c['Native_Runtime'])) for c in ledger['calls'] if c['algorithm']==algorithm)<=cap,'ALGORITHM_RUNTIME_CAP')
    packet=dict(PASS=True,binding=audit['binding'],original_rows_independently_rederived=len(original),
                Lagrangian_evaluations=evaluations,support_certificates=cut_checks,
                FULL_incumbents_replayed=len(read(OUT/'CURRENT_FULL_INCUMBENT_REPLAY.json')['incumbents']),
                measured_Native_Runtime=float(total),exact_validity_and_transport=True,exact_BB_proof_trace=False,
                Native_optimize_calls=0,Gurobi_imported=False,solver_bound_trust='Original numerical Gurobi global-bound contract only')
    (OUT/'INDEPENDENT_FINAL_CERTIFICATION.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('INDEPENDENT_CERTIFICATION_PASS',len(evaluations),len(cut_checks),float(total))


if __name__=='__main__':verify()
