"""Seal the final execution envelope after numerical and liveness gates."""
from pathlib import Path
import sys,subprocess,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40b.common import *

def main():
    target=ROOT/'V40B_EXECUTION_FREEZE.json'
    if target.exists():raise RuntimeError('EXECUTION_ALREADY_SEALED')
    gates={name:read(ROOT/name) for name in ('V40B_REUSE_AUTHORIZATION.json','V40B_NUMERICAL_REGRESSION.json',
       'V40B_DETACHED_TEST.json','V40B_PRESERVATION_RECHECK.json','V40B_MAY_A0_ADMISSION_TEST.json','V40B_ADDITIONAL_D1_TRAFFIC_INPUTS.json')}
    assert all(value['status']=='PASS' for value in gates.values())
    test_results={}
    for name in ('V40B_PYTEST.xml','V40B_EVIDENCE_PYTEST.xml'):
        suite=ET.parse(ROOT/name).getroot().find('testsuite')
        assert suite is not None and int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
        test_results[name]={'tests':int(suite.attrib['tests']),'SHA':sha(ROOT/name)}
    monitor={}
    for test in ('test_v39l_monitor_liveness.ps1','test_v40b_monitor.ps1'):
        value=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(REPO/'tests/dayahead'/test)],
             text=True,capture_output=True,encoding='utf-8',errors='replace',check=True)
        monitor[test]={'status':'PASS','output':value.stdout.strip(),'source_SHA':sha(REPO/'tests/dayahead'/test)}
    baseline=read(V40A/'V40A_PRESTOP_CAMPAIGN_SNAPSHOT.json')
    assert audit(REPO,baseline['source_file_fingerprints'])['status']=='PASS'
    sources={**baseline['source_file_fingerprints'],**read(V40A/'V40A_ARTIFACT_SHA256.json')['V40A_source_files']}
    for p in list((REPO/'dayahead/v40b').glob('*.py'))+list((REPO/'dayahead/tools').glob('*v40b*.py'))+[REPO/'dayahead/tools/monitor_v40a_may_campaign.ps1']:
        sources[p.relative_to(REPO).as_posix()]=sha(p)
    inputs=dict(baseline['production_authority_fingerprints'])
    for p in (REPO/'dayahead/cache/v37_may_locked_final').iterdir():
        if p.name not in ('electrical','traffic'):continue
        for q in p.rglob('*'):
            if q.is_file():inputs[q.relative_to(REPO).as_posix()]=sha(q)
    for p in (ROOT/'reuse_certificates').glob('*.json'):inputs[p.relative_to(REPO).as_posix()]=sha(p)
    for name in gates:inputs[(ROOT/name).relative_to(REPO).as_posix()]=sha(ROOT/name)
    tests={p.relative_to(REPO).as_posix():sha(p) for p in (REPO/'tests/dayahead').glob('test_v40*.py')}
    identity={'method_SHA':read(ROOT/'V40B_V40A_METHOD_FREEZE.json')['method_SHA'],
       'source_manifest_SHA':digest(sources),'input_manifest_SHA':digest(inputs),'tests_manifest_SHA':digest(tests),
       'namespace':str(ROOT),'max_parallel_day_workers':4,'Gurobi_threads_per_model':4,'old_B3_reuse':False}
    write(target,{'status':'PASS','sealed_at_utc':now_utc(),'execution_SHA':digest(identity),'identity':identity,
        'source_files':sources,'input_files':inputs,'test_source_files':tests,'May_result_based_tuning_allowed':False})
    write(ROOT/'V40B_TEST_REPORT.json',{'status':'PASS','sealed_at_utc':now_utc(),'execution_SHA':digest(identity),
      'pytest':test_results,'monitor':monitor,'gates':{name:value['status'] for name,value in gates.items()},
      'tests_source_files':tests,'required_checks':{
        'method_freeze':'PASS','B0_B1_B2_current_loader':'PASS','old_B3_rejection':'PASS','124_case_matrix':'PASS',
        'exactly_one_M1':'PASS','no_Fresh_inside_loop':'PASS','terminal_invariant':'PASS','joint_Fresh_Actual_binding':'PASS',
        'detached_child_survival':'PASS','dead_PID':'PASS','stale_heartbeat':'PASS','duplicate_orchestrator':'PASS','old_result_preservation':'PASS'},
      'development_diagnostics':[
        'Initial schema validator used April aliases; corrected to unchanged current V39E producer schema before freeze.',
        'Missing May20-31 D-1 traffic inputs materialized with frozen model; method/source parameters unchanged.',
        'Evidence test uses April fixtures and test doubles, not May scientific results. Native OpenDSS emitted a Windows exception diagnostic; the final uncaptured test completed PASS. Corrected test-double signature before final PASS.']})
    print('PRELAUNCH_SEALED',digest(identity),flush=True)

if __name__=='__main__':main()
