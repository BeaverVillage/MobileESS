"""Publish measured receipts, preserving incomplete and diagnostic states."""
from pathlib import Path
import subprocess
from v44.common import read,record,verify,atomic,now


def optional(path):return read(path) if Path(path).exists() else {}


def summarize(root):
    root=Path(root);output=root/'A2/OUTPUT'
    return dict(root=str(root),case=optional(root/'RESULT.json'),A2=optional(root/'A2/RESULT.json'),
        Phase_I_native_budget=optional(output/'PHASE_I_NATIVE_BUDGET.json'),
        A2_native_ledger=optional(root/'A2/NATIVE_RUNTIME_LEDGER.json'),
        Phase_I_trace=optional(output/'PHASE_I_TRACE.json'),P1_trace=optional(output/'P1_TRACE.json'),
        voltage_policy=optional(output/'A2_VOLTAGE_POLICY_CERTIFICATE.json'),
        conditional_voltage_progress=optional(output/'R026F1_CONDITIONAL_VOLTAGE_PROGRESS.json'),
        M2=optional(root/'M2/RESULT.json'),M2_strict_recovery=optional(root/'M2/M2_STRICT_VOLTAGE_RECOVERY.json'),
        M2_diagnostic_handoff=optional(root/'M2/M2_ACTUAL_VOLTAGE_DIAGNOSTIC_HANDOFF.json'),
        Actual_Fresh=optional(root/'ACTUAL/RESULT.json'))


def write_report(case):
    from .operations import OPS,PERMIT
    from .voltage_policy import authority
    baseline=read(OPS/'R026F1_PASS_AND_M1_PRESERVATION_BASELINE.json');verify(baseline['files'])
    value=dict(UTC=now(),revision='v44_recovery_r026f1',current=summarize(case),permit=record(PERMIT),
        policy=authority(),Phase_I_native_ceiling=1500.,A_total_native_ceiling=5400.,
        r023_source_sha='e7533625281ff41f3ed2cb29b2c6cd90292a618eb1f19de5629abf84ff810450',
        all_existing_PASS_and_M1_bytes_unchanged=True,baseline=record(OPS/'R026F1_PASS_AND_M1_PRESERVATION_BASELINE.json'),
        final_PASS_authority='UNCHANGED_INDEPENDENT_ACTUAL_FRESH_STRICT_PHYSICS',
        M2_voltage_nonrecovery_alone_is_failure=False)
    atomic(OPS/'R026F1_MEASURED_COMPARISON.json',value)
    path=Path(__file__).resolve().parents[1]/'docs/v44/R026F1_MEASURED_OUTCOME.json'
    atomic(path,value);return path,value


def publish(case):
    from .operations import OPS
    path,value=write_report(case);worktree=Path(__file__).resolve().parents[1];relative=path.relative_to(worktree).as_posix()
    def git(*args):return subprocess.check_output(['git',*args],cwd=worktree,stderr=subprocess.STDOUT,text=True,encoding='utf-8').strip()
    if git('status','--porcelain','--',relative):
        git('add','--',relative);git('commit','--only','-m','Record measured r026f1 A2 M2 and Actual Fresh outcome','--',relative)
    pushed=git('push','origin','HEAD:refs/heads/codex/v44-may01-07-prestart')
    receipt=dict(UTC=now(),PASS=True,commit=git('rev-parse','HEAD'),PR='https://github.com/BeaverVillage/MobileESS/pull/233',
        report=record(path),push=pushed,completed_case_PASS=value['current']['case'].get('PASS'),existing_PASS_bytes_preserved=True)
    atomic(OPS/'R026F1_REPORT_PUBLISHED.json',receipt);return receipt
