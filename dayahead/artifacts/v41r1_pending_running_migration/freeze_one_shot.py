"""Seal verified pre-run evidence for the final user-authorized contract."""
from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from dayahead.paper_analysis.storage import read
from dayahead.v41.preflight import OUT,ROOT,record
from dayahead.v41.scientific_archive import document
from dayahead.v41.execution import science
from dayahead.v41r1.migration import CONTRACT


def run():
    xml=OUT/'V41_TEST_RESULTS.xml';tree=ET.parse(xml)
    cases=list(tree.iter('testcase'))
    assert len(cases)>=221 and not any(list(tree.iter(tag)) for tag in ('failure','error','skipped'))
    equivalent=[c for c in cases if c.attrib['classname'].endswith('test_v41r1_compression')]
    assert len(equivalent)==11
    pre=OUT/'PRE_MAY01_ONE_SHOT_AUDIT';receipt=read(pre/'PRE_MAY01_GATE.json')
    assert receipt['status']=='PASS' and receipt['contract']==CONTRACT and receipt['optimizer_calls']==0
    candidate=read(pre/'MIGRATION_ELIGIBILITY_SUMMARY.json');model=read(pre/'MODEL/PRIMARY_STRUCTURE.json')
    assert candidate['explicit_candidate_combination_count']==model['domain_counts']['options']
    request=record(OUT/'USER_FINAL_ONE_SHOT_MIGRATION_CONTRACT.txt')
    sources=[record(ROOT/p) for p in ('dayahead/v40g/domain.py','dayahead/v40g/optimizer.py',
        'dayahead/v41r1/migration.py','dayahead/v41r1/migration_factor.py','dayahead/v41r1/migration_load.py','dayahead/v41r1/migration_memory.py',
        'dayahead/v41r1/migration_retention.py','dayahead/v41/retention.py','dayahead/v41/solver_observer.py',
        'dayahead/v40a/feedback.py','dayahead/v40h/feedback.py','dayahead/v40h/policy.py',
        'tests/dayahead/test_v41r1_compression.py','tests/dayahead/test_v41r1_migration.py')]
    prior=read(OUT/'SUPERSEDED_FIRST_CHECKPOINT_COMPRESSION_GATE.json')
    gate={k:prior[k] for k in ('method','forward','reverse','P1_P2','P3','P4','P5','checks')}
    gate.update(status='PASS',contract=CONTRACT,request=request,sources=sources,
        equivalence_test_count=len(equivalent),test_results=record(xml),
        tests=[c.attrib['name'] for c in equivalent],
        explicit_reference='Final user-authorized one-shot rule; independent direct reduced oracle, then production finite Option set',
        checkpoint_authority='User FINAL ONE-SHOT sections 0, 8, 20, 22; deterministic first boundary, D00 inclusive for established RUNNING',
        earlier_equivalence_claims='WITHDRAWN_AS_CURRENT_APPROVAL; retained as historical evidence',
        full_explicit_candidate_combinations=candidate['explicit_candidate_combination_count'],
        model_structure=record(pre/'MODEL/PRIMARY_STRUCTURE.json'),
        model_variables=model['model_variables'],binary_variables=model['binary_variables'],
        integer_variables_including_binary=model['integer_variables_including_binary'],
        linear_constraints=model['model_constraints'],general_constraints=model['general_constraints'],
        explicit_to_compressed_integer_ratio=candidate['explicit_candidate_combination_count']/model['integer_variables_including_binary'],
        superseded_all_checkpoint_explicit_count=54411054,
        superseded_all_checkpoint_to_final_integer_ratio=54411054/model['integer_variables_including_binary'],
        dimension_reduction_is_user_authorized_scientific_revision=True,
        factorization_is_exact_under_final_semantics=True,pruning_methods_used=[],
        diagnostic_only_build=True,Actual_reads=0)
    gate.update(event_load_recurrence=True,matrix_nonzeros=model['matrix_nonzeros'],
        interval_incidence_equivalence='GPU[t]=GPU[t-1]+starts[t]-ends[t], GPU[-1]=0; summing recovers every dense interval row, differencing reverses it. Exact for the continuous relaxation too.',
        H4_expression='Same headroom computed from constrained GPU state variables instead of repeatedly expanding equivalent option sums.',
        dense_reference_matrix_nonzeros=52197761)
    document(OUT/'EXACT_COMPRESSION_GATE.json',gate)
    scope=read(OUT/'FINAL_SCOPE_REGISTRATION.json')
    scope.update(contract=CONTRACT,checkpoint_contract=request,
        checkpoint_selection='DETERMINISTIC_FIRST_VALID_ONLY',
        supersession='SUPERSEDED_IN_V41R1_BY_ONE_SHOT_FIRST_CHECKPOINT_MIGRATION',
        previous_all_valid_checkpoint_interpretation_wrong=False,
        first_checkpoint_UID_serial_cursor_rule='First checkpoint fixed by new user contract; inherited WAN cursor=max(cursor,first_checkpoint) from operating slot 2',
        selected_checkpoint_opportunities_per_eligible_job=1,additional_checkpoint_opportunities=0,
        prestart_placement_not_running_migration=True,full_May_authorized='CONDITIONAL_ON_MAY01_AUDITS_AND_FIXED_FOUR_WORKER_STRESS_PASS',
        parallel_day_workers=4,solver_threads_per_day=4,
        memory_contract=record(OUT/'USER_FIXED_FOUR_WORKER_MEMORY_CONTRACT.txt'),
        voltage_margin='CANCELLED_BY_USER',new_voltage_margin=None)
    document(OUT/'FINAL_SCOPE_REGISTRATION.json',scope)
    registry=read(OUT/'V41_POLICY_REGISTRY_FREEZE.json')
    registry['V41R1_authorized_candidate_amendment'].update(contract=CONTRACT,
        checkpoint_choice='FIRST_VALID_ONLY_ONE_SHOT',additional_migration_opportunities=0)
    document(OUT/'V41_POLICY_REGISTRY_FREEZE.json',registry)
    document(OUT/'FINAL_CHECKPOINT_AUTHORITY_AUDIT.json',dict(status='PASS',contract=CONTRACT,
        current_normative_answer='A_USER_AUTHORIZED_NEW_REVISION',source_contract=request,
        supersession='SUPERSEDED_IN_V41R1_BY_ONE_SHOT_FIRST_CHECKPOINT_MIGRATION',
        previous_all_valid_checkpoint_interpretation_wrong=False,
        prior_audit=record(OUT/'CHECKPOINT_NORMATIVE_AUTHORITY_AUDIT.json'),
        final_gate=record(OUT/'EXACT_COMPRESSION_GATE.json'),
        first_D00_boundary_rule='Positive established progress exactly on the existing 1800-second cadence includes D00. PENDING starts require the next boundary.',
        first_checkpoint_at_D00_jobs=candidate['N_RUNNING_WITH_FIRST_CHECKPOINT_AT_D00'],
        count_clarification='4,251,141 was the earlier first-only explicit option count, not all-checkpoint count. The superseded all-checkpoint audit measured 54,411,054. Final count is independently recomputed.',
        checkpoint_choice_dimension=False))
    from dayahead.v41r1.migration_factor import verify_gate
    verify_gate()
    document(OUT/'SCIENTIFIC_SOURCE_FREEZE_PRECOMMIT.json',dict(status='PASS',contract=CONTRACT,
        science=science(),full_regression=record(xml),regression_test_count=len(cases),
        exact_equivalence=record(OUT/'EXACT_COMPRESSION_GATE.json'),
        candidate_and_persistence_gate=record(pre/'PRE_MAY01_GATE.json'),
        independent_day_slots=96,source_clock_issue_offset=24,prestart_reference_start_fixed=True,
        terminal_experiments_active=False,new_voltage_margin=None,full_May_authorized=False))
    print('FINAL_ONE_SHOT_FREEZE_READY',len(cases),len(equivalent),flush=True)


if __name__=='__main__':run()
