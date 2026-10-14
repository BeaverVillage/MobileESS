from pathlib import Path
import json,shutil,hashlib,xml.etree.ElementTree as ET
from PACKAGE_AND_REPORT import package
ROOT=Path(__file__).resolve().parents[1];DOC=ROOT/'docs/v42_experimental_flex_qos_20261014'
FILES={
 'EXPERIMENTAL_FLEX_QOS_POLICY_KO.md':'qos/EXPERIMENTAL_FLEX_QOS_POLICY_KO.md',
 'SOURCE_VS_ASSUMED_QOS_CONTRACT.json':'qos/SOURCE_VS_ASSUMED_QOS_CONTRACT.json',
 'E0_E1_E2_POLICY_MANIFEST.json':'qos/E0_E1_E2_POLICY_MANIFEST.json',
 'FLEX20_30_40_MEMBERSHIP_AUDIT.csv':'qos/FLEX20_30_40_MEMBERSHIP_AUDIT.csv',
 'Q90_QUEUE_CARRYOVER_REFORMULATION.json':'Q90_QUEUE_CARRYOVER_REFORMULATION.json',
 'CONTROL_RESOURCE_GUARD_BEFORE_AFTER.json':'CONTROL_RESOURCE_GUARD_BEFORE_AFTER.json',
 'PREPLACEMENT_ZERO_DELAY_REGRESSION.json':'PREPLACEMENT_ZERO_DELAY_REGRESSION.json',
 'MIGRATION_ASSUMPTION_AUTHORITY.json':'MIGRATION_ASSUMPTION_AUTHORITY.json',
 'KNOWN_UNKNOWN_POLICY_EQUIVALENCE.json':'qos/KNOWN_UNKNOWN_POLICY_EQUIVALENCE.json',
 'CONTROL_POLICY_CANDIDATE_FUNNEL.csv':'CONTROL_POLICY_CANDIDATE_FUNNEL.csv',
 'POLICY_E0_E1_E2_COMPARISON.csv':'POLICY_E0_E1_E2_COMPARISON.csv',
 'POLICY_GRID_GREEDY_FIXED_ABLATION.json':'POLICY_GRID_GREEDY_FIXED_ABLATION.json',
 'SCIENTIFIC_SOURCE_SUPERSESSION.json':'SCIENTIFIC_SOURCE_SUPERSESSION.json',
 'CONTROL_POLICY_FLEXIBILITY_FINAL_KO.md':'CONTROL_POLICY_FLEXIBILITY_FINAL_KO_DRAFT.md'}
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def main():
    evidence=read(ROOT/'audit/control/FINAL_FLEX_COMPARISON/COMPARISON_DETAIL.json')
    validation_path=ROOT/'audit/independent_review/C_COMPLETED_CASE_VALIDATION.json'
    validation=read(validation_path)
    cases=read(ROOT/'audit/control/FINAL_FLEX_COMPARISON/CASE_MANIFEST.json')
    frozen=read(ROOT/'audit/SOURCE_FREEZE_C.json')
    expected={'_'.join(c[k] for k in ('scenario','participation','algorithm')):c for c in cases['cases']}
    checked={c['name']:c for c in validation['cases']}
    assert (validation['complete'] is True and validation['completed_cases']==validation['expected_cases']==18
        and validation['all_completed_PASS'] is True and len(checked)==18 and set(checked)==set(expected)), 'INDEPENDENT18_VALIDATION_NOT_COMPLETE_PASS'
    assert validation['source_sha']==cases['source_sha']==evidence['source_sha']==frozen['source_sha'], 'FINAL_SOURCE_BINDING_DRIFT'
    assert all(c['PASS'] and all(c['checks'].values()) and c['checks']['intentional_budget']
        and c['case_sha']==expected[name]['case_sha'] and c['source_sha']==frozen['source_sha']
        and c['summary']['intentional_budget_violation_jobs']==0 for name,c in checked.items()), 'INDEPENDENT_CASE_PROGRAM_RESULT_OR_BUDGET_GUARD_FAILED'
    assert len(evidence['cells'])==27 and evidence['E1_E2_physical_executions']==18
    assert evidence['all_capacity_PASS'] and evidence['all_private_reads_zero'] and evidence['all_service_mass_PASS']
    assert all(r['dropped_jobs']==0 and r['CC4_once_depletion_PASS'] for r in evidence['cells'])
    assert all(r['intentional_budget_violation_jobs']==0 for r in evidence['cells']), 'FINAL_INTENTIONAL_BUDGET_VIOLATION'
    for name,source in FILES.items():
        path=ROOT/'audit'/source
        if not path.is_file():raise ValueError('REQUIRED_FINAL_ARTIFACT_MISSING:'+str(path))
        shutil.copyfile(path,DOC/name)
    report=DOC/'CONTROL_POLICY_FLEXIBILITY_FINAL_KO.md';text=report.read_text(encoding='utf8')
    assert 'PENDING_FINAL_EXECUTION_RECEIPTS' not in text,'REPORT_STILL_DRAFT_PENDING'
    report.write_text(text.replace('최종 보고서 초안','최종 보고서'),encoding='utf8')
    shutil.copyfile(ROOT/'audit/SOURCE_FREEZE_C.json',DOC/'SOURCE_FREEZE_C.json')
    rows=package()
    manifest=dict(required_file_count=14,required_file_sha256={name:hashlib.sha256((DOC/name).read_bytes()).hexdigest() for name in FILES},
        lossless_packaged_evidence=len(rows),source_sha=evidence['source_sha'],comparison_cells=27,
        E0_physical_executions=1,E1_E2_physical_executions=18,new_Native_Optimize_calls=0,Fresh_AC='NOT_RUN',
        independent18_validation_complete=True,independent18_validation_PASS=True,
        independent_validation_report_sha256=hashlib.sha256(validation_path.read_bytes()).hexdigest(),
        CaseManifest_source_program_result_binding_PASS=True,all_intentional_budget_violations_zero=True,
        all_service_mass_PASS=True,all_capacity_PASS=True,all_private_controller_reads_zero=True,
        B2_B3_M_HOLD=True,May31_HOLD=True,old_results_modified=False)
    write(DOC/'FINAL_ARTIFACT_MANIFEST.json',manifest)
    print(json.dumps(dict(required=14,evidence=len(rows),source_sha=evidence['source_sha'])))
if __name__=='__main__':main()
