"""Independent final matrix, inclusion, source, and sequential-gate checks."""
from datetime import datetime,timezone,timedelta
import re
import xml.etree.ElementTree as ET
import gurobipy as gp
from .common import *
from .report import REQUIRED

def run():
    missing=[n for n in REQUIRED if n!='VERIFICATION.json' and not (OUT/n).exists()];assert not missing,missing
    legacy=read(OUT/'LEGACY_PRESERVATION_AUDIT.json')
    assert len(legacy['files'])==1400
    for r in legacy['files']:assert sha(ROOT/r['path'])==r['sha256'],r['path']
    changed=git('diff','--name-only',BASE).splitlines();assert all(n.startswith(('docs/v42_m1_late_window_certificate_mipstart/','v42_certificate/','tests/v42_certificate/')) for n in changed)
    add=read(OUT/'SCOPE_CORRECTION_ADDENDUM.json');freeze=read(OUT/'EXECUTION_FREEZE.json');manifest=read(OUT/'SOURCE_MANIFEST.json')
    assert sha(OUT/'PREREGISTRATION.json')==add['original_preregistration_sha256']==freeze['preregistration_sha256']
    assert sha(OUT/'SCOPE_CORRECTION_ADDENDUM.json')==freeze['scope_addendum_sha256']==manifest['scope_addendum_sha256']
    assert add['before_any_new_optimization'] and not add['optimization_markers_at_correction']
    for r in add['existing_prepare_files_preserved']:assert sha(OUT/r['path'])==sha(OUT/'prepare_before_scope_correction'/r['path'])==r['sha256']
    for r in freeze['source_files']:assert sha(ROOT/r['path'])==r['sha256'],('FROZEN_EXECUTION_SOURCE_CHANGED',r['path'])
    for r in manifest['sources']:assert sha(ROOT/r['path'])==r['sha256']
    assert sha(LOCAL/'F3.mps')==manifest['original_template_sha256']==read(OUT/'MIP_START_IMPORT_AUDIT.json')['model_sha256']
    xml=ET.parse(OUT/'PYTEST_RESULTS.xml').getroot();suite=xml.find('testsuite')
    assert int(suite.attrib['errors'])==int(suite.attrib['failures'])==int(suite.attrib.get('skipped',0))==0
    tests=int(suite.attrib['tests']);assert tests>=586
    questions=len(re.findall(r'^\d+\. ',(OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf8'),re.M));assert questions==manifest['final_review_questions']>=50
    inherited44=read(PRIOR/'WINDOW_INTEGRALITY_VALIDATION_SUMMARY.json');assert inherited44['PASS'] and inherited44['checks']==44
    assert read(OUT/'NESTING_DOMAIN_VALIDATION.json')['PASS']
    with np.load(OUT/'NESTING_DOMAIN_AXIS.npz',allow_pickle=False) as z:domains={a:z[a] for a in WINDOWS}
    assert np.all(~domains['B1']|domains['B2']) and np.all(~domains['B2']|domains['B3'])
    axis=load_axis();names,start=load_start();pos={str(n):i for i,n in enumerate(names)}
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=gp.read(str(LOCAL/'F3.mps'),env=env)
    assert m.getAttr('VarName')==list(names) and np.array_equal(m.getAttr('VType'),axis['original_types'])
    assert (m.NumConstrs,m.NumVars,m.NumNZs)==(954560,316743,8282350)
    A=m.getA();rhs=np.asarray(m.getAttr('RHS'));sense=np.asarray(m.getAttr('Sense'));lo=axis['lower'];hi=axis['upper']
    assert np.array_equal(m.getAttr('LB'),lo) and np.array_equal(m.getAttr('UB'),hi)
    with np.load(OUT/'MPS_ROW_ALIAS_AXIS.npz',allow_pickle=False) as z:
        assert np.array_equal(z['native_names'],axis['rownames']) and list(z['mps_names'])==m.getAttr('ConstrName')
    assert all(sense[int(i)]=='=' and rhs[int(i)]==760 for i in axis['terminal_rows'])
    assert np.count_nonzero(m.getAttr('Obj'))==1 and m.getVarByName('rho_max').Obj==1 and m.ModelSense==1
    def validate_vector(v,mask):
        r=A@v-rhs;err=np.where(sense=='=',abs(r),np.where(sense=='<',r,-r))
        violation=max(0.,float(err.max()),float((lo-v).max()),float((v-hi).max()))
        frac=float(np.max(abs(v[mask]-np.rint(v[mask]))));assert violation<=TOL and frac<=TOL,(violation,frac)
        return dict(matrix_max_violation=violation,binary_max_fractionality=frac,PASS=True)
    checks=[dict(point='complete_imported_start',**validate_vector(start,axis['original_types']=='B'))]
    acceptance=read(OUT/'MIP_START_NATIVE_ACCEPTANCE.json');assert acceptance['PASS'] and acceptance['folded_into_B3'] and not acceptance['original_full_binary_model']
    assert acceptance['accepted_initial_objective']<=START_UB+OBJ_TOL and not acceptance['old_UB_fallback']
    with np.load(OUT/'MIP_START_NATIVE_ACCEPTED.npz',allow_pickle=False) as z:assert np.array_equal(z['names'],names);v=z['values']
    checks.append(dict(point='actual_native_accepted_start',**validate_vector(v,axis['original_types']=='B')))
    assert abs(v[pos['rho_max']]-acceptance['accepted_initial_objective'])<=OBJ_TOL
    assert original_validation(names,v)['valid_new_UB']
    actual={a:read(OUT/(a+'_OPTIMIZATION.json')) for a in WINDOWS if (OUT/(a+'_OPTIMIZATION.json')).exists()}
    certificates={a:read(OUT/(a+{'B1':'_ROUTE','B2':'_ROUTE_MODE','B3':'_BUFFER'}[a]+'_CERTIFICATE.json')) for a in WINDOWS}
    assert 'B3' in actual
    if 'B2' in actual:assert certificates['B3']['material']
    if 'B1' in actual:assert 'B2' in actual and certificates['B2']['material']
    if certificates['B3']['negative_certificate']:assert set(actual)=={'B3'}
    if certificates['B3']['conclusion']=='INCONCLUSIVE':assert set(actual)=={'B3'}
    if 'B2' in actual and certificates['B2']['negative_certificate']:assert 'B1' not in actual
    timing=[]
    for a,r in actual.items():
        assert r['optimize_calls']==1 and r['settings']==SETTINGS and not r['GPU'] and not r['production']
        assert r['rows']==954560 and r['columns']==316743 and r['nonzeros']==8282350
        assert r['restored_binaries']==int(domains[a].sum()) and r['template_sha256']==sha(LOCAL/'F3.mps')
        marker=read(OUT/(a+'_EXECUTION_MARKER.json'));assert marker['scope_addendum_sha256']==sha(OUT/'SCOPE_CORRECTION_ADDENDUM.json')
        commit=marker['execution_commit'];committime=datetime.fromtimestamp(int(git('show','-s','--format=%ct',commit)),timezone.utc)
        assert datetime.fromisoformat(add['created_utc'].replace('Z','+00:00'))<=committime
        for s in freeze['source_files']:
            blob=subprocess.check_output(['git','show',commit+':'+s['path']],cwd=ROOT);assert hashlib.sha256(blob).hexdigest()==s['sha256']
        log=gzip.decompress((OUT/(a+'_SOLVER.log.gz')).read_bytes()).decode()
        assert 'Loaded user MIP start with objective' in log and r['initial_start_acceptance']['PASS']
        assert r['initial_start_acceptance']['first_incumbent']['objective']<=START_UB+OBJ_TOL
        native_time=re.search(r'logging started (.+)',log)
        dt=datetime.strptime(native_time[1].strip(),'%a %b %d %H:%M:%S %Y').replace(tzinfo=timezone(timedelta(hours=9)))
        assert committime<=dt.astimezone(timezone.utc)+timedelta(seconds=1)
        timing.append(dict(arm=a,scope_UTC=add['created_utc'],execution_commit=commit,execution_commit_UTC=committime.isoformat(),solver_start_KST=dt.isoformat(),PASS=True))
        d=json.loads(gzip.decompress((OUT/(a+'_DOMAIN.json.gz')).read_bytes()))
        assert d['restored']==list(map(str,names[domains[a]])) and not any(d[k] for k in ['fixed','removed_rows','new_rows'])
        with np.load(OUT/(a+'_SOLUTION.npz'),allow_pickle=False) as z:assert np.array_equal(z['names'],names);v=z['values']
        checks.append(dict(point=a,**validate_vector(v,domains[a])))
        assert abs(v[pos['rho_max']]-r['solver_incumbent'])<=OBJ_TOL
        if r['validated_original_UB'] is not None:assert original_validation(names,v)['valid_new_UB']
    for a,c in certificates.items():
        assert c['run']==(a in actual) and c['lower']<=c['upper']+OBJ_TOL
        assert c['material']==(c['lower']-S2>=MATERIAL) and c['negative_certificate']==(c['upper']-S2<=MATERIAL)
        if c['upper_source'] in actual:
            s=c['upper_source']
            with np.load(OUT/(s+'_SOLUTION.npz'),allow_pickle=False) as z:v=z['values']
            validate_vector(v,domains[a]);assert abs(c['upper']-v[pos['rho_max']])<=OBJ_TOL
            assert np.all(~domains[a]|domains[s]) or actual[s]['validated_original_UB'] is not None
        else:assert c['upper']==START_UB
        if c['lower_source'].startswith('NEW_'):
            s=c['lower_source'][4:];assert np.all(~domains[s]|domains[a]) and c['lower']==actual[s]['valid_partial_LB']
        else:
            s=c['lower_source'][6:];oldname={'B1':'R_ROUTE_ONLY','B2':'R_ACTIVE','B3':'R_BUFFER'}[s]
            assert np.all(~domains[s]|domains[a]) and c['lower']==read(PRIOR/(oldname+'_OPTIMIZATION.json'))['certified_global_LB']
        if c['execution']=='NOT_RUN_NESTING_CERTIFIED':assert a not in actual and c['negative_certificate']
    markers=list(LOCAL.glob('*_OPTIMIZE_STARTED.json'));assert {p.name.split('_')[0] for p in markers}==set(actual)
    flags=read(OUT/'FINAL_FLAGS.json');assert flags['DIAGNOSTIC_OPTIMIZE_CALLS']==len(actual)
    assert flags['BEST_VALIDATED_ORIGINAL_M1_UB']>=flags['BEST_CERTIFIED_ORIGINAL_M1_LB']-OBJ_TOL
    assert flags['BEST_CERTIFIED_ORIGINAL_M1_LB']==max([S2]+[c['global_LB'] for c in certificates.values()])
    assert flags['ROOT_CAUSE_CLASS']==choose_case(certificates)
    assert not any(flags[k] for k in ['PRODUCTION_M1_RUN','PRODUCTION_M1_P1_ACCEPTED','P2_RUN','M1_ACCEPTED','PROBLEM13_FINAL_VALIDATED','A2_ALLOWED','A2_RUN','M2_RUN','ACTUAL_RUN','FRESH_AC_RUN','IEEE8500_RUN','ACTUAL_P_CORRECTION_ENABLED','ACTUAL_Q_CORRECTION_ENABLED','EXCLUDED_PROBLEMS_NEW_WORK'])
    assert not read(OUT/'PRODUCTION_AUTHORIZATION.json')['authorized'] and not (OUT/'M1_PRODUCTION_OPTIMIZATION.json').exists()
    assert flags['A1_OPTIMIZE_CALLS']==flags['S1_OPTIMIZE_CALLS']==flags['S2_OPTIMIZE_CALLS']==flags['S3_OPTIMIZE_CALLS']==0
    dump('EXECUTION_TIMELINE_VALIDATION.json',dict(PASS=True,before_results_scope_correction=True,timing=timing))
    dump('VERIFICATION.json',dict(PASS=True,required_outputs=len(REQUIRED),full_tests=tests,new_tests=tests-541,inherited_tests=541,inherited_bounded_checks=44,
        Korean_review_questions=questions,legacy_tracked_files_preserved=1400,preregistration_and_prepare_preserved=True,
        frozen_optimization_source_PASS=True,default_native_exact_matrix_domain_PASS=True,row_aliases_only=True,
        independent_vectors=checks,independent_nesting_PASS=True,sequential_gate_PASS=True,start_native_accepted=True,
        scientific_diagnostic_optimize_calls=len(actual),verification_optimize_calls=0,new_parameter_sweeps=0,fallbacks=0,
        production=False,P2=False,downstream=False,new_cuts=0,scientific_physics_changed=False))
    m.dispose();env.dispose();print('FINAL VERIFICATION PASS',tests,'tests',len(actual),'new diagnostic solve(s)',flush=True)
if __name__=='__main__':run()
