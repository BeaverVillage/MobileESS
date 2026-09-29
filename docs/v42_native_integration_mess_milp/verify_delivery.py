"""Verify artifacts, protected inputs, and optional staged Git blob identity."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
REQUIRED='''README.md PREREGISTRATION.json NATIVE_SOURCE_AUTHORITY_AUDIT.md
V42_CONTINUOUS_SERVICE_CONTRACT.md CARRY_OVER_RECONCILIATION_AUDIT.json SERVICE_IDENTITY_AUDIT.json
PR79_RESOURCE_CONFLICT_ROOT_CAUSE.md EPISODE_RESOURCE_RECONCILIATION.json RUNTIME_CC4_INTERFACE_STATUS.json
AIDC_NATIVE_BINDING_AUDIT.json AIDC_OPTION_PRESCREEN_AUDIT.csv MESS_QUADRATIC_CONSTRAINT_AUDIT.csv
MESS_MILP_FORMULATION.md MESS_UNIT_AUDIT.json PCS_POLYGON_VALIDATION.csv MISOCP_VS_MILP_BOUNDED_COMPARISON.csv
OBJECTIVE_NATIVE_BINDING.md P2_RESERVE_STATUS.json EVENT_ACTUAL_CONTROL_CONTRACT.md LOCAL_REPAIR_PQ_CONTRACT.md
MODEL_SIZE_AUDIT.csv WARM_START_AUDIT.json NATIVE_COMPUTATIONAL_CANARY.csv NATIVE_COMPUTATIONAL_CANARY.json
FRESH_AC_CANARY_VALIDATION.json FINAL_FLAGS.json FINAL_VERDICT.json FINAL_REVIEW_KO.md SOURCE_MANIFEST.json
TEST_RESULTS.xml NATIVE_GATE_EVIDENCE.json'''.split()


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(name):return json.loads((HERE/name).read_text(encoding='utf-8'))
def save(name,data):(HERE/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write-manifest',action='store_true');parser.add_argument('--staged',action='store_true');args=parser.parse_args()
    for name in REQUIRED:assert (HERE/name).is_file(),name
    review=(HERE/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8')
    assert [int(x) for x in re.findall(r'^(\d+)\. ',review,re.M)]==list(range(1,51))
    flags=read('FINAL_FLAGS.json');native=read('NATIVE_COMPUTATIONAL_CANARY.json')
    for k in ('FULL_IEEE123_ROUND_RUN','IEEE8500_FULL_RUN','FLEX_SENSITIVITY_RUN','NEW_MAY_POLICY_EVALUATION','SEMANTIC_ML_MERGED','FRESH_AC_CANARY_PASS','V42_PHYSICAL_OPTIMIZER_READY'):
        assert flags[k] is False,k
    for stage in ('A1','M1','A2','M2'):
        assert all(flags[stage+'_'+suffix] is None for suffix in ('RUNTIME_SECONDS','FINAL_GAP','BINARY_COUNT'))
    assert native['status']=='NOT_RUN_SOURCE_GATE_FAILED' and native['preregistered_day']=='2025-04-01'
    assert flags['MESS_QUADRATIC_CONSTRAINT_COUNT']==0 and flags['PCS_POLYGON_IS_INNER_SAFE'] and flags['P2_RESERVE_OBJECTIVE_RETAINED']
    for row in read('SOURCE_MANIFEST.json')['files']:assert sha(row['path'])==row['sha256'],row['path']
    join=read('EPISODE_RESOURCE_RECONCILIATION.json')['source_join'];assert sha(join['path'])==join['sha256']
    suites=list(ET.parse(HERE/'TEST_RESULTS.xml').getroot().iter('testsuite'))
    assert all(int(s.attrib.get('failures',0))+int(s.attrib.get('errors',0))==0 for s in suites)
    files=sorted(set(p for p in list(HERE.glob('*'))+list((ROOT/'v42_native').glob('*'))+
        [ROOT/'tests/test_v42_native.py',ROOT/'tests/.gitattributes'] if p.is_file() and p.name not in ('DELIVERY_MANIFEST.json','VERIFICATION.json')))
    entries=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in files]
    if args.write_manifest:save('DELIVERY_MANIFEST.json',dict(files=entries,excluded_self_and_verification=True))
    assert entries==read('DELIVERY_MANIFEST.json')['files'],'DELIVERY_MANIFEST_DRIFT'
    if args.staged:
        for row in entries:
            blob=subprocess.run(['git','show',':'+row['path']],cwd=ROOT,capture_output=True,check=True).stdout
            assert hashlib.sha256(blob).hexdigest()==row['sha256'],'STAGED_BLOB_DRIFT:'+row['path']
    result=dict(PASS=True,required_artifacts=len(REQUIRED),review_answers=50,delivery_files=len(entries),
        protected_source_files=len(read('SOURCE_MANIFEST.json')['files']),protected_files_changed=0,
        tests_passed=sum(int(s.attrib['tests']) for s in suites),native_canary_run=False,Fresh_AC_run=False,
        staged_blob_verification=args.staged,manifest_excludes=['DELIVERY_MANIFEST.json','VERIFICATION.json'])
    save('VERIFICATION.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
