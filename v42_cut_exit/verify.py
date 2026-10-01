"""Final validation without optimization or scientific-stage execution."""
import csv,gzip,subprocess,xml.etree.ElementTree as ET
from .context import *
from .report import REQUIRED
from .policy import select,isolation_allowed
def run():
    check_sources();manifest=read(OUT/'SOURCE_MANIFEST.json')
    for r in manifest['reporting_sources']:assert sha(ROOT/r['path'])==r['sha256'],r['path']
    assert all((OUT/n).exists() for n in REQUIRED if n!='VERIFICATION.json')
    a,b=[read(OUT/(n+'_OPTIMIZATION.json')) for n in ['CP0','CP1']];policy=read(OUT/'SOLVER_POLICY_SELECTION.json');expected=select(a,b)
    assert all(policy[k]==expected[k] for k in expected)
    optional=read(OUT/'OPTIONAL_HEURISTIC_ISOLATION.json');assert optional['run']==optional['authorized']==isolation_allowed(a,b)
    done=read(LOCAL/'EXPERIMENT_FINISHED.json');assert done['production']==policy['production_authorized']
    labels=['CP0','CP1']+(['CP0_H0'] if optional['run'] else [])+(['M1'] if done['production'] else [])
    assert sorted(p.parent.name for p in LOCAL.glob('*/STARTED.json'))==sorted(labels)
    assert a['settings'].keys()==b['settings'].keys()
    assert [k for k in a['settings'] if a['settings'][k]!=b['settings'][k]]==['CutPasses']
    fingerprint=read(OUT/'M1_F3_REBUILD_RECEIPT.json')['fingerprint']
    for label in labels:
        prefix='M1_PRODUCTION' if label=='M1' else label;r=read(OUT/(prefix+'_OPTIMIZATION.json'));s=r['settings']
        assert r['model_fingerprint']==fingerprint and not r['formulation_changed'] and r['A1_optimize_calls']==0
        assert s['Method']==2 and s['Threads']==1 and s['Seed']==20260929 and s['MIPGap']==.005 and s['NodeLimit'] is None
        assert s['Cuts']==-1 and s['MIPFocus']==0 and s['Presolve']==-1 and s['NumericFocus']==0
        assert s['Heuristics']==(0 if label=='CP0_H0' else .05)
        assert s['TimeLimit']==(1800 if label=='M1' else 300 if label=='CP0_H0' else 600)
        assert r['total_optimize_seconds']<=s['TimeLimit']+5
        assert all(p['MIP_start_accepted'] for p in r['passes'])
        if label!='M1':assert len(r['passes'])==1
        if not r['passes'][0]['quality_PASS']:assert len(r['passes'])==1
        raw=(LOCAL/label/'GUROBI.log').read_bytes();assert gzip.decompress((OUT/(prefix+'_SOLVER.raw.gz')).read_bytes())==raw
        assert sha(LOCAL/label/'GUROBI.log')==r['native_log_sha256']
    for row in read(OUT/'PR107_BASELINE_REUSE.json')['files']:assert sha(ROOT/row['path'])==row['sha256']
    for row in read(OUT/'PR107_A1_ANCHOR_REUSE.json')['files']:assert sha(OUT/row['path'])==row['sha256']==row['PR107_sha256']
    flags=read(OUT/'FINAL_FLAGS.json');assert flags['ROOT_POLICY_DIAGNOSIS']=='ROOT_LOOP_POLICY_EFFECT'
    assert not any(flags[k] for k in ['FORMULATION_CHANGED_THIS_TASK','SCIENTIFIC_PHYSICS_CHANGED','CANDIDATE_DOMAIN_CHANGED','A1_RERUN','GPU_USED','BASELINE_RERUN','ACTUAL_P_CORRECTION_ENABLED','ACTUAL_Q_CORRECTION_ENABLED','ACTUAL_LOCAL_REPAIR_ENABLED','PROBLEM13_FINAL_VALIDATED','A2_RUN','M2_RUN','ACTUAL_RUN','FRESH_AC_RUN','IEEE8500_RUN'])
    assert flags['A1_OPTIMIZE_CALLS']==0 and flags['M1_ROBUST_VOLTAGE_MIN']==.955 and flags['M1_ROBUST_VOLTAGE_MAX']==1.045
    bundle,anchor,prior,sites,initial,routes,battery=inputs();source='M1' if done['production'] else policy['selected'];plan=read(LOCAL/source/'FINAL_PLAN.json');controls=controls_from_plan(plan,anchor)
    assert validate(plan,sites,routes,battery,96)['PASS'] and supplemental_physical(plan,sites,battery)['charge_mode_and_connection_PASS'] and grid_report(bundle,controls,plan['values']['rho_max'])['PASS']
    assert plan['domain_sha256']==prior['domain_sha256']
    assert all(abs(plan['values'][f'SOC[{u},0]']-battery.initial)<=1e-5 for u in initial)
    assert all(controls[t][i]==anchor['controls'][t][i] for t in range(96) for i in anchor['fixed_AIDC_control_columns'])
    accepted=read(OUT/'M1_ACCEPTANCE.json')
    if accepted['M1_ACCEPTED']:assert accepted['production_run'] and accepted['P1_quality_PASS'] and accepted['P2_complete'] and accepted['physical_PASS'] and accepted['robust_grid_PASS'] and accepted['anchor_identity_PASS']
    with (OUT/'M1_Q_UTILIZATION.csv').open(encoding='utf8',newline='') as file:qr=list(csv.DictReader(file))
    assert len(qr)==384
    for row in qr:
        if row['connected']=='True':
            available=np.sqrt(max(0,battery.pcs_kva**2-float(row['P_kw'])**2));assert abs(available-float(row['Q_available_kvar']))<1e-8
            if available>1e-6:assert abs(abs(float(row['Q_kvar']))/available-float(row['utilization']))<1e-8
    suite=ET.parse(OUT/'TEST_RESULTS.xml').getroot().find('testsuite');assert int(suite.attrib['tests'])>=503 and int(suite.attrib['errors'])==int(suite.attrib['failures'])==0
    for cmd in [['git','diff','--check'],['git','diff','--cached','--check']]:assert subprocess.run(cmd,cwd=ROOT,capture_output=True).returncode==0
    files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='VERIFICATION.json']
    dump('VERIFICATION.json',dict(PASS=True,tests=int(suite.attrib['tests']),A1_optimize_calls=0,baseline_rerun=False,CP0_runs=1,CP1_runs=1,H0_runs=int(optional['run']),production_runs=int(done['production']),legacy_all_bytes_preserved=True,formulation_fingerprint_identity=True,executed_sources_unchanged=True,independent_physical_PASS=True,robust_grid_PASS=True,full_domain_unchanged=True,original_solver_logs_preserved=True,diagnostic_interpretation='ROOT_LOOP_POLICY_EFFECT',no_specific_cut_causal_attribution=True,files=files))
    print('VERIFICATION PASS',suite.attrib['tests'],flush=True)
if __name__=='__main__':run()
