"""Collect measured receipts and remaining approval requirements, Native0."""
import argparse
import csv
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def record(path):
    with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path.resolve()),sha256=sha,bytes=path.stat().st_size)


def main(output,execution):
    read=lambda p:json.loads(p.read_text(encoding='utf8'))
    isolated=read(output/'C3A_FINAL02/RESULT.json');full=read(output/'FULL_NATIVE0_01/RESULT.json')
    regression=read(output/'REGRESSION_FINAL/RESULTS.json');warm=read(output/'WARM_MAPPING02/RESULT.json')
    equivalence=read(output/'ALL_ARTIFACTS_EQUIVALENCE.json');audit=read(output/'EXECUTION08_FAILURE_AUDIT.json')
    stop=read(output/'EXECUTION08_STOP_AUDIT.json')
    preserved=all(record(Path(r['path']))==r for r in stop['raw_and_freeze_records'])
    archive=read(execution/'SOURCE_ARCHIVE_RECEIPT.json')
    archive_manifest=read(Path(archive['manifest']['path']))
    archived_preserved=all(record(Path(r['archived']['path']))==r['archived'] for r in archive_manifest['records'])
    # Preserve all 1,172 IDs from the preceding successful regression, not
    # just the original 682 IDs already checked by the common runner.
    previous=Path('D:/v42_mess_prep_fix_20261015/REGRESSION_FROZEN03/TESTS.xml')
    ids=lambda p:{(r.attrib['classname'],r.attrib['name']) for r in ET.parse(p).getroot().iter('testcase')}
    old_ids=ids(previous);new_ids=ids(output/'REGRESSION_FINAL/TESTS.xml')
    if len(old_ids)!=1172 or not old_ids<=new_ids:raise AssertionError('1172_REGRESSION_IDS_LOST')
    profiles=[]
    for path in (output/'FULL_NATIVE0_01').rglob('PREPARATION_PROFILE.jsonl'):
        profiles.extend(json.loads(line) for line in path.read_text().splitlines() if line)
    profiles.sort(key=lambda row:row['wall_seconds'],reverse=True)
    fields=['stage','wall_seconds','CPU_seconds','peak_RSS_sampled_bytes','peak_private_sampled_bytes',
            'peak_system_commit_sampled_bytes','process_lifetime_peak_RSS_bytes','sample_period_seconds']
    with (output/'B2_STAGE_WALL_CPU_RAM.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(profiles)
    comparisons=[dict(metric='C3A_saved_matrix',before=isolated['previous_C3A_wall_seconds'],after=isolated['candidate_C3A_wall_seconds'],scope='Same saved matrices; different runs'),
                 dict(metric='C3A_independent_verifier',before=isolated['previous_verifier_wall_seconds'],after=isolated['candidate_proof']['independent_verifier_wall_seconds'],scope='Same saved matrices; different runs'),
                 dict(metric='M1_Native0_total',before=1268.,after=full['total_with_Joint_readback_wall_seconds'],scope='Historical approximate baseline vs one complete current build/readback'),
                 dict(metric='Static_presolve',before=112.279,after=full['static_presolve']['wall_seconds'],scope='Historical run; presolve algorithm unchanged by this patch')]
    for r in comparisons:r['reduction_percent']=100*(1-r['after']/r['before'])
    with (output/'PERFORMANCE_COMPARISON.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(comparisons[0]));writer.writeheader();writer.writerows(comparisons)
    plan=dict(status='NOT_AUTHORIZED_NOT_EXECUTED',campaign_resume=False,total_max_Native_seconds=1020,
              same_A1_5400_second_stage_cap=True,Native_reset=False,new_5400_or_1800_budget=False,
              B1_A1_already_used=audit['B1']['cumulative_stage_Native_seconds'],
              B1_A1_remaining=audit['B1']['Native_remaining_seconds'],
              B2_M1_already_used=audit['B2']['cumulative_stage_Native_seconds'],
              B2_M1_remaining=1800-audit['B2']['cumulative_stage_Native_seconds'],
              calls=[dict(model='Saved May01 S0',Method=2,parameters='FAST_B',Threads=1,max_seconds=120,
                          purpose='Barrier comparison; raw Phi/primal/dual/KKT/Work/RSS'),
                     dict(model='Same saved May01 S0',Method=1,parameters='FAST_B',Threads=1,max_seconds=120,
                          purpose='Dual Simplex comparison on identical rows/RHS/bounds/objective'),
                     dict(model='Current original FULL Integer MILP',Threads=1,max_seconds=360,
                          purpose='Validate warning recovery and incumbent preservation beyond the old 266s abort'),
                     dict(model='B2 M1 F2 stationary free modes',Threads=1,max_seconds=180,
                          purpose='Check the first seed trial previously blocked before Optimize by the RAM gate'),
                     dict(model='B2 M1 F3 current-day route seed',Threads=1,max_seconds=240,
                          purpose='Check the second previously blocked seed trial; same M-stage 1800s cumulative cap')],
              prerequisite='Explicit user approval, current source/case binding and cumulative ledger carry-forward; no production auto launch')
    (output/'NATIVE_EXPERIMENT_PROPOSAL.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf8')
    summary=dict(status='NATIVE0_VERIFIED_CAMPAIGN_STOPPED_NATIVE_TESTS_PENDING',
                 generated_KST=datetime.now(timezone(timedelta(hours=9))).isoformat(),
                 Native_optimize_calls_for_improvement=0,regression_tests=regression['tests'],
                 all_1172_predecessor_IDs_preserved=True,new_IDs=len(new_ids-old_ids),
                 regression_PASS=regression['status']=='PASS',matrix_domain_proof_equivalence=equivalence['PASS'],
                 all_190248_interval_endpoints_bit_exact=isolated['checks']['all_interval_values_bit_exact'],
                 EXECUTION08_Raw_ledgers_freeze_preserved=preserved,source_archive_preserved=archived_preserved,
                 RAM_Commit_thresholds_removed_from_campaign_paths=True,Worker1_Threads1_preserved=True,
                 B1_Phase_I_status='NATIVE_REVALIDATION_PENDING',B1_Integer_status='CALLBACK_FATAL_WARNING_FIXED_NATIVE_PENDING',
                 warm_mapping=warm,comparisons=comparisons,full_Native0=full,
                 targets=dict(C3A_saved_matrix_400_seconds=isolated['candidate_C3A_wall_seconds']<=400,
                              static_presolve_90_seconds=full['static_presolve']['wall_seconds']<=90,
                              total_M1_Native0_700_seconds=full['total_with_Joint_readback_wall_seconds']<=700,
                              S0_60_seconds='NOT_TESTED'),
                 Native_experiment_proposal=plan,May01_resume='HOLD_NEW_EXACT_SOURCE_APPROVAL_AND_NATIVE_VALIDATION_REQUIRED',
                 P2_calls=0,R2='HOLD',IEEE8500_executed=False)
    if not all((preserved,archived_preserved,equivalence['PASS'],regression['status']=='PASS')):
        raise AssertionError('EVIDENCE_OR_SOURCE_PRESERVATION_FAILED')
    (output/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
    with (output/'LOCAL_LARGE_ARTIFACTS_SHA256_MANIFEST.json').open('w',encoding='utf8') as stream:
        paths=[p for p in (output/'FULL_NATIVE0_01').rglob('*') if p.is_file() and p.stat().st_size>1024**2]
        paths += list((output/'C3A_FINAL02').glob('*.npy'))+list((output/'WARM_MAPPING02').glob('*.npz'))
        json.dump(dict(local_only=True,records=[record(p) for p in paths]),stream,indent=2)
    print(json.dumps(dict(status=summary['status'],tests=summary['regression_tests'],comparisons=comparisons,targets=summary['targets'])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--execution',type=Path,required=True)
    a=p.parse_args();main(a.output,a.execution)
