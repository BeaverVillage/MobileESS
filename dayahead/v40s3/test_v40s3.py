"""Independent numerical, row-authority and freeze regressions; no model fits."""
import ast
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from .contracts import (Q,U_HOURS,FIELDS,positive,slots,baseline_safe,body_tail,
                        metrics,recall_capture,select_eta,hybrid,validate_adapter)
from .audit import ROOT,OUT,BASE,S2,git,sha
from .experiment import get,load_panel,predictor_x,BOUNDS


@pytest.fixture(scope='module')
def panel():return load_panel()


@pytest.fixture(scope='module')
def results():return get('DEV_CAL_RESULTS')['results']+get('EXPOSED_RESULTS')['results']


def test_live_head_resolved():
    x=get('CURRENT_PR27_HEAD_AUDIT')
    assert x['live']['headRefOid']==BASE and x['resolved_HEAD']==BASE


def test_separate_worktree():
    assert git('branch','--show-current')=='codex/v40s3-body-tail-runtime-risk'
    assert ROOT.name=='MobileESS_v40s3_body_tail_runtime_risk'


def test_all_production_blobs_unchanged():
    a={s.split('\t')[1]:s.split('\t')[0] for s in git('ls-tree','-r',BASE).splitlines()}
    b={s.split('\t')[1]:s.split('\t')[0] for s in git('ls-tree','-r','HEAD').splitlines()}
    assert all(b.get(k)==v for k,v in a.items())
    assert all(p.startswith(('dayahead/v40s3/','dayahead/artifacts/v40s3_body_tail_runtime_risk/')) for p in git('diff','--name-only',BASE).splitlines())


def test_s2_sha_reference():
    x=get('V40S2_REFERENCE_FREEZE')
    assert x['status']=='PASS' and x['full_receipt_commit']==S2 and x['file_count']==145


def test_pending_membership_exact(panel):
    assert panel.state_at_issue.eq('PENDING').all()
    assert (panel.submit_time<=panel.issue_time).all()
    assert (panel.start_time>panel.issue_time).all() and (panel.end_time>panel.issue_time).all()
    assert panel.issue_time.dt.hour.eq(8).all()


def test_missing_snapshot_does_not_block():
    assert get('FEATURE_AUTHORITY_AUDIT')['status']=='PASS_STRICT_CLOCK_ONLY'
    assert get('METHOD_SELECTION')['membership_authority']=='PASS_NORMATIVE_RECONSTRUCTION'


def test_running_redesign_zero():
    assert get('SCOPE_CONTRACT')['RUNNING_redesign_count']==0


@pytest.mark.parametrize('key',['source_changes_migration','source_changes_WAN','source_changes_terminal'])
def test_protected_changes_zero(key):assert get('PROTECTED_SCOPE_DIFF')[key]==0


@pytest.mark.parametrize('key',['event_trigger_added','local_repair_added','rolling_MPC_added'])
def test_no_extra_architecture(key):assert get('SCOPE_CONTRACT')[key]==0


def test_labels_exact(panel):
    np.testing.assert_array_equal(panel.runtime_seconds,(panel.end_time-panel.start_time).dt.total_seconds())


def test_original_cohort_zero_identity():
    a=get('POPULATION_AUDIT')
    assert (a['original_N'],a['positive_service_N'],a['zero_N'],a['negative_N'],a['duplicate_job_id_N'])==(73504,72292,1212,0,0)
    assert a['exact_S2_identity']


def test_features_exact_and_no_future(panel):
    x=predictor_x(panel)
    assert x.shape==(len(panel),2)
    np.testing.assert_array_equal(x[:,0],panel.submit_time.dt.hour)
    np.testing.assert_array_equal(x[:,1],panel.submit_time.dt.dayofweek)
    other=panel.copy()
    for c in ('runtime_seconds','requested_seconds','num_gpus_req','K0'):other[c]=-98765
    other['start_time']=pd.Timestamp('2099-01-01T00:00Z')
    np.testing.assert_array_equal(x,predictor_x(other))


def test_feature_admission():
    assert get('CAUSAL_FEATURE_CONTRACT')['admitted_model_features']==['submit_hour','weekday']
    assert 'requested_seconds' in get('CAUSAL_FEATURE_CONTRACT')['rejected_predictors']


@pytest.mark.parametrize('role',BOUNDS)
def test_temporal_label_availability(panel,role):
    a,b=map(pd.Timestamp,BOUNDS[role]);p=panel[panel.role.eq(role)]
    assert p.issue_time.ge(a).all() and p.issue_time.lt(b).all() and p.end_time.lt(b).all()
    if role!='TRAIN':assert panel[panel.role.eq('TRAIN')].end_time.max()<p.issue_time.min()


def test_no_training_job_leaks_into_later_pending(panel):
    roles=list(BOUNDS)
    for i,r in enumerate(roles):
        old=set(panel[panel.role.eq(r)].job_id)
        for later in roles[i+1:]:assert not old & set(panel[panel.role.eq(later)].job_id)


def test_u_fixed_no_eval_or_may_selection():
    assert get('PREREGISTRATION')['threshold_hours']==[4,6,8,12,24]
    assert get('METHOD_SELECTION')['selection_roles']==['DEVELOPMENT','CALIBRATION']


@pytest.mark.parametrize('h',U_HOURS)
def test_body_tail_exact_partition(panel,h):
    body,tail=body_tail(panel.runtime_seconds,h*3600)
    assert not (body & tail).any() and (body | tail).all()
    np.testing.assert_array_equal(body,panel.runtime_seconds<=h*3600)


def test_equality_belongs_to_body():
    a,b=body_tail([14400,14401],14400)
    assert a.tolist()==[True,False] and b.tolist()==[False,True]


def test_tail_remains_denominator(results,panel):
    for r in results:
        if r['replay'] is not None:
            assert r['replay']['N']==r['replay']['full_denominator']==int(panel.role.eq(r['role']).sum())


@pytest.mark.parametrize('h',U_HOURS)
def test_new_quantile_order_positive(h):
    for role in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']:
        f=pd.read_parquet(OUT/f'V40S3_PREDICTIONS_u{h}_{role}.parquet')
        for b in ['B1','B2','B3']:
            assert np.isfinite(f[[b+'_Q50',b+'_Q90']]).all().all()
            assert f[b+'_Q50'].gt(0).all() and (f[b+'_Q50']<=f[b+'_Q90']).all()


@pytest.mark.parametrize('v',[0,-1,float('nan'),float('inf')])
def test_invalid_duration_rejected(v):
    with pytest.raises(ValueError):positive([v])


def test_ceiling_boundary_exact():
    assert slots([.1,899,900,900.001,1800,1800.001]).tolist()==[1,1,1,2,2,3]


def test_no_repeated_ceiling_bias():
    x=np.array([12.,899.,901.,12345.])
    np.testing.assert_array_equal(slots(x),slots(slots(x)*900))


def test_eta_only_calibration():
    for role in ['TRAIN','DEVELOPMENT','EXPOSED_EVALUATION','MAY']:
        with pytest.raises(ValueError):select_eta([20000]*100,14400,[.4]*100,[1]*100,[10000]*100,role=role)


def test_eta_largest_valid_not_half():
    y=np.array([20000]*100+[1000]*100)
    p=np.r_[np.repeat(.8,90),np.repeat(.2,10),np.repeat(.1,100)]
    assert select_eta(y,14400,p,np.ones(200),np.ones(200)*500,role='CALIBRATION')==.8


def test_eta_requires_support():
    assert select_eta([20000]*99,14400,[.4]*99,[1]*99,[1000]*99,role='CALIBRATION') is None


def test_saved_eta_independent_maximality(panel):
    d=panel[panel.role.eq('CALIBRATION')].reset_index(drop=True)
    for row in get('ETA_SELECTION')['rows']:
        assert row['source_role']=='CALIBRATION'
        p=pd.read_parquet(OUT/f"V40S3_PREDICTIONS_u{row['u_hours']}_CALIBRATION.parquet")
        prob=p[row['classifier']+'_p_tail'].to_numpy();tail=d.runtime_seconds.gt(row['u_hours']*3600).to_numpy();g=d.num_gpus_req.to_numpy()
        if tail.sum()<100:assert row['eta'] is None;continue
        eligible=[v for v in np.unique(np.r_[0.,prob,1.]) if ((prob>=v)[tail]).mean()>=.9 and g[(prob>=v)&tail].sum()/g[tail].sum()>=.9]
        assert row['eta']==max(eligible)


def test_tail_recall_gpu_and_mass_by_hand():
    x=recall_capture([20000,40000,1000],14400,[.8,.2,.9],.5,[1,4,1],[10000,10000,2000])
    assert x['recall']==.5 and x['GPU_recall']==.2
    assert x['mass_capture']==pytest.approx(10000/130000)


def test_r0_exact_existing_reference():
    np.testing.assert_array_equal(hybrid([100,200],[False,True],[999,888],[5000,6000],'R0',state='PENDING'),[100,888])


def test_r1_exact_existing_request():
    np.testing.assert_array_equal(hybrid([100,200],[False,True],[999,888],[5000,6000],'R1',state='PENDING'),[100,6000])


def test_no_q99_policy():
    with pytest.raises(ValueError):hybrid([1],[True],[2],[3],'Q99',state='PENDING')


def test_running_adapter_blocked():
    with pytest.raises(ValueError):hybrid([1],[True],[2],[3],'R0',state='RUNNING')


def test_walltime_not_hard_bound(panel):
    assert (panel.runtime_seconds>panel.requested_seconds).any()
    assert 'not exact completion or guaranteed hard bound' in get('ROBUST_POLICY_R1_REPORT')['meaning']


def test_gpu_underprediction_and_overreserve_by_hand():
    m=metrics([1000,5000],[1800,2700],[2,4])
    assert m['GPU_underprediction_sec']==9200
    assert m['overreservation_GPU_hours']==pytest.approx(1600/3600)
    assert m['coverage']==.5 and m['GPU_coverage']==pytest.approx(1/3)
    assert m['MAE_sec']==1550


def test_saved_hybrid_reconstruction_independent(panel):
    # Every exposed body/classifier/policy: independent numpy replay, no fitting.
    d=panel[panel.role.eq('EXPOSED_EVALUATION')].reset_index(drop=True)
    predictions={h:pd.read_parquet(OUT/f'V40S3_PREDICTIONS_u{h}_EXPOSED_EVALUATION.parquet') for h in U_HOURS}
    for r in get('EXPOSED_RESULTS')['results']:
        if r['replay'] is None:continue
        f=predictions[r['u_hours']];flag=f[r['classifier']+'_p_tail'].to_numpy()>=r['tail']['eta']
        fallback=d.reference_safe_sec.to_numpy() if r['policy']=='R0' else d.requested_seconds.to_numpy()
        sec=np.where(flag,fallback,f[r['body']+'_Q90'].to_numpy());dur=np.ceil(sec/900)*900
        e=d.runtime_seconds.to_numpy()-dur;g=d.num_gpus_req.to_numpy()
        assert r['replay']['GPU_underprediction_sec']==pytest.approx(float((g*np.maximum(e,0)).sum()))
        assert r['replay']['overreservation_GPU_hours']==pytest.approx(float((g*np.maximum(-e,0)).sum()/3600))


def test_terminal_audit_only():
    r=get('TERMINAL_CLASS_IMPACT_AUDIT')
    assert r['terminal_decisions_modified']==0 and not r['actual_start_used_as_scheduled_start']
    assert r['matched_N']==0 and r['selected_change_count'] is None and r['counts']==[]


def test_migration_audit_readonly():
    r=get('EXISTING_MIGRATION_TOUCH_AUDIT')
    assert r['migration_changed']=='NO' and r['migration_solve_calls']==0
    assert r['candidate_inherited_migration_touch_count'] is None


@pytest.mark.parametrize('key',['optimizer_calls','Gurobi_calls','Fresh_OpenDSS_calls'])
def test_no_optimizer_calls(key):assert get('SCOPE_CONTRACT')[key]==0


def test_source_import_firewall():
    for p in (ROOT/'dayahead/v40s3').glob('*.py'):
        tree=ast.parse(p.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                assert not any(a.name.split('.')[0] in ['gurobipy','opendssdirect','dss'] for a in node.names)
            if isinstance(node,ast.ImportFrom):
                assert not (node.module or '').startswith(('dayahead.v40a','dayahead.v40g','dayahead.v37','dayahead.v38'))


def test_may_rows_zero_discovery_disclosed(panel):
    f=get('MAY_FIREWALL')
    assert not f['May_total_read_count_zero_claim']
    for k,v in f.items():
        if k.startswith('MAY_') and k.endswith('_READS') and 'DISCOVERY' not in k and 'METADATA' not in k:assert v==0
    for c in ['submit_time','start_time','end_time']:assert panel[c].lt(pd.Timestamp('2025-04-24T00:00Z')).all()


@pytest.mark.parametrize('key,value',[('production_q_seconds',Q),('PF',.95),('Q_control','NO'),('electrical_regeneration','HOLD'),
                                    ('B0_B1_B2_B3','NO'),('FULL_MAY','NO'),('optimizer_integration','NO')])
def test_holds(key,value):assert get('SCOPE_CONTRACT')['holds'][key]==value


def test_adapter_exact_fields():
    assert get('RUNTIME_ADAPTER_PROPOSAL')['candidate_fields']==list(FIELDS)
    assert len(FIELDS)==10 and get('RUNTIME_ADAPTER_PROPOSAL')['records']==[]
    r=dict(zip(FIELDS,['x','BODY',100,200,.1,14400,False,'NONE',200,False]))
    assert validate_adapter(r,state='PENDING')
    with pytest.raises(ValueError):validate_adapter({**r,'migration':True},state='PENDING')


def test_committed_prereg_and_method_lock():
    for name,receipt in [('PREREGISTRATION','PREREGISTRATION_COMMIT_RECEIPT'),('METHOD_SELECTION','METHOD_SELECTION_COMMIT_RECEIPT')]:
        c=get(receipt)['commit']
        assert git('show',f'{c}:dayahead/artifacts/v40s3_body_tail_runtime_risk/V40S3_{name}.json',binary=True)==(OUT/f'V40S3_{name}.json').read_bytes()
    assert get('METHOD_SELECTION')['selected'] is None


def test_models_frozen_byte_exact():
    for name,digest in get('MODEL_FREEZE')['model_SHA256'].items():assert sha((OUT/'models'/name).read_bytes())==digest


def test_independent_determinism():
    rows=get('TRAINING_AUDIT')['models']
    pairs=[r for r in rows if 'independent_repeat_equal' in r]
    assert len(pairs)==35 and all(r['independent_repeat_equal'] and r['max_difference']==0 for r in pairs)


def test_no_eligible_method_hidden(results):
    keys={(r['u_hours'],r['body'],r['classifier'],r['policy']) for r in results if r['role']!='EXPOSED_EVALUATION'}
    for k in keys:
        rr=[r for r in results if (r['u_hours'],r['body'],r['classifier'],r['policy'])==k and r['role']!='EXPOSED_EVALUATION']
        assert not all(r['gates']['PASS'] for r in rr)


def test_amendment_before_any_model_result():
    a=get('PREREGISTRATION_AMENDMENT_01')
    assert a['new_model_fit_count_before_change']==a['new_prediction_count_before_change']==0
    assert not a['new_candidate_ranking_observed'] and not a['final_shadow_opened']
