"""Single admitted D0 A1 pilot; durable source, Native0, and failure receipts."""
from pathlib import Path
import json
import sys
import traceback
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.d0_case import build_planning_inputs,require_case,REPORT
from v42_integration.d0_a_planning import build_d0_native_model,solve_d0_native_model,write_d0_a_planning_audit
from v42_integration.d0_resource import D0PilotBudget
from v42_integration.unified_contract import digest
from v42_integration.m_engine import _write,file_record
from v42_integration.unified_resource import UnifiedResearchBudget


def main():
    attempt=REPORT/'A1_PILOT01'
    if attempt.exists():raise FileExistsError('D0_EXISTING_PILOT_MUST_NOT_BE_OVERWRITTEN')
    attempt.mkdir(parents=True)
    began=perf_counter();built=None;context=None;matrix=None;result=None
    canonical=UnifiedResearchBudget()
    before=json.loads(canonical.path.read_text())
    _write(attempt/'NATIVE_LEDGER_BEFORE.json',before)
    receipt=dict(schema='D0_SINGLE_A1_ADMITTED_PILOT_V1',status='NOT_RUN',
        requested_native_seconds=25.,return_reserve_seconds=30.,
        prior_used_seconds=canonical.used(),historical_prefix_gate_used=False,
        original_A_model_not_replaced=True,old_results_not_reused=True)
    try:
        _write(attempt/'RESOURCE_BEFORE_BUILD.json',canonical.preflight())
        context=build_planning_inputs(output=REPORT,call_cap=25.)
        manifest=context['manifest'];require_case(manifest,stage='A1')
        case=context['make_a_case']('A1',folder=attempt/'SOLVE')
        budget=D0PilotBudget(manifest,stage_case_sha=case.case_sha,
            source_input_sha=context['input_audit']['a_input_sha'])
        receipt.update(identity=manifest['identity'],source_sha=manifest['source_sha'],
            manifest_sha=manifest['manifest_sha'],stage_case_sha=case.case_sha,
            input_MESS_anchor=case.grid.fixed_mess['plan_sha'],
            source_input_sha=context['input_audit']['a_input_sha'])
        _write(attempt/'PILOT_ADMISSION.json',receipt)
        build_began=perf_counter()
        built=build_d0_native_model(case,build_admission=dict(status='PASS',
            operation='D0_A_NATIVE0_BUILD',case_sha=case.case_sha,concurrent_heavy_solver=False))
        matrix=built[-1];matrix['build_wall_seconds']=perf_counter()-build_began
        _write(attempt/'NATIVE0_MATRIX_RECEIPT.json',matrix)
        _write(attempt/'RESOURCE_AFTER_BUILD.json',budget.preflight())
        result=solve_d0_native_model(built,case=case,budget=budget,cap_seconds=25.)
        receipt.update(status='PASS_FEASIBLE_PILOT' if result['FULL_feasible'] else 'NOT_CERTIFIED_NO_FULL_PRIMAL',
            native_pilot_executed=True,Native_used_seconds=result['Native_used_seconds'],
            A1_FULL_feasible=result['FULL_feasible'],P1_status=result['P1_status'],P2_status=result['P2_status'],
            A_result=file_record(attempt/'SOLVE/A_RESULT.json'))
    except Exception as exc:
        current=json.loads(canonical.path.read_text())
        executed=len(current['calls'])>len(before['calls'])
        receipt.update(status='FAIL' if executed or built is None and context is not None else 'NOT_RUN_RESOURCE_OR_ADMISSION_GATE',
            native_pilot_executed=executed,
            error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
        print(receipt['traceback'],flush=True)
    finally:
        if built is not None:built[0].dispose()
        after=json.loads(canonical.path.read_text())
        receipt.update(wall_seconds=perf_counter()-began,cumulative_used_seconds=after['conservative_solve_seconds'],
            remaining_seconds=after['limit_seconds']-after['conservative_solve_seconds'],
            new_native_calls=len(after['calls'])-len(before['calls']),
            historical_calls_prefix_byte_semantics_preserved=after['calls'][:len(before['calls'])]==before['calls'],
            old_parent_ledgers_unchanged=after['historical_ledgers']==before['historical_ledgers'],
            no_native_budget_reset=True,inflight=after['inflight'])
        _write(attempt/'PILOT_RESULT.json',receipt)
        if context is not None:
            write_d0_a_planning_audit(REPORT,context['classification'],context['input_audit'],
                matrix_receipt=matrix,a_result=result)
        print(json.dumps(receipt,indent=2),flush=True)
    return 0 if receipt.get('native_pilot_executed') or receipt['status'].startswith('NOT_RUN') else 1


if __name__=='__main__':raise SystemExit(main())
