"""Current public candidate counterfactuals; never a future Job safety certificate."""
from pathlib import Path
from time import perf_counter
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from v42_integration.unified_contract import REPORT,load_contracts,require_bindings
from v42_integration.unified_resource import UnifiedResearchBudget
from v42_integration.m_engine import _write,file_record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if not args.run:raise SystemExit('Explicit --run required for fresh AC probes.')
    witness_path=REPORT/'CURRENT_C1_CANDIDATE_WITNESSES.json'
    data=json.loads(witness_path.read_text(encoding='utf8'))
    require_bindings(data['bindings'],load_contracts()['bindings'])
    selected={}
    for row in data['witnesses']:
        if row['current_non_grid_eligible'] and row['candidate_start_seconds']==1746021600.:
            selected.setdefault(row['uid'],row)
    if not selected:raise ValueError('NO_CURRENT_PUBLIC_NON_GRID_ELIGIBLE_WITNESS')
    from v42_integration.actual_validation import fresh_ac_minimum
    from v42_integration.partial_canary import SOURCE_DIR
    root=REPORT.parents[1];archive=Path('D:/v42_may_joint_repair_campaign_20261013')
    out=REPORT/'UNKNOWN_CURRENT_CANDIDATE_FRESH_AC';out.mkdir(exist_ok=False)
    budget=UnifiedResearchBudget();_write(out/'RESOURCE_ADMISSION.json',budget.preflight())
    source_freeze=json.loads((SOURCE_DIR/'SOURCE_FREEZE_DDAY_GRID_V5.json').read_text(encoding='utf8'))
    results=[]
    for uid,row in selected.items():
        folder=out/uid;folder.mkdir()
        trace=folder/'COUNTERFACTUAL_CURRENT_PQ.npz'
        np.savez_compressed(trace,PCC_P_kw=np.asarray([row['candidate_PCC_P_kw']]),
            PCC_Q_kvar=np.asarray([row['candidate_PCC_Q_kvar']]),sites=np.asarray(data['site_axis']),
            timestamps_start_epoch_seconds=np.asarray([row['observed_at_seconds']]))
        scope=dict(partial_actual_trace_authorized=True,planning_case_sha=data['bindings']['case_sha'],
            common_initial_state_sha=data['bindings']['initial_state_sha'],
            label='COUNTERFACTUAL_CURRENT_PUBLIC_ELIGIBLE_CANDIDATE_NOT_ACTUAL_EXECUTION',
            public_witness=file_record(witness_path),uid=uid,site=row['site'],
            future_runtime_96_safety_certified=False)
        began=perf_counter()
        try:
            with budget.exclusive_worker():
                physical=fresh_ac_minimum(archive/'raw/2025-05-01',root/'docs/v42_trajectory_tracking_may01_canary_20261014/DIAGNOSTIC_FINAL',
                    folder/'FRESH',source_freeze=source_freeze,campaign_manifest=archive/'CAMPAIGN_MANIFEST.json',
                    slots=1,trace_path=trace,arm='B1',case_scope=scope)
        except BaseException:
            budget.record_external('UNKNOWN_CURRENT_CANDIDATE:'+uid,perf_counter()-began,solver='AC',status='FAILED')
            raise
        budget.record_external('UNKNOWN_CURRENT_CANDIDATE:'+uid,physical['AC_wall_seconds'],solver='AC')
        results.append(dict(uid=uid,site=row['site'],public_non_grid_eligible=True,
            current_affine_violations=row['current_signed_affine_violations'],
            current_affine_peak=row['current_signed_affine_peak'],Fresh_AC_PASS=physical['PASS'],
            physical_result=file_record(folder/'FRESH/FRESH_PHYSICAL_RESULT.json'),
            scope='CURRENT_POINT_ONLY_NOT_FUTURE_96_OR_ACTUAL_ALLOCATION'))
    summary=dict(bindings=data['bindings'],rows=results,executed_Job_allocation=False,
        current_physical_PASS=all(r['Fresh_AC_PASS'] for r in results),
        interpretation='CURRENT_FEASIBILITY_MUST_BE_SEPARATE_FROM_FUTURE_AFFINE_REJECTION',
        future_96_runtime_safety='NOT_CERTIFIED',new_A1_actual_performance='NOT_CERTIFIED',
        source_witness=file_record(witness_path))
    _write(REPORT/'UNKNOWN_CURRENT_CANDIDATE_FRESH_AC_RESULT.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
