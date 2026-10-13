from pathlib import Path
import hashlib,json,subprocess,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def main():
    freeze=read(ROOT/'audit/SOURCE_FREEZE_C.json');source_PASS=all(sha(ROOT/r['path'])==r['sha256'] for r in freeze['files'])
    protected=read('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/PRESERVATION_AFTER.json')
    protected_rows=[dict(r,current_sha256=sha(r['path']),PASS=sha(r['path'])==r['sha256']) for r in protected['files']]
    budget=read(ROOT/'audit/PRESERVATION_AND_BUDGET_BEFORE.json');ledger=read(budget['path'])
    lineage=[]
    for path,expected in [('D:/v42_common_am_qos_integration_20261013','8f0ea6e8f97147bb425530e8d787ca89f4a05053'),
        ('D:/v42_policy_root_cause_fix_20261013','c6f1a0f41164b7da4afe406dd692abd583a29d1e'),
        ('D:/v42_q90_service_recourse_20261014','97da5c097f0eefc30a057c51378676c6402138c8')]:
        actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()
        lineage.append(dict(path=path,expected=expected,actual=actual,PASS=actual==expected))
    old=read(ROOT/'audit/performance/EPOCH03_OLD_PREFIX/PREFIX_RECEIPT.json')
    new=read(ROOT/'audit/performance/EPOCH04_EXACT_CACHE_PREFIX/PREFIX_RECEIPT.json')
    parsed=ET.parse(ROOT/'audit/FINAL_INTEGRATED_TEST_RESULTS.xml').getroot();tests=list(parsed.iter('testsuite'))
    value=dict(source_sha=freeze['source_sha'],source_bytes_PASS=source_PASS,old_A_B_D_lineage=lineage,
        original_V5_1779_python_bytes_PASS=freeze['original_V5_files_unchanged'],protected_campaign_files=protected_rows,
        solver_ledger_sha_unchanged_PASS=sha(budget['path'])==budget['sha256'],solver_charged_seconds=ledger['conservative_solve_seconds'],
        solver_limit_seconds=3600,old_AC_seconds=ledger['AC_wall_seconds'],new_Native_Optimize_calls=0,new_AC_calls=0,
        tests=sum(int(t.get('tests')) for t in tests),test_failures=sum(int(t.get('failures')) for t in tests),
        two_slot_performance=dict(old_source_sha=old['source_sha'],new_source_sha=new['source_sha'],
            old_seconds=old['wall_seconds'],new_seconds=new['wall_seconds'],ratio=old['wall_seconds']/new['wall_seconds'],
            canonical_behavior_PASS=old['canonical_behavior_sha']==new['canonical_behavior_sha'],
            all_GPU_IT_PCC_arrays_bitwise_PASS=old['array_sha']==new['array_sha'],
            independent_review='audit/independent_review/C_EXACT_CACHE_PREFIX_INDEPENDENT_REVIEW.json',
            scope='TWO_SLOT_SAME_INPUT_INCLUDE_SETUP_NOT_WHOLE_FULL96_SPEEDUP'),
        abandoned_probe='audit/performance/EPOCH03_PRECACHE/ABORTED_PROBE_RECEIPT.json',
        B2_B3_M_HOLD=True,May31_HOLD=True,new_A_M_optimization='NOT_RUN',Fresh_AC='NOT_RUN')
    value['PASS']=source_PASS and value['solver_ledger_sha_unchanged_PASS'] and all(r['PASS'] for r in protected_rows+lineage) and value['test_failures']==0
    assert value['PASS'];write(ROOT/'audit/FINAL_PRESERVATION_AND_PERFORMANCE.json',value)
    print(json.dumps({k:value[k] for k in ('source_sha','PASS','tests','solver_charged_seconds')}))
if __name__=='__main__':main()
