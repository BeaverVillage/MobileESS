"""Independent Native0 FCFS replay; never calls a campaign worker or AC adapter.

Uses the frozen r043 event/controller classes unchanged. All writes go to this
study's runtime. An existing reference is input only; its grid results are not
read or transferred. No production locks or worker entrypoints are invoked.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = Path('D:/smartds_gso_substation2_v44_r043_runtime/jobs')


def main():
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    if psutil.virtual_memory().available < 5_000_000_000:
        raise RuntimeError('RESOURCE_PROTECTION_LOW_MEMORY')
    from v43_arms.actual import ArmBinding
    from v43_baseline.worker import BaselineController
    from v43_corrective.reference import CorrectedReferenceScheduler
    from v43_actual.observations import load_observations
    from v43_actual.vendor.actual import run_actual
    from v42_may_campaign_native90.preflight import native_zero
    from v43.common import read, record, atomic

    ref = Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/references/2025-05-01')
    began = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    with native_zero() as denied:
        binding = ArmBinding('B0', ref, None)
        args, case = binding.prepare(OUT/'CASE', private_service=True)
        args['reference'] = CorrectedReferenceScheduler.from_dict(args['reference'].to_dict())
        commands = deepcopy(args['known_schedule'])
        assigned = deepcopy(args['reference'].assigned)
        observations = load_observations(begin=args['begin'], end=args['end'])
        args['weather'] = [observations.at(args['begin']+t*900,
            observed_now=args['begin']+t*900)['weather']['values'] for t in range(120)]
        def controller(*a, **kw):
            return BaselineController(*a, rack_limits=binding.aidc['identity'].get(
                'rack_compatibility', read(case['source_receipts'][0]['path'])['rack_compatibility']), **kw)
        actual = run_actual(**args, frozen_policy=None, controller_class=controller)
        assert args['known_schedule'] == commands
        assert all(args['reference'].assigned[u] == r for u,r in assigned.items())
        assert not denied and not actual['migration_receipts']
        physical = actual['physical']
        np.savez_compressed(OUT/'ACTUAL_PHYSICAL.npz', GPU=actual['occupancy_GPU'],
            compute_GPU=actual['compute_occupancy_GPU'], IT_kw=physical['IT_kw'],
            PCC_P_kw=physical['PCC_P_kw'], PCC_Q_kvar=physical['PCC_Q_kvar'],
            sites=np.array(actual['sites']))
        atomic(OUT/'EVENT_LEDGERS.json', {k:v for k,v in actual.items() if k not in
            ('occupancy_GPU','compute_occupancy_GPU','physical','carryout')})
        prior = Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-01/B0/attempt001/ACTUAL/ACTUAL_PHYSICAL.npz')
        with np.load(prior) as z:
            difference = {k:float(np.max(np.abs(z[k]-physical[k]))) for k in
                ('IT_kw','PCC_P_kw','PCC_Q_kvar')}
        receipt = dict(status='INDEPENDENT_GRID_BLIND_FCFS_REPLAY_COMPLETE', Native_calls=0,
            native_denials=denied, receipt=actual['receipt'], begin=args['begin'], end=args['end'],
            slots=120, prefix_slots=24, evaluation_slots=96, site_scale=1.0,
            authority_sha=physical['authority_sha'], sources=case['source_receipts'],
            observations=observations.sources if hasattr(observations,'sources') else [],
            reference=record(ref/'AIDC_REFERENCE.json'), grid_result_reused=False,
            prior_non_electrical_trace=record(prior), maximum_trace_difference=difference,
            inherited_initial_site_assumption=case['missing_initial_sites'],
            causal_certification=case['FORECAST_CAUSAL_AVAILABILITY'],
            wall_seconds=time.perf_counter()-began)
        atomic(OUT/'REPLAY_RECEIPT.json', receipt)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
