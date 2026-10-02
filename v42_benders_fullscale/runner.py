"""Ordered pilot, optional clean full B3, optional original M1 canary/production."""
import xml.etree.ElementTree as ET
import numpy as np
import gurobipy as gp
from v42_benders_v2.representation import from_model,audit
from .common import *
from .controller import loop,snapshot

def pilot_gate(r):
    if r.get('status')=='STOP_UNCERTIFIABLE' or r.get('numerical_contradiction') or r.get('uncertified_cuts_inserted',1):return False
    return bool(r.get('validated_witness') or r.get('global_master_infeasible') or
        (r.get('inserted_valid_cuts',0)>=1 and r.get('distinct_persisted_candidates',0)>=2))

def canary_gate(r):
    if r.get('status')=='STOP_UNCERTIFIABLE' or r.get('numerical_contradiction') or r.get('uncertified_cuts_inserted',1):return False
    return bool(r.get('validated_witness') or r.get('global_master_infeasible') or
        (r.get('stage')=='FULL_B3' and r.get('inserted_valid_cuts',0)>=2 and r.get('distinct_persisted_candidates',0)>=3))

def production_gate(r):
    if r.get('status')=='STOP_UNCERTIFIABLE' or r.get('numerical_contradiction') or r.get('uncertified_cuts_inserted',1):return False
    ub=r.get('upper');lb=r.get('lower')
    return bool(ub is not None and lb is not None and np.isfinite([ub,lb]).all() and lb<=ub+1e-7 and
        (lb>=LB+1e-4 or (ub-lb)/abs(ub)<=.005))

def classify(r):
    if r.get('numerical_contradiction') or r.get('uncertified_cuts_inserted',1):return 'B3_INCONCLUSIVE'
    if r.get('validated_witness'):return 'B3_NEGATIVE_CERTIFIED'
    if r.get('global_master_infeasible'):return 'B3_POSITIVE_CERTIFIED'
    return 'B3_INCONCLUSIVE'

def build(env,threshold=True):
    from v42_benders.audit import mask
    path=ROOT.parent/'THRESHOLD_LOCAL/F3.mps'
    if sha(path)!='cf4c631c8e3ecc0ebd3ec055d82f15965faf6c92a53833877f727c55948dede8':raise ValueError('SEALED_MPS_HASH')
    m=gp.read(str(path),env=env)
    if threshold:m.addConstr(m.getVarByName('rho_max')<=T,name='exact_B3_threshold');m.update()
    n=from_model(m,mask() if threshold else None)
    a=audit(m,n);assert a['PASS']
    expected=(85744,230999,954561) if threshold else (208312,108431,954560)
    assert (len(n.xi),len(n.yi),len(n.b))==expected
    prior=read('V1_V2_MATRIX_COMPARISON.json',ROOT/'docs/v42_mess_benders_v2_native_recourse')
    expected_hash=next(r['source_hash'] for r in prior['partitions'] if r['partition']==('B3' if threshold else 'full'))
    assert n.source_hash==expected_hash
    dump('B3_MODEL_AUTHORITY.json' if threshold else 'FULL_M1_MODEL_AUTHORITY.json',dict(**a,
        source_mps_sha256=sha(path),outside_B3_relaxed=122568 if threshold else 0,
        scientific_source_matches_PR116=True,grid_rows_deleted=0,route_pruning=False,threshold=T if threshold else None))
    return m,n

def b3_validator(m,n,point):
    from v42_threshold.validate import physical,grid
    frac=float(np.max(abs(point[n.xi]-np.rint(point[n.xi])),initial=0));residual=n.residual(point[n.xi],point[n.yi])
    physics=physical(n.names,point);electrical,slots=grid(n.names,point)
    rho=float(point[list(n.names).index('rho_max')]);recomputed=electrical['independently_recomputed_P1']
    accepted=bool(frac<=1e-7 and residual<=1e-7 and physics['PASS'] and electrical['PASS'] and rho<=T and recomputed<=T-1e-6)
    return dict(PASS=accepted,threshold_witness=accepted,rho=rho,recomputed_rho=recomputed,threshold=T,guard=1e-6,
        restored_binary_fractionality=frac,native_full_row_bound_residual=residual,physical=physics,grid=electrical,
        full96=True,no_repair=True,outside_B3_fractionality_authorized=True,slot_recomputation=slots)

def original_validator(n,point):
    from v42_certificate.common import original_validation
    original=original_validation(n.names,point)
    return dict(PASS=bool(original['valid_new_UB'] and n.residual(point[n.xi],point[n.yi])<=1e-7),
        original=original,native_residual=n.residual(point[n.xi],point[n.yi]),all_original_integer=True)

def nonrun(name,reason,budget):dump(name,dict(authorized=False,status='NOT_RUN',reason=reason,budget_seconds=budget))

def run():
    require_scope();p=read('PREREGISTRATION.json')
    for r in p['native_source_hashes']:assert sha(ROOT/r['path'])==r['sha256']
    suite=ET.parse(OUT/'PREFLIGHT_789_TESTS.xml').getroot().find('testsuite')
    assert int(suite.attrib['tests'])==789 and int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
    assert not (OUT/'PILOT_EXECUTION_STARTED.json').exists(),'NO_RESULT_DRIVEN_RERUN'
    resource=snapshot();dump('RESOURCE_RECEIPT.json',dict(initial=resource,master_threads=1,
        recourse_policy=p['recourse_thread_policy'],single_optimizer_at_a_time=True,B0_B1_executed=False))
    dump('PILOT_EXECUTION_STARTED.json',dict(source_commit=git('rev-parse','HEAD'),created_UTC=stamp(),
        scope_addendum_sha256=sha(OUT/'SCOPE_CORRECTION_ADDENDUM.json'),preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),
        preflight_789_PASS=True,zero_initial_fullscale_cuts=True,max_candidate_evaluations=2))
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();model=None;fullmodel=None
    try:
        model,n=build(env,True)
        pilot,_=loop(n,env=env,directory=OUT,stage='PILOT',validate=lambda z:b3_validator(model,n,z),max_evaluations=2)
        pg=pilot_gate(pilot);pilot['PILOT_PROGRESS_GATE']=pg
        pilot['BENDERS_FULLSCALE_LOOP_PROVEN']=bool(pg and pilot.get('inserted_valid_cuts',0)>=1 and pilot.get('distinct_persisted_candidates',0)>=2)
        dump('PILOT_PROGRESS.json',pilot)
        dump('PILOT_FINAL_FLAGS.json',dict(PILOT_PROGRESS_GATE=pg,BENDERS_FULLSCALE_LOOP_PROVEN=pilot['BENDERS_FULLSCALE_LOOP_PROVEN'],
            classification=classify(pilot),B3_THRESHOLD_WITNESS=pilot.get('validated_witness',False),historical_same_x_claim=False))
        full=dict(stage='FULL_B3',status='NOT_RUN',reason='PILOT_NOT_P1',uncertified_cuts_inserted=0,
            validated_witness=False,global_master_infeasible=False,inserted_valid_cuts=0,distinct_persisted_candidates=0,recourses=[],cuts=[],progress=[])
        if pg and pilot['BENDERS_FULLSCALE_LOOP_PROVEN'] and not (pilot['validated_witness'] or pilot['global_master_infeasible']):
            dump('B3_FULL_RUN_AUTHORIZATION.json',dict(authorized=True,budget_seconds=1800,created_UTC=stamp(),
                restart='ZERO_CUT_CLEAN_DETERMINISTIC_RESTART',pilot_cuts_reused=0,pilot_receipt_sha256=sha(OUT/'PILOT_PROGRESS.json'),
                master_threads=1,freeze_source_sha256=sha(OUT/'EXECUTION_FREEZE.json')))
            full,_=loop(n,env=env,directory=OUT/'FULL_B3',stage='FULL_B3',validate=lambda z:b3_validator(model,n,z),seconds=1800)
        else:nonrun('B3_FULL_RUN_AUTHORIZATION.json','PILOT_WITNESS_OR_PROOF_NO_FULL_RUN_NEEDED' if pg else 'PILOT_PROGRESS_GATE_FALSE',1800)
        final_b3=full if full['status']!='NOT_RUN' else pilot
        final_b3['classification']=classify(final_b3);dump('B3_FULL_CERTIFICATE.json',full|dict(classification=classify(final_b3)))
        table('B3_FULL_PROGRESS.csv',full['progress'],['iteration','source_x_hash','cut_ID','cut_hash','upper','lower','elapsed'])
        cg=canary_gate(final_b3)
        canary=dict(status='NOT_RUN',reason='B3_CANARY_PROGRESS_GATE_FALSE',upper=None,lower=None,gap=None,
            candidates=[],recourses=[],cuts=[],progress=[],uncertified_cuts_inserted=0)
        production=dict(status='NOT_RUN',reason='CANARY_PRODUCTION_GATE_FALSE',upper=None,lower=None,gap=None,
            candidates=[],recourses=[],cuts=[],progress=[],uncertified_cuts_inserted=0)
        if cg:
            dump('FULL_M1_CANARY_AUTHORIZATION.json',dict(authorized=True,budget_seconds=600,source_sha256=sha(OUT/'B3_FULL_CERTIFICATE.json'),
                all_original_binaries=208312,canary_is_production_acceptance=False))
            fullmodel,original=build(env,False)
            with np.load(ROOT/'docs/v42_m1_late_window_certificate_mipstart/MIP_START_EXACT.npz') as z:
                assert np.array_equal(z['names'],original.names);warm=z['values']
            canary,best=loop(original,env=env,directory=OUT/'FULL_M1_CANARY',stage='CANARY',
                validate=lambda z:original_validator(original,z),seconds=600,warm=warm)
            prodgate=production_gate(canary)
            if prodgate:
                dump('M1_PRODUCTION_AUTHORIZATION.json',dict(authorized=True,budget_seconds=1800,
                    source_canary_sha256=sha(OUT/'FULL_M1_CANARY/RESULT.json'),progress_definition=p['production_gate'],
                    downstream_authorized=False))
                production,_=loop(original,env=env,directory=OUT/'PRODUCTION_M1',stage='PRODUCTION',
                    validate=lambda z:original_validator(original,z),seconds=1800,warm=best)
            else:nonrun('M1_PRODUCTION_AUTHORIZATION.json','CANARY_PRODUCTION_GATE_FALSE',1800)
        else:
            nonrun('FULL_M1_CANARY_AUTHORIZATION.json','B3_CERTIFICATE_OR_FULL_RUN_PROGRESS_ABSENT',600)
            nonrun('M1_PRODUCTION_AUTHORIZATION.json','CANARY_NOT_RUN',1800)
        dump('FULL_M1_CANARY_RESULT.json',canary);dump('PRODUCTION_M1_RESULT.json',production)
        table('FULL_M1_CANARY_PROGRESS.csv',canary['progress'],['iteration','source_x_hash','cut_ID','cut_hash','upper','lower','elapsed'])
        accepted=bool(production['status']=='P1_GAP_TARGET' and production['gap'] is not None and production['gap']<=.005)
        flags=dict(P1_ACCEPTED=accepted,M1_ACCEPTED=False,P2_RUN=False,A2_RUN=False,M2_RUN=False,
            PROBLEM13_FINAL_VALIDATED=False,PILOT_PROGRESS_GATE=pg,BENDERS_FULLSCALE_LOOP_PROVEN=pilot['BENDERS_FULLSCALE_LOOP_PROVEN'],
            B3_FULL_RUN=full['status']!='NOT_RUN',B3_classification=classify(final_b3),FULL_M1_CANARY_RUN=canary['status']!='NOT_RUN',
            PRODUCTION_M1_RUN=production['status']!='NOT_RUN',new_x0_persisted=bool(pilot['candidates']),
            fullscale_valid_cuts=len(pilot['cuts'])+len(full['cuts']),distinct_pilot_master_x=pilot['distinct_persisted_candidates'],
            original_M1_UB=production['upper'] or canary['upper'] or UB,
            valid_original_LB=production['lower'] or canary['lower'] or LB,
            gap=(production['gap'] if production['gap'] is not None else canary['gap'] if canary['gap'] is not None else (UB-LB)/UB),
            new_V2_global_LB=production['lower'] or canary['lower'],Actual_P_correction=False,Actual_Q_correction=False,
            historical_PR115_x='NOT_AVAILABLE',speedup_causal_claim=False,uncertified_cuts_inserted=0,
            B0_B1_RUN=False,downstream_separate_approval_required=True)
        dump('FINAL_FLAGS.json',flags)
        dump('FINAL_VERDICT.json',dict(verdict='P1_CERTIFIED_ACCEPTED_DOWNSTREAM_NOT_RUN' if accepted else 'INCONCLUSIVE',
            B3=flags['B3_classification'],P1_ACCEPTED=accepted,M1_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False,
            current_blocker=pilot.get('reason') or final_b3.get('reason') or final_b3['status'],historical_same_x_claim=False))
        print('FULLSCALE FINAL',flags,flush=True)
    finally:
        if model is not None:model.dispose()
        if fullmodel is not None:fullmodel.dispose()
        env.dispose()

if __name__=='__main__':run()
