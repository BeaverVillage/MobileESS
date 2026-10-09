"""Post-run delivery audits with no solver calls or historical mutations."""
from datetime import datetime,timedelta
from fractions import Fraction as F
import json
from pathlib import Path
import shutil
from .case import REPORTS
from v42_unified.audit import ROOT,git,write
from v42_unified.storage import sha
from v42_unified.delivery import verify_preservation


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def verify_final_binding(original):
    """Bind one immutable Native run, admission view and final checker receipt.

    This performs no model solve or source mutation.  Rechecking the small
    ledger prevents a stale PASS receipt from supplying another run's costs.
    """
    original=Path(original).resolve()
    base=(ROOT/'runtime/v42_m1_joint_gap_research').resolve()
    if ROOT.resolve().drive.upper()!='D:' or not original.is_relative_to(base):
        raise ValueError('FINAL_DELIVERY_D_RESEARCH_RUN_REQUIRED')
    receipt=read(REPORTS/'JOINT_LB_UB_GAP.json')
    creation=read(REPORTS/'FINAL_ADMISSION_VIEW.json')
    if receipt.get('PASS') is not True or creation.get('PASS') is not True:
        raise ValueError('FINAL_INDEPENDENT_ADMISSION_REQUIRED')
    if Path(creation['original_run']).resolve()!=original:
        raise ValueError('FINAL_DELIVERY_ORIGINAL_RUN_MISMATCH')
    view=Path(creation['read_only_replay_view']).resolve()
    if not view.is_relative_to(base) or view==original:
        raise ValueError('FINAL_DELIVERY_VIEW_PATH_MISMATCH')
    ledger=read(original/'NATIVE_RUNTIME_LEDGER.json')
    raw=read(original/'RESEARCH_TRACK_RESULTS.json')
    case_sha=read(REPORTS/'SCIENTIFIC_MODEL_IDENTITY.json')['case_sha']
    if any(obj.get('case_sha')!=case_sha for obj in (receipt,creation,ledger,raw)):
        raise ValueError('FINAL_DELIVERY_SCIENTIFIC_CASE_MISMATCH')
    if ledger.get('inflight') is not None or raw.get('ledger')!=ledger:
        raise ValueError('FINAL_DELIVERY_ORIGINAL_LEDGER_NOT_FINALIZED')
    original_ledger_sha=sha(original/'NATIVE_RUNTIME_LEDGER.json')
    view_ledger_sha=sha(view/'NATIVE_RUNTIME_LEDGER.json')
    if (original_ledger_sha!=view_ledger_sha or
        creation.get('original_native_ledger_sha256')!=original_ledger_sha or
        creation.get('view_native_ledger_sha256')!=view_ledger_sha):
        raise ValueError('FINAL_DELIVERY_ORIGINAL_VIEW_LEDGER_BYTE_DRIFT')
    if read(view/'RESEARCH_TRACK_RESULTS.json').get('ledger')!=ledger:
        raise ValueError('FINAL_DELIVERY_VIEW_LEDGER_SNAPSHOT_DRIFT')
    files=creation.get('original_files_SHA256',{})
    if not {'RESEARCH_TRACK_RESULTS.json','NATIVE_RUNTIME_LEDGER.json','FINAL_VALID_UB_POINT.npz'}<=set(files):
        raise ValueError('FINAL_DELIVERY_ORIGINAL_FILE_MANIFEST_INCOMPLETE')
    for name,digest in files.items():
        path=(original/name).resolve()
        if path.parent!=original or sha(path)!=digest:
            raise ValueError('FINAL_DELIVERY_ORIGINAL_PRODUCER_FILE_DRIFT:'+name)
    selected=(view/'FINAL_VALID_UB_POINT.npz').resolve()
    for evidence in (receipt.get('checked_UB_packet',{}),creation.get('selected_view_packet',{})):
        if Path(evidence.get('path','')).resolve()!=selected or evidence.get('sha256')!=sha(selected):
            raise ValueError('FINAL_DELIVERY_CHECKED_UB_VIEW_PACKET_MISMATCH')
    # The recorded static review pins the strict gate used by admission and by
    # final aggregation.  A hard-coded "unchanged" flag is insufficient.
    review=read(REPORTS/'FINAL_INDEPENDENT_REVIEW.json')
    expected=review['final_admission']['unchanged_final_check_joint_source_sha256']
    actual=sha(ROOT/'v42_m1_research/check_joint.py')
    if review.get('scientific_case_sha')!=case_sha or expected!=actual:
        raise ValueError('FINAL_DELIVERY_INDEPENDENT_CHECKER_SOURCE_DRIFT')
    from .check_joint import check_ledger
    accounting=check_ledger(ledger,case_sha)
    if receipt.get('independent_native_accounting')!=accounting:
        raise ValueError('FINAL_DELIVERY_INDEPENDENT_ACCOUNTING_RECEIPT_DRIFT')
    return dict(PASS=True,case_sha=case_sha,original_run=str(original),view=str(view),
        original_native_ledger_sha256=original_ledger_sha,view_native_ledger_sha256=view_ledger_sha,
        independent_final_gate=dict(expected_sha256=expected,actual_sha256=actual,PASS=True),
        original_producer_files_checked=len(files),original_files_unchanged=True,
        checker_accounting_freshly_recomputed_without_Native=True,
        Native_Runtime=accounting['Native_Runtime_sum'],additional_Native_optimize_calls=0)


def final_audits(original):
    original=Path(original).resolve();binding=verify_final_binding(original)
    receipt=read(REPORTS/'JOINT_LB_UB_GAP.json')
    ledger=read(original/'NATIVE_RUNTIME_LEDGER.json')
    if ledger['inflight'] is not None:raise ValueError('RUN_MUST_HAVE_FINISHED')
    expected={'UB':['case','ledger','runner','check_ub','ub'],
              'LB':['case','ledger','runner','check_ub','check_lb','lb']}
    checks={}
    for track,names in expected.items():
        saved=read(REPORTS/(track+'_EXECUTED_SOURCE_HASHES.json'))
        checks[track]={}
        for name in names:
            relative=Path('v42_m1_research')/(name+'.py')
            actual=sha(ROOT/relative);expected_sha=saved[str(relative)]
            if actual!=expected_sha:raise ValueError('NATIVE_EXECUTED_SOURCE_DRIFT:'+str(relative))
            checks[track][str(relative)]=dict(executed_sha256=expected_sha,final_sha256=actual,PASS=True)
    changes=git('diff','--name-only','3019dd59ee70241407dc6f9e70016de1e67d9385').decode().splitlines()
    if set(changes)-{'.gitattributes','README.md'}:raise ValueError('EXISTING_INTEGRATION_OR_SCIENTIFIC_FILE_CHANGED:'+str(changes))
    preserve=verify_preservation()
    write(REPORTS/'EXECUTION_PRESERVATION_AUDIT.json',dict(PASS=True,case_sha=receipt['case_sha'],
        actually_executed_Native_dependency_hash_checks=checks,
        snapshot_also_lists_unused_non_native_modules=True,existing_changed_files=changes,
        original_integration_and_scientific_code_unchanged=True,source_preservation=preserve,
        Native_model_callback_parameters_inflight_modified=False,original_case_objective_tolerances_unchanged=True,
        original_native_run_preserved=binding['original_files_unchanged'],
        final_run_evidence_and_accounting_binding=binding,
        independent_final_gate_source_unchanged=binding['independent_final_gate']['PASS'],additional_Native_optimize_calls=0))
    projection=read(REPORTS/'OBJECTIVE_PROJECTION_AUDIT.json')
    parents=receipt['independent_domain_and_multiplier_checks']['original_ROOT_certificates']
    baseline=max(F(r['exact_bound']) for r in parents)
    projection['bound_effect']['status']='FINAL_INDEPENDENT_CERTIFICATES_CHECKED'
    projection['bound_effect']['final_independent_check']=dict(
        source_path=str(REPORTS/'JOINT_LB_UB_GAP.json'),sha256=sha(REPORTS/'JOINT_LB_UB_GAP.json'),
        independently_certified_Global_LB=receipt['independently_certified_Global_LB'],
        exact_Global_LB=receipt['Global_LB_exact'],fresh_exact_parent_LB=str(baseline),
        exact_gain_over_fresh_parent=str(F(receipt['Global_LB_exact'])-baseline),
        material_gain_at_least_0p001=F(receipt['Global_LB_exact'])-baseline>=F(1,1000),
        inherited_native_LB_not_reclassified_exact=True)
    write(REPORTS/'OBJECTIVE_PROJECTION_AUDIT.json',projection)
    resource=read(REPORTS/'RESOURCE_USAGE_AUDIT.json')
    samples_path=original/'READ_ONLY_RESOURCE_SAMPLES.ndjson'
    samples=[json.loads(line) for line in samples_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    intervals=[]
    for call in ledger['calls']:
        start=datetime.fromisoformat(call['started_utc']);end=start+timedelta(seconds=call['optimize_wall_seconds'])
        selected=[s for s in samples if s['phase']==call['label'] and start<=datetime.fromisoformat(s['utc'].replace('Z','+00:00'))<=end]
        intervals.append(dict(label=call['label'],sample_count=len(selected),
            observation_status='PARTIAL_CALL_READ_ONLY_SAMPLES' if selected else 'NOT_MEASURED',
            sample_span_CPU_seconds=selected[-1]['cumulative_process_CPU_seconds']-selected[0]['cumulative_process_CPU_seconds'] if len(selected)>1 else None,
            sampled_max_RSS_bytes=max(s['RSS_bytes'] for s in selected) if selected else None,
            isolated_exact_whole_call_CPU_seconds='NOT_MEASURED',
            isolated_exact_whole_call_peak_RSS_bytes='NOT_MEASURED',
            Gurobi_MaxMemUsed_attribute_observed_at_call_end_GB=call['peak_memory_GB']))
    resource.update(per_call_CPU_RSS_sample_diagnostics=intervals,resource_sample_count=len(samples),
        resource_samples=dict(path=str(samples_path),sha256=sha(samples_path)),
        sampler_bounded_to_1080_observations_5_second_spacing=True,
        sampler_controls_no_process_and_does_not_delay_solver=True,
        Native_Work_is_not_CPU_seconds=True,additional_Native_optimize_calls=0,
        RSS_is_not_Gurobi_memory_attribute=True)
    resource['per_call_Gurobi_MaxMemUsed']='ATTRIBUTES_RECORDED_AT_CALL_END; NOT_ISOLATED_OS_RSS_PEAK'
    write(REPORTS/'RESOURCE_USAGE_AUDIT.json',resource)
    artifacts=REPORTS/'artifacts';artifacts.mkdir(exist_ok=True)
    shutil.copyfile(samples_path,artifacts/samples_path.name)
    if sha(artifacts/samples_path.name)!=sha(samples_path):raise ValueError('RESOURCE_SAMPLE_COPY_DRIFT')
    return dict(PASS=True,source_preservation=preserve)


def manifest():
    files={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(REPORTS.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json'}
    files.update({p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'v42_m1_research').glob('*.py'))})
    files.update({p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'tests').glob('test_v42_m1_research*.py'))})
    for name in ('Start-V42-M1-Research.ps1','README.md','.gitattributes'):files[name]=sha(ROOT/name)
    write(REPORTS/'SHA256_MANIFEST.json',dict(case_sha=read(REPORTS/'SCIENTIFIC_MODEL_IDENTITY.json')['case_sha'],
        hash_algorithm='SHA256',files=files,manifest_self_hash_excluded=True,all_new_files_on_D=True,
        original_Native_ledger_only_one_accounting_source=True))
    return files

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('original_run');a=p.parse_args();final_audits(a.original_run);manifest()
    print('FINAL_DELIVERY_SOURCE_AND_RESOURCE_AUDIT_PASS')
