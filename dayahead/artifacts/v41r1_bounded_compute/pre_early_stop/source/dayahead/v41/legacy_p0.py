"""Seven explicit legacy P0 closure gates backed by current regression/output evidence."""
from pathlib import Path
import xml.etree.ElementTree as ET
from dayahead.paper_analysis.storage import read
from .preflight import ROOT,OUT,record
from .data import RUNTIME,SOURCE_REPO
from .reserve import require
from .scientific_archive import document,verify_manifest

ITEMS = {
 'P0-01':dict(original_defect='Old B0/B2 and other historical PASS results could bypass current corrected execution.',
    paths=['dayahead/v41/execution.py','dayahead/v41/campaign.py'],
    exact_fix='V41-specific phase schema, exact source and input identities, new generated outputs, verified phase/unit manifests; only V41 B0/B1 decisions feed B2/B3.',
    tests=['test_p0_01_old_success_is_not_v41_execution','test_old_v40b_certificate_rejected','test_only_complete_current_case_can_skip'],
    scope='B0-B3 DayAhead/Actual and B2/B3 A0 reuse'),
 'P0-02':dict(original_defect='A top-level day/case certificate did not recursively verify all scientific output leaves.',
    paths=['dayahead/v41/scientific_archive.py','dayahead/v41/campaign.py'],
    exact_fix='Exact manifest file set, nested phase/unit traversal, SHA256/schema/count readback, missing/corrupted/orphan rejection before reuse and COMPLETE.',
    tests=['test_manifest_readback_orphans_missing_and_corruption','test_day_certificate_recursively_revalidates_leaves','test_summary_and_solver_pass_cannot_mark_a_phase_complete'],
    scope='All policy/day phase and unit completion/restart'),
 'P0-03':dict(original_defect='M1 stage, restricted and full-child caches could restore stale inputs or approximate parent identities.',
    paths=['dayahead/v41/execution.py','dayahead/v40h/cache.py','dayahead/v40h/candidate_cache.py','dayahead/v40h/beam_driver.py'],
    exact_fix='Retain hardened exact M1 cache family; bind V41 ML/source, electrical coefficients, exact AIDC/parent/PQ, traffic/road/route/MESS authorities; reject stale payloads before deserialization.',
    tests=['test_p0_03_v41_snapshot_changes_all_cache_families','test_stage_different_dependency_rejected_and_preserved',
           'test_exact_current_stage_resumes_and_parent_mutation_rejected','test_restricted_pickle_cache_validates_before_deserialization','test_full_child_identity_binds_exact_unrounded_parent'],
    scope='B2/B3 M1 stage/restricted/full-child/MIP-start cache'),
 'P0-04':dict(original_defect='Current source hashes could be attached after the fact to old electrical outputs without proof of generation.',
    paths=['dayahead/v41/electrical.py','dayahead/v40i/electrical.py','dayahead/v41/mapper_audit.py'],
    exact_fix='Capture source/input hashes before fresh producer; preserve pre/start/end/post order; require 23234 measured solves and zero reused outputs/nonconvergence; verify all numerical arrays on load.',
    tests=['test_p0_04_v41_requires_actual_generation_proof','test_durable_pre_freeze_before_actual_generation','test_old_coefficient_cannot_be_recertified','test_post_input_mutation_preserves_actual_failure_hashes'],
    scope='All policies Planning coefficient generation, Fresh and Actual physical input identity'),
 'P0-05':dict(original_defect='B1 results used as B3 A0 were not bound to current B1 source, common duration and electrical generation.',
    paths=['dayahead/v41/execution.py','dayahead/v41/common.py'],
    exact_fix='Capture GENERATION_INPUT_IDENTITY before the optimizer; verify source/manifest leaves and current ML, common-service and electrical certificate before exact prior-policy reuse.',
    tests=['test_p0_05_reuse_requires_current_generation_inputs','test_b1_external_generation_identity_rejects_stale','test_unattested_b1_no_posthoc_adoption'],
    scope='B1 DayAhead generation, B3 A0 and B2 common reference reuse'),
 'P0-06':dict(original_defect='RUNNING migration could collapse source/destination compute segments and incorrectly count transfer/restart gaps as service.',
    paths=['dayahead/v40g_segments/canonical.py','dayahead/v40g/domain.py','dayahead/v41/actual.py','dayahead/v41/common.py','dayahead/v41r1/migration.py','dayahead/v41r1/migration_dispatch.py'],
    exact_fix='Use canonical source/pause/destination service throughout. V41R1 freezes one first-checkpoint progress offset, initial site, destination, path, payload and UID ordering. Actual physical dispatch shifts checkpoint/WAN/restart clocks deterministically without optimization; exact compute service and capacity are verified.',
    tests=['test_8666895_required_canonical_migration_example','test_canonical_normalization_and_pause_conserve_service','test_invalid_migration_fails_closed','test_running_migration_retains_frozen_checkpoint_and_ready','test_one_shot_no_later_checkpoint_and_single_event','test_actual_checkpoint_follows_delayed_progress_without_new_decision','test_actual_shifted_wan_queues_same_path_and_frozen_uid_order'],
    scope='B1/B3 RUNNING migration, A0/A1/MF/Actual occupancy and service'),
 'P0-07':dict(original_defect='Observed historical end time incorrectly justified PRE_DAY_COMPLETE even when frozen policy start plus realized service crossed D00 (UID 8749975).',
    paths=['dayahead/v41/actual.py','dayahead/v40h/pre_day_complete.py'],
    exact_fix='Classify only reconstructed counterfactual compute segments. Do not drop any job by observed end. Under the explicit V41 admission amendment, unadmitted service remains explicit full backlog, never invented site/execution or zero-service exclusion.',
    tests=['test_p0_07_8749975_not_excluded_from_counterfactual_day','test_8749975_counterfactual_day_overlap_fail_closed','test_known_site_overlap_is_preserved_in_actual_gpu','test_actual_migration_carry_out_is_recorded_not_policy_failure','test_native_issue_axis_explicit_off_by_24_regression'],
    scope='B0-B3 Actual completion, occupancy, service/backlog and pre-day exclusion')}


def audit():
    from .execution import science
    xml=OUT/'V41_TEST_RESULTS.xml'; root=ET.parse(xml).getroot(); cases=list(root.iter('testcase'))
    require(cases and not list(root.iter('failure')) and not list(root.iter('error')),'P0_REGRESSION_SUITE_FAILED')
    rows=[]
    for key,spec in ITEMS.items():
        regression=[]
        for name in spec['tests']:
            matching=[c for c in cases if c.attrib['name'].split('[',1)[0]==name]
            require(matching and all(not list(c.iter('skipped')) for c in matching),'P0_REGRESSION_MISSING:'+name)
            regression.append(dict(test=name,cases=len(matching),status='PASS',junit=record(xml)))
        rows.append(dict(item=key,original_defect=spec['original_defect'],current_implementation_path=spec['paths'],
            exact_fix=spec['exact_fix'],regression_test=regression,artifact_hash_evidence=[record(ROOT/p) for p in spec['paths']],
            status='PASS',affected_policy_stage=spec['scope']))
    electrical=RUNTIME/'e/20250501/V41_ELECTRICAL_CERTIFICATE.json'
    from .electrical import verify_generation_proof
    value=read(electrical); verify_generation_proof(value)
    rows[3]['artifact_hash_evidence'].append(record(electrical))
    rows[5]['artifact_hash_evidence'].append(record(OUT/'V41_LEGACY_MIGRATION_REGRESSION_FIXTURE.json'))
    mapper_paths=[RUNTIME/'e/20250501/mapper_audit/MAPPER_AUDIT.json']
    for policy in ('B0','B1'):
        unit=RUNTIME/'pilot/2025-05-01'/policy
        verify_manifest(unit/'UNIT_SCIENTIFIC_MANIFEST.json')
        for phase in ('dayahead','actual'):
            mapper_paths.append(unit/phase/'audit/mapper/MAPPER_AUDIT.json')
            for row in rows: row['artifact_hash_evidence'].append(record(unit/phase/'SCIENTIFIC_MANIFEST.json'))
        rows[4]['artifact_hash_evidence'].append(record(unit/'dayahead/GENERATION_INPUT_IDENTITY.json'))
    mapper=[]
    for path in mapper_paths:
        result=read(path)
        require(result['status']=='PASS' and result['slots']==96 and result['duplicated_group_slots']==0 and
                max(result['P_max_error_kW'],result['Q_max_error_kvar'])<=result['tolerance'],'P0_BACKGROUND_DUPLICATION_OR_CONSERVATION_FAILURE')
        from .persistence import verify_table
        frame=verify_table(result['rows']); require(not frame.duplication_detected.any(),'P0_DUPLICATED_NATIVE_GROUP')
        mapper.append(dict(artifact=record(path),status='PASS',shared_groups=result['shared_group_count'],
            all_groups=result['native_group_count'],group_slots=len(frame),slots=96,duplicate_group_slots=0,
            P_max_error_kW=result['P_max_error_kW'],Q_max_error_kvar=result['Q_max_error_kvar']))
    result=dict(schema='V41_LEGACY_P0_CLOSURE_V1',status='PASS',items=rows,PASS=7,FAIL=0,
        source_manifest= science(),original_defect_registry=record(ROOT/'dayahead/v40h/closeout.py'),
        historical_status_not_assumed_as_closure=True,background_duplication=dict(status='PASS',evidence=mapper,
            legacy_duplication_branch='Unreachable with a nonempty native-load list; corrected wrapper empties loads before invoking legacy non-native code',
            regression='test_corrected_mapper_never_forwards_native_loads_to_duplicated_branch'),
        May1_B0_B1_boundary_revalidated=True)
    document(OUT/'V41_LEGACY_P0_01_07_CLOSURE_AUDIT.json',result)
    return result


if __name__=='__main__': audit(); print('V41_LEGACY_P0_01_07_ALL_PASS',flush=True)
