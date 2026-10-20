"""Seal only after Native0 parent replay, regressions, and preservation checks."""
from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r026
from v44.common import read,record,verify,atomic,digest,now
from v44.locks import alive
from v44_recovery_r026.operations import OPS,CAMPAIGN,sources,make_permit,PERMIT,workers
from v44_recovery_r026.voltage_policy import authority


def new(path,value):
    if path.exists():raise FileExistsError(path)
    atomic(path,value)


def run():
    root=Path(__file__).resolve().parents[2];dev=Path('D:/MobileESS_V44/development/r026')
    regression=ET.parse(dev/'regressions_seal.xml').getroot().find('testsuite')
    assert int(regression.attrib['tests'])>=275 and all(int(regression.attrib[k])==0 for k in ('failures','errors','skipped'))
    original=read(OPS/'R023_SEALED.json');verify(original['sources']+[original['permit'],original['validation']])
    assert digest(original['sources'])==original['source_sha']=='e7533625281ff41f3ed2cb29b2c6cd90292a618eb1f19de5629abf84ff810450'
    assert len(original['sources'])==38
    parent=read(dev/'latest_parent_validation/RESULT.json');assert parent['PASS'] and parent['Native_calls']==0
    verify([parent['parent']]+parent['original_files_unchanged'])
    oldbase=read(OPS/'R024B_PASS_AND_M1_PRESERVATION_BASELINE.json');verify(oldbase['files'])
    stopped=CAMPAIGN/'2025-05-02/B3/attempt010';oldresult=read(stopped/'RESULT.json')
    assert oldresult['status']=='USER_STOPPED' and not workers()
    lease=read(CAMPAIGN/'COORDINATOR_LEASE.json');assert not alive(lease)
    start=read(stopped/'START.json');assert not alive(start)
    files={p['path']:p for p in oldbase['files']}
    for p in [stopped/'RESULT.json',stopped/'USER_INTERRUPTION.json',*stopped.rglob('*LEDGER.json')]:files[str(p)]=record(p)
    new(OPS/'R026_PASS_AND_M1_PRESERVATION_BASELINE.json',dict(UTC=now(),files=list(files.values()),
        original_baseline=record(OPS/'R024B_PASS_AND_M1_PRESERVATION_BASELINE.json'),
        original_PASS_Raw_and_native_ledgers_preserved=True,old_stopped_attempt_native_seconds=555.2489993572235))
    new(OPS/'R026_USER_AUTHORIZATION.json',dict(UTC=now(),explicit_resume_May02_B3_A2_Native0=True,
        supersedes_previous_user_stop=True,preserve_all_existing_PASS_Raw_ledgers_A1_M1=True,
        algorithm_revision='r026',algorithm_base=original['source_sha'],A_total_native_seconds=5400.,Phase_I_native_seconds=1500.,
        Phase_I_limit_action='FAIL_ONLY_DATE_ARM_CONTINUE_NEXT_COMPARISON',A2_voltage_policy=authority(),
        latest_M2_override='M2 voltage nonrecovery alone is recorded, not a case failure. Continue Actual/Fresh using independently nonvoltage-validated operating plan; no false M2 FULL or gap claim. Original strict Actual/Fresh physical verification determines final PASS.',
        future_unstarted_B1_B3_A_stages_unconditional=True,authorization_source='USER_MESSAGES_IN_CURRENT_CHAT'))
    new(OPS/'R026_HANDOVER_GUARD.json',dict(UTC=now(),protected_case_root=str(stopped),
        protected_worker=start,protected_coordinator=lease,current_worker_interrupt_allowed=False,
        acceptable_terminal_statuses=['COMPLETE','FAILED','BLOCKED_DEPENDENCY','USER_STOPPED'],pilot_PASS_required=False,
        authorization=record(OPS/'R026_USER_AUTHORIZATION.json'),superseded_user_stop=record(OPS/'STOP_AUTONOMY.json')))
    differences=[]
    for r in original['sources']:
        p=Path(r['path']);current=root/'v44_recovery_r026'/p.name
        assert current.exists()
        old=p.read_text(encoding='utf-8-sig').replace('r023','r026').replace('R023','R026')
        if current.read_text(encoding='utf-8-sig')!=old:differences.append(p.name)
    validation=dict(UTC=now(),PASS=True,revision='r026',r023_source_sha=original['source_sha'],r023_sources_verified=38,
        modified_from_label_normalized_r023=differences,source_records=sources(),A2_voltage_policy=authority(),
        regressions=dict(PASS=True,tests=int(regression.attrib['tests']),failures=0,errors=0,
            log=record(dev/'regressions_seal.log'),junit=record(dev/'regressions_seal.xml')),
        current_M1_FULL_native0_replay=record(dev/'latest_parent_validation/RESULT.json'),
        preservation=record(OPS/'R026_PASS_AND_M1_PRESERVATION_BASELINE.json'),
        current_A2_M2_Actual_results='NOT_YET_EXECUTED; DO_NOT_CLAIM_PASS',
        superseded_uniform_voltage_preflight='STOPPED_NATIVE0_AND_PRESERVED; NOT_USED_FOR_CURRENT_POLICY',
        Phase_I_P1_structure_preserved=True,Phase_I_native_limit=1500.,A_total_native_limit=5400.,
        no_older_A2_model_rows_duals_or_clock_import=True,M2_voltage_nonrecovery_only_is_not_failure=True,
        final_PASS_requires_original_Actual_Fresh_physics=True)
    new(OPS/'R026_CHANGE_AND_VALIDATION.json',validation)
    make_permit()
    new(OPS/'R026_SEALED.json',dict(UTC=now(),PASS=True,sources=sources(),source_sha=digest(sources()),
        permit=record(PERMIT),validation=record(OPS/'R026_CHANGE_AND_VALIDATION.json')))
    atomic(root/'docs/v44/R026_CHANGE_AND_VALIDATION.json',dict(validation,
        sealed_source_sha=digest(sources()),seal=record(OPS/'R026_SEALED.json')))
    print('R026_SEALED',digest(sources()),'tests',regression.attrib['tests'],flush=True)

if __name__=='__main__':run()
