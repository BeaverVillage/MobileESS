"""Bind research QoS at issue before materializing the Known A1/A2 domain."""
from copy import deepcopy
from dataclasses import asdict, fields
from pathlib import Path
import hashlib

from .policy import digest
from .qos import ObservedJob, receipt_slot_domain
from .experimental_actual import prepare_conditional_arguments


def bind_experimental_planning(case, issue_records, *, scenario, participation,
                               unknown_conditions=None, migration_authority=None,service_reallocation=False):
    """Install a new scientific case without running any optimizer or Actual.

    issue_records must be the Source Planning Known ledger, never DD00 or future
    Unknown metadata. The production case is prepared with strict public inputs
    first; its immutable initial-state proof is reused, not regenerated.
    """
    if case._consumed:raise ValueError('PLANNING_CASE_ALREADY_CONSUMED')
    if scenario not in ('E1','E2'):raise ValueError('NEW_RESEARCH_PLANNING_E1_E2_ONLY')
    if migration_authority is None and case.evidence_kind=='REAL_DATA':
        from .experimental_policy import load_experimental_migration_authority
        migration_authority=load_experimental_migration_authority()
    records={}
    for uid,value in issue_records.items():
        if not isinstance(value,ObservedJob):value=value.get('observed',value)
        job=value if isinstance(value,ObservedJob) else ObservedJob(**{f.name:value[f.name] for f in fields(ObservedJob) if f.name in value})
        if (uid!=job.uid or job.origin_unknown or job.event_seconds>case.planning_slot_zero_seconds
                or job.submit_seconds>case.planning_slot_zero_seconds):
            raise ValueError('ISSUE_ONLY_KNOWN_RECORDS_REQUIRED')
        records[uid]=job
    root=Path(__file__).parent
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))}
    if unknown_conditions is not None and any(any(k in r for k in ('uid','job_uid','actual_end','future_queue')) for r in unknown_conditions):
        raise ValueError('UNKNOWN_NO_FUTURE_UID_AT_PLANNING')
    compiler_contract=dict(coverage=unknown_conditions,service_reallocation=service_reallocation,
        migration_authority_sha=None if migration_authority is None else digest(migration_authority))
    new_science=digest(dict(parent_science=case.science_sha,contract='KNOWN_MILP_UNKNOWN_MULTI_ALTERNATIVE_FROZEN_V2',
        source_files=files,compiler_contract=compiler_contract))
    new_case=digest(dict(parent_case=case.case_sha,science=new_science,scenario=scenario,participation=participation,
        issue_Known_records_sha=digest({u:asdict(j) for u,j in records.items()})))
    strict_provider=case.qos_provider
    # Do not enumerate the Actual request bank at issue. It can contain future
    # Unknown UIDs, which have no role in any Planning domain or policy row.
    projection=prepare_conditional_arguments(dict(qos_window_provider=strict_provider),records,
        scenario=scenario,participation=participation,case_sha=new_case)
    provider=projection['new_qos_provider'];case.qos_provider=provider
    def prepare_research_actual_arguments():
        projected=prepare_conditional_arguments(dict(case.actual_arguments,qos_window_provider=strict_provider),records,
            scenario=scenario,participation=participation,case_sha=new_case,existing_provider=provider)
        arguments=projected['arguments'];arguments.pop('qos_window_provider')
        return arguments,projected['projection_receipt']
    case.prepare_research_actual_arguments=prepare_research_actual_arguments
    old_a=case.make_a_case;old_m=case.make_m_case
    def make_a(arm,stage,mess,output):
        result=old_a(arm,stage,mess,output)
        if set(result.data[1])-set(records):raise ValueError('UNKNOWN_NOT_PRESENT_AT_PLANNING')
        result.qos_receipts={u:provider.receipts[u] for u in result.data[1]}
        result.window_slots={u:receipt_slot_domain(provider.receipts[u],axis_origin_seconds=case.planning_slot_zero_seconds)
            if job.state=='PENDING' else (job.reference_start,) for u,job in result.data[1].items()}
        result.case_sha=digest(dict(parent_case=new_case,stage=stage,arm=arm,MESS=mess['plan_sha'],QoS=provider.stats.sha))
        return result
    def make_m(arm,stage,aidc,output):
        result=old_m(arm,stage,aidc,output)
        # The physical M packet consumes the current A anchor unchanged.
        result.identity.update(qos_sha=provider.stats.sha,research_planning_case_sha=new_case)
        result.case_sha=digest(dict(parent_physical_case=result.case_sha,research_case=new_case,
            current_AIDC_anchor=aidc['aidc_anchor'],QoS=provider.stats.sha,stage=stage))
        from .m_engine import _write
        _write(Path(output)/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=result.case_sha,**result.identity))
        return result
    case.make_a_case=make_a;case.make_m_case=make_m
    case.case_sha=new_case;case.science_sha=new_science
    if case.actual_gate:
        case.evaluation_case_sha=digest(dict(planning_case_sha=new_case,
            common_Dday_initial_state_sha=case.actual_gate.get('common_initial_state_sha')))
    from .m_engine import file_record
    case.input_receipts.extend(file_record(root/name) for name in files)
    case.unknown_conditions=unknown_conditions;case.experimental_migration_authority=deepcopy(migration_authority)
    case.service_reallocation=service_reallocation
    case.research_contract_binding=dict(source_science_sha=new_science,case_sha=new_case,source_files=files,
        Known_issue_UIDs=len(records),Known_issue_UID_sha=digest(sorted(records)),new_Known_domain_required=True,
        Native_Optimize_calls=0,Fresh_AC_status='NOT_RUN',projection=projection['projection_receipt'],
        future_Actual_request_bank_enumerated_at_Planning=False,
        Actual_public_request_projection='DEFERRED_UNTIL_AFTER_FINAL_POLICY_FREEZE')
    return case
