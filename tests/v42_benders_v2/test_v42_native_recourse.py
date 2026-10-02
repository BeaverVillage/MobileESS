import copy,csv,gzip,json
from fractions import Fraction as F
from pathlib import Path
import numpy as np
import pytest
import gurobipy as gp
from v42_benders.fixtures import build,CASES
from v42_benders.certificates import Uncertifiable
from v42_benders.canonical import digest_arrays
from v42_benders_v2.common import ROOT,OUT,BASE,read,sha
from v42_benders_v2.representation import from_model,audit
from v42_benders_v2.engine import certified,add_validated_cut
from v42_benders_v2.certificates import create
from v42_benders_v2.independent import verify,persisted
from v42_benders_v2.gates import *

@pytest.fixture
def env():
    e=gp.Env(empty=True);e.setParam('OutputFlag',0);e.start();yield e;e.dispose()

def records(case,path='native'):
    with gzip.open(OUT/'RAW_FINAL'/case/path/'raw_certificates.jsonl.gz','rt') as f:return [json.loads(l) for l in f]

def attach(raw,record):
    r=copy.deepcopy(raw);r['persistence']=record['raw_persistence'];return r

@pytest.mark.parametrize('case',list(CASES))
def test_all_assignments_independent_replay(env,case):
    m=build(env,case);n=from_model(m);rows=[r for r in csv.DictReader((OUT/'V2_FIXTURE_CENSUS.csv').open()) if r['case']==case]
    assert len(rows)==128 and {r['bits'] for r in rows}=={format(i,'07b') for i in range(128)}
    assert all(r['match']=='True' and r['original_native_status']==r['V1_status']==r['V2_status'] for r in rows)
    known=[(np.array(list(map(int,r['bits']))),float(r['V2_optimum'])) for r in rows if r['feasible']=='True']
    native=records(case);phase=records(case,'phase1')
    audits=[r for r in read('NATIVE_FARKAS_CERTIFICATE_AUDIT.json')['records'] if r['case']==case]
    paudits=[r for r in read('PHASE1_CERTIFICATE_AUDIT.json')['records'] if r['case']==case]
    for rec in audits+paudits:
        idx=rec['assignment'];raw=attach(phase[idx] if rec['kind']=='phase1' else native[idx],rec)
        cut=create(n,raw,rec['kind']);assert verify(n,cut,known)['PASS']
        assert cut['record']['cut_hash']==rec['cut_hash']
    m.dispose()

@pytest.mark.parametrize('case',list(CASES))
def test_native_representation_domain_and_equalities(env,case):
    m=build(env,case);n=from_model(m)
    assert audit(m,n)['PASS'] and n.A.shape[0]==m.NumConstrs
    assert np.array_equal(n.sense,np.asarray(m.getAttr('Sense')))
    assert len(n.xi)==7 and len(n.names)==m.NumVars
    assert sum(n.sense=='=')>=8
    x=np.array([0.,0.,1.,1.,0.,0.,1.]);rhs=n.rhs(x)
    for i in range(len(rhs)):
        exact=F.from_float(float(n.b[i]))
        for k in range(n.B.indptr[i],n.B.indptr[i+1]):exact-=F.from_float(float(n.B.data[k]))*F.from_float(float(x[n.B.indices[k]]))
        assert rhs[i]==float(exact)
    m.dispose()

@pytest.fixture
def good_cut(env):
    m=build(env,'A');n=from_model(m);rec=read('NATIVE_FARKAS_CERTIFICATE_AUDIT.json')['records'][0]
    raw=attach(records('A')[0],rec);cut=certified(n,raw,'native_farkas');yield n,cut;m.dispose()

@pytest.mark.parametrize('mutation',['sign','proof','status','NaN','bound','coeff','intercept','rawhash','axis','rhs','source','record'])
def test_altered_certificates_rejected(good_cut,mutation):
    n,good=good_cut;bad=copy.deepcopy(good)
    if mutation=='sign':bad['raw']['multipliers']=[-v for v in bad['raw']['multipliers']]
    elif mutation=='proof':bad['raw']['farkas_proof']+=1
    elif mutation=='status':bad['raw']['status']=9
    elif mutation=='NaN':bad['raw']['multipliers'][0]=np.nan
    elif mutation=='bound':bad['record']['bound_contribution']='100'
    elif mutation=='coeff':bad['coefficients'][0]+=1
    elif mutation=='intercept':bad['record']['intercept']+=1
    elif mutation=='rawhash':bad['raw']['persistence']['payload_sha256']='0'*64
    elif mutation=='axis':bad['raw']['axis_npz_sha256']='0'*64
    elif mutation=='rhs':bad['raw']['solver_rhs'][0]+=1
    elif mutation=='source':bad['raw']['source_x'][0]=1
    else:bad['raw']['persistence']['record']=9999
    with pytest.raises(Uncertifiable):verify(n,bad)

def test_insertion_boundary_replays_certificate(env,good_cut):
    n,cut=good_cut;bad=copy.deepcopy(cut);bad['record']['bound_contribution']='100'
    master=gp.Model(env=env);x=master.addMVar(len(n.xi),vtype='B');master.update();before=master.NumConstrs
    with pytest.raises(Uncertifiable):add_validated_cut(master,x,None,n,bad)
    master.update();assert master.NumConstrs==before;master.dispose()

def test_independent_does_not_call_generator(monkeypatch,good_cut):
    n,cut=good_cut
    import v42_benders_v2.certificates as c
    monkeypatch.setattr(c,'create',lambda *a,**k:pytest.fail('generator called'))
    assert verify(n,cut)['PASS']

@pytest.mark.parametrize('num',range(1,11))
def test_numerical_adversarial(num):
    with (OUT/'V2_NUMERICAL_ADVERSARIAL_RESULTS.csv').open() as f:rows={r['case']:r for r in csv.DictReader(f)}
    row=rows['N'+str(num)];assert row['PASS']=='True'
    if num==6:assert row['valid_certificate']=='False' and row['scientific_classification']=='INCONCLUSIVE_NEAR_ZERO'
    else:assert row['valid_certificate']=='True'

def test_preserved_bytes_and_bounded_receipt():
    r=read('PR115_BASE_RECEIPT.json');assert r['base']==BASE and r['tracked_files']==1615
    from v42_voltage.preservation import assert_snapshot
    assert assert_snapshot(r['files'])
    assert r['inherited_tests']==708 and r['inherited_bounded_checks']==44
    assert sha(ROOT/'docs/v42_m1_integrality_gap_root_cause/WINDOW_INTEGRALITY_VALIDATION_SUMMARY.json')==r['bounded_receipt_sha256']

def test_same_x_missing_is_closed():
    r=read('PR115_FIRST_X_RECEIPT.json');assert not r['restored'] and not r['master_resolved']
    with pytest.raises(ValueError,match='PR115_FIRST_X_UNAVAILABLE'):restore_first_x(r,None,None)
    assert not isolated_gate(r,read('V2_FIXTURE_EXACTNESS.json'),dict(status=3,independent_valid_cut=True,same_x_verified=True))

@pytest.mark.parametrize('field',['restored','same_x_verified','independent_valid_cut'])
def test_isolated_gate_requires_all_fields(field):
    x=dict(restored=True);r=dict(status=3,same_x_verified=True,independent_valid_cut=True)
    (x if field=='restored' else r)[field]=False
    assert not isolated_gate(x,dict(PASS=True,agreement=1536),r)

@pytest.mark.parametrize('case',['fast_master','invalid_cut','contradiction','missing_isolated','valid_cut','witness','proof'])
def test_progress_gate(case):
    b=dict(numerical_contradiction=False,uncertified_cuts_used=0,independent_valid_cuts=0)
    if case in ['invalid_cut','valid_cut','missing_isolated','contradiction']:b['independent_valid_cuts']=1
    if case=='invalid_cut':b['uncertified_cuts_used']=1
    if case=='contradiction':b['numerical_contradiction']=True
    if case=='witness':b['validated_witness']=True
    if case=='proof':b['global_master_infeasible']=True
    assert progress_gate(case!='missing_isolated',b)==(case in ['valid_cut','witness','proof'])

@pytest.mark.parametrize('failure',['none','uncertified','noUB','noLB','noProgress','unstable','contradiction'])
def test_production_bound_progress(failure):
    c=dict(upper=.5912812634331275,lower=.574,cut_validity=True,independent_original_UB=True,
        global_LB_valid=True,numerical_stability=True,uncertified_cuts_used=0)
    if failure=='uncertified':c['uncertified_cuts_used']=1
    if failure=='noUB':c['independent_original_UB']=False
    if failure=='noLB':c['global_LB_valid']=False
    if failure=='noProgress':c['lower']=.5722125039436496
    if failure=='unstable':c['numerical_stability']=False
    if failure=='contradiction':c['lower']=1.
    assert production_gate(c)==(failure=='none')

@pytest.mark.parametrize('accepted',[False,True])
@pytest.mark.parametrize('approved',[False,True])
def test_downstream_separate_approval(accepted,approved):assert downstream_allowed(accepted,approved)==(accepted and approved)

def test_actual_matrix_and_all_domain_counts():
    a=read('ACTUAL_NATIVE_LP_MATRIX_AUDIT.json');assert a['PASS'] and a['optimize_calls']==0
    rows={r['partition']:r for r in a['records']}
    assert (rows['full']['columns'],rows['B3']['columns'])==(108431,230999)
    assert (rows['full']['rows'],rows['B3']['rows'])==(954560,954561)
    original=read('NATIVE_BOUND_RECOURSE_AUDIT.json')['partitions']
    assert [r['master_columns'] for r in original]==[208312,85744]
    assert all(r['scientific_rows_deleted']==r['route_columns_pruned']==0 for r in original)

def test_global_gap_semantics():
    from v42_benders.engine import relative_gap
    ub=.5912812634331275;lb=.5722125039436496
    assert relative_gap(ub,lb)==pytest.approx((ub-lb)/abs(ub))
    assert relative_gap(ub,None) is None
    with pytest.raises(Uncertifiable):relative_gap(ub,ub+1e-3)

def test_phase1_diagnostic_complete():
    a=read('PHASE1_CERTIFICATE_AUDIT.json');assert a['diagnostic_cuts']==1487 and a['all_feasible_zero']
    assert not a['production_artificial_slack'] and not a['full_scale_fallback_used']

def test_actual_correction_and_science_unchanged():
    p=read('PREREGISTRATION.json');assert not p['Actual_P_correction'] and not p['Actual_Q_correction'] and not p['science_changes']
    assert read('V1_NUMERICAL_ROOT_CAUSE_AUDIT.json')['sole_cause_claim'] is False

def test_rejected_native_saved_before_validation(env):
    rejection=read('NATIVE_FARKAS_CERTIFICATE_AUDIT.json')['rejected_native'][0]
    case=rejection['case'];idx=rejection['assignment'];raw=records(case)[idx]
    raw['persistence']=rejection['raw_persistence'];persisted(raw)
    m=build(env,case);n=from_model(m)
    with pytest.raises(Uncertifiable,match='NATIVE_PROOF_MISMATCH'):create(n,raw,'native_farkas')
    persisted(raw);assert raw['multipliers'] and raw['row_axis_hash'];m.dispose()

def test_native_bounds_essential_phase1_case_J():
    a=read('PHASE1_CERTIFICATE_AUDIT.json')['records']
    assert any(r['case']=='J' and F(r['bound_contribution'])!=0 for r in a)

def test_free_variable_residual_not_truncated(env):
    from v42_benders_v2.adversarial import build as nb
    m=nb(env,3);n=from_model(m)
    with gzip.open(OUT/'NUMERICAL_RAW_FINAL/N3/native/raw_certificates.jsonl.gz','rt') as f:raw=json.loads(f.readline())
    raw['persistence']={};raw['multipliers'][0]+=1e-12
    with pytest.raises(Uncertifiable,match='UNBOUNDED_STATIONARITY_SUPPORT'):create(n,raw,'native_farkas')
    m.dispose()

def test_append_reuse_keeps_raw_axis_and_record_numbers(env,tmp_path):
    from v42_benders_v2.recourse import Recourse
    m=build(env,'A');n=from_model(m);lp=Recourse(n,env,tmp_path);r1=lp.solve(np.zeros(7));lp.close()
    h=sha(tmp_path/'axis.npz');lp=Recourse(n,env,tmp_path);r2=lp.solve(np.zeros(7));lp.close()
    assert sha(tmp_path/'axis.npz')==h and r2['persistence']['record']==2
    persisted(r1);persisted(r2);m.dispose()

def test_final_closed_flags_and_review():
    f=read('FINAL_FLAGS.json')
    assert all(f[k] is False for k in ['P1_ACCEPTED','M1_ACCEPTED','P2_RUN','A2_RUN','M2_RUN','PROBLEM13_FINAL_VALIDATED'])
    assert f['full_scale_valid_cuts']==0 and f['new_V2_global_LB'] is None
    assert read('SAME_X_V2_RECOURSE_RESULT.json')['status']=='NOT_RUN'
    assert read('REPORT_GENERATION_RECEIPT.json')['questions']==60
    assert all(not read(p)['authorized'] for p in ['B3_V2_AUTHORIZATION.json','FULL_M1_CANARY_AUTHORIZATION.json','M1_PRODUCTION_AUTHORIZATION.json'])

def test_explicit_N10_sign_mutation():
    a=read('N10_SIGN_MUTATION_REPLAY.json');assert a['PASS'] and a['rejected'] and a['optimization_calls']==0
