"""Proven host-restart bounds never masquerade as exact Gurobi Runtime."""
from datetime import datetime
import json
import math
from pathlib import Path
import re
from .m_engine import file_record


def restart_bounds(call,events,*,boot_epoch,pid_alive,log_text):
    if pid_alive or not call or not call.get('pid'):
        raise ValueError('DEAD_NATIVE_OWNER_REQUIRED')
    begin=call['started_epoch_seconds']
    def epoch(e):return datetime.fromisoformat(e['TimeCreated']).timestamp()
    restarts=[epoch(e) for e in events if e['Id']==1074 and epoch(e)>begin]
    boots=[epoch(e) for e in events if e['Id']==6005 and any(
        r<epoch(e) and any(x['Id']==6006 and r<=epoch(x)<epoch(e) for x in events) for r in restarts)]
    if not boots or not math.isfinite(boot_epoch) or boot_epoch<min(boots)-30 or boot_epoch<=begin:
        raise ValueError('AFTER_CALL_OS_RESTART_AND_NEW_BOOT_PROOF_REQUIRED')
    # Printed integer times can round up. Subtract one second for a safe lower
    # bound. The first proven post-call boot, plus one second of clock margin,
    # is an upper bound independent of later Codex/session downtime.
    times=[float(m.group(1)) for m in re.finditer(r'\s(\d+(?:\.\d+)?)s\s*$',log_text,re.MULTILINE)]
    if not times:raise ValueError('ACTUAL_NATIVE_LOG_PROGRESS_REQUIRED')
    lower=max(0.,max(times)-1.);upper=min(boots)-begin+1.
    if not 0<=lower<=upper:raise ValueError('INCONSISTENT_RESTART_NATIVE_INTERVAL')
    return dict(lower=lower,upper=upper,exact=None,printed_native_log_seconds=max(times),
        first_proven_reboot_epoch_seconds=min(boots),
        accounting='NATIVE_INTERVAL_NOT_EXACT_RUNTIME',offline_downtime_charged_as_native=False)


def validate_restart_receipt(receipt,call):
    for name in ('events','native_log','original_ledger'):
        r=receipt[name]
        if file_record(r['path'])!=r:raise ValueError('RESTART_RECEIPT_EVIDENCE_BYTE_DRIFT')
    original=json.loads(Path(receipt['original_ledger']['path']).read_text(encoding='utf8'))
    if original.get('inflight')!=call:raise ValueError('RESTART_RECEIPT_EXACT_INFLIGHT_REQUIRED')
    interval=restart_bounds(call,json.loads(Path(receipt['events']['path']).read_text(encoding='utf8')),
        boot_epoch=receipt['observed_new_boot_epoch_seconds'],pid_alive=False,
        log_text=Path(receipt['native_log']['path']).read_text(encoding='utf8'))
    if interval!=receipt.get('native_runtime_interval_seconds'):
        raise ValueError('RESTART_RECEIPT_NATIVE_INTERVAL_MISMATCH')
    return interval


def archived_runtime_summary(document):
    if document.get('inflight') or document.get('active_stage_context'):
        raise ValueError('UNRECONCILED_NATIVE_CANNOT_BE_ARCHIVED')
    known=document.get('Gurobi_Native_seconds')
    if type(known) not in (int,float) or not math.isfinite(known) or known<0:
        raise ValueError('KNOWN_NATIVE_SUBTOTAL_REQUIRED')
    lower=upper=float(known);uncertain=[]
    measured=sum(r['Native_Runtime'] for r in document.get('calls',[])
        if r.get('solver')=='GUROBI' and type(r.get('Native_Runtime')) in (int,float))
    if not math.isfinite(measured) or abs(measured-known)>1e-6:
        raise ValueError('KNOWN_NATIVE_SUBTOTAL_CALL_SUM_DRIFT')
    for row in document.get('calls',[]):
        if row.get('solver')=='GUROBI_INTERRUPTED' and row.get('Native_Runtime') is not None:
            raise ValueError('INTERRUPTED_RUNTIME_MUST_REMAIN_NULL')
        if row.get('solver') not in ('GUROBI','GUROBI_INTERRUPTED') or row.get('Native_Runtime') is not None:continue
        proof=row.get('host_restart_receipt')
        if not proof or file_record(proof['path'])!=proof:
            raise ValueError('UNKNOWN_NATIVE_REQUIRES_VERIFIED_RESTART_RECEIPT')
        receipt=json.loads(Path(proof['path']).read_text(encoding='utf8'))
        interval=validate_restart_receipt(receipt,row.get('interrupted_call'))
        if row.get('native_runtime_bounds_seconds')!=interval or row.get('charged_seconds',-1)<interval['upper']:
            raise ValueError('UNKNOWN_NATIVE_INTERVAL_OR_CONSERVATIVE_CHARGE_DRIFT')
        lower+=interval['lower'];upper+=interval['upper'];uncertain.append(proof)
    return dict(known_native_seconds=float(known),native_lower_bound_seconds=lower,
        native_upper_bound_seconds=upper,native_runtime_fully_known=not uncertain,
        uncertainty_receipts=uncertain)
