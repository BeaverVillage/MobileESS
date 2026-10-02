import copy,gzip,json
from pathlib import Path
import numpy as np
import pytest
import gurobipy as gp
from v42_benders.fixtures import build
from v42_benders_v2.representation import from_model
from v42_benders_fullscale.common import ROOT,OUT,BASE,read,sha,require_scope,verify_inherited
from v42_benders_fullscale.candidates import persist,load
from v42_benders_fullscale.runner import pilot_gate,canary_gate,production_gate,classify

@pytest.fixture
def env():
    e=gp.Env(empty=True);e.setParam('OutputFlag',0);e.start();yield e;e.dispose()

def test_scope_committed_before_optimize():
    checkpoint=require_scope();assert checkpoint['optimize_calls_before_commit']==0
    r=read('SCOPE_CORRECTION_ADDENDUM.json');assert r['user_authorized_new_candidate'] and r['historical_PR115_x']=='NOT_AVAILABLE'
    assert not r['same_x_performance_comparison'] and r['V2_engine_inherited_from_PR116']

def test_base_2054_and_789_preserved():
    assert verify_inherited();r=read('PR116_BASE_RECEIPT.json')
    assert r['base']==BASE and r['tracked_files']==2054 and r['inherited_tests']==789 and r['inherited_bounded_checks']==44
    for r in read('PREREGISTRATION.json')['native_source_hashes']:assert sha(ROOT/r['path'])==r['sha256']

@pytest.mark.parametrize('bad',['vector','axis','receipt','missing'])
def test_atomic_candidate_hash_guard(env,tmp_path,bad):
    m=build(env,'A');n=from_model(m)
    class Master:
        Status=2;Runtime=.1;ObjVal=0
        class Params:Threads=1;Seed=20260929;Method=1;FeasibilityTol=1e-7;IntFeasTol=1e-7;MIPGap=0
    r=persist(tmp_path,0,n,np.zeros(len(n.xi)),Master,[],{},'TEST')
    values,receipt=load(tmp_path,0,n);assert np.array_equal(values,np.zeros(len(n.xi))) and receipt['vector_sha256']==r['vector_sha256']
    if bad=='vector':(tmp_path/'MASTER_X_000.npz').write_bytes(b'altered')
    elif bad=='axis':(tmp_path/'MASTER_X_000_AXIS.json').write_text('{}')
    elif bad=='receipt':
        r['persisted_before_recourse']=False;(tmp_path/'MASTER_X_000_RECEIPT.json').write_text(json.dumps(r))
    else:(tmp_path/'MASTER_X_000_RECEIPT.json').unlink()
    with pytest.raises((ValueError,OSError)):load(tmp_path,0,n)
    m.dispose()

def test_recourse_receives_exact_persisted_candidate(env,tmp_path,monkeypatch):
    import v42_benders_fullscale.controller as c
    from v42_benders_v2.recourse import Recourse
    m=build(env,'A');n=from_model(m);seen=[];original=Recourse.solve
    def checked(self,x,seconds):
        index=len(seen);values,r=load(tmp_path,index,n)
        assert np.array_equal(x,values) and r['persisted_before_recourse'] and r['master_settings']['Threads']==1
        seen.append(r['vector_sha256']);return original(self,x,seconds)
    monkeypatch.setattr(Recourse,'solve',checked)
    monkeypatch.setattr(c,'snapshot',lambda:dict(other_heavy_solve=False))
    r,_=c.loop(n,env=env,directory=tmp_path,stage='PILOT',validate=lambda z:dict(PASS=n.residual(z[n.xi],z[n.yi])<=1e-7),max_evaluations=2)
    assert r['validated_witness'] and seen and not r['zero_objective_bound_used_as_rho_LB']
    assert r['lower'] is None and r['uncertified_cuts_inserted']==0
    with gzip.open(tmp_path/'native/raw_certificates.jsonl.gz','rt') as f:raw=json.loads(f.readline())
    assert np.array_equal(raw['source_x'],load(tmp_path,0,n)[0]);m.dispose()

def test_cut_then_new_candidate_or_proof(env,tmp_path,monkeypatch):
    import v42_benders_fullscale.controller as c
    monkeypatch.setattr(c,'snapshot',lambda:dict(other_heavy_solve=False))
    m=build(env,'B');n=from_model(m)
    r,_=c.loop(n,env=env,directory=tmp_path,stage='PILOT',validate=lambda z:dict(PASS=False),max_evaluations=2)
    assert r['inserted_valid_cuts']>=1 and (r['distinct_persisted_candidates']>=2 or r['global_master_infeasible'])
    assert r['uncertified_cuts_inserted']==0
    for cut in r['cuts']:
        assert cut['validator_result'] and cut['source_violation']>1e-8 and len(cut['coefficients_hash'])==64
    assert len({x['vector_sha256'] for x in r['candidates']})==r['distinct_persisted_candidates'];m.dispose()

@pytest.mark.parametrize('case',['none','cut_only','x_only','loop','witness','proof','invalid','stop'])
def test_pilot_gate(case):
    r=dict(status='PILOT_MAX_EVALUATIONS',uncertified_cuts_inserted=0,inserted_valid_cuts=0,distinct_persisted_candidates=1)
    if case in ['cut_only','loop','invalid','stop']:r['inserted_valid_cuts']=1
    if case in ['x_only','loop','invalid','stop']:r['distinct_persisted_candidates']=2
    if case=='witness':r['validated_witness']=True
    if case=='proof':r['global_master_infeasible']=True
    if case=='invalid':r['uncertified_cuts_inserted']=1
    if case=='stop':r['status']='STOP_UNCERTIFIABLE'
    assert pilot_gate(r)==(case in ['loop','witness','proof'])

@pytest.mark.parametrize('stage,cuts,xs,expected',[('PILOT',2,3,False),('FULL_B3',1,3,False),('FULL_B3',2,2,False),('FULL_B3',2,3,True)])
def test_full_M1_requires_full_run_progress(stage,cuts,xs,expected):
    assert canary_gate(dict(stage=stage,status='TIME_LIMIT',uncertified_cuts_inserted=0,inserted_valid_cuts=cuts,distinct_persisted_candidates=xs))==expected

@pytest.mark.parametrize('certificate',['validated_witness','global_master_infeasible'])
def test_certificate_exempts_count_gate(certificate):
    r=dict(stage='PILOT',status='CERTIFIED',uncertified_cuts_inserted=0);r[certificate]=True;assert canary_gate(r)

@pytest.mark.parametrize('field',['uncertified_cuts_inserted','numerical_contradiction'])
def test_invalid_or_contradictory_progress_closed(field):
    r=dict(stage='FULL_B3',status='TIME_LIMIT',uncertified_cuts_inserted=0,inserted_valid_cuts=2,distinct_persisted_candidates=3)
    r[field]=1;assert not canary_gate(r)

@pytest.mark.parametrize('lb,expected',[(None,False),(.5722125039436496,False),(.574,True),(1.,False)])
def test_production_meaningful_gap_reduction(lb,expected):
    assert production_gate(dict(status='TIME_LIMIT',uncertified_cuts_inserted=0,upper=.5912812634331275,lower=lb))==expected

def test_original_domain_and_no_downstream():
    p=read('PREREGISTRATION.json')
    assert (p['master_binaries_B3'],p['master_binaries_full'],p['continuous_full'])==(85744,208312,108431)
    assert p['route_full']==207928 and p['mode_full']==384 and p['witness_guard']==1e-6
    assert not p['Actual_P_correction'] and not p['Actual_Q_correction'] and not p['scientific_changes']
    assert p['P2_A2_M2'].startswith('separate user approval')

def test_threshold_classification_not_solver_infeasibility():
    assert classify(dict(uncertified_cuts_inserted=0))=='B3_INCONCLUSIVE'
    assert classify(dict(uncertified_cuts_inserted=0,global_master_infeasible=True))=='B3_POSITIVE_CERTIFIED'
    assert classify(dict(uncertified_cuts_inserted=0,validated_witness=True))=='B3_NEGATIVE_CERTIFIED'
    assert classify(dict(uncertified_cuts_inserted=1,global_master_infeasible=True))=='B3_INCONCLUSIVE'
