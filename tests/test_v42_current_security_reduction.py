"""Fresh PR160/161 certificate attacks and fractional LP equivalence."""
from copy import deepcopy
from fractions import Fraction
from types import SimpleNamespace
import numpy as np
import pytest
from scipy import sparse
from scipy.optimize import linprog
from test_v42_current_exact_c3a import fixture
from v42_supercompact.formulation import Compact
from v42_supercompact.presolve import Presolve
from v42_may_campaign_native90.m_model import verify_transport
from v42_ultracompact.security import prepare_current_security
from v42_ultracompact.security_verify import verify_current_security

def case():
    _,graph,old,_=fixture();A,d=old.original,old.original_data
    names=list(map(str,d['names']))+[f'SOC[MESS01,{t}]' for t in range(3)]+['response_tail[1,0]']
    positions={n:j for j,n in enumerate(names)};n=len(names)
    A=sparse.hstack([A,sparse.csr_matrix((A.shape[0],4))],format='csr')
    rows=[];labels=[];rhs=[];sense=[]
    def add(terms,value,sg,label):
        rows.append({positions[k]:w for k,w in terms.items()});labels.append(label);rhs.append(value);sense.append(sg)
    for t in range(2):
        terms={f'SOC[MESS01,{t}]':-1,f'SOC[MESS01,{t+1}]':1}
        for name in names:
            if name.startswith(('Pch[','Pdis[')) and name.endswith(f',{t}]'):
                terms[name]=-.25 if name.startswith('Pch[') else .25
        if t==0:terms['arc[MESS01,4]']=1.
        add(terms,0,'=','energy_balance')
    add({'SOC[MESS01,0]':1},500,'=','initial_SOC');add({'SOC[MESS01,2]':1},500,'=','terminal_SOC')
    add({'response_line_P[0,0]':1},450,'<','line_thermal_face[0,0,0]')
    add({'response_line_P[0,0]':1},1,'<','voltage_upper[0,0]')
    add({'response_line_P[1,0]':1},500,'<','NormalAmps[1,0]')
    add({'response_tail[1,0]':1,'response_line_P[1,0]':-.5},3,'=','response_tail_binding[1,0]')
    rr=[];cc=[];vv=[]
    for i,v in enumerate(rows):
        for j,w in v.items():rr.append(i);cc.append(j);vv.append(w)
    A=sparse.vstack([A,sparse.csr_matrix((vv,(rr,cc)),shape=(len(rows),n))],format='csr')
    d=dict(d,names=np.asarray(names),types=np.r_[d['types'],np.full(4,'C')],
        lower=np.r_[d['lower'],np.zeros(3),-np.inf],upper=np.r_[d['upper'],np.full(3,1000.),np.inf],
        objective=np.r_[d['objective'],np.zeros(4)],rhs=np.r_[d['rhs'],rhs],
        sense=np.r_[d['sense'],sense],row_names=np.r_[d['row_names'],labels])
    graph=(*graph[:3],SimpleNamespace(p_limit=300.,pcs_kva=400.),{})
    compact=Compact(A,d,graph[2],graph[1],2);pre=prepare_current_security(compact,graph);pre['battery']=graph[3]
    p=Presolve(compact.A,dict(compact.d,lower=pre['lower'],upper=pre['upper']));p.current_security=pre
    p.bound.extend(pre['bounds']);p.row_delete({q['row'] for q in pre['certificates']},pre['certificates']);p.run()
    return compact,p,graph

def native_case():
    _,graph,old,_=fixture();A,d=old.original,old.original_data
    extra=[f'injection_{f}[{s},{t}]' for s in graph[0] for t in range(2) for f in ('P','Q')]
    names=list(map(str,d['names']))+extra;pos={n:j for j,n in enumerate(names)}
    A=sparse.hstack([A,sparse.csr_matrix((A.shape[0],len(extra)))],format='lil')
    for i,n in enumerate(d['row_names']):
        if not str(n).startswith('response_line_P_binding'):continue
        t=int(str(n).split('[',1)[1].split(',')[0]);terms={pos[f'response_line_P[{t},0]']:1.}
        for s in graph[0]:
            if f'Pdis[MESS01,{s},{t}]' in pos:terms[pos[f'injection_P[{s},{t}]']]=-.25
            if f'Q[MESS01,{s},{t}]' in pos:terms[pos[f'injection_Q[{s},{t}]']]=-.125
        A.rows[i]=sorted(terms);A.data[i]=[terms[j] for j in sorted(terms)]
    rows=[];rhs=[];senses=[];labels=[]
    for name in extra:
        f=name.split('[',1)[0];site,t=name.split('[',1)[1][:-1].split(',');terms={pos[name]:1.}
        for prefix,weight in ([('Q',-1.)] if f=='injection_Q' else [('Pch',1.),('Pdis',-1.)]):
            n=f'{prefix}[MESS01,{site},{t}]'
            if n in pos:terms[pos[n]]=weight
        rows.append(terms);rhs.append(0.);senses.append('=');labels.append(f'{f}_binding[{site},{t}]')
    for t,f,value in ((0,'line_thermal_face',450.),(0,'voltage_upper',1.),(1,'NormalAmps',500.)):
        rows.append({pos[f'response_line_P[{t},0]']:1.});rhs.append(value);senses.append('<');labels.append(f'{f}[{t},0]')
    rr=[];cc=[];vv=[]
    for i,row in enumerate(rows):
        for j,w in row.items():rr.append(i);cc.append(j);vv.append(w)
    A=sparse.vstack([A.tocsr(),sparse.csr_matrix((vv,(rr,cc)),shape=(len(rows),len(names)))],format='csr')
    k=len(extra);d=dict(d,names=np.asarray(names),types=np.r_[d['types'],np.full(k,'C')],lower=np.r_[d['lower'],np.full(k,-np.inf)],
        upper=np.r_[d['upper'],np.full(k,np.inf)],objective=np.r_[d['objective'],np.zeros(k)],
        rhs=np.r_[d['rhs'],rhs],sense=np.r_[d['sense'],senses],row_names=np.r_[d['row_names'],labels])
    compact=Compact(A,d,graph[2],graph[1],2);pre=prepare_current_security(compact,graph);pre['battery']=graph[3]
    p=Presolve(compact.A,dict(compact.d,lower=pre['lower'],upper=pre['upper']));p.current_security=pre
    p.bound.extend(pre['bounds']);p.row_delete({q['row'] for q in pre['certificates']},pre['certificates']);p.run()
    return compact,p,graph

def test_pr160_sparse_site_path_has_independent_elementary_interval_replay():
    compact,p,_=native_case();pre=p.current_security
    assert pre['summary']['support_implementation']=='PR160_CERTIFIED_SPARSE_SITE_PQ'
    proof=verify_transport(compact,p)
    assert proof['PASS'] and proof['pre_C2_security_independent_proof']['removed_rows']==2
    assert all(q['arithmetic']=='PR160_CERTIFIED_SPARSE_SITE_PQ' for q in pre['certificates'])
    assert 'response_line_P[1,0]' not in p.d['names']
    off=p.inverse(np.zeros(p.A.shape[1]));T=np.column_stack([p.inverse(np.eye(p.A.shape[1])[j])-off for j in range(p.A.shape[1])])
    objective=np.arange(compact.A.shape[1],dtype=float)/8
    assert _lp(compact.A,compact.d,objective)==pytest.approx(_lp(p.A,p.d,objective@T)+float(objective@off),abs=1e-8)

@pytest.mark.parametrize('attack',('underclaim','injection','response','metadata','source','pcs'))
def test_sparse_site_path_rejects_mutated_certificates_and_coefficients(attack):
    compact,p,_=native_case();compact,p=deepcopy((compact,p));pre=p.current_security
    if attack=='underclaim':
        q=pre['certificates'][0];q['certified_upper_bound']=0.;q['slack']=q['rhs']
    elif attack in ('injection','response'):
        prefix='injection_P_binding[A,0]' if attack=='injection' else 'response_line_P_binding[0'
        i=next(i for i,n in enumerate(compact.d['row_names']) if str(n).startswith(prefix));a,b=compact.A.indptr[i:i+2]
        k=next(k for k in range(a,b) if str(compact.d['names'][compact.A.indices[k]]).startswith('Pdis[' if attack=='injection' else 'injection_P['))
        compact.A.data[k]*=2
    elif attack=='metadata':pre['certificates'][0]['family']='voltage_lower'
    elif attack=='source':
        q=next(q for q in pre['bounds'] if q['proof']=='CURRENT_EXACT_SOURCE_FLOW_NODE');q['new_lower']=q['new_upper']+1
    else:
        i=next(i for i,n in enumerate(compact.original_data['row_names']) if n=='PCS16');compact.original.data[compact.original.indptr[i]]*=2
    with pytest.raises(ValueError,match='CURRENT_'):verify_current_security(compact,p)

def test_fresh_security_removes_only_proven_rows_and_newly_unconsumed_aux():
    compact,p,graph=case();proof=verify_transport(compact,p)
    assert proof['PASS']
    assert {q['family'] for q in p.current_security['certificates']}=={'line_thermal_face','NormalAmps'}
    assert any(str(n).startswith('voltage_upper') for n in p.d['row_names'])
    assert any(q['kind']=='UNCONSUMED_AFFINE_AUXILIARY' for q in p.steps)
    assert 'response_line_P[1,0]' not in p.d['names']
    assert p.current_security['summary']['SOC_aggregate_bounds_used_for_site_union_deletions'] is False
    assert all(q['new_lower']==q['new_upper'] for q in p.current_security['bounds'] if q['proof']=='CURRENT_EXACT_SOURCE_FLOW_NODE')
    assert any(q['name']=='SOC[MESS01,1]' and q['new_lower']==425 and q['new_upper']==575 for q in p.current_security['bounds'])

def _lp(A,d,objective):
    eq=d['sense']=='=';le=d['sense']=='<';gt=d['sense']=='>';ub=sparse.vstack([A[le],-A[gt]],format='csr')
    result=linprog(objective,A_ub=ub,b_ub=np.r_[d['rhs'][le],-d['rhs'][gt]],A_eq=A[eq],b_eq=d['rhs'][eq],
        bounds=list(zip(d['lower'],d['upper'])),method='highs')
    assert result.success,result.message
    return result.fun

def test_original_and_reduced_fractional_lp_optima_agree():
    compact,p,_=case();assert verify_transport(compact,p)['PASS']
    # This exact affine map transports arbitrary original objectives, including
    # the response eliminated after security proofs. The domain comparison
    # includes fractional routing; no operational point proves redundancy.
    off=p.inverse(np.zeros(p.A.shape[1]));T=np.column_stack([p.inverse(np.eye(p.A.shape[1])[j])-off for j in range(p.A.shape[1])])
    rng=np.random.default_rng(42)
    for _ in range(4):
        objective=np.zeros(compact.A.shape[1]);objective[:compact.n]=rng.normal(size=compact.n)
        before=_lp(compact.A,compact.d,objective);after=_lp(p.A,p.d,objective@T)+float(objective@off)
        assert before==pytest.approx(after,rel=1e-10,abs=1e-8)

def test_weighted_recursive_auxiliary_lift_satisfies_original_equalities_exactly():
    compact,p,_=case();assert verify_transport(compact,p)['PASS']
    y=np.arange(p.A.shape[1],dtype=float)/8;x=p.inverse(y)
    steps=[q for q in p.steps if q['kind']=='UNCONSUMED_AFFINE_AUXILIARY']
    assert len(steps)==2
    tail=next(q for q in steps if q['name']=='response_tail[1,0]')
    line=next(q for q in steps if q['name']=='response_line_P[1,0]')
    assert tail['terms']=={str(line['column']):.5}
    assert Fraction(float(x[tail['column']]))==3+Fraction(1,2)*Fraction(float(x[line['column']]))
    for step in steps:
        i=step['defining_row'];a,b=compact.A.indptr[i:i+2]
        value=sum((Fraction(float(w))*Fraction(float(x[j])) for j,w in zip(compact.A.indices[a:b],compact.A.data[a:b])),Fraction(0))
        assert value==Fraction(float(compact.d['rhs'][i]))

@pytest.mark.parametrize('attack',('underclaim','rhs','coefficient','pcs','soc','source','missing_bound','initial_domain'))
def test_independent_security_replay_rejects_mutations(attack):
    compact,p,_=case();compact,p=deepcopy((compact,p));pre=p.current_security
    if attack=='underclaim':
        q=pre['certificates'][0];q['certified_upper_bound']=0.;q['slack']=q['rhs']
    elif attack=='rhs':pre['certificates'][0]['rhs']='0'
    elif attack=='coefficient':
        i=next(i for i,n in enumerate(compact.d['row_names']) if str(n).startswith('response_line_P_binding[0'))
        a,b=compact.A.indptr[i:i+2]
        k=next(k for k in range(a,b) if str(compact.d['names'][compact.A.indices[k]]).startswith('Pdis['))
        compact.A.data[k]*=2
    elif attack=='pcs':
        i=next(i for i,n in enumerate(compact.original_data['row_names']) if n=='PCS16');compact.original.data[compact.original.indptr[i]]*=2
    elif attack in ('soc','source'):
        kind='CURRENT_EXACT_SOC_ENDPOINT_ENVELOPE' if attack=='soc' else 'CURRENT_EXACT_SOURCE_FLOW_NODE'
        q=next(q for q in pre['bounds'] if q['proof']==kind);q['new_lower']=q['new_upper']+1
    elif attack=='missing_bound':pre['bounds'].pop()
    else:p.initial_d['objective']=p.initial_d['objective'].copy();p.initial_d['objective'][0]=1
    with pytest.raises((ValueError,KeyError),match='CURRENT_'):verify_current_security(compact,p)
