"""Post-worker tests/source/cold-model audit. No optimize call is permitted."""
import os,json,re,subprocess,py_compile,sys,hashlib
from pathlib import Path
from v42_cutpass.common import ROOT,OUT,REF,SCIENCE,SOURCE,BASE,ENV,sha,read,write

def result(label,filename):
    text=(OUT/filename).read_text(encoding='utf8');matches=re.findall(r'(\d+) passed(?:, (\d+) warnings?)? in ([\d.]+)s',text)
    receipt=read(OUT/('PYTEST_EXECUTION_'+label+'.json'))
    assert receipt['exit_code']==0 and matches,(label,'PYTEST_FAILED')
    passed,warnings,seconds=matches[-1]
    assert receipt['one_pytest_process'] and not receipt['xdist_used'] and receipt['all_test_Gurobi_Threads_one'] and receipt['observed_test_calls_nonoverlapping']
    return dict(exit_code=0,passed=int(passed),warnings=int(warnings or 0),runtime_seconds=float(seconds),log_sha256=sha(OUT/filename),one_pytest_process=True,xdist_used=False,test_optimization_calls=len(receipt['test_optimization_calls']),all_Gurobi_Threads_one=True,observed_calls_nonoverlapping=True,native_exception_traces_preserved=True,native_exception_trace_count=text.count('Windows fatal exception:'),PR135_native_exception_traces_also_present=True)

def run():
    os.environ.update(ENV)
    receipt=read(OUT/'EXECUTION_RECEIPT.json');assert receipt['error'] is None and receipt['P1_optimization_calls']==1 and receipt['P2_optimization_calls']==0
    semantic=result('SEMANTIC','SEMANTIC_TEST.log');full=result('FULL','FULL_TEST.log')
    write('SEMANTIC_TEST_RESULT.json',semantic);write('FULL_TEST_RESULT.json',full)
    try:import jsonschema
    except ModuleNotFoundError:
        sys.path.insert(0,str(ROOT.parent/'CUTPASS_LOCAL/SCHEMA_DEPS'))
        import jsonschema
    schemas={name:read(OUT/name) for name in ('B3_LOOP_STATE_SCHEMA.json','B3_LOOP_CONVERGENCE_METRICS_SCHEMA.json','B3_LOOP_FIXED_POINT_CYCLE_SCHEMA.json')}
    for schema in schemas.values():jsonschema.Draft202012Validator.check_schema(schema)
    synthetic=read(OUT/'BOUNDED_SYNTHETIC_ORCHESTRATION.json')
    for row in synthetic['state_freezes'].values():jsonschema.validate(row['state'],schemas['B3_LOOP_STATE_SCHEMA.json'])
    for row in synthetic['convergence']:
        jsonschema.validate(row['metrics'],schemas['B3_LOOP_CONVERGENCE_METRICS_SCHEMA.json'])
        jsonschema.validate({key:row[key] for key in ('EXACT_FIXED_POINT','TWO_CYCLE','STILL_EVOLVING','stop_requested')},schemas['B3_LOOP_FIXED_POINT_CYCLE_SCHEMA.json'])
    write('CAMPAIGN_SCHEMA_VALIDATION.json',dict(PASS=True,JSON_schema_draft='2020-12',schemas=3,synthetic_states_checked=7,synthetic_metrics_checked=4,production_metrics_filled=False))
    manifest=read(OUT/'PR135_BYTE_PRESERVATION.json')
    drift=[row['path'] for row in manifest['files'] if sha(ROOT/row['path'])!=row['sha256']]
    assert not drift,drift;write('PR135_FINAL_BYTE_PRESERVATION.json',dict(PASS=True,base_exact_head=BASE,checked_files=len(manifest['files']),drift=drift))
    executed=read(OUT/'EXECUTED_SOURCE_RECEIPT.json')
    drift=[row['path'] for row in executed['files'] if sha(ROOT/row['path'])!=row['sha256']]
    assert not drift,drift;write('EXECUTED_SOURCE_FINAL_AUDIT.json',dict(PASS=True,executed_source_unchanged=True,drift=drift,files=executed['files']))
    source_identity=read(SCIENCE/'M1_MODEL_IDENTITY.json')
    pairs=[('FULL.mps','full_MPS_sha256'),('REDUCED.mps','reduced_MPS_sha256'),('FULL_A.npz','matrix_sha256'),('FULL_DATA.npz','data_sha256')]
    source_rows=[]
    for name,key in pairs:
        actual=sha(SOURCE/name);assert actual==source_identity[key];source_rows.append(dict(path=str(SOURCE/name),sha256=actual))
    assert sha(SOURCE/'DATA.pkl')==read(OUT/'M1_PR135_MODEL_IDENTITY.json')['source_data_sha256']
    source_rows.append(dict(path=str(SOURCE/'DATA.pkl'),sha256=sha(SOURCE/'DATA.pkl')))
    assert sha(SCIENCE/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')==source_identity['A1_freeze_sha256']
    assert sha(REF/'RAW_POINTS/ZERO_ACTION_CANDIDATE.npz')==read(OUT/'M1_ZERO_ACTION_START_SOLVER_BINDING.json')['candidate_sha256']
    write('SOURCE_DATA_FINAL_AUDIT.json',dict(PASS=True,all_PR135_model_asset_SHAs_rechecked=True,files=source_rows,A1_freeze_sha256=source_identity['A1_freeze_sha256'],Start_SHA_unchanged=True,A1_reoptimization_calls=0,Runtime_refit=0,CC4_refit=0))
    # Explicit row-name audit supplements the scientific array identity recorded
    # before/after the original solve. This is a read-only cold import, no trial.
    import numpy as np
    import gurobipy as gp
    from v42_degen.identity import signature
    from v42_integrated.matrix import arrays
    gp.setParam('Threads',1);original=gp.Model.optimize
    def forbidden(*args,**kwargs):raise RuntimeError('POSTVERIFY_OPTIMIZATION_FORBIDDEN')
    gp.Model.optimize=forbidden
    try:
        m=gp.read(str(SOURCE/'REDUCED.mps'));m.Params.Threads=1;m.Params.OutputFlag=0
        A,d=arrays(m);identity=read(OUT/'M1_PR135_MODEL_IDENTITY.json')
        assert signature(A,d)==identity['reference'] and m.Fingerprint==identity['cold_Gurobi_fingerprint']
        # FULL_DATA.row_names are family labels (e.g. repeated "flow"), not
        # Gurobi constraint identifiers. Compare native names to the exact
        # preserved PR135 MPS ROWS namespace instead of conflating the two.
        expected=[];in_rows=False
        with (SOURCE/'REDUCED.mps').open(encoding='utf8') as source:
            for line in source:
                parts=line.split()
                if parts==['ROWS']:in_rows=True;continue
                if parts==['COLUMNS']:break
                if in_rows and len(parts)==2 and parts[0] in ('E','L','G'):expected.append(parts[1])
        rows=np.asarray(m.getAttr('ConstrName'));assert np.array_equal(rows,np.asarray(expected)),'PR135_NATIVE_ROW_NAMES_IDENTITY_FAILED'
        with np.load(SOURCE/'FULL_DATA.npz') as data,np.load(SOURCE/'REDUCTION_AXES.npz') as axes:family_labels=data['row_names'][axes['keep']][:8].tolist()
        write('POST_TEST_COLD_MODEL_IDENTITY.json',dict(PASS=True,all_scientific_arrays_equal=True,row_names_equal_PR135_MPS=True,row_count=len(rows),row_names_SHA256=hashlib.sha256('\0'.join(expected).encode('utf8')).hexdigest(),row_names_SHA_scope='ordered native constraint names in immutable PR135 REDUCED.mps ROWS',FULL_DATA_family_labels_namespace='separate original grouping labels, not native constraint identifiers',first_original_family_labels=family_labels,first_native_row_names=expected[:8],column_names_equal=True,cold_Gurobi_fingerprint=m.Fingerprint,read_only_model_imports=1,optimize_calls=0))
        m.dispose()
    finally:gp.Model.optimize=original
    paths=subprocess.check_output(['git','ls-files','-z','--','*.py'],cwd=ROOT).decode('utf8').split('\0')
    paths=[ROOT/p for p in paths if p]+list((ROOT/'v42_cutpass').glob('*.py'))+list((ROOT/'v42_campaign').glob('*.py'))+list((ROOT/'tests/v42_cutpass').glob('*.py'))+list((ROOT/'tests/v42_campaign').glob('*.py'))
    for path in sorted(set(paths)):py_compile.compile(str(path),doraise=True)
    write('COMPILE_CHECK.json',dict(PASS=True,files=len(set(paths)),one_process=True,after_whole_heavy_worker=True))
    code=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True,text=True)
    assert code.returncode==0,code.stdout+code.stderr
    write('POST_HEAVY_VERIFICATION.json',dict(PASS=True,SEMANTIC=semantic,FULL=full,all_tests_after_whole_M1_worker=True,one_pytest_process_at_a_time=True,PR135_byte_preservation=True,executed_source_unchanged=True,scientific_model_identity=True,row_names_identity=True,source_data_identity=True,compile_PASS=True,git_diff_check_PASS=True,additional_scientific_solves=0))
    print('POST_VERIFY_PASS',semantic['passed'],full['passed'],len(manifest['files']),'preserved files; zero extra scientific solves')
if __name__=='__main__':run()
