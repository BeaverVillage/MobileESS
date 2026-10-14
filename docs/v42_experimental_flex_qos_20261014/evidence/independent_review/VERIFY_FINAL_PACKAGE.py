"""Independently verify packaged artifacts; no replay, optimizer or AC call."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,gzip,json

ROOT=Path(__file__).parents[2]
DOC=ROOT/'docs/v42_experimental_flex_qos_20261014'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest_stream(stream):
    digest=hashlib.sha256()
    for chunk in iter(lambda:stream.read(1<<20),b''):digest.update(chunk)
    return digest.hexdigest()
def sha(path):
    with Path(path).open('rb') as stream:return digest_stream(stream)

def main():
    manifest=read(DOC/'FINAL_ARTIFACT_MANIFEST.json');index=read(DOC/'PACKAGE_INDEX.json')
    frozen=read(ROOT/'audit/SOURCE_FREEZE_C.json');copied=read(DOC/'SOURCE_FREEZE_C.json')
    detail=read(ROOT/'audit/control/FINAL_FLEX_COMPARISON/COMPARISON_DETAIL.json')
    validation=read(ROOT/'audit/independent_review/C_COMPLETED_CASE_VALIDATION.json')
    funnel=read(ROOT/'audit/CONTROL_POLICY_CANDIDATE_FUNNEL_RECONCILIATION.json')
    checks=dict(required14=len(manifest['required_file_sha256'])==manifest['required_file_count']==14,
        required14_sha=all(sha(DOC/name)==expected for name,expected in manifest['required_file_sha256'].items()),
        source_sha=manifest['source_sha']==detail['source_sha']==validation['source_sha']==frozen['source_sha']==copied['source_sha'],
        source_freeze_bytes=sha(DOC/'SOURCE_FREEZE_C.json')==sha(ROOT/'audit/SOURCE_FREEZE_C.json'),
        independent18_complete_PASS=validation['complete'] is True and validation['completed_cases']==18
            and validation['all_completed_PASS'] is True and all(r['PASS'] and all(r['checks'].values()) for r in validation['cases']),
        independent_report_manifest_sha=sha(ROOT/'audit/independent_review/C_COMPLETED_CASE_VALIDATION.json')==manifest['independent_validation_report_sha256'],
        comparison27=len(detail['cells'])==27 and detail['E0_physical_executions']==1 and detail['E1_E2_physical_executions']==18,
        capacities_private_drop_budget_CC4=all(r['capacity_violations']==0 and r['private_future_controller_reads']==0
            and r['dropped_jobs']==0 and r['intentional_budget_violation_jobs']==0 and r['CC4_once_depletion_PASS'] for r in detail['cells']),
        service_mass=all(r['retrospective_service_audit']['PASS'] is True for r in detail['cells']),
        unperformed_AC_null=all(r['Actual_Maximum_Line_Loading'] is None and r['Fresh_AC']=='NOT_RUN' for r in detail['cells']),
        no_new_Native_or_optimality=all(r['Native_Optimize_calls']==0 and r['new_A_M_optimum'] is False for r in detail['cells']),
        funnel_reconciliation=funnel['PASS'] is True and funnel['aggregate_rows']==funnel['independent_executed_cases']==18
            and all(funnel['complete_detail_reparse_matches_each_case_aggregate'].values()),
        no_pending_execution_report_marker='PENDING_FINAL_EXECUTION_RECEIPTS' not in (DOC/'CONTROL_POLICY_FLEXIBILITY_FINAL_KO.md').read_text(encoding='utf8'),
        index_count=index['count']==len(index['artifacts'])==manifest['lossless_packaged_evidence'])
    errors=[];compressed_detail=None
    for record in index['artifacts']:
        target=DOC/record['packaged'];source=Path(record['source'])
        packed=sha(target)
        with (gzip.open(target,'rb') if record['compression'] else target.open('rb')) as stream:
            restored=digest_stream(stream)
        current_original=sha(source)
        if packed!=record['packaged_sha256'] or restored!=record['sha256'] or current_original!=record['sha256']:
            errors.append(dict(source=str(source),packaged=str(target),packed_sha=packed,
                restored_sha=restored,current_original_sha=current_original,record=record))
        if source.name=='CONTROL_POLICY_CANDIDATE_FUNNEL_EVENT_DETAIL.csv':
            compressed_detail=dict(record,restored_sha256=restored)
    checks['every_indexed_original_and_lossless_copy_SHA_PASS']=not errors
    checks['full_detail_csv_preserved_as_lossless_gzip']=compressed_detail is not None and compressed_detail['compression']=='GZIP_LOSSLESS'
    checks['detail_csv_reconciliation_SHA']=compressed_detail is not None and compressed_detail['sha256']==funnel['original_full_UID_time_detail_sha256']
    report=dict(schema='INDEPENDENT_FINAL_C_PACKAGE_READY_V1',updated_utc=datetime.now(timezone.utc).isoformat(),
        source_sha=frozen['source_sha'],checks=checks,PASS=all(checks.values()),packaged_artifacts=index['count'],
        required_artifacts=14,independent_E1_E2_executions=18,strict_E0_executions=1,comparison_cells=27,
        full_detail_event_rows=funnel['detailed_event_rows'],full_detail_compressed_copy=compressed_detail,
        copy_errors=errors,Native_Optimize_calls_by_reviewer=0,Actual_replays_by_reviewer=0,Fresh_AC_calls_by_reviewer=0,
        source_or_production_edits_by_reviewer=0,new_A_M_optimality_or_actual_AC_claim=False)
    # This final review is an extra root document, outside indexed evidence.
    # Creating it does not change any audited original or indexed copy.
    output=DOC/'FINAL_PACKAGE_INDEPENDENT_REVIEW.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps(dict(PASS=report['PASS'],failed=[k for k,v in checks.items() if not v],
        artifacts=index['count'],detail_rows=funnel['detailed_event_rows'],report=str(output))))
    if not report['PASS']:raise SystemExit(1)

if __name__=='__main__':main()
