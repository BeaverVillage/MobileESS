"""Verify fixed provenance, cutoff, preservation and model-free audit invariants."""
from common7 import *
import ast,datetime,subprocess,re,pandas as pd

REQUIRED=['REQUEST_FIELD_LINEAGE.csv','REQUEST_VERSION_FORENSIC.md','REQUEUE_DUPLICATE_AUDIT.csv','REQUEUE_DUPLICATE_SUMMARY.json','SUBMIT_TIME_AUTHORITY_AUDIT.json','ADDITIONAL_FEATURE_INVENTORY.csv','WORKFLOW_IDENTITY_AUDIT.csv','FEATURE_AUTHORITY_DECISION.csv','STRICT_CAUSAL_FEATURE_CONTRACT.json','RESEARCH_PROXY_FEATURE_CONTRACT.json','LONG_JOB_FEATURE_DIAGNOSTIC.csv','LONG_JOB_ROOT_CAUSE_AUDIT.md','COHORT_SUPPORT_AUDIT.csv','EXTERNAL_AUTHORITY_SOURCES.md','SOURCE_MANIFEST.json','FINAL_REVIEW_KO.md','FINAL_VERDICT.json']

def main():
    checks={};errors=[]
    def check(name,condition):
        checks[name]=bool(condition)
        if not condition:errors.append(name)
    for name in REQUIRED:check('required:'+name,(ROOT/name).is_file() and (ROOT/name).stat().st_size>0)
    freeze=read(ROOT/'FEATURE_AUTHORITY_FREEZE.json')
    for row in freeze['files']:check('frozen:'+Path(row['path']).name,sha(ROOT/Path(row['path']).name)==row['sha256'])
    a=pd.read_csv(ROOT/'FEATURE_AUTHORITY_DECISION.csv');strict=read(ROOT/'STRICT_CAUSAL_FEATURE_CONTRACT.json');v=read(ROOT/'FINAL_VERDICT.json')
    check('all_physical_fields_classified',set(read(ROOT/'RAW_SCHEMA_AUDIT.json')['actual_union_fields'])<=set(a.published_field.dropna()))
    check('all_58_candidates_unique',len(a)==58 and a.feature.is_unique)
    check('strict_set_exact_empty',strict['features']==[] and not a.strict_runtime_ml_allowed.any() and v['STRICT_CAUSAL_JOB_FEATURE_COUNT']==0)
    check('fail_closed',not v['NEXT_RUNTIME_ML_RETRAIN_AUTHORIZED'] and not v['STRICT_CAUSAL_RUNTIME_PROVIDER_READY'])
    check('workflow_partial_not_strict',v['WORKFLOW_IDENTITY_SUPPORTED']=='PARTIAL' and not pd.read_csv(ROOT/'WORKFLOW_IDENTITY_AUDIT.csv').strict_allowed.any())
    check('authority_before_diagnostics',freeze['time']<read(ROOT/'DESCRIPTIVE_RECEIPT.json')['time'])
    prep=read(ROOT/'PREPARATION_RECEIPT.json');d=read(ROOT/'REQUEUE_DUPLICATE_SUMMARY.json')
    check('raw_no_dedup',prep['total_rows']==6326884==d['total_preApril_rows'] and not prep['all_rows_deduplicated'] and d['no_deduplication_before_audit'])
    check('no_April_May_partitions',all(tuple(map(int,re.search(r'year=(\d+)/month=(\d+)/',p['member']).groups()))<=(2025,3) for p in prep['partitions']))
    g=pd.read_parquet(LOCAL/'GPU_PREAPRIL.parquet')
    cut=pd.Timestamp('2025-04-01T00Z')
    check('no_future_label_values',g.submit_time.lt(cut).all() and g.end_time.dropna().lt(cut).all() and g.start_time.dropna().lt(cut).all())
    check('gpu_rows_and_source_hash',len(g)==621583 and sha(LOCAL/'GPU_PREAPRIL.parquet')==prep['gpu_local_data']['sha256'])
    check('nonnegative_mature_labels',(g.loc[g.label_valid,'runtime_seconds']>=0).all() and int(g.label_valid.sum())==621004)
    audit=pd.read_csv(ROOT/'REQUEUE_DUPLICATE_AUDIT.csv')
    check('duplicate_reconciliation',len(audit)==4104 and int(audit.record_count.sum())==310128 and d['full_id_duplicate_rows']==0)
    check('no_false_revision_claim',not audit.initial_request_reconstructable.any() and not audit.change_observed_within_same_task.any())
    supplement=read(ROOT/'ARRAY_IDENTITY_SUPPLEMENT.json')
    check('array_supplement',supplement['groups']==274 and supplement['all_have_single_unindexed_row'] and supplement['same_coordinate_duplicate_nonmissing_rows']==0)
    rs=pd.read_csv(ROOT/'COHORT_ROLE_SUMMARY.csv').set_index('role')
    check('role_cohort_counts',rs.loc['CAL','n']==rs.loc['CAL_FIT','n']+rs.loc['CAL_VALID','n'] and rs.loc['DEV','high_gpu_n']==93 and rs.loc['CAL','high_gpu_n']==27)
    cats=pd.read_csv(ROOT/'COHORT_CATEGORY_SUPPORT.csv.gz')
    totals=cats.groupby(['role','feature']).n.sum()
    check('category_counts_reconcile',all(total==rs.loc[key[0],'n'] for key,total in totals.items()))
    forbidden_imports={'lightgbm','xgboost','sklearn','torch','tensorflow','lifelines','sksurv'};banned_calls={'fit','fit_transform','train','partial_fit'}
    for p in ROOT.glob('*.py'):
        tree=ast.parse(p.read_text(encoding='utf-8-sig'));bad=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):bad.extend(n.name for n in node.names if n.name.split('.')[0] in forbidden_imports)
            if isinstance(node,ast.ImportFrom) and (node.module or '').split('.')[0] in forbidden_imports:bad.append(node.module)
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in banned_calls:bad.append(node.func.attr)
        check('no_ML_code:'+p.name,not bad)
    check('no_reported_training',v['models_trained']==0 and not v['model_selected'] and prep['models_trained']==0)
    check('16_questions',len(re.findall(r'^## \d+\.',(ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8'),flags=re.M))==16)
    manifest=read(ROOT/'SOURCE_MANIFEST.json');source_checks=[]
    for rec in manifest['local']+manifest['remote']+manifest['search_receipts']+[manifest['raw_archives']['primary'],manifest['raw_archives']['second']]:
        ok=Path(rec['path']).is_file() and sha(rec['path'])==rec['sha256'];source_checks.append(ok)
        if not ok:errors.append('source_hash:'+rec['path'])
    check('all_source_bytes_unchanged',all(source_checks))
    old=REPO/'docs/runtime_vnext6_callable_total';oldm=read(old/'DELIVERY_MANIFEST.json')
    # Byte hashes only: no April/May semantic payload decoding.
    old_ok=all(sha(old/r['relative'])==r['sha256'] for r in oldm['files'])
    check('vNext6_delivery_bytes_unchanged',old_ok)
    diff=subprocess.run(['git','diff',BASE,'--name-only','--'],cwd=REPO,capture_output=True,text=True,encoding='utf-8')
    changed=[p for p in diff.stdout.splitlines() if p]
    check('base_tracked_scope_preserved',diff.returncode==0 and all(p.startswith('docs/runtime_vnext7_feature_authority_recovery/') for p in changed))
    status=subprocess.run(['git','status','--porcelain','--untracked-files=all'],cwd=REPO,capture_output=True,text=True,encoding='utf-8')
    check('working_changes_in_namespace_only',status.returncode==0 and all('docs/runtime_vnext7_feature_authority_recovery/' in x for x in status.stdout.splitlines()))
    result=dict(status='PASS' if not errors else 'FAIL',created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),checks=checks,errors=errors,
      required_artifacts=len(REQUIRED),source_hashes_checked=len(source_checks),vNext6_files_hashed=len(oldm['files']),
      immutable_preservation='Byte-only SHA verification of prior artifacts; no locked metrics read or selected on.',new_namespace_only=True,
      model_training_count=0,April_May_evaluation_run=False)
    # Rechecking must not overwrite the original verification receipt.
    if (ROOT/'VERIFICATION.json').exists():
        if read(ROOT/'VERIFICATION.json')['status']!='PASS':raise SystemExit('Prior verification failed; preserve it and investigate.')
    else:write('VERIFICATION.json',result)
    print(result['status'],len(checks),'checks',len(errors),'errors',flush=True)
    if errors:raise SystemExit(errors)

if __name__=='__main__':main()
