"""Fresh fixed planning replay on original hardware and forecast inputs."""
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from time import perf_counter

from v43.common import RUNS,read,record,atomic
from v43_actual.case import accepted
from v43_actual.io import checked
from .current_ac import ArmCurrentAC


def run(binding,output):
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    output=Path(output)
    if output.exists():raise ValueError('FRESH_PLANNING_REPLAY_OUTPUT_REQUIRED')
    with ExitStack() as stack:
        locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
        locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
        locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
        for path in locks:stack.enter_context(exclusive_lock(path))
        denied=stack.enter_context(native_zero())
        began=perf_counter();native=accepted()[2]
        electrical=read(checked(native['electrical_certificate']))
        inputs=electrical['input_identity']['identity']['inputs']
        demand_record=inputs['demand']['source'];pv_record=inputs['PV']['source']
        demand=read(checked(demand_record));pv=read(checked(pv_record))
        begin=datetime.fromisoformat('2025-05-01T00:00:00+10:00').timestamp()
        a=binding.arrays;rows=[]
        for t in range(96):
            rows.append(dict(slot=t,start_seconds=begin+900*t,end_seconds=begin+900*(t+1),
                GPU=a['GPU'][t].tolist(),P=a['PCC_P_kw'][t].tolist(),Q=a['PCC_Q_kvar'][t].tolist(),
                observations=dict(demand=dict(values=dict(demand_mw=demand['demand_mw_96'][t])),
                    pv=dict(values=dict(pv_mw=pv['pv_mw_96'][t])))))
        oracle=ArmCurrentAC(issue_seconds=begin,day_start_seconds=begin,sites=a['sites'],
            power_model=None,observations=None,mess_plan=binding.mess)
        result=oracle._probe(rows)
        result.update(arm=binding.arm,scope='FRESH_FIXED_PLANNING_FORECAST96_ORIGINAL7',
            Native_calls=0,denied_Native_calls=denied,wall_seconds=perf_counter()-began,
            inputs=[binding.freeze,demand_record,pv_record,native['electrical_certificate']],
            FULL_optimization_claimed=False,Global_Gap='NOT_APPLICABLE_REFERENCE' if binding.arm=='B0' else 'SEPARATE_STAGE_CERTIFICATES')
        result['PASS']=len(result['physical_steps'])==96 and all(r['PASS'] for r in result['physical_steps'])
        atomic(output,result)
    return result
