"""31-day public initial-driver reconciliation; no private preparation/Actual."""
import argparse
import gc
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration import release_date_case as cases
from v42_integration import release_date_execution as execution
from v42_integration import release_initial_states as io
from v42_integration.actual import JobRequest
from v42_integration.d0_actual_inputs import D0BacklogProvider
from v42_integration.qos import QoSWindowProvider,TrainingStatistics
from v42_integration.followup_contract import require_initial_state_alignment


class OpaquePrivateEnvironment:
    def __getattribute__(self,name):
        raise AssertionError('PUBLIC_RECONCILIATION_MUST_NOT_READ_PRIVATE_ENVIRONMENT')


def public_arguments(state,provider):
    begin=state['begin_epoch_seconds']
    def request(row):
        return JobRequest(row['uid'],row['submit_seconds'],row['gpu'],tuple(row['compatible_sites']),row['q50'],row['site'],
            dict(row['metadata'],origin_unknown=row['origin_unknown'],episode_id=row['episode_id'],
                elapsed_compute_seconds=row['elapsed_compute_seconds'],
                reused_planning_qos_authority=dict(scope='NAMED_PUBLIC_FIXTURE_STALE_D1_MARKER_MUST_BE_REMOVED'),
                reference_sha='d'*64,reference_start_seconds=begin-21600,provider_sha='e'*64))
    return dict(begin=begin,end=begin+86400,capacities=state['capacities'],
        running=[(request(row),row['site'],row['observed_start_seconds']) for row in state['running']],
        requests=[request(row) for row in state['pending']],environment=OpaquePrivateEnvironment(),qos_window_provider=provider)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(cases.BASE/'RC03/DATE_ACTUAL_HANDOFF/PUBLIC01'))
    args=parser.parse_args()
    out=Path(args.output)
    if out.exists():raise FileExistsError('PUBLIC_DATE_EXECUTION_AUDIT_MUST_NOT_OVERWRITE')
    out.mkdir(parents=True)
    import gurobipy as gp
    frozen=[io.record(ROOT/p) for p in cases.SOURCE13]
    additive=[io.record(ROOT/p) for p in ('v42_integration/release_date_execution.py',
        'tools/audit_v42_release_date_execution.py','v42_integration/release_date_case.py')]
    io.write_json(out/'EXECUTED_SOURCE.json',dict(Source13=frozen,additive=additive))
    saved_native={name:getattr(gp.Model,name) for name in ('__init__','optimize','presolve','computeIIS')}
    attempts=[]
    def forbidden(*a,**k):
        attempts.append('NATIVE_MODEL_OR_SOLVER_ENTRYPOINT');raise AssertionError('PUBLIC_HANDOFF_NATIVE_FORBIDDEN')
    begun=time.perf_counter();rows=[]
    try:
        for name in saved_native:setattr(gp.Model,name,forbidden)
        for day_index in range(1,32):
            day=f'2025-05-{day_index:02d}'
            context=cases.load_date_case(day,cases.BASE/'RC02/DATE_CASES/COMPILE01'/day/'CASE')
            state=context['state'];identity=context['manifest']['identity']
            # No QoS receipt is issued. This named empty-statistics object is
            # only a typed fixture for the public metadata projection. The
            # production driver must supply its original strict Source issuer.
            stats=TrainingStatistics.from_records([],source_sha=io.digest('NAMED_PUBLIC_RECONCILIATION_ONLY_NO_QOS_ISSUANCE'))
            strict=QoSWindowProvider(stats,case_sha=identity['case_sha'],provider_sha=identity['runtime_sha'])
            provider=D0BacklogProvider(strict,state=state,contract=context['backlog'],identity=identity,
                reference_sha=io.digest(dict(scope='PUBLIC_METADATA_RECONCILIATION_ONLY',day=day)))
            arguments=public_arguments(state,strict)
            projected=execution.project_date_driver_arguments(arguments,state=state,provider=provider,context=context,
                evidence_scope='PUBLIC_INITIAL_STATE_RECONCILIATION_ONLY_NO_PRIVATE_DRIVER')
            actual=projected.arguments
            if actual['environment'] is not arguments['environment'] or any('reused_planning_qos_authority' in r.metadata
                for r in actual['requests']+[r for r,_,_ in actual['running']]):
                raise ValueError('PUBLIC_PROJECTED_ENVIRONMENT_OR_STALE_D1_RECEIPT_DRIFT')
            # Pure original numeric join; authoritative compressed-date source
            # is independently validated by load_date_case/project helper.
            join=require_initial_state_alignment(execution._observed_boundary(state),actual,
                dict(initial_state_sha=identity['initial_state_sha']),evidence_scope='PUBLIC_NUMERIC_JOIN_ONLY')
            row=dict(day=day,status='PASS_PUBLIC_INITIAL_DRIVER_RECONCILIATION_ONLY',
                initial_semantic_sha=state['common_initial_state_sha'],case_sha=identity['case_sha'],
                running_UIDs=join['Running_UIDs'],pending_UIDs=join['Pending_UIDs'],
                running_GPU=sum(r.gpu for r,_,_ in actual['running']),
                legacy_D1_planning_receipts_removed=True,Source_metadata_rights_and_hard_windows_unchanged=True,
                private_Environment_preserved_by_identity=True,private_Environment_field_reads=0,
                private_future_request_bank_constructed=False,source_QoS_receipts_issued=len(provider.receipts),
                QoS_fixture_only_no_policy_or_SLA_authority_granted=True,
                commands='NOT_RUN_CURRENT_FINAL_A2_M2_NOT_AVAILABLE',
                production_private_preparation='NOT_RUN_REQUIRES_CURRENT_A2_M2_AND_ORIGINAL_SOURCE_PROVIDER',
                Actual_runs=0,Native_calls=0,AC_solves=0,
                current_D0_Original_clock_settle_slot_Fresh96='NOT_RUN_REQUIRED_FOR_OFFICIAL_PHYSICAL_GATE',
                previous_PR223_Fresh_PASS_transferred=False,substep_diagnostic_used_as_official_voltage_gate=False)
            io.write_json(out/day/'PUBLIC_INITIAL_DRIVER_RECONCILIATION.json',row)
            rows.append(row);print(day,row['status'],flush=True)
            del context;gc.collect()
    finally:
        for name,method in saved_native.items():setattr(gp.Model,name,method)
    if attempts or any(io.record(r['path'])!=r for r in frozen+additive):
        raise ValueError('PUBLIC_HANDOFF_NATIVE_ATTEMPT_OR_SOURCE_DRIFT')
    summary=dict(status='PASS_PUBLIC_INITIAL_RECONCILIATION_ONLY',days=rows,dates=len(rows),
        Native_calls=0,native_model_builds=0,AC_solves=0,Actual_runs=0,private_environment_field_reads=0,
        source13_unchanged=True,additive_source_unchanged=True,source_QoS_receipts_issued=0,
        production_Actual_or_FULL_handoff_certified=False,
        precise_remaining_inputs=['CURRENT_ORIGINAL_FULL_A2_P1_RESULT_AND_M2_P1_ACCEPTANCE',
            'APPROVED_DOWNSTREAM_NATIVE_BUDGET',
            'ORIGINAL_PRIVATE_DRIVER_PREPARATION_WITH_ITS_FROZEN_STRICT_QOS_SOURCE',
            'CURRENT_D0_ORIGINAL_COMMON_CLOCK_SETTLED_FULL_NETWORK_FRESH96'],
        operational_private_preparation_is_not_proven_missing_by_public_fixture=True,
        old_PR223_physical_PASS_or_substep_FAIL_not_transferred_to_new_official_gate=True,
        wall_seconds=time.perf_counter()-begun)
    io.write_json(out/'MAY31_PUBLIC_DATE_ACTUAL_INPUT_AUDIT.json',summary)
    print('SUMMARY',len(rows),summary['wall_seconds'],flush=True)


if __name__=='__main__':main()
