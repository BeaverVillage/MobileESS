"""Read-only final seals, proof arithmetic, handoff and measurements audit."""
import csv,subprocess,xml.etree.ElementTree as ET
import numpy as np
from v42_root.common import *
from .a1 import check_sources
from .report import REQUIRED
from .handoff import validate_handoff

def verify():
    check_sources()
    changed=[r['path'] for r in read(OUT/'A1_EXECUTED_SOURCE_MANIFEST.json')['sources'] if sha(ROOT/r['path'])!=r['sha256']]
    assert changed==['v42_bootstrap/handoff.py'],changed
    recovery=read(OUT/'A1_EXPORT_RECOVERY_RECEIPT.json')
    assert recovery['PASS'] and recovery['optimize_calls']==0 and recovery['electrical_controls_unchanged'] and recovery['selected_plan_unchanged']
    m1_changed=[r['path'] for r in read(OUT/'M1_EXECUTED_SOURCE_MANIFEST.json')['sources'] if sha(ROOT/r['path'])!=r['sha256']]
    assert set(m1_changed)<={'v42_bootstrap/report.py','v42_bootstrap/verify.py'},m1_changed
    baseline=ROOT.parent/'v42_voltage_margin_pr'
    for r in read(OUT/'PR105_INFEASIBILITY_PRESERVATION.json')['files']:
        assert sha(ROOT/r['path'])==r['sha256']==sha(baseline/r['path'])
    assert all((OUT/n).is_file() for n in REQUIRED if n!='VERIFICATION.json')
    f=read(OUT/'FINAL_FLAGS.json');a=read(OUT/'A1_BOOTSTRAP_OPTIMIZATION.json');m=read(OUT/'M1_OPTIMIZATION.json')
    assert not any(f[k] for k in ('A2_RUN','M2_RUN','ACTUAL_RUN','FRESH_AC_RUN','IEEE8500_RUN','PROBLEM13_FINAL_VALIDATED','ACTUAL_LOCAL_PQ_REPAIR_ENABLED','ACTUAL_Q_CORRECTION_ENABLED','ACTUAL_P_CORRECTION_ENABLED'))
    assert f['FINAL_SCIENTIFIC_OBJECTIVE_COUNT']==2 and f['M1_AIDC_DECISION_VARIABLES']==0
    astats=read(OUT/'A1_BOOTSTRAP_MODEL_STATS.json')
    assert astats['jobs_complete']==1499 and astats['scientific_classes']==117
    assert a['settings']['Threads']==1 and a['settings']['MIPGap']==.005 and a['settings']['GPU'] is False
    assert a['total_optimize_seconds']<=3605
    if a['complete']:
        assert len(a['passes'])==4 and all(r['status']==2 for r in a['passes'])
        assert read(OUT/'A1_BOOTSTRAP_PHYSICAL_VALIDATION.json')['PASS'] and read(OUT/'A1_BOOTSTRAP_VOLTAGE_REPORT.json')['PASS']
        anchor=read(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json');h=read(OUT/'A1_TO_M1_HANDOFF.json');validate_handoff(h,anchor)
        assert len(anchor['controls'])==96 and all(len(r)==60 for r in anchor['controls'])
        assert h['anchor_file_sha256']==sha(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json')
        for key,name in [('table_sha256','A1_PROVISIONAL_CONTROL_TABLE.csv'),('unknown_policy_sha256','A1_UNKNOWN_POLICY_TABLE.json'),('site_time_sha256','A1_AIDC_SITE_TIME_ANCHOR.csv')]:assert h[key]==sha(OUT/name)
        with (OUT/'A1_PROVISIONAL_CONTROL_TABLE.csv').open(encoding='utf8',newline='') as file:rows=list(csv.DictReader(file))
        assert len(rows)==len(set(r['job_uid'] for r in rows))==1499
        assert set(r['job_uid'] for r in rows)==set(read(LOCAL/'replay/SELECTED_PHYSICAL.json'))
        assert read(OUT/'A1_UNKNOWN_POLICY_TABLE.json')['individual_future_jobs']==[]
        with (OUT/'A1_AIDC_SITE_TIME_ANCHOR.csv').open(encoding='utf8',newline='') as file:cells=list(csv.DictReader(file))
        assert len(cells)==12*96
        for r in cells:
            t=int(r['control_slot']);i=anchor['control_names'].index(f"aidc_load_kw[{r['site']}]")
            assert float(r['AIDC_kW'])==anchor['controls'][t][i]
            assert abs(float(r['total_GPU'])-float(r['known_GPU'])-float(r['anonymous_GPU']))<1e-8
        interval=read(OUT/'M1_MESS_PQ_VOLTAGE_INTERVAL_DIAGNOSIS.json')
        assert interval['impossible_count']==len(interval['impossible_rows'])
        for row in interval['impossible_rows']:
            w=np.array(row['coefficients']);lo=np.array(row['lower_controls']);hi=np.array(row['upper_controls'])
            lower=row['voltage_constant']+np.maximum(w,0)@lo+np.minimum(w,0)@hi
            upper=row['voltage_constant']+np.maximum(w,0)@hi+np.minimum(w,0)@lo
            assert abs(lower-row['minimum_squared'])<1e-12 and abs(upper-row['maximum_squared'])<1e-12
            assert lower>1.092025+1e-8 or upper<.912025-1e-8
        if not interval['PASS']:
            assert not f['M1_RUN'] and not (LOCAL/'M1/STARTED.json').exists()
            assert f['M1_BOTTLENECK']=='PREFLIGHT_STATIC_INFEASIBILITY'
    if f['M1_RUN']:
        assert m['settings']['Threads']==1 and m['settings']['Seed']==20260929 and m['settings']['MIPGap']==.005 and m['settings']['GPU'] is False
        assert m['total_optimize_seconds']<=1805
        stats=read(OUT/'M1_MODEL_STATS.json');assert stats['AIDC_decision_variables']==0
        assert all(stats['family_columns'][k]>0 for k in ('arc','Pch','Pdis','Q','SOC','charge_mode'))
        assert stats['quadratic_constraints']==stats['SOS']==stats['general_constraints']==stats['quadratic_objective_terms']==0
        snapshots=read(OUT/'M1_TELEMETRY_SNAPSHOTS.json');assert snapshots['all_requested_targets_observed']
        assert [r['requested_optimize_seconds'] for r in snapshots['snapshots']]==[60,300,600,1200,1800]
        for r in snapshots['snapshots']:assert r['selected']['measurement']['optimize_seconds']>=r['requested_optimize_seconds']
        raw=read(OUT/'M1_OPTIMIZATION_NATIVE_RAW.json');assert raw['passes'][0]['incumbent']==m['passes'][0]['incumbent'] and raw['passes'][0]['bound']==m['passes'][0]['bound']
        assert m['passes'][0]['root']['status']=='time limit' and m['passes'][0]['root']['iterations']==217222
        assert f['M1_BOTTLENECK']=='ROOT_LP' and not f['M1_ROBUST_ACCEPTED'] and len(m['passes'])==1
        with (OUT/'M1_Q_UTILIZATION.csv').open(encoding='utf8',newline='') as file:qrows=list(csv.DictReader(file))
        connected=[r for r in qrows if r['connected']=='True'];assert len(qrows)==384 and len(connected)==384
        for r in connected:
            expected=np.sqrt(max(0,400**2-float(r['P_kw'])**2));assert abs(expected-float(r['Q_available_kvar']))<1e-8
            assert abs(abs(float(r['Q_kvar']))/expected-float(r['utilization']))<1e-10
        block=read(OUT/'PR105_BLOCKER_M1_RESOLUTION.json');assert block['resolved'] and block['causal_Q_alone_claim'] is False and block['M1_ROBUST_ACCEPTED'] is False
        summed=block['voltage_constant_squared']+block['fixed_AIDC_contribution_squared']+block['aggregate_MESS_P_contribution_squared']+block['aggregate_MESS_Q_contribution_squared']
        assert abs(summed-block['M1_squared_voltage'])<1e-12
        if m['accepted']:
            assert len(m['passes'])==3 and all(r['status']==2 for r in m['passes'])
            assert read(OUT/'M1_PHYSICAL_VALIDATION.json')['PASS'] and read(OUT/'M1_ROBUST_VOLTAGE_REPORT.json')['PASS']
    suite=ET.parse(OUT/'TEST_RESULTS.xml').getroot().find('testsuite')
    assert int(suite.attrib['tests'])>=480 and int(suite.attrib['errors'])==int(suite.attrib['failures'])==0
    for args in (['git','diff','--check'],['git','diff','--cached','--check']):
        r=subprocess.run(args,cwd=ROOT,capture_output=True);assert r.returncode==0,(r.stdout+r.stderr).decode('utf8',errors='replace')
    evidence=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='VERIFICATION.json']
    dump('VERIFICATION.json',dict(PASS=True,tests=int(suite.attrib['tests']),failures=0,errors=0,required_outputs=len(REQUIRED),
         PR105_evidence_byte_identical=True,A1_executed_scientific_sources_unchanged=True,A1_export_only_fix=changed,A1_export_recovery_zero_optimize=True,current_source_seals_PASS=True,preflight_proof_arithmetic_PASS=True,
         M1_executed_model_and_solver_sources_unchanged=True,M1_post_run_reporting_source_changes=m1_changed,
         hash_handoff_PASS=bool(a['complete']),production_runs=dict(A1=f['A1_RUN'],M1=f['M1_RUN'],A2=False,M2=False,Actual=False,Fresh_AC=False,IEEE8500=False),
         git_diff_check=True,files=evidence))
    print('FINAL VERIFICATION PASS',suite.attrib['tests'],'tests',flush=True)

if __name__=='__main__':verify()
