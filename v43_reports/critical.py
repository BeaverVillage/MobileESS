"""Add required branch/phase identities without rerunning the event controller."""
from contextlib import ExitStack
from datetime import datetime,timedelta,timezone
import inspect
from pathlib import Path
import textwrap

import numpy as np
import psutil

from v43.common import ROOT,RUNS,DOC,read,record,verify_records,atomic,now
from v43_actual.current_ac import OriginalCurrentAC
from v43_actual.observations import load_observations
from v43_arms.current_ac import ArmCurrentAC


def probe():
    source=textwrap.dedent(inspect.getsource(OriginalCurrentAC._probe))
    boundary=next(line for line in source.splitlines(keepends=True) if "authority.assert_inventory(source['inventory'](odd))" in line)
    indent=boundary[:len(boundary)-len(boundary.lstrip())]
    if source.count(boundary)!=2:raise ValueError('ORIGINAL_INVENTORY_BOUNDARY_CHANGED')
    source=source.replace(boundary,indent+'self._apply_frozen_mess(odd,row)\n'+boundary,1)
    marker='checked_nodes=len(names),checked_branch_phases=len(branches)))'
    if source.count(marker)!=1:raise ValueError('ORIGINAL_LINE_PHASE_RECEIPT_BOUNDARY_CHANGED')
    source=source.replace(marker,'checked_nodes=len(names),checked_branch_phases=len(branches),\n'
        "            critical_line=str(branches[np.flatnonzero(lines)[np.argmax(measured[lines,1])]].branch_id),\n"
        "            critical_phase=str(branches[np.flatnonzero(lines)[np.argmax(measured[lines,1])]].phase)))")
    ns=dict(OriginalCurrentAC._probe.__globals__);exec(compile(source,OriginalCurrentAC._probe.__code__.co_filename,'exec'),ns)
    return ns['_probe']


class IdentifiedFresh(ArmCurrentAC):
    _probe=probe()


def report(attempt,*,mess_result=None):
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    attempt=Path(attempt);start=read(attempt/'START.json')
    if psutil.pid_exists(start['pid']) and psutil.Process(start['pid']).create_time()==start['process_created']:
        raise RuntimeError('NO_CRITICAL_IDENTITY_REPLAY_WHILE_EVENT_WORKER_ALIVE')
    case=read(attempt/'CASE/CASE_BINDINGS.json');output=attempt/'INDEPENDENT_CRITICAL_PHASE_FRESH.json'
    if output.exists():raise ValueError('CRITICAL_IDENTITY_REPORT_ALREADY_SEALED')
    mess=None
    if mess_result is not None:
        value=read(mess_result)
        if not value['FULL_feasible']:raise ValueError('ORIGINAL_FULL_MESS_REQUIRED')
        mess=value['MESS_plan']
    from v43_actual.vendor.policy import digest
    if case.get('Final_MESS_plan_sha',digest(None))!=digest(mess):raise ValueError('ARM_FINAL_MESS_SHA_DRIFT')
    result={};curves={};checks={}
    with ExitStack() as stack:
        locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
        locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
        locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
        for path in locks:stack.enter_context(exclusive_lock(path))
        denied=stack.enter_context(native_zero())
        for variant in ('C0','C1'):
            physical=attempt/variant/'ACTUAL_PHYSICAL.npz';fresh=read(attempt/variant/'FRESH_ORIGINAL7_AC.json')
            # Exact C0/C1 physical and observations identity permits reuse of
            # this extra identity-only replay. Each arm's original C0/C1 Fresh
            # already ran independently in its own engine.
            key=record(physical)['sha256']
            if key not in curves:
                with np.load(physical,allow_pickle=False) as z:a={k:z[k].copy() for k in z.files}
                source=read(case['source_receipts'][0]['path']);issue=datetime.fromisoformat(source['issue_time']).timestamp()
                observations=load_observations(begin=issue,end=issue+120*900)
                rows=[dict(slot=t,start_seconds=issue+t*900,end_seconds=issue+(t+1)*900,GPU=a['GPU'][t].tolist(),
                    P=a['PCC_P_kw'][t].tolist(),Q=a['PCC_Q_kvar'][t].tolist(),
                    observations=observations.at(issue+t*900,observed_now=issue+t*900)) for t in range(120)]
                oracle=IdentifiedFresh(issue_seconds=issue,day_start_seconds=issue+21600,
                    sites=tuple(map(str,a['sites'])),power_model=None,observations=observations,mess_plan=mess)
                curves[key]=oracle._probe(rows)
            identified=curves[key]
            checks[variant]={name:np.array_equal([r[name] for r in identified['physical_steps']],
                [r[name] for r in fresh['physical_steps']]) for name in
                ('maximum_phase_line_loading','voltage_min_pu','voltage_max_pu','converged')}
            if not all(checks[variant].values()):raise ValueError('CRITICAL_IDENTITY_REPLAY_NOT_BIT_EXACT')
            steps=identified['physical_steps'][24:];peak=max(steps,key=lambda r:r['maximum_phase_line_loading'])
            result[variant]=dict(peak_line_phase_loading=peak['maximum_phase_line_loading'],
                line=peak['critical_line'],phase=peak['critical_phase'],slot=peak['slot']-24,
                interval_start_AEST=datetime.fromtimestamp(issue+peak['slot']*900,timezone(timedelta(hours=10))).isoformat(),
                interval_end_AEST=datetime.fromtimestamp(issue+(peak['slot']+1)*900,timezone(timedelta(hours=10))).isoformat(),
                physical=record(physical),extra_replay_reused_for_bit_exact_C0_C1=variant=='C1' and len(curves)==1)
        payload=dict(UTC=now(),PASS=True,scope='IDENTITIES_ONLY_EXTRA_FRESH_NOT_NEW_EVENT_OR_OPTIMIZATION',
            variants=result,original_Fresh_replay_bit_exact=checks,Native_calls=0,denied_Native_attempts=denied,
            original_control='7REG_SNAPSHOT_STATIC',source=record(__file__),MESS_plan_sha=digest(mess))
        atomic(output,payload)
    arm=case.get('arm','B1');atomic(DOC/f'V43_MAY01_{arm}_CRITICAL_PHASE_CERTIFICATION.json',dict(PASS=True,report=record(output)))
    return payload


if __name__=='__main__':
    import sys
    print(report(sys.argv[1],mess_result=sys.argv[2] if len(sys.argv)>2 else None))
