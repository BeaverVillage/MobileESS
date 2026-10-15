"""Revalidate unchanged actual matrix proofs and new accounting without Native."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def audit(output,b1,m,recovery):
    from v42_integration.m_engine import file_record
    from v42_integration.table_v_interruption import archived_runtime_summary
    from v42_integration.table_v_flex_planning import require_flex_case
    from v42_integration.table_v_native_journal import atomic_json,NativeJournal
    from tools.audit_v42_aidc_compression import forbid_native
    import gurobipy as gp
    import numpy as np
    from types import SimpleNamespace
    output=Path(output).resolve();output.mkdir(exist_ok=False,parents=True);forbid_native()
    b1=Path(b1);m=Path(m);recovery=Path(recovery)
    records=json.loads((b1/'B1/A1/DW/DW_SOURCE_FREEZE.json').read_text())['sources']
    records+=json.loads((m/'RESULT.json').read_text())['current_source_records']
    if not all(file_record(r['path'])==r for r in records):
        raise ValueError('UNCHANGED_ACTUAL_FULL_AND_M_PRODUCER_SOURCE_BYTES_REQUIRED')
    manifest=require_flex_case(json.loads((b1/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json').read_text()))
    prior=json.loads((recovery/'RECOVERY_COMPLETE.json').read_text())
    descriptor=prior['ledger']
    if file_record(descriptor['path'])!=descriptor:raise ValueError('RECONCILED_LEDGER_BYTE_DRIFT')
    summary=archived_runtime_summary(json.loads(Path(descriptor['path']).read_text()))
    if summary!=prior['native_accounting']:raise ValueError('RECOVERY_NATIVE_INTERVAL_DRIFT')
    model=gp.Model('NAMED_RECOVERY_OBSERVATION_NATIVE0_READBACK');model.Params.OutputFlag=0
    try:
        x=model.addVars(2,lb=[-1.,0.],ub=[2.,3.]);model.addConstr(x[0]+2*x[1]<=5.)
        model.setObjective(x[0]);model.Params.Threads=1;model.update()
        before=(model.getA().toarray(),model.getAttr('LB'),model.getAttr('UB'),model.getAttr('Obj'))
        budget=SimpleNamespace(path=output/'NAMED_NATIVE0_NO_BUDGET_LEDGER.json',document=dict(inflight=None))
        journal=NativeJournal(budget,'NAMED_NATIVE0_OBSERVER_ONLY')
        journal.finish(model,dict(native_execution_entered=False,Native_Runtime=None,
            fixture=True,diagnostic_only=True))
        after=(model.getA().toarray(),model.getAttr('LB'),model.getAttr('UB'),model.getAttr('Obj'))
        if not all(np.array_equal(a,b) for a,b in zip(before,after)):
            raise ValueError('NATIVE_JOURNAL_CHANGED_MODEL_MATRIX_DOMAIN_OBJECTIVE')
    finally:model.dispose()
    result=dict(PASS=True,Native_calls=0,Native_Optimize_forbidden=True,
        actual_static_FULL_and_M_matrix_proofs_reused_only_after_exact_producer_source_check=True,
        actual_full_matrix_rebuilt=False,current_static_source_records=records,
        static_evidence=[file_record(b1/'RESULT.json'),file_record(m/'RESULT.json'),
            file_record(b1/'ACTUAL_S1_BASIS_NATIVE0/RESULT.json')],
        native_observer_readback_is_named_small_fixture_not_FULL_matrix=True,
        observer_matrix_domain_objective_unchanged=True,recovered_native_accounting=summary,
        scientific_source_sha=manifest['source_sha'],Original_FULL_UB_claimed=False,Actual_Fresh_PASS_claimed=False,
        new_accounting_source_records=[file_record(ROOT/p) for p in (
            'v42_integration/table_v_budget.py','v42_integration/release_production_budget.py',
            'v42_integration/table_v_interruption.py','v42_integration/table_v_native_journal.py')])
    atomic_json(output/'RESULT.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--b1-native0',type=Path,required=True);p.add_argument('--m-native0',type=Path,required=True)
    p.add_argument('--recovery',type=Path,required=True);a=p.parse_args()
    r=audit(a.output,a.b1_native0,a.m_native0,a.recovery);print(json.dumps(dict(PASS=r['PASS'],Native_calls=0)))
