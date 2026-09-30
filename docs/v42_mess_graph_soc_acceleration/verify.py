"""Verify evidence, allowed merge surface and byte-preserved PR99 files.

Default seals manifests; --check is read-only and verifies the existing seal.
"""
import argparse
import ast
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from v42_native.contracts import file_sha, require
from v42_native.mess_audit import BASE

ALLOWED_CHANGED={'v42_native/mess.py','tests/test_v42_temporal.py'}
ADDED={'v42_native/mess_domain.py','v42_native/mess_optimizer.py','v42_native/mess_audit.py',
       'tests/test_v42_mess_acceleration.py'}
REQUIRED=('README.md PREREGISTRATION.json MESS_BASELINE_DOMAIN_AUDIT.csv MESS_BASELINE_MODEL_SIZE.json '
          'MESS_FORWARD_REACHABILITY.csv MESS_BACKWARD_REACHABILITY.csv MESS_FORWARD_SOC_ENVELOPE.csv '
          'MESS_BACKWARD_SOC_ENVELOPE.csv MESS_SOC_INTERSECTION_AUDIT.csv MESS_ARC_SOC_FEASIBILITY.csv '
          'MESS_EXACT_DUPLICATE_AUDIT.json MESS_FIXED_POINT_PRUNING.json MESS_FINAL_DOMAIN_AUDIT.csv '
          'MESS_ELECTRICAL_COLUMN_REDUCTION.csv MESS_FORMULATION_EQUIVALENCE.json MESS_OBJECTIVE_EQUIVALENCE.json '
          'MESS_ADVERSARIAL_SOC_TESTS.json MESS_SHARED_DOMAIN_AUTHORITY.json MESS_M1_MODEL_STATS.json '
          'MESS_M2_MODEL_STATS.json MESS_WARM_START_AUDIT.json MESS_BOTTLENECK_CLASSIFICATION.json '
          'MESS_NEXT_ALGORITHM_DECISION.json FINAL_FLAGS.json FINAL_VERDICT.json FINAL_REVIEW_KO.md '
          'SOURCE_MANIFEST.json LOCAL_EVIDENCE_MANIFEST.json LEGACY_PRESERVATION_AUDIT.json VERIFICATION.json').split()


def read(name):return json.loads((HERE/name).read_text(encoding='utf-8'))
def dump(name,data):(HERE/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def source_sha(path):return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    preservation=read('LEGACY_PRESERVATION_AUDIT.json');changes=[]
    for row in preservation['files']:
        current=file_sha(ROOT/row['path'])
        row['current_sha256']=current;row['unchanged']=current==row['sha256']
        if not row['unchanged']:changes.append(row['path'])
    require(set(changes)==ALLOWED_CHANGED,'UNAUTHORIZED_OR_MISSING_LEGACY_CHANGE:'+str(changes))
    preservation.update(PASS=True,authorized_changes=sorted(ALLOWED_CHANGED),
                        unchanged_files=len(preservation['files'])-len(changes),
                        old_evidence_files_byte_preserved=True,AIDC_Runtime_CC4_TS_byte_preserved=True)
    old_ast=ast.parse(subprocess.check_output(['git','show',BASE+':v42_native/mess.py'],cwd=ROOT).decode())
    new_ast=ast.parse((ROOT/'v42_native/mess.py').read_text())
    for definition in ('RouteArc','Battery','pcs_rows'):
        get=lambda tree:next(n for n in tree.body if getattr(n,'name',None)==definition)
        require(ast.dump(get(old_ast))==ast.dump(get(new_ast)),'PHYSICAL_AUTHORITY_AST_CHANGED:'+definition)
    diff=subprocess.check_output(['git','diff','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    require(all(p in ALLOWED_CHANGED|ADDED or p.startswith('docs/v42_mess_graph_soc_acceleration/') for p in diff),'MERGE_SURFACE_DRIFT')
    suite=ET.parse(HERE/'TEST_RESULTS.xml').getroot().find('testsuite')
    require(suite is not None and int(suite.attrib['tests'])>=457,'TEST_SUITE_INCOMPLETE')
    require(int(suite.attrib['failures'])==int(suite.attrib['errors'])==int(suite.attrib['skipped'])==0,'TEST_FAILURE_OR_SKIP')
    formulation=read('MESS_FORMULATION_EQUIVALENCE.json');objective=read('MESS_OBJECTIVE_EQUIVALENCE.json')
    require(formulation['PASS'] and objective['PASS'] and len(formulation['cases'])==77,'EQUIVALENCE_MISSING')
    for row in formulation['cases'].values():require(row['PASS'] and row['false_pruned']==0,'FALSE_PRUNING')
    for row in objective['cases'].values():require(row['PASS'] and all(abs(d)<=3e-7 for d in row['differences'].values()),'OBJECTIVE_DRIFT')
    warm=read('MESS_WARM_START_AUDIT.json');require(warm['PASS'] and warm['accepted'] and warm['physical_validation']['PASS'],'WARM_FAILED')
    require(all(abs(v-warm['warm']['objectives'][k])<=3e-7 for k,v in warm['cold']['objectives'].items()),'WARM_OBJECTIVE_CHANGED')
    require(all(d['object_identity_reused'] for d in read('MESS_SHARED_DOMAIN_AUTHORITY.json').values()),'DOMAIN_NOT_REUSED')
    prereg=read('PREREGISTRATION.json')
    require(prereg['native_optimize_seconds']=={'M1':1800,'M2':1800} and prereg['native_MIPGap']==.005,'PREREGISTRATION_DRIFT')
    flags=read('FINAL_FLAGS.json')
    require(not any(flags[k] for k in ('MESS_PHYSICS_CHANGED','MESS_ROUTE_AUTHORITY_CHANGED','FALSE_FEASIBLE_PATH_PRUNED',
            'NATIVE_M1_RUN','NATIVE_M2_RUN','MESS_DW_TRIGGER','CL_MC_BD_TRIGGER','NEW_ML')),'FORBIDDEN_FLAG')
    for stage in ('M1','M2'):
        stats=read(f'MESS_{stage}_MODEL_STATS.json')
        require(stats['native_status']=='NOT_RUN_AWAITING_ACCEPTED_A_BLOCK' and not stats['native_grid_model_built'],'NATIVE_GATE_DRIFT')
        r=stats['bounded_receipt']
        require(r['budget_origin']=='FIRST_OPTIMIZE' and r['presolve_included'] and not r['build_included'],'TIMER_DRIFT')
        require(r['model_size_before_solve']['quadratic_constraints']==0,'NON_MILP')
    source=read('SOURCE_MANIFEST.json')
    native=source['native_route_source'];require(file_sha(native['path'])==native['expected_sha256']==native['sha256'],'NATIVE_SOURCE_DRIFT')
    for f in source['files']:require(file_sha(f['path'])==f['sha256'],'SOURCE_HASH_DRIFT')
    reduction=list(csv.DictReader((HERE/'MESS_ELECTRICAL_COLUMN_REDUCTION.csv').open(encoding='utf-8')))
    static={row['metric']:row for row in reduction if row['case']=='native_static_96'}
    require(float(static['arc']['reduction'])==float(static['Pch']['reduction'])==0,'NATIVE_REDUCTION_OVERCLAIM')
    require(float(static['total_rows']['reduction'])==274 and float(static['nonzeros']['reduction'])==0,'NATIVE_SIZE_DRIFT')
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True,capture_output=True)
    if not args.check:
        dump('LEGACY_PRESERVATION_AUDIT.json',preservation)
        source['implementation_hash_policy']='Python code hashes normalize CRLF to LF for checkout portability; legacy/evidence/source-data hashes preserve bytes'
        source['implementation_files']=[dict(path=p,sha256=source_sha(ROOT/p)) for p in sorted(ALLOWED_CHANGED|ADDED)]
        dump('SOURCE_MANIFEST.json',source)
        evidence=[dict(path=p.relative_to(ROOT).as_posix(),sha256=file_sha(p),bytes=p.stat().st_size)
                  for p in sorted(HERE.iterdir()) if p.is_file() and p.name not in ('LOCAL_EVIDENCE_MANIFEST.json','VERIFICATION.json')]
        dump('LOCAL_EVIDENCE_MANIFEST.json',dict(files=evidence,exclusions=['Self hash and VERIFICATION.json excluded to avoid recursive seals']))
        dump('VERIFICATION.json',dict(PASS=True,tests=int(suite.attrib['tests']),failures=0,errors=0,skipped=0,
             bounded_cases=77,baseline=BASE,byte_preserved_files=preservation['unchanged_files'],
             authorized_modified_existing_files=sorted(ALLOWED_CHANGED),native_M1_M2_run=False,
             legacy_evidence_byte_preserved=True,physics_authority_AST_equal=True,
             feasible_set_and_objective_equivalence=True,full_warm_start_validated=True,
             native_route_source_SHA_verified=True,git_diff_check=True,
             numerical_note='Diagnostic FeasibilityTol/OptimalityTol/IntFeasTol 1e-9 on both models; production gap .005 unchanged',
             commands=['python docs/v42_mess_graph_soc_acceleration/audit.py',
                       'python -m pytest -q --junitxml=docs/v42_mess_graph_soc_acceleration/TEST_RESULTS.xml',
                       'python docs/v42_mess_graph_soc_acceleration/verify.py --check','git diff --check'],
             limits=['No accepted A1/A2; native solve/root/grid/B&B classification unmeasured',
                     'Existing 600s total-wall supervisor remains untouched; future native outer timer integration required',
                     'Domain reuse measured within common engine process and explicit object handoff, not unimplemented native backend']))
    for f in read('LOCAL_EVIDENCE_MANIFEST.json')['files']:
        require(file_sha(ROOT/f['path'])==f['sha256'],'LOCAL_EVIDENCE_HASH_DRIFT:'+f['path'])
    for f in read('SOURCE_MANIFEST.json')['implementation_files']:
        require(source_sha(ROOT/f['path'])==f['sha256'],'IMPLEMENTATION_HASH_DRIFT')
    require(all((HERE/name).is_file() for name in REQUIRED),'REQUIRED_OUTPUT_MISSING')
    print(json.dumps(dict(PASS=True,tests=int(suite.attrib['tests']),byte_preserved_files=preservation['unchanged_files'],
                          bounded_cases=77,native_status='NOT_RUN_AWAITING_ACCEPTED_A_BLOCK'),indent=2))


if __name__=='__main__':main()
