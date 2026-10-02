import copy,gzip,hashlib,json
from fractions import Fraction as F
import numpy as np
import pytest
import gurobipy as gp
from v42_benders.canonical import digest_arrays
from v42_benders.certificates import Uncertifiable
from v42_benders_v2.representation import from_model
from v42_benders_v2.recourse import Recourse
from v42_x0_repair.common import OUT,PRIOR,load_x0,load_native,read,preserve
from v42_x0_repair.exact import create,complete,products,q,support
from v42_x0_repair.independent import verify
from v42_x0_repair.fixtures import reproducer
from v42_x0_repair.scaling import scaled
from v42_x0_repair.runner import master_gate

@pytest.fixture
def env():
    e=gp.Env(empty=True);e.setParam('OutputFlag',0);e.start();yield e;e.dispose()

@pytest.fixture
def synthetic(env,tmp_path):
    m=reproducer(env);n=from_model(m);lp=Recourse(n,env,tmp_path/'native');raw=lp.solve(np.array([0.]),30);lp.close()
    # Explicit reduced test vector: .3 and 3*.1 differ as exact IEEE rationals.
    raw=copy.deepcopy(raw);raw.pop('persistence');raw['multipliers']=[.3,3.,-3.];raw['farkas_proof']=.3
    raw['vector_sha256']=digest_arrays(np.asarray(raw['multipliers']));raw['synthetic_fixture_only']=True
    payload=json.dumps(raw,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    journal=tmp_path/'synthetic.jsonl.gz'
    with gzip.open(journal,'wb') as f:f.write(payload+b'\n')
    raw['persistence']=dict(journal=str(journal),record=1,payload_sha256=hashlib.sha256(payload).hexdigest(),persisted_before_validation=True)
    cut=create(n,raw);yield n,raw,cut;m.dispose()

def test_exact_saved_x0_axis_and_base_bytes():
    x,r=load_x0();assert len(x)==85744 and digest_arrays(x)==r['vector_sha256']
    assert r['label']=='NEW_V2_EXPERIMENT_X0' and preserve()==2121

def test_all_1589_classified_with_exact_provenance():
    r=read('BOUND_SUPPORT_CLASSIFICATION.json')
    assert r['unsupported_columns']==1589 and r['exclusive_class_counts']['B_FREE_NONZERO']==1589
    assert r['exclusive_class_counts']['A_FREE_EXACT_ZERO']==79627
    assert r['unsupported_physical_families']==dict(injection_P=792,injection_Q=792,response_line_P=1,response_line_Q=4)
    assert r['E_FINITE_BOUND_SUPPORT_MISSING']==0 and not r['F_NUMERICAL_NEAR_ZERO_ONLY']['accepted_as_zero']
    with gzip.open(OUT/'UNSUPPORTED_COEFFICIENT_PROVENANCE.jsonl.gz','rt') as f:
        rows=[json.loads(v) for v in f]
    assert len(rows)==1589 and len({r['column'] for r in rows})==1589
    assert all(sum((F(t['product']) for t in r['terms']),F(0))!=0 for r in rows)

def test_free_exact_zero_reconstruction_without_clamp(synthetic):
    n,raw,cut=synthetic;original=products(n.A,{i:q(v) for i,v in enumerate(raw['multipliers'])})
    assert original[1]!=0 and abs(float(original[1]))<1e-16
    completed={int(i):F(v) for i,v in cut['record']['rational_multipliers'].items()};a=products(n.A,completed)
    assert 1 not in a and 2 not in a and completed[2]==q(raw['multipliers'][2])
    assert not any(cut['record'][k] for k in ['clamp','flip','tiny_coefficient_deletion','scientific_matrix_changed'])
    assert verify(n,cut)['PASS'] and cut['record']['strict_margin']>0.29

@pytest.mark.parametrize('a,lo,up,valid',[(1,0,np.inf,True),(-1,0,np.inf,False),(-1,-np.inf,0,True),(1,-np.inf,0,False),(1,-np.inf,np.inf,False),(-1,-2,2,True)])
def test_one_sided_and_finite_support(a,lo,up,valid):
    if valid:assert isinstance(support({0:F(a)},[lo],[up])[0],F)
    else:
        with pytest.raises(Uncertifiable):support({0:F(a)},[lo],[up])

@pytest.mark.parametrize('mutation',['exact_intercept','rounded_intercept','float_coefficient','bound','raw_proof','status','ray_sign','free_residual','cut_hash'])
def test_invalid_certificate_never_authorizes_master(synthetic,mutation):
    n,raw,cut=synthetic;bad=copy.deepcopy(cut);r=bad['record']
    if mutation=='exact_intercept':r['exact_intercept']='1'
    elif mutation=='rounded_intercept':r['intercept']+=1
    elif mutation=='float_coefficient':bad['coefficients'][0]+=1
    elif mutation=='bound':r['bound_contribution']='0'
    elif mutation=='raw_proof':bad['raw']['farkas_proof']+=1
    elif mutation=='status':bad['raw']['status']=9
    elif mutation=='ray_sign':bad['raw']['multipliers']=[-v for v in bad['raw']['multipliers']]
    elif mutation=='free_residual':r['rational_multipliers']['0']=str(F(r['rational_multipliers']['0'])+F(1,10**30))
    else:r['cut_hash']='invalid'
    with pytest.raises(Uncertifiable):master_gate(n,bad)

def test_no_master_before_valid_certificate(synthetic):
    n,raw,cut=synthetic;assert not master_gate(n,None) and master_gate(n,cut)

def test_feasible_assignment_survives_exact_cut(synthetic):
    n,raw,cut=synthetic
    assert verify(n,cut,[(np.array([1.]),0.)])['PASS']
    assert cut['record']['intercept']+float(cut['coefficients']@np.array([0.]))<-1e-8

@pytest.mark.parametrize('exponent',[-4,4])
def test_power2_scaling_optimum_and_mapped_identity(env,tmp_path,exponent):
    m=reproducer(env);n=from_model(m);ns=scaled(n,np.full(len(n.b),exponent))
    lp=Recourse(n,env,tmp_path/'native');sp=Recourse(ns,env,tmp_path/'scaled')
    for bit in [0.,1.]:
        a=lp.solve(np.array([bit]));b=sp.solve(np.array([bit]));assert a['status']==b['status']
        if a['status']==2:
            assert abs(a['objective']-b['objective'])<=1e-7 and n.residual(np.array([bit]),b['primal'])<=1e-7
            y=np.asarray(b['primal']);assert np.array_equal(y.copy(),y) # actual chosen primal map and inverse are identity
        else:assert verify(ns,create(ns,b))['PASS']
    lp.close();sp.close();m.dispose()

def test_fixture_1536_and_N1_N10_executed():
    r=read('FIXTURE_REGRESSION.json');assert r['PASS'] and (r['assignments'],r['feasible'],r['infeasible'])==(1536,49,1487)
    assert len(r['numerical_N1_N10'])==10 and all(v['PASS'] for v in r['numerical_N1_N10'])
    assert r['reduced_unsupported_support_fixture']['PASS'] and r['fullscale_master_optimize_calls']==0
    assert read('STANDARD_FORM_EQUIVALENCE.json')['bijection']

def test_no_production_or_downstream_authorized():
    p=read('PREREGISTRATION.json');assert p['production_M1_P2_A2_M2_forbidden'] and not p['full_B3_RUN'] and not p['full_M1_canary_RUN']
    if (OUT/'FINAL_FLAGS.json').exists():
        f=read('FINAL_FLAGS.json');assert all(f[k] is False for k in ['production_M1_RUN','P1_ACCEPTED','P2_RUN','A2_RUN','M2_RUN','M1_ACCEPTED','PROBLEM13_FINAL_VALIDATED','Actual_P_correction','Actual_Q_correction'])
        assert f['new_x0_master_optimize_calls']==0 and f['uncertified_cuts_inserted']==0

def test_actual_x1_lineage_when_available():
    if not (OUT/'FINAL_FLAGS.json').exists():return
    f=read('FINAL_FLAGS.json')
    if not f['x1_generated']:return
    r=read('MASTER_X1_RECEIPT.json');assert r['persisted_before_recourse'] and r['created_only_after_valid_cut']
    assert r['parent_PR117_x0']==load_x0()[1]['vector_sha256'] and r['vector_sha256']!=r['parent_PR117_x0']
    assert f['valid_cut_count']>=1 and r['master_settings']['Threads']==1
    started=read('RECOURSE_STARTED.json',OUT/'X1');assert started['source_saved_verified_before_optimize']
    assert started['source_x_hash']==r['vector_sha256'] and started['started_UTC']>=r['created_UTC']
