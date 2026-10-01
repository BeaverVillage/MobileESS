"""Independent final physical/reproducibility checks; zero optimization."""
import csv,subprocess,gzip,xml.etree.ElementTree as ET
import numpy as np
from v42_root.common import *
from v42_native.mess import validate
from v42_bootstrap.grid import grid_report
from v42_bootstrap.attribution import supplemental_physical
from .build import inputs
from .report import REQUIRED
def run():
    frozen();selection=read(OUT/'FORMULATION_SELECTION.json');manifest=read(OUT/'SOURCE_MANIFEST.json')
    for r in manifest['sources']+manifest['final_reporting_sources']:
        assert sha(ROOT/r['path'])==r['sha256'],r['path']
    assert sha(ROOT/manifest['tests']['path'])==manifest['tests']['sha256']
    assert all((OUT/n).exists() for n in REQUIRED if n!='VERIFICATION.json')
    assert (OUT/'P1_LP_RELAXATION_LOGS').is_dir()
    f=read(OUT/'FINAL_FLAGS.json');m=read(OUT/'M1_OPTIMIZATION.json')
    assert not any(f[k] for k in ['SCIENTIFIC_PHYSICS_CHANGED','CANDIDATE_DOMAIN_CHANGED','A1_RERUN','ACTUAL_Q_CORRECTION_ENABLED','ACTUAL_P_CORRECTION_ENABLED','GPU_USED','A2_RUN','M2_RUN','ACTUAL_RUN','FRESH_AC_RUN','IEEE8500_RUN','PROBLEM13_FINAL_VALIDATED'])
    assert f['A1_OPTIMIZE_CALLS_THIS_TASK']==0 and f['M1_ROBUST_VOLTAGE_MIN']==.955 and f['M1_ROBUST_VOLTAGE_MAX']==1.045
    assert m['settings']['Threads']==selection['threads'] and m['settings']['Method']==selection['method']
    assert m['settings']['Seed']==20260929 and m['settings']['MIPGap']==.005 and m['settings']['TimeLimit']==1800
    assert m['total_optimize_seconds']<=1805
    assert not m['passes'][0]['quality_PASS'] or m['passes'][0]['relative_gap']<=.005+1e-12
    if not m['passes'][0]['quality_PASS']:assert len(m['passes'])==1
    if m['accepted']:assert m['complete'] and all(p['quality_PASS'] for p in m['passes'])
    assert len(list(LOCAL.glob('M1/STARTED.json')))==1 and not list(LOCAL.glob('A1*/STARTED.json'))
    cross=read(OUT/'PR106_INCUMBENT_CROSS_FORMULATION.json');assert cross['PASS'] and len(cross['candidates'])>=6 and all(r['PASS'] for r in cross['candidates'].values())
    eq=read(OUT/'FORMULATION_EQUIVALENCE.json');assert eq['PASS'] and eq['fixtures']==20
    with (OUT/'BOUNDED_EQUIVALENCE_RESULTS.csv').open(encoding='utf8',newline='') as file:bounded=list(csv.DictReader(file))
    assert len(bounded)==20 and all(r['PASS']=='True' for r in bounded)
    assert selection['LP_objective_agreement_PASS'] and len(selection['LP_ranking'])<=3
    assert selection['extra_four_thread_diagnostics']<=1
    one=selection['root_canaries'][0]
    if one['root_processing_wall_seconds']<=300:assert selection['threads']==1 and selection['extra_four_thread_diagnostics']==0
    if one['root_LP_complete'] and one['root_LP_seconds']<=300:assert selection['threads']==1 and selection['extra_four_thread_diagnostics']==0
    for fixture in eq['results'].values():
        baseline=fixture['M1-F0']
        for candidate,result in fixture.items():
            for old,new in zip(baseline,result):
                assert old['feasible']==new['feasible'] and old['route']==new['route']
                if old['feasible']:
                    assert abs(old['scores'][0]-new['scores'][0])<=1e-7
                    assert abs(old['scores'][1]-new['scores'][1])<=1e-8
                    assert abs(old['scores'][2]-new['scores'][2])<=1e-5
    for r in read(OUT/'PR106_A1_ANCHOR_REUSE_RECEIPT.json')['files']:
        assert sha(OUT/r['path'])==r['sha256']==r['PR106_sha256']
    for r in read(OUT/'SOLVER_LOG_PRESERVATION.json')['logs']:
        assert sha(r['native_path'])==r['native_sha256']
        assert gzip.decompress((OUT/r['raw_gzip']).read_bytes())==Path(r['native_path']).read_bytes()
    for p in (OUT/'P1_LP_RELAXATION_LOGS').glob('*.receipt.json'):
        r=read(p);label=p.name.replace('.receipt.json','');assert hashlib.sha256(gzip.decompress((p.parent/(label+'.raw.gz')).read_bytes())).hexdigest()==r['native_sha256']
    bundle,anchor,prior,sites,initial,routes,battery=inputs();plan=read(LOCAL/'M1/FINAL_PLAN.json');ctrl=read(LOCAL/'M1/CONTROLS.json')
    physical=validate(plan,sites,routes,battery,96);extra=supplemental_physical(plan,sites,battery);grid=grid_report(bundle,ctrl,plan['values']['rho_max'])
    assert physical['PASS'] and extra['charge_mode_and_connection_PASS'] and grid['PASS']
    assert plan['domain_sha256']==prior['domain_sha256']
    assert all(abs(plan['values'][f'SOC[{u},0]']-battery.initial)<=1e-5 for u in initial)
    assert all(ctrl[t][i]==anchor['controls'][t][i] for t in range(96) for i in anchor['fixed_AIDC_control_columns'])
    with (OUT/'M1_Q_UTILIZATION.csv').open(encoding='utf8',newline='') as file:qr=list(csv.DictReader(file))
    assert len(qr)==384
    for r in qr:
        if r['connected']=='True':
            available=np.sqrt(max(0,battery.pcs_kva**2-float(r['P_kw'])**2));assert abs(available-float(r['Q_available_kvar']))<1e-8
            if available>1e-6:assert abs(abs(float(r['Q_kvar']))/available-float(r['utilization']))<1e-8
    suite=ET.parse(OUT/'TEST_RESULTS.xml').getroot().find('testsuite');assert int(suite.attrib['tests'])>=489 and int(suite.attrib['errors'])==int(suite.attrib['failures'])==0
    for args in [['git','diff','--check'],['git','diff','--cached','--check']]:
        r=subprocess.run(args,cwd=ROOT,capture_output=True);assert r.returncode==0,(r.stdout+r.stderr).decode('utf8',errors='replace')
    files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='VERIFICATION.json']
    dump('VERIFICATION.json',dict(PASS=True,tests=int(suite.attrib['tests']),failures=0,errors=0,A1_optimize_calls=0,production_M1_runs=1,legacy_all_bytes_preserved=True,executed_sources_unchanged=True,exact_projection_and_20_fixtures_PASS=True,independent_physical_PASS=True,independent_robust_grid_PASS=True,full_domain_unchanged=True,MIP_start_only=True,original_solver_logs_preserved=True,git_diff_check=True,files=files))
    print('VERIFICATION PASS',suite.attrib['tests'],'tests',flush=True)
if __name__=='__main__':run()
