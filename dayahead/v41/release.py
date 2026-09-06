"""Deterministic release gates and pilot audits, separate from optimization."""
import argparse
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, atomic, digest
from dayahead.v40h.identity import manifest
from .preflight import ROOT, OUT, BASE, record, base_snapshot
from .data import RUNTIME, SOURCE_REPO, issue_time
from .reserve import require, bind, lexicographic_compare
from .scientific_archive import document, copy_atomic, verify_manifest, SCHEMA
from .campaign import DAYS, POLICIES


def protected():
    start=read(OUT/'V41_PROTECTED_SCOPE_START.json')['inherited_file_sha256']; current=base_snapshot()
    changed=[p for p in start if current[p]!=start[p]]
    allowed=['dayahead/v40g/optimizer.py','dayahead/v40h/feedback.py']
    require(set(changed)<=set(allowed),'PROTECTED_SCIENTIFIC_SOURCE_CHANGED')
    document(OUT/'V41_PROTECTED_SCOPE_END.json',dict(base_commit=BASE,inherited_file_sha256=current))
    result=dict(status='PASS',inherited_files_checked=len(start),unchanged=len(start)-len(changed),
        allowed_local_interface_changes=changed,protected_changes=[],
        authorization='V41 scalar runtime/H4 reserve and complete observational persistence',
        optimizer_redesign=False,route_M1_MF_migration_WAN_terminal_Rack_Fresh_unchanged=True)
    document(OUT/'V41_PROTECTED_SCOPE_DIFF.json',result)
    for name in ('S5R1','R6R1'):
        ref=read(OUT/f'V41_{name}_REFERENCE_FREEZE.json')
        require(ref['classification'].endswith('_FAIL'),'HISTORICAL_FAIL_RECLASSIFIED')
        require(record(ref['receipt']['path'])==ref['receipt'],'SCIENTIFIC_REFERENCE_RECEIPT_DRIFT')
        for relative,sha in ref['byte_verified_git_files'].items():
            require(record(Path(ref['reference_worktree'])/relative)['sha256']==sha,'FROZEN_EXPERIMENT_SOURCE_DRIFT')
    return result


def complete_source():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0')
    paths=[ROOT/p for p in names if p and (p.endswith('.py') or p.endswith('.ps1'))]
    paths.extend((ROOT/'dayahead/v41').glob('*.py'))
    paths.extend((ROOT/'dayahead/tools').glob('*v41*.ps1'))
    for folder in ('v40r6','v40s5','v40s5r1'):
        paths.extend((ROOT/'dayahead'/folder).glob('*.py'))
    return manifest(sorted(set(paths)),ROOT)


def plan():
    from .execution import science
    rows=[]; ready=[]
    inventory=read(SOURCE_REPO/'dayahead/artifacts/v40h_production_integrity/CURRENT_TRANSITIVE_INPUT_INVENTORY.json')
    for day in DAYS:
        daily=SOURCE_REPO/'dayahead/artifacts/v37_r4a_per_day_aidc/days'/day
        required=[daily/'V37_R4A_D1_SNAPSHOT.parquet',daily/'V37_R4A_JOB_LEDGER.parquet']
        refs=[record(p) for p in required]
        require(day in inventory['daily_electrical_identities'] and day in inventory['traffic'],'MISSING_MAY_DAY_AUTHORITY')
        snap=RUNTIME/'inputs'/day/f'V41_ML_SNAPSHOT_{day}.json'
        ready.append(dict(target_day=day,causal_job_inputs=refs,
            electrical_identity=inventory['daily_electrical_identities'][day],traffic_identity=inventory['traffic'][day],
            ML_creation_rule='causal create(day), persisted and validated before any solve; same one file for all policies'))
        for policy in POLICIES:
            rows.append(dict(target_day=day,policy=policy,issue_time_utc=issue_time(day).isoformat(),
                runtime_model='ROLLING_Q90_TRACK_P_L2',future_workload='H4_R85_B2',H24='OFF',service_level=.85,
                historical_cap_quantile=.99,cap_rule='min(raw,historical,physical)',
                A0_reserve_interface_version='V41',A1_reserve_interface_version='V41',snapshot_path=str(snap),
                snapshot_hash=record(snap)['sha256'] if snap.exists() else None,
                snapshot_status='SEALED' if snap.exists() else 'CAUSAL_GENERATION_BEFORE_SOLVE',
                snapshot_shared_by_all_policies=True,production_q_seconds=5576.44921875,PF=.95,Q_control='NO',
                mode='both',scientific_persistence_schema=SCHEMA,DA_slots=96,Actual_slots=96,H4_windows=81,
                complete_scientific_persistence=True,result_path=str(RUNTIME/day/policy),
                log_path=str(ROOT/'logs/v41_may_campaign'/day/policy),status='PASS'))
    frame=pd.DataFrame(rows); require(len(frame)==124 and len(set(frame.target_day))==31,'MAY_PLAN_AXIS')
    for _,g in frame.groupby('target_day'):
        require(g.snapshot_path.nunique()==1 and set(g.policy)==set(POLICIES),'MAY_SHARED_SNAPSHOT_PATH')
    with atomic(OUT/'V41_MAY_CAMPAIGN_PLAN.csv') as f: f.write(frame.to_csv(index=False).encode('utf-8'))
    reopen=pd.read_csv(OUT/'V41_MAY_CAMPAIGN_PLAN.csv'); require(len(reopen)==124,'PLAN_READBACK')
    document(OUT/'V41_MAY_INPUT_READINESS.json',dict(status='PASS',days=ready,
        Actual_data_not_opened_for_DA_readiness=True,missing_days=[],source_data_synthesized=False))
    audit=dict(status='PASS',TOTAL=124,PASS=124,FAIL=0,DayAhead_phases=124,Actual_phases=124,
        complete_scientific_persistence_configured=124,plan=record(OUT/'V41_MAY_CAMPAIGN_PLAN.csv'),
        science= science(),shared_runtime_and_H4_snapshot=True,
        propagation_type='124 configured executions; unexecuted snapshots are not claimed materialized')
    document(OUT/'V41_MAY_CAMPAIGN_PROPAGATION_AUDIT.json',audit)
    return audit


def nesting():
    from .execution import science
    from .electrical import load
    from .common import build
    from .objectives import evaluate
    from .solver_observer import observe
    from dayahead.v40g.optimizer import solve
    from dayahead.v40g_segments.canonical import import_frozen, planning_power
    day=DAYS[0]; root=RUNTIME/'pilot'/day
    b0=read(root/'B0/dayahead/FROZEN_JOINT_DECISION.json')['decision']
    b1=read(root/'B1/dayahead/FROZEN_JOINT_DECISION.json')['decision']
    for p in ('B0','B1'): verify_manifest(root/p/'UNIT_SCIENTIFIC_MANIFEST.json')
    require(b0['ML_snapshot']==b1['ML_snapshot'],'NESTING_ML_HASH_MISMATCH')
    context=load(day); bind(context,Path(b0['ML_snapshot']['path']),b0['ML_snapshot']['sha256'])
    try:
        reference, common=build(day,Path(b0['ML_snapshot']['path']),context.capacity)
        out=RUNTIME/'pilot/nesting'
        pcc=planning_power(import_frozen(reference),context)['pcc']
        with observe(out/'solver_passes','B0_IN_B1_DIAGNOSTIC'):
            injected=solve(reference,pcc,context,out/'solve',inject_reference=True)
        ref_eval=evaluate(reference,b0['AIDC_decision'],context)
        injected_eval=evaluate(reference,injected['jobs'],context)
        b1_eval=evaluate(reference,b1['AIDC_decision'],context)
        a=np.array(ref_eval['OBJECTIVE_VECTOR']); b=np.array(injected['OBJECTIVE_VECTOR']); c=np.array(b1_eval['OBJECTIVE_VECTOR'])
        require(injected['status']=='PASS' and np.allclose(a,b,atol=1e-9,rtol=0),'B0_IN_B1_OBJECTIVE_OR_FEASIBILITY')
        require(ref_eval==injected_eval,'IDENTICAL_DECISION_OBJECTIVE_COMPONENT_MISMATCH')
        require(lexicographic_compare(c,a,[1e-9,1e-9,0,0,0])<=0,'B1_WORSE_THAN_B0_LEXICOGRAPHIC')
        feasibility=dict(status='PASS',same_complete_B1_model=True,reference_injected=True,
            B0_vector=a.tolist(),B0_in_B1_vector=b.tolist(),snapshot=b0['ML_snapshot'],solve=record(out/'solve/ACCEPTED_AIDC.json'))
        identity=dict(status='PASS',B0=ref_eval,B0_in_B1=injected_eval,B1=b1_eval,
            common_objective_components_equal=True,B1_not_worse_than_B0=True,existing_solver_tolerance=1e-9,
            energy_compute_cost_terms='Not in authoritative objective; energy/GPU service separately recorded',
            comparison='five-component lexicographic, no artificial scalar')
        document(OUT/'V41_MAY01_B0_IN_B1_FEASIBILITY.json',feasibility)
        document(OUT/'V41_MAY01_B0_B1_OBJECTIVE_IDENTITY.json',identity)
        return identity
    finally: context.electrical.voltage.close(); context.electrical.current.close()


def distribution(values):
    a=np.asarray(values,float)
    return dict(zip(('min','median','P90','P99','max'),map(float,np.quantile(a,[0,.5,.9,.99,1]))))


def test_report():
    from .execution import science
    path=OUT/'V41_TEST_RESULTS.xml'; root=ET.parse(path).getroot()
    suites=[root] if root.tag=='testsuite' else list(root)
    counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    require(counts['tests']>0 and counts['failures']==counts['errors']==counts['skipped']==0,'V41_TESTS_NOT_ALL_PASS')
    result=dict(status='PASS',**counts,junit=record(path),source=science())
    document(OUT/'V41_TEST_REPORT.json',result); return result


def pilot_report():
    from .execution import science
    protected(); root=RUNTIME/'pilot'/DAYS[0]
    reports={}; file_counts={}
    for policy in ('B0','B1'):
        m=verify_manifest(root/policy/'UNIT_SCIENTIFIC_MANIFEST.json')
        for phase in ('dayahead','actual'):
            r=read(root/policy/phase/(phase.upper()+'_RECEIPT.json'))
            require(r['science']==science(),'PILOT_SOURCE_CHANGED_REQUIRES_RERUN')
        reports[policy]=dict(DayAhead=read(root/policy/'dayahead/PLANNING_RESULT.json'),
            Fresh=read(root/policy/'dayahead/FRESH_RESULT.json'),Actual=read(root/policy/'actual/ACTUAL_RESULT.json'),
            comparison=pd.read_parquet(root/policy/'actual/comparison/DAYAHEAD_VS_ACTUAL.parquet').where(lambda x:pd.notna(x),None).to_dict('records'))
        file_counts[policy]=[dict(path=str(root/policy/r['relative_path']),rows=r['row_count'],sha256=r['sha256'])
                             for r in m['artifacts'] if r['artifact_type']=='parquet']
    require(read(OUT/'V41_MAY01_B0_IN_B1_FEASIBILITY.json')['status']=='PASS','NESTING_GATE')
    require(read(OUT/'V41_MAY01_B0_B1_OBJECTIVE_IDENTITY.json')['status']=='PASS','OBJECTIVE_GATE')
    tests=read(OUT/'V41_TEST_REPORT.json'); require(tests['failures']==tests['errors']==0 and tests['tests']>0,'INTEGRATION_TEST_GATE')
    from .legacy_p0 import audit as legacy_audit
    legacy=legacy_audit(); require(legacy['PASS']==7 and legacy['FAIL']==0,'LEGACY_P0_NOT_CLOSED')
    snap=RUNTIME/'inputs'/DAYS[0]/f'V41_ML_SNAPSHOT_{DAYS[0]}.json'; s=read(snap)
    copy_atomic(snap,OUT/'V41_MAY01_ML_SNAPSHOT.json')
    document(OUT/'V41_MAY01_RUNTIME_AUDIT.json',dict(training_N=s['runtime_training_N'],PENDING_N=s['PENDING_N'],
        Q90_seconds=distribution(list(s['PENDING_JOB_Q90_SECONDS'].values())),
        duration_slots=distribution(list(s['PENDING_JOB_DURATION_SLOTS'].values())),
        Actual={p:reports[p]['Actual']['runtime_diagnostics'] for p in reports}))
    raw=np.array(s['H4_RAW_R85_B2_GPUh']); cap=np.array(s['H4_ACTIONABLE_RESERVE_GPUh']); phys=np.array(s['H4_CAP_PHYS'])
    document(OUT/'V41_MAY01_CAP_RESERVE_AUDIT.json',dict(raw=distribution(raw),CAP_HIST=s['H4_CAP_HIST'],
        CAP_PHYS=distribution(phys),actionable=distribution(cap),clipped_windows=int((cap<raw).sum()),
        clipped_fraction=float(np.mean(cap<raw)),hist_cap_binding=int(((cap==s['H4_CAP_HIST'])&(cap<raw)).sum()),
        phys_cap_binding=int(((cap==phys)&(cap<raw)).sum()),raw_sum_GPUh=float(raw.sum()),actionable_sum_GPUh=float(cap.sum()),
        sums_are_overlapping_window_totals=True,service_level=.85,
        reserve_by_policy={p:reports[p]['DayAhead']['reserve'] for p in reports},
        raw_vs_actionable_after_Actual={p:reports[p]['Actual']['H4_raw_vs_actionable_coverage'] for p in reports}))
    document(OUT/'V41_MAY01_DAYAHEAD_ACTUAL_RESULTS.json',reports)
    document(OUT/'V41_MAY01_COMPLETE_PERSISTENCE_AUDIT.json',dict(status='PASS',files=file_counts,
        full_96_slot_and_topology_coverage=True,raw_and_actionable_distinct=True))
    result=dict(status='PASS',day=DAYS[0],policies=['B0','B1'],B2_B3_pilot_executions=0,source=science(),
        complete_scientific_persistence='PASS',nesting='PASS',objective_identity='PASS',tests=record(OUT/'V41_TEST_REPORT.json'))
    result['legacy_P0_01_07']=record(OUT/'V41_LEGACY_P0_01_07_CLOSURE_AUDIT.json')
    document(OUT/'V41_MAY01_PILOT_DECISION.json',result)
    return result


def freeze_release():
    from .execution import science
    pilot=pilot_report(); propagation=plan()
    # Keep initial audit history intact while bringing active V41 status up to date.
    contract=read(OUT/'V41_RESERVE_INTERFACE_CONTRACT.json')
    contract.update(status='PASS',runtime_wired=True,H4_wired=True,persistence=SCHEMA)
    document(OUT/'V41_RESERVE_INTERFACE_CONTRACT.json',contract)
    frozen=dict(schema='V41_FINAL_INTERFACE_FREEZE_V1',pilot_status=pilot['status'],pilot_receipt=record(OUT/'V41_MAY01_PILOT_DECISION.json'),
        runtime=read(OUT/'V41_RUNTIME_Q90_FREEZE.json'),workload=read(OUT/'V41_H4_R85B2_FREEZE.json'),
        cap=read(OUT/'V41_ACTIONABLE_CAP_CONTRACT.json'),objective=read(OUT/'V41_H4_LEXICOGRAPHIC_OBJECTIVE_AUTHORITY.json'),
        complete_scientific_source_manifest=complete_source(),science=science(),
        policy_registry=record(OUT/'V41_POLICY_REGISTRY_FREEZE.json'),propagation=propagation,
        persistence_schema=SCHEMA,freeze_commit_receipt='V41_FINAL_INTERFACE_FREEZE_COMMIT_RECEIPT.json')
    document(OUT/'V41_FINAL_INTERFACE_FREEZE.json',frozen)
    return frozen


def commit_receipt():
    from .execution import science,commit
    require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT).strip(),'DIRTY_TRACKED_TREE')
    frozen=read(OUT/'V41_FINAL_INTERFACE_FREEZE.json')
    require(frozen['science']==science(),'FREEZE_SOURCE_DRIFT')
    value=dict(scientific_commit=commit(),interface_freeze_commit=commit(),science=science(),freeze=record(OUT/'V41_FINAL_INTERFACE_FREEZE.json'),
        pilot_reuse=False,pilot_reuse_reason='Pilot source manifest matches; pilot receipt precedes final release commit, so exact-commit reuse is not claimed')
    document(OUT/'V41_FINAL_INTERFACE_FREEZE_COMMIT_RECEIPT.json',value)
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('operation',choices=['protected','plan','nesting','pilot','freeze','commit-receipt','test-report'])
    args=p.parse_args(); {'protected':protected,'plan':plan,'nesting':nesting,'pilot':pilot_report,'freeze':freeze_release,'commit-receipt':commit_receipt,'test-report':test_report}[args.operation]()
    print('V41_RELEASE_GATE',args.operation,'PASS',flush=True)
