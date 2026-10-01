"""Check revised scope, proof gate, immutable science and physical evidence."""
import csv,gzip,subprocess,xml.etree.ElementTree as ET
from .context import *
from .proof_context import check_proof_sources
from .proof_policy import select,degen_diagnostic_allowed
from .report import REQUIRED
def run():
    check_proof_sources();manifest=read(OUT/'FINAL_SOURCE_MANIFEST.json')
    assert manifest['CP0_manifest_sha256']==sha(OUT/'SOURCE_MANIFEST.json')
    assert manifest['proof_manifest_sha256']==sha(OUT/'PROOF_SOURCE_MANIFEST.json')
    for row in manifest['sources']:assert sha(ROOT/row['path'])==row['sha256'],row['path']
    assert all((OUT/n).exists() for n in REQUIRED if n!='VERIFICATION.json')
    done=read(LOCAL/'PROOF_EXPERIMENT_FINISHED.json');primary=read(OUT/'PROOF_AUTO_OPTIMIZATION.json');policy=read(OUT/'SOLVER_POLICY_SELECTION.json');cp=read(OUT/'CP0_OPTIMIZATION.json')
    assert cp['passes'][0]['status']==11 and cp['total_optimize_seconds']<600
    assert read(OUT/'CP0_PARTIAL_DIAGNOSTIC.json')['partial_diagnostic'] and not read(OUT/'CP1_OPTIMIZATION.json')['run']
    assert done['DG0']==degen_diagnostic_allowed(primary)
    results=[primary]+([read(OUT/'PROOF_DG0_OPTIMIZATION.json')] if done['DG0'] else [])
    expected=select(results);assert all(policy[k]==expected[k] for k in expected)
    assert done['production']==policy['production_authorized']
    labels=['CP0','PROOF_AUTO']+(['PROOF_DG0'] if done['DG0'] else [])+(['M1_PROOF'] if done['production'] else [])
    assert sorted(p.parent.name for p in LOCAL.glob('*/STARTED.json'))==sorted(labels)
    if done['DG0']:
        a,b=[r['settings'] for r in results];assert [k for k in a if a[k]!=b[k]]==['DegenMoves']
    fp=read(OUT/'M1_F3_REBUILD_RECEIPT.json')['fingerprint']
    for label in labels:
        prefix='M1_PRODUCTION' if label=='M1_PROOF' else label;r=read(OUT/(prefix+'_OPTIMIZATION.json'));s=r['settings']
        assert r['model_fingerprint']==fp and not r['formulation_changed'] and r['A1_optimize_calls']==0
        assert s['Method']==2 and s['Threads']==1 and s['Seed']==20260929 and s['MIPGap']==.005 and s['NodeLimit'] is None
        assert s['Cuts']==-1 and s['Presolve']==-1 and s['NumericFocus']==0
        assert s['MIPFocus']==(0 if label=='CP0' else 3)
        assert s['Heuristics']==(.05 if label=='CP0' else 0)
        assert s['CutPasses']==(0 if label=='CP0' else -1)
        if label!='CP0':assert s['DegenMoves']==(0 if label=='PROOF_DG0' else policy['DegenMoves'] if label=='M1_PROOF' else -1)
        assert r['total_optimize_seconds']<=s['TimeLimit']+5
        assert r['passes'][0]['MIP_start_accepted']
        if label!='M1_PROOF' or not r['passes'][0]['quality_PASS']:assert len(r['passes'])==1
        assert gzip.decompress((OUT/(prefix+'_SOLVER.raw.gz')).read_bytes())==(LOCAL/label/'GUROBI.log').read_bytes()
        assert sha(LOCAL/label/'GUROBI.log')==r['native_log_sha256']
    for row in read(OUT/'PR107_BASELINE_REUSE.json')['files']:assert sha(ROOT/row['path'])==row['sha256']
    for row in read(OUT/'PR107_A1_ANCHOR_REUSE.json')['files']:assert sha(OUT/row['path'])==row['sha256']==row['PR107_sha256']
    flags=read(OUT/'FINAL_FLAGS.json');assert flags['DIAGNOSTIC_INTERPRETATION']=='ROOT_LOOP_POLICY_EFFECT'
    assert not any(flags[k] for k in ['FORMULATION_CHANGED_THIS_TASK','SCIENTIFIC_PHYSICS_CHANGED','CANDIDATE_DOMAIN_CHANGED','A1_RERUN','GPU_USED','BASELINE_RERUN','CP1_RUN','ACTUAL_P_CORRECTION_ENABLED','ACTUAL_Q_CORRECTION_ENABLED','ACTUAL_LOCAL_REPAIR_ENABLED','PROBLEM13_FINAL_VALIDATED','A2_RUN','M2_RUN','ACTUAL_RUN','FRESH_AC_RUN','IEEE8500_RUN','HEURISTIC_IMPROVEMENT_ACCEPTANCE_BASIS','FIRST_BRANCH_PRODUCTION_GATE'])
    assert flags['A1_OPTIMIZE_CALLS']==0 and flags['SELECTED_CUTPASSES']=='AUTO' and flags['CUTS']==flags['INDIVIDUAL_CUT_FAMILIES']=='AUTO'
    assert flags['M1_ROBUST_VOLTAGE_MIN']==.955 and flags['M1_ROBUST_VOLTAGE_MAX']==1.045
    bundle,anchor,prior,sites,initial,routes,battery=inputs();source='M1_PROOF' if done['production'] else policy['selected'];plan=read(LOCAL/source/'FINAL_PLAN.json');controls=controls_from_plan(plan,anchor)
    assert validate(plan,sites,routes,battery,96)['PASS'] and supplemental_physical(plan,sites,battery)['charge_mode_and_connection_PASS'] and grid_report(bundle,controls,plan['values']['rho_max'])['PASS']
    assert plan['domain_sha256']==prior['domain_sha256'] and all(abs(plan['values'][f'SOC[{u},0]']-battery.initial)<=1e-5 for u in initial)
    assert all(controls[t][i]==anchor['controls'][t][i] for t in range(96) for i in anchor['fixed_AIDC_control_columns'])
    accepted=read(OUT/'M1_ACCEPTANCE.json')
    if accepted['M1_ACCEPTED']:assert all(accepted[k] for k in ['production_run','P1_quality_PASS','P2_complete','physical_PASS','robust_grid_PASS','anchor_identity_PASS'])
    with (OUT/'M1_Q_UTILIZATION.csv').open(encoding='utf8',newline='') as file:qr=list(csv.DictReader(file))
    assert len(qr)==384
    for row in qr:
        if row['connected']=='True':
            available=np.sqrt(max(0,battery.pcs_kva**2-float(row['P_kw'])**2));assert abs(available-float(row['Q_available_kvar']))<1e-8
            if available>1e-6:assert abs(abs(float(row['Q_kvar']))/available-float(row['utilization']))<1e-8
    suite=ET.parse(OUT/'TEST_RESULTS.xml').getroot().find('testsuite');assert int(suite.attrib['tests'])>=509 and int(suite.attrib['errors'])==int(suite.attrib['failures'])==0
    assert read(OUT/'NATIVE_FINGERPRINT_IDENTITY.json')['PASS']
    for cmd in [['git','diff','--check'],['git','diff','--cached','--check']]:assert subprocess.run(cmd,cwd=ROOT,capture_output=True).returncode==0
    files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='VERIFICATION.json']
    dump('VERIFICATION.json',dict(PASS=True,tests=int(suite.attrib['tests']),A1_optimize_calls=0,baseline_rerun=False,CP0_partial_preserved=True,CP1_runs=0,proof_primary_runs=1,DG0_runs=int(done['DG0']),production_runs=int(done['production']),legacy_all_bytes_preserved=True,formulation_fingerprint_identity=True,executed_sources_unchanged=True,independent_physical_PASS=True,robust_grid_PASS=True,full_domain_unchanged=True,original_solver_logs_preserved=True,global_bound_proof_gate_checked=True,heuristic_improvement_not_acceptance=True,diagnostic_interpretation='ROOT_LOOP_POLICY_EFFECT',no_specific_cut_causal_attribution=True,files=files))
    print('PROOF VERIFICATION PASS',suite.attrib['tests'],flush=True)
if __name__=='__main__':run()
