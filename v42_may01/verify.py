"""Read-only evidence checks plus an explicitly generated delivery receipt."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,xml.etree.ElementTree as ET
import pandas as pd
from .prepare import ROOT,OUT,read,sha,dump

BASE='50de58e7be6fa02abfa0d8e02b6d96b6397a1dc1'
REQUIRED='''README.md PREREGISTRATION.json PENDING_RUNNING_STATE_CONTRACT.md
PR79_CONFLICT_REAUDIT.csv PR79_CONFLICT_REAUDIT_SUMMARY.json MAY01_JOB_STATE_LEDGER.csv
MAY01_GPU_CAPACITY_RECONCILIATION.csv T2_Q25_FINAL_RULE.json MAY01_TIMESHIFT_CAPABILITY.csv
MAY01_TIMESHIFT_SUMMARY.json MAY01_CAPABILITY_OVERLAP.csv MAY01_NATIVE_INPUT_BUNDLE.json
MAY01_NATIVE_INPUT_MANIFEST.json MAY01_CC4_P2_BINDING.json MAY01_GRID_BINDING_AUDIT.json
MAY01_AIDC_OPTION_PRESCREEN.csv MAY01_MODEL_SIZE_AUDIT.csv MAY01_A1_SOLVER_METRICS.json
MAY01_M1_SOLVER_METRICS.json MAY01_A2_SOLVER_METRICS.json MAY01_M2_SOLVER_METRICS.json
MAY01_GAP_TIME_TRACE.csv MAY01_WARM_START_AUDIT.json MAY01_NATIVE_COMPUTATIONAL_CANARY.csv
MAY01_NATIVE_COMPUTATIONAL_VERDICT.json FRESH_AC_MAY01_VALIDATION.json FINAL_FLAGS.json
FINAL_VERDICT.json FINAL_REVIEW_KO.md SOURCE_MANIFEST.json TEST_RESULTS.xml
MAY01_A1_RESOURCE_CERTIFICATE.json MAY01_RESOURCE_NECESSARY_BOUND.csv
A1_RESOURCE_INFEASIBILITY_PROOF.md PRE_SOLVE_IO_FAILURE.json REFERENCE_VERSION_COMPATIBILITY_AUDIT.json'''.split()


def git(*args):return subprocess.run(['git',*args],cwd=ROOT,capture_output=True,check=True).stdout


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write-manifest',action='store_true');parser.add_argument('--staged',action='store_true');args=parser.parse_args()
    for name in REQUIRED:assert (OUT/name).is_file(),name
    assert [int(n) for n in re.findall(r'^(\d+)\. ',(OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf8'),re.M)]==list(range(1,51))
    bundle=read(OUT/'MAY01_NATIVE_INPUT_BUNDLE.json');cert=read(OUT/'MAY01_A1_RESOURCE_CERTIFICATE.json');flags=read(OUT/'FINAL_FLAGS.json')
    assert bundle['day']=='2025-05-01' and bundle['network']=='IEEE123' and bundle['alpha_BG']==1.15
    assert not bundle['unresolved_transitive_physical_inputs'] and not bundle['unknown_arrival_actions']
    jobs=bundle['known_population'];known=[r for r in jobs if r['planning_eligible']]
    assert len(jobs)==1649 and len(known)==1605 and all(r['can_timeshift'] is False for r in known)
    assert all(r['current_physical_occupancy']==(0 if r['state']=='PENDING' else r['GPU_gang']) for r in jobs)
    assert all(r['reference_end']-r['reference_start_if_authorized']==r['service_slots'] for r in jobs)
    assert all(r['reference_end']<=24 and r['FIX'] is None for r in jobs if not r['planning_eligible'])
    assert sum(bundle['capacities'].values())==780 and bundle['WAN']['maximum_active_transfers']==1
    # Independent arithmetic implementation, without invoking the projection code.
    lower=pd.read_csv(OUT/'MAY01_RESOURCE_NECESSARY_BOUND.csv');assert len(lower)==96
    for row in lower.to_dict('records'):
        t=int(row['slot_issue_origin']);gangs=sorted([r['GPU_gang'] for r in known if r['reference_start_if_authorized']<=t<r['reference_end']],reverse=True)
        need=sum(gangs[120:])+bundle['C0_Q50'][(t-24)//4]
        assert abs(need-row['necessary_total_GPU_lower_bound'])<1e-8
        assert row['known_reference_GPU']==sum(gangs)
    assert sum(lower.excess_GPU>1e-8)==28 and abs(lower.excess_GPU.max()-456.6725825123947)<1e-8
    assert cert['full_A1_infeasible_proven'] and cert['solver_status']==3 and not cert['incumbent_available']
    assert cert['full_A1_model_size'] is None and cert['full_A1_MIP_gap'] is None
    assert cert['MIPGap_parameter']==.001 and cert['supervisor']['budget_seconds']==600 and cert['supervisor']['exit_code']==0
    assert 0<cert['supervisor']['total_wall_seconds']<=600 and cert['supervisor']['external_process_tree']
    assert cert['model_size']['continuous']==1605 and cert['model_size']['linear_constraints']==97
    audited=read(OUT/'PR79_CONFLICT_REAUDIT_SUMMARY.json')
    assert audited['original_conflicts']==321 and audited['remaining_true_physical_conflicts']==0
    assert audited['current_future_reservation_collision_records']==321 and audited['future_planning_collisions_proven_resolved']==0
    r=pd.read_csv(OUT/'PR79_CONFLICT_REAUDIT.csv');assert len(r)==321 and r.source_contribution_rows.sum()==26586
    assert (r.current_RUNNING_physical_GPU<=r.site_cap).all() and (r.pending_current_physical_GPU==0).all()
    for key in ('T2_Q25_USES_MAY_OUTCOMES','RUNTIME_PROVIDER_READY','UNKNOWN_DDAY_TEMPORAL_ACTIVE','UNKNOWN_DDAY_MIGRATION_ACTIVE',
                'MESS_NATIVE_MILP_BOUND','FRESH_AC_MAY01_PASS','ALL_BLOCKS_TARGET_GAP_0P1_PERCENT','V42_NATIVE_BLOCK_RUNTIME_FEASIBLE',
                'RESPONSE_KERNEL_REGENERATION_REQUIRED','CL_MC_BD_TRIGGERED','FULL_IEEE123_ROUND_RUN','IEEE8500_RUN',
                'FULL_MAY_POLICY_EVALUATION','FLEX_SENSITIVITY_RUN','SEMANTIC_ML_MERGED'):
        assert flags[key] is False,key
    for s in ('A1','M1','A2','M2'):
        metric=read(OUT/f'MAY01_{s}_SOLVER_METRICS.json')
        assert metric['final_gap'] is None and metric['binary_count'] is None and metric['full_model_built'] is False
        if s!='A1':assert metric['runtime_seconds'] is None and metric['status']=='NOT_RUN_UPSTREAM_A1_INFEASIBLE'
    source_files=read(OUT/'SOURCE_MANIFEST.json')['files']
    all_sources=source_files+read(OUT/'MAY01_NATIVE_INPUT_MANIFEST.json')['files']+cert['evidence']+read(OUT/'PRE_SOLVE_IO_FAILURE.json')['evidence']
    for row in all_sources:assert sha(row['path'])==row['sha256'],'SOURCE_DRIFT:'+row['path']
    request=read(next(Path(r['path']) for r in cert['evidence'] if Path(r['path']).name=='request.json'))
    for row in request['payload']['source_files']:assert sha(row['path'])==row['sha256'],'EXECUTED_CODE_OR_SOURCE_DRIFT:'+row['path']
    assert sha(request['payload']['bundle'])==request['payload']['bundle_sha']
    suites=list(ET.parse(OUT/'TEST_RESULTS.xml').getroot().iter('testsuite'))
    assert suites and all(int(s.attrib.get('errors',0))+int(s.attrib.get('failures',0))+int(s.attrib.get('skipped',0))==0 for s in suites)
    test_count=sum(int(s.attrib['tests']) for s in suites);assert test_count>=208
    # Scientific code and evidence already tracked in PR90/91 must be byte-identical.
    protected=git('ls-tree','-r','--name-only',BASE,'v42_job_capability.py','v42_native','docs/v42_job_capability_joint_flexibility',
        'docs/v42_native_integration_mess_milp','tests/test_v42_job_capability.py','tests/test_v42_native.py').decode().splitlines()
    for name in protected:
        assert (ROOT/name).read_bytes()==git('show',BASE+':'+name),'PR90_PR91_PROTECTED_BYTES_CHANGED:'+name
    files=sorted(p for p in list(OUT.glob('*'))+list((ROOT/'v42_may01').glob('*'))+
        [ROOT/'v42_native/may01_worker.py',ROOT/'tests/test_v42_may01.py',ROOT/'tests/.gitattributes']
        if p.is_file() and p.name not in ('DELIVERY_MANIFEST.json','VERIFICATION.json'))
    entries=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in files]
    if args.write_manifest:dump('DELIVERY_MANIFEST.json',dict(base_commit=BASE,files=entries,excluded=['DELIVERY_MANIFEST.json','VERIFICATION.json']))
    assert entries==read(OUT/'DELIVERY_MANIFEST.json')['files'],'DELIVERY_MANIFEST_DRIFT'
    if args.staged:
        for r in entries:assert hashlib.sha256(git('show',':'+r['path'])).hexdigest()==r['sha256'],'STAGED_BLOB_DRIFT:'+r['path']
    verification=dict(PASS=True,tests_passed=test_count,required_artifacts=len(REQUIRED),review_answers=50,
        unique_source_files=len({r['path'] for r in all_sources}),prior_protected_files=len(protected),prior_protected_bytes_changed=0,
        input_and_executed_source_seals=True,independent_arithmetic_proof=True,native_resource_projection_executed=True,
        full_A1_MILP_executed=False,full_four_block_canary_completed=False,Fresh_AC_executed=False,
        scientific_PASS=False,staged_blob_verification=args.staged,delivery_files=len(entries))
    dump('VERIFICATION.json',verification);print(json.dumps(verification,indent=2))


if __name__=='__main__':main()
