"""Independent frozen-C1 power recomputation; no OpenDSS or optimizer."""
from pathlib import Path
import numpy as np
import psutil

from v43.common import DOC,read,record,verify_records,atomic,now


def report(attempt):
    from v43_actual.case import power_model
    from v43_actual.observations import load_observations
    attempt=Path(attempt);start=read(attempt/'START.json')
    if psutil.pid_exists(start['pid']) and psutil.Process(start['pid']).create_time()==start['process_created']:
        raise RuntimeError('FINAL_POWER_AUDIT_REQUIRES_TERMINATED_ARM')
    case=read(attempt/'CASE/CASE_BINDINGS.json');verify_records(case['source_receipts'])
    plan=read(case['source_receipts'][0]['path']);power=read(case['source_receipts'][3]['path'])
    from datetime import datetime
    issue=datetime.fromisoformat(plan['issue_time']).timestamp();end=issue+120*900
    observations=load_observations(begin=issue,end=end)
    weather=[observations.at(issue+t*900,observed_now=issue+t*900)['weather']['values'] for t in range(120)]
    model,sources=power_model(power,plan['capacities']);rows=[]
    for variant in read(attempt/'RESULT.json')['variants']:
        physical=attempt/variant/'ACTUAL_PHYSICAL.npz'
        with np.load(physical,allow_pickle=False) as z:
            fresh=model.recompute(z['GPU'],tuple(map(str,z['sites'])),weather)
            errors={k:float(np.max(abs(fresh[k]-z[k]))) for k in ('IT_kw','PCC_P_kw','PCC_Q_kvar')}
            exact={k:np.array_equal(fresh[k],z[k]) for k in errors}
        if not all(exact.values()):raise ValueError('EXACT_FROZEN_C1_RECOMPUTATION_MISMATCH:'+str(errors))
        rows.append(dict(variant=variant,PASS=True,arrays=record(physical),max_abs_error=errors,bit_exact=exact))
    payload=dict(UTC=now(),PASS=True,scope='EXECUTED_GPU_TO_ORIGINAL_EXACT_C1_IT_PCC_PQ_120_SLOTS',
        Native_calls=0,OpenDSS_calls=0,actual_source=record(attempt/'RESULT.json'),power_sources=sources,variants=rows)
    output=attempt/'INDEPENDENT_EXACT_C1_POWER_REPORT.json'
    if output.exists():raise ValueError('POWER_AUDIT_ALREADY_SEALED')
    atomic(output,payload)
    arm=case.get('arm','B1')
    atomic(DOC/f'V43_MAY01_{arm}_EXACT_C1_POWER_CERTIFICATION.json',dict(PASS=True,report=record(output)))
    return payload


if __name__=='__main__':
    import sys
    print(report(sys.argv[1]))
