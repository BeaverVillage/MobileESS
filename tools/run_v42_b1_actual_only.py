"""Replay a proved current B1 A1 with no native model or optimization."""
from pathlib import Path
from time import perf_counter
import argparse
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from v42_integration.unified_contract import REPORT,load_contracts
from v42_integration.m_engine import _write,file_record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--a1',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--slots',type=int,default=16)
    parser.add_argument('--fresh-ac',action='store_true')
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    a1=json.loads(args.a1.read_text(encoding='utf8'))
    if not a1.get('FULL_feasible'):raise ValueError('CURRENT_FULL_B1_A1_REQUIRED')
    from v42_integration.aidc_sensitivity_runtime import build_new_unified_case,run_b1_prefix_canary
    from v42_integration.unified_resource import UnifiedResearchBudget
    budget=UnifiedResearchBudget();_write(out/'RESOURCE_ADMISSION.json',budget.preflight())
    common=load_contracts();start=perf_counter()
    case=build_new_unified_case(out/'PREPARATION',shared_manifest=common)
    # Descriptors populate the factory's current producer identity. No graph,
    # native model, or solver is built by make_a_case.
    current=case.make_a_case('B1','A1',case.initial_mess,out/'DESCRIPTOR_ONLY')
    current.grid.fixed_mess=case.initial_mess
    result=run_b1_prefix_canary(case,a1,slots=args.slots,output=out/'ACTUAL',profile=True)
    receipt=result['receipt'];receipt.update(A1_artifact=file_record(args.a1),
        output_path=str(out),wall_seconds=perf_counter()-start,Native_Optimize_calls=0)
    if args.fresh_ac:
        from v42_integration.actual_validation import fresh_ac_minimum
        from v42_integration.partial_canary import SOURCE_DIR
        source_freeze=json.loads((SOURCE_DIR/'SOURCE_FREEZE_DDAY_GRID_V5.json').read_text(encoding='utf8'))
        archive=Path('D:/v42_may_joint_repair_campaign_20261013')
        fresh={}
        for label,actual in result['results'].items():
            trace=out/(label+'_ACTUAL_PQ.npz')
            np.savez_compressed(trace,PCC_P_kw=np.asarray(actual['physical']['PCC_P_kw']),
                PCC_Q_kvar=np.asarray(actual['physical']['PCC_Q_kvar']),sites=np.asarray(actual['sites']),
                timestamps_start_epoch_seconds=receipt['prefix_begin_seconds']+np.arange(args.slots)*900)
            scope=dict(partial_actual_trace_authorized=True,planning_case_sha=common['bindings']['case_sha'],
                common_initial_state_sha=common['bindings']['initial_state_sha'],
                label='CURRENT_B1_A1_'+label+'_ACTUAL_PREFIX',A1_artifact=file_record(args.a1),
                source_canary=file_record(out/'ACTUAL/B1_PREFIX_COMPARISON.json'))
            began=perf_counter()
            try:
                with budget.exclusive_worker():
                    physical=fresh_ac_minimum(archive/'raw/2025-05-01',out/'ACTUAL',out/(label+'_FRESH'),
                        source_freeze=source_freeze,campaign_manifest=archive/'CAMPAIGN_MANIFEST.json',
                        slots=args.slots,trace_path=trace,arm='B1',case_scope=scope)
            except BaseException:
                budget.record_external('B1_PREFIX_FRESH:'+label,perf_counter()-began,solver='AC',status='FAILED')
                raise
            budget.record_external('B1_PREFIX_FRESH:'+label,physical['AC_wall_seconds'],solver='AC')
            fresh[label]=dict(PASS=physical['PASS'],status=physical['status'],
                result=file_record(out/(label+'_FRESH')/'FRESH_PHYSICAL_RESULT.json'))
        receipt.update(Fresh_AC=fresh,all_variant_Fresh_AC_PASS=all(v['PASS'] for v in fresh.values()))
    _write(out/'AIDC_B1_VALIDATION_RESULT.json',receipt)
    _write(REPORT/'AIDC_B1_VALIDATION_RESULT.json',receipt)
    print(json.dumps({k:receipt.get(k) for k in ('status','variants','full96_release_eligible','Fresh_AC')},indent=2))


if __name__=='__main__':main()
