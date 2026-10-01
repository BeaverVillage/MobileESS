"""Final independent hashes, matrices, actual vectors and execution gates; zero optimize."""
from datetime import datetime,timezone,timedelta
import gzip,re,xml.etree.ElementTree as ET
import gurobipy as gp
from .common import *
from .prepare import audit
from .validate import validate_point
from .routes import path_validation

REQUIRED='''PREREGISTRATION.json PR113_BASE_RECEIPT.json THRESHOLD_AUTHORITY.json B3_THRESHOLD_FORMULATION.md B3_THRESHOLD_MATRIX_IDENTITY.json ROOT_GUIDED_WITNESS_PREREGISTRATION.json ROOT_ROUTE_SUPPORT.csv ROUTE_WITNESS_CANDIDATES.csv B3_WITNESS_SEARCH_RESULTS.csv B3_THRESHOLD_SOLVER.json B3_THRESHOLD_SOLVER.raw.gz B3_THRESHOLD_PROGRESS.csv B3_THRESHOLD_CERTIFICATE.json CAUSAL_BACKWARD_CLOSURE.json CAUSAL_BACKWARD_CLOSURE.csv NUMERICAL_WARNING_AUDIT.json FINAL_FLAGS.json FINAL_VERDICT.json NEXT_MODIFICATIONS.md FINAL_REVIEW_KO.md SOURCE_MANIFEST.json PYTEST_RESULTS.xml'''.split()

def run():
    assert all((OUT/n).exists() for n in REQUIRED)
    legacy=read(OUT/'LEGACY_PRESERVATION_AUDIT.json');assert len(legacy['files'])==1464
    for f in legacy['files']:assert sha(ROOT/f['path'])==f['sha256'],f['path']
    names=git('diff','--name-only',BASE).splitlines()
    assert all(n.startswith(('docs/v42_m1_b3_threshold_certificate/','v42_threshold/','tests/v42_threshold/')) for n in names)
    manifest=read(OUT/'SOURCE_MANIFEST.json');freeze=read(OUT/'EXECUTION_FREEZE.json')
    assert manifest['preregistration_sha256']==freeze['preregistration_sha256']==sha(OUT/'PREREGISTRATION.json')
    assert manifest['execution_freeze_sha256']==sha(OUT/'EXECUTION_FREEZE.json') and freeze['before_any_new_optimization']
    for f in manifest['sources']+freeze['source_files']:assert sha(ROOT/f['path'])==f['sha256'],f['path']
    assert sha(LOCAL/'F3.mps')==freeze['template_sha256']==read(PR112/'F3_TEMPLATE_RECEIPT.json')['sha256']
    assert sha(OUT/'ROUTE_WITNESS_CANDIDATES.json')==freeze['root_candidates_sha256']
    xml=ET.parse(OUT/'PYTEST_RESULTS.xml').getroot().find('testsuite');tests=int(xml.attrib['tests'])
    assert tests>=631 and int(xml.attrib['errors'])==int(xml.attrib['failures'])==int(xml.attrib.get('skipped',0))==0
    qa=len(re.findall(r'^\d+\. ',(OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf8'),re.M));assert qa==manifest['Korean_questions']>=50
    inherited=read(PR112/'WINDOW_INTEGRALITY_VALIDATION_SUMMARY.json');assert inherited['PASS'] and inherited['checks']==44
    assert read(PR113/'VERIFICATION.json')['full_tests']==593
    prior_audit=read(OUT/'B3_THRESHOLD_MATRIX_IDENTITY.json');audit();assert read(OUT/'B3_THRESHOLD_MATRIX_IDENTITY.json')==prior_audit
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=threshold_model(env)
    candidates=read(OUT/'ROUTE_WITNESS_CANDIDATES.json')['candidates'];assert len(candidates)==2
    _,_,_,_,initial,_,_=inputs()
    for c in candidates:
        assert sha(ROOT/c['source_solution_path'])==c['source_sha256']
        for u,chosen in c['routes'].items():assert path_validation(arcs(),initial[u],chosen)['PASS']
    assert not matrix_validation(m,full_start())['PASS'] and matrix_validation(m,full_start(),include_threshold=False)['PASS']
    assert m.getAttr('LB')==axis()['lower'].tolist() and m.getAttr('UB')==axis()['upper'].tolist()
    roots=[]
    for source in SOURCES:
        values,path=root(source);missing=[str(n) for n in axis()['names'] if str(n) not in values];assert not missing,missing[:5]
        v=np.asarray([values[str(n)] for n in axis()['names']]);check=matrix_validation(m,v)
        fractionality=float(np.max(abs(v[domains()]-np.rint(v[domains()]))))
        roots.append(dict(source=source,sha256=sha(path),threshold_continuous_row_bound_validation=check,
            B3_restored_binary_fractionality=fractionality,B3_integer_witness=False,
            meaning='Continuous root reference only, never a B3 integrality certificate or evidence against valid integer cuts.'))
        assert fractionality>INTEGER_TOL
    dump('INHERITED_ROOT_THRESHOLD_RELAXATION_AUDIT.json',dict(root_optimization_calls=0,checks=roots))
    runs={k:read(OUT/(k+'_SOLVER.json')) for k in ['W1','W2','DIRECT'] if (OUT/(k+'_SOLVER.json')).exists()};assert 'DIRECT' in runs
    assert {p.stem.replace('_STARTED','') for p in LOCAL.glob('*_STARTED.json')}==set(runs)
    timeline=[];vectors=[];safe=[];boundary=[]
    for k,r in runs.items():
        assert r['optimize_calls']==1 and r['settings']==settings(k) and not r['callback_errors']
        assert r['zero_objective_bound_not_B3_rho_LB'] and not any(r[x] for x in ['production','P2','B1','B2'])
        if k=='DIRECT':assert r['fixed_route_bounds']==0
        else:assert r['fixed_route_bounds']==85592 and not r['proven_infeasible']
        marker=read(OUT/(k+'_EXECUTION_MARKER.json'));commit=marker['execution_commit']
        assert marker['preregistration_sha256']==sha(OUT/'PREREGISTRATION.json') and marker['execution_freeze_sha256']==sha(OUT/'EXECUTION_FREEZE.json')
        assert git('rev-parse',commit+'^')==BASE
        commitUTC=datetime.fromtimestamp(int(git('show','-s','--format=%ct',commit)),timezone.utc)
        preregUTC=datetime.fromisoformat(read(OUT/'PREREGISTRATION.json')['created_UTC'].replace('Z','+00:00'))
        markerUTC=datetime.fromisoformat(marker['created_UTC'].replace('Z','+00:00'))
        assert preregUTC<=commitUTC<=markerUTC
        for f in freeze['source_files']:
            blob=subprocess.check_output(['git','show',commit+':'+f['path']],cwd=ROOT);assert hashlib.sha256(blob).hexdigest()==f['sha256']
        raw=gzip.decompress((OUT/(k+'_SOLVER.raw.gz')).read_bytes()).decode()
        assert sha(OUT/(k+'_SOLVER.raw.gz'))==r['raw_log_sha256']
        nativeUTC=datetime.strptime(re.search(r'logging started (.+)',raw)[1].strip(),'%a %b %d %H:%M:%S %Y').replace(tzinfo=timezone(timedelta(hours=9)))
        assert commitUTC<=nativeUTC and markerUTC>=nativeUTC.astimezone(timezone.utc)-timedelta(seconds=15)
        timeline.append(dict(kind=k,preregistration_UTC=preregUTC.isoformat(),checkpoint_commit=commit,checkpoint_UTC=commitUTC.isoformat(),marker_UTC=markerUTC.isoformat(),native_log_start_KST=nativeUTC.isoformat(),PASS=True))
        if r['SolCount']:
            with np.load(OUT/(k+'_SOLUTION.npz'),allow_pickle=False) as z:
                validation,slots=validate_point(m,z['names'],z['values'])
                assert validation==r['validation']
                if validation['threshold_certificate_PASS']:safe.append(k)
                else:boundary.append(k)
                vectors.append(dict(kind=k,validation=validation,PASS=validation['B3_feasible_PASS']))
                if k!='DIRECT':
                    c=next(c for c in candidates if c['id']==k);selected={u:set(ks) for u,ks in c['routes'].items()}
                    for i,n in enumerate(z['names']):
                        if domains()[i] and n.startswith('arc['):
                            u,j=n[4:-1].split(',');assert abs(z['values'][i]-int(int(j) in selected[u]))<=INTEGER_TOL
    assert (OUT/'B3_THRESHOLD_SOLVER.raw.gz').read_bytes()==(OUT/'DIRECT_SOLVER.raw.gz').read_bytes()
    c=read(OUT/'B3_THRESHOLD_CERTIFICATE.json');d=runs['DIRECT'];f=read(OUT/'FINAL_FLAGS.json')
    root_audit=read(OUT/'ROOT_COMPLETION_AUDIT.json')
    for observation in root_audit['runs']:
        raw=gzip.decompress((OUT/(observation['kind']+'_SOLVER.raw.gz')).read_bytes()).decode()
        root_lines=[s.strip() for s in raw.splitlines() if s.startswith('Root relaxation:')]
        assert observation['raw_root_lines']==root_lines
        assert observation['independently_completed_feasible_root']==any('objective ' in s and 'interrupted' not in s.lower() for s in root_lines)
    assert f['DIRECT_ROOT_COMPLETED']==next(r['independently_completed_feasible_root'] for r in root_audit['runs'] if r['kind']=='DIRECT')
    expected=classify(read(OUT/'B3_THRESHOLD_POINT_VALIDATION.json') if safe else None,d['solver_status'])
    if safe and d['solver_status']==3:expected='B3_INCONCLUSIVE'
    assert c['classification']==expected==f['CERTIFICATE_CLASSIFICATION']
    assert c['negative_certificate']==(expected=='B3_NEGATIVE_CERTIFIED') and c['positive_certificate']==(expected=='B3_POSITIVE_CERTIFIED')
    if safe:
        with np.load(OUT/'B3_THRESHOLD_FEASIBLE_POINT.npz',allow_pickle=False) as z:v,_=validate_point(m,z['names'],z['values'])
        assert v['threshold_certificate_PASS']
    if c['positive_certificate']:assert d['solver_status']==3 and 'infeasible' in gzip.decompress((OUT/'DIRECT_SOLVER.raw.gz').read_bytes()).decode().lower()
    upper_candidates=[ORIGINAL_UB]+[r['validation']['rho'] for r in runs.values() if r['validation'] and r['validation']['B3_feasible_PASS']]
    assert c['partial_feasible_upper']==f['B3_PARTIAL_FEASIBLE_UPPER']==min(upper_candidates)
    promotion=read(OUT/'ORIGINAL_M1_PROMOTION_AUDIT.json');assert promotion['PASS']
    original_candidates=[ORIGINAL_UB]
    from v42_certificate.common import original_validation
    for p in promotion['points']:
        r=runs[p['kind']]
        assert p['all_original_binary_integrality_screen']==r['validation']['original_M1_UB_eligible']
        if p['promotable_original_UB']:
            with np.load(OUT/(p['kind']+'_SOLUTION.npz'),allow_pickle=False) as z:full=original_validation(z['names'],z['values'])
            assert full['valid_new_UB'] and full==p['independent_full_original_validation']
            original_candidates.append(r['validation']['rho'])
    assert f['ORIGINAL_M1_UB']==min(original_candidates) and f['ORIGINAL_M1_LB']==(T if c['positive_certificate'] else S2)
    assert f['TOTAL_NEW_OPTIMIZE_CALLS']==len(runs) and f['DIRECT_OPTIMIZE_CALLS']==1
    assert f['B1_OPTIMIZE_CALLS']==f['B2_OPTIMIZE_CALLS']==f['EXPANDED_WINDOW_OPTIMIZE_CALLS']==f['DECOMPOSITION_OPTIMIZE_CALLS']==f['NEW_FORMULATION_CUTS']==0
    assert not any(f[x] for x in ['PRODUCTION_M1_RUN','P2_RUN','A2_ALLOWED','A2_RUN','M2_RUN','ACTUAL_RUN','FRESH_AC_RUN','IEEE8500_RUN','MAY_CAMPAIGN_RUN','SENSITIVITY_CAMPAIGN_RUN','M1_ACCEPTED','PROBLEM13_FINAL_VALIDATED','B0_WORK_TOUCHED','B1_COMPARISON_WORK_TOUCHED','EXCLUDED_PROBLEMS_NEW_WORK','ACTUAL_P_CORRECTION','ACTUAL_Q_CORRECTION'])
    closure=read(OUT/'CAUSAL_BACKWARD_CLOSURE.json')
    if expected=='B3_INCONCLUSIVE':
        assert closure['execution']=='DIAGNOSIS_ONLY' and closure['earliest_causal_predecessor_slot']==0 and not closure['expanded_window_run']
        assert all(u['route_dependency']['earliest_slot']==u['earliest_SOC_decision_predecessor_slot']==0 for u in closure['units'])
    else:assert closure['execution']=='NOT_RUN_CERTIFICATE_OBTAINED'
    dump('EXECUTION_TIMELINE_VALIDATION.json',dict(PASS=True,preregistration_and_source_checkpoint_before_all_new_optimizations=True,runs=timeline))
    dump('VERIFICATION.json',dict(PASS=True,full_tests=tests,new_tests=tests-593,inherited_tests=593,inherited_bounded_checks=44,
        inherited_tracked_files_byte_preserved=1464,Korean_review_questions=qa,exact_threshold=T,threshold_matrix_identity_PASS=True,
        frozen_execution_source_PASS=True,independent_candidate_route_legality_PASS=True,actual_vectors=vectors,
        numerical_borderline_or_invalid_native_points_not_certified=boundary,threshold_classification=expected,
        scientific_optimize_calls=len(runs),verification_optimize_calls=0,B1_optimize_calls=0,B2_optimize_calls=0,
        production=False,P2=False,downstream=False,new_cuts=0,expanded_window_solve=False,decomposition_implemented=False))
    m.dispose();env.dispose();print('THRESHOLD FINAL VERIFICATION PASS',tests,'tests',len(runs),'new calls',expected,flush=True)

if __name__=='__main__':run()
