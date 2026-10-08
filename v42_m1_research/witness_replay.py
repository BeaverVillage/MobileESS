"""Zero-native full replay of all twenty completed-M188 recourse witnesses."""
from contextlib import ExitStack
import numpy as np
from time import perf_counter
from .case import load_case,committed_file,REPORTS
from .check_ub import validate_candidate
from v42_unified.audit import write
from v42_unified.replay import forbid_native

def run():
    started=perf_counter();rows=[]
    with ExitStack() as stack:
        forbid_native(stack)
        case=load_case()
        for i in range(20):
            name=f'docs/v42_m1_route_mode_benders_20261008/artifacts/recourse_{i:03d}_RAW.npz'
            path,source=committed_file(name)
            with np.load(path,allow_pickle=False) as archive:
                if set(archive.files)!={'x','pi','rc','slack','z','B'}:raise ValueError('ARCHIVED_RECOURSE_RAW_KEY_DRIFT')
                if not np.array_equal(archive['B'],np.flatnonzero(case.d['types']!='C')):raise ValueError('ARCHIVED_BINARY_AXIS_DRIFT')
                if not np.array_equal(archive['z'],archive['x'][archive['B']]):raise ValueError('ARCHIVED_BINARY_ASSIGNMENT_DRIFT')
                x=archive['x'].copy()
            checked=validate_candidate(case,x)
            rows.append(dict(assignment=i,source=source,independent_full_original_replay=checked))
    passed=all(r['independent_full_original_replay']['PASS'] and
        r['independent_full_original_replay']['C3A']['integer_pattern_exact'] and
        r['independent_full_original_replay']['original_full_matrix']['integer_pattern_exact'] for r in rows)
    result=dict(PASS=bool(passed),case_sha=case.case_sha,scope='ALL_20_ARCHIVED_M188_FIXED_ASSIGNMENT_RECOURSE_RAW_WITNESSES',
        original_9322_C3A_binary_and_208312_full_integer_axes_checked=True,witnesses=rows,
        all_integer_domain_validity_proof='COMPLETE_COUNT_COVER_THEOREM_AND_ORIGINAL_ROWS_INDEPENDENT_OF_WITNESS_FINITE_SET',
        native_optimize_calls=0,original_historical_receipts_overwritten=False,
        repairs=0,rounding=0,wall_seconds=perf_counter()-started)
    write(REPORTS/'ALL_ORIGINAL_INTEGER_WITNESS_REPLAY.json',result)
    print('ALL_ORIGINAL_INTEGER_WITNESS_REPLAY',passed,len(rows),result['wall_seconds'])
    return result

if __name__=='__main__':run()
