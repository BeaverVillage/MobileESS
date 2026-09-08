"""Native-engine mapper regression using synthetic setpoints, not outcome data.

This cannot create an eligible Planning-Actual voltage pair. No voltage is
measured and no policy replay or optimization is invoked.
"""
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import os

from .audit import OUT, ROOT, ref, read, write


def run():
    from dayahead.v28r2.opendss_mapping import FeederAssets, compile_clean_engine
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.v40e.mapping import NativeAllocation
    from dayahead.v41.mapper_audit import observe
    assets = FeederAssets.from_repo(SOURCE_DATA_REPOSITORY)
    previous = Path.cwd()
    results = []
    try:
        for stage in ('Planning', 'Fresh', 'Actual'):
            odd, adapter = compile_clean_engine(assets)
            allocation = NativeAllocation.from_adapter(adapter)
            allocation.validate_native_engine(odd)
            p, q = defaultdict(float), defaultdict(float)
            for row in adapter['loads']:
                for phase in row['phases']:
                    key = (row['bus'].lower(), 'ABC'[phase-1])
                    p[key] += row['base_p_kw']/len(row['phases'])
                    q[key] += row['base_q_kvar']/len(row['phases'])
            background = SimpleNamespace(
                gross_p_kw_96=[{key: value*(.5+t/192) for key, value in p.items()} for t in range(96)],
                gross_q_kvar_96=[{key: value*(.6+t/240) for key, value in q.items()} for t in range(96)])
            output = OUT / 'background_regression' / stage
            with observe(output, 'SYNTHETIC_NO_POLICY_DAY', stage):
                for slot in range(96):
                    allocation.apply(odd, background, slot)
            result = read(output / 'MAPPER_AUDIT.json')
            assert result['status'] == 'PASS' and result['duplicated_group_slots'] == 0
            results.append(dict(stage=stage, audit=ref(output / 'MAPPER_AUDIT.json'),
                slots=result['slots'], shared_groups=result['shared_group_count'],
                duplicated_group_slots=0, P_max_error_kW=result['P_max_error_kW'], Q_max_error_kvar=result['Q_max_error_kvar']))
    finally:
        os.chdir(previous)
    write('V41R1_BACKGROUND_LOAD_REGRESSION.json', dict(status='PASS',
        scope='96 synthetic native-setpoint slots per stage label, real OpenDSS Loads.kW/kvar readback; not policy-day AC replay',
        calibration_rows_created=0, Actual_outcome_reads=0, new_optimization_calls=0,
        stage_scientific_paths='Inherited V41 source hashes unchanged; corrected_mapping supplies empty native loads to legacy mapper (separate regression test)',
        corrected_mapper=ref(ROOT / 'dayahead/v40e/mapping.py'),
        feeder_assets={k: ref(v) for k, v in assets.__dict__.items()}, results=results))
    print('PASS: 3 x 96 native mapper readback slots, zero duplicated group slots')


if __name__ == '__main__':
    run()
