from pathlib import Path
import hashlib,json,gzip,subprocess,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs/v42_cc4_v21_q90_recourse_20261014'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
report=DOC/'CONTROL_POLICY_Q90_CORRECTION_FINAL_KO.md'
report.write_text(report.read_text(encoding='utf8').replace('이 초안의 Source','이 보고서의 Source'),encoding='utf8')
freeze=json.loads((ROOT/'audit/CONTROL_POLICY_SOURCE_SHA_MANIFEST.json').read_text(encoding='utf8'))
source_ok=all(sha(ROOT/r['path'])==r['sha256'] for r in freeze['files'])
before=json.loads(Path('D:/v42_experimental_flex_qos_20261014/audit/PRESERVATION_AND_BUDGET_BEFORE.json').read_text(encoding='utf8'))
ledger=Path(before['path']);budget_ok=sha(ledger)==before['sha256']
lineage=[]
for path,head in [('D:/v42_common_am_qos_integration_20261013','8f0ea6e8f97147bb425530e8d787ca89f4a05053'),('D:/v42_policy_root_cause_fix_20261013','c6f1a0f41164b7da4afe406dd692abd583a29d1e')]:
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()
    lineage.append(dict(worktree=path,expected_head=head,actual_head=actual,PASS=actual==head))
xml=ET.parse(ROOT/'audit/FINAL_Q90_TEST_RESULTS.xml').getroot()
tests=list(xml.iter('testsuite'));test_ok=sum(int(x.get('tests','0')) for x in tests)==41 and all(int(x.get('errors','0'))==0 and int(x.get('failures','0'))==0 for x in tests)
receipt=dict(science_version=freeze['science_version'],source_sha=freeze['source_sha'],source_bytes_PASS=source_ok,
    original_V5_files_unchanged=freeze['original_V5_files_unchanged'],lineage=lineage,
    solver_budget_unchanged_PASS=budget_ok,solver_budget_sha=sha(ledger),solver_seconds=before['before_C']['conservative_solve_seconds'],
    limit_seconds=3600,Native_calls=0,AC_calls=0,tests=41,tests_PASS=test_ok,
    new_Fresh_AC='NOT_RUN',campaign31_HOLD=True,B2_B3_M_HOLD=True,
    PASS=source_ok and budget_ok and test_ok and all(x['PASS'] for x in lineage))
assert receipt['PASS'],receipt
write(ROOT/'audit/FINAL_DELIVERY_VERIFICATION.json',receipt)
manifest=json.loads((DOC/'ARTIFACT_MANIFEST.json').read_text(encoding='utf8'))
for name in ['FINAL_DELIVERY_VERIFICATION.json','FINAL_Q90_TEST_RESULTS.xml','FINALIZE_DELIVERY.py']:
    source=ROOT/'audit'/name;target=DOC/'evidence'/name;target.write_bytes(source.read_bytes())
    manifest['artifacts'].append(dict(path=target.relative_to(DOC).as_posix(),source=str(source),sha256=sha(source),compression=None))
for row in manifest['artifacts']:
    raw=(DOC/row['path']).read_bytes()
    if row['compression']:raw=gzip.decompress(raw)
    assert hashlib.sha256(raw).hexdigest()==row['sha256'],row['path']
manifest['required_file_sha256']={name:sha(DOC/name) for name in manifest['required_files']}
write(DOC/'ARTIFACT_MANIFEST.json',manifest)
attrs=ROOT/'.gitattributes';s=attrs.read_text(encoding='utf8')
for row in ['v42_integration/q90_*.py -text whitespace=cr-at-eol','tests/test_v42_q90_*.py -text whitespace=cr-at-eol','docs/v42_cc4_v21_q90_recourse_20261014/** -text whitespace=cr-at-eol','docs/v42_cc4_v21_q90_recourse_20261014/**/*.md whitespace=-blank-at-eol,cr-at-eol']:
    if row not in s:s+=row+'\n'
attrs.write_text(s,encoding='utf8')
print(json.dumps(dict(PASS=receipt['PASS'],source_sha=freeze['source_sha'],required=len(manifest['required_files']),evidence=len(manifest['artifacts']),budget_seconds=receipt['solver_seconds'])))
