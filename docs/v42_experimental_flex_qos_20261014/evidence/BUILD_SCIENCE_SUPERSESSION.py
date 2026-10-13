from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def main():
    freeze=read(ROOT/'audit/SOURCE_FREEZE_C.json');cases=read(ROOT/'audit/control/FINAL_FLEX_COMPARISON/CASE_MANIFEST.json')
    original=read(ROOT/'audit/SCIENTIFIC_SOURCE_SUPERSESSION_DRAFT.json')
    original['lineage'].append(dict(pr=225,commit='97da5c097f0eefc30a057c51378676c6402138c8',
        source_sha='fe2d882b3db6c43422436e4ea0f5dbd7f7bd1462298389031e18384293d3f0f5',
        role='SOURCE_ONLY_Q90_CORRECTION_REUSES_ORIGINAL_A2_LITERAL_SERVICE',preserved=True))
    original.update(source_freeze_C=freeze['source_sha'],shared_Q90_exact_head='97da5c097f0eefc30a057c51378676c6402138c8',
        conditional_cases=cases,new_Known_contract_domain_optimized=False,
        comparison_scope='E0_ONE_PHYSICAL_BASELINE_NINE_EXPLICIT_ALIASES_AND_18_NEW_FIXED_ANCHOR_REPLAYS',
        new_Full96_event_replay_status='SEE_CASE_EXECUTION_RECEIPTS',new_Fresh_AC='NOT_RUN',
        new_A_M_optimization='NOT_RUN',old_A_M_FULL_UB_LB_or_joint_gap_transferred=False,
        Q50_service_distribution='ORIGINAL_A2_LITERAL_X_SITE_GPU_CARRY_PLUS_ACTION_MINUS_REFERENCE_DELTA',
        Q90_extra_module='SHARED_PR225_v42_integration/q90_recourse.py',
        Q90_duplicate_queue_removed=True,old_full_Q50_fluid='ARCHIVED_SUPERSEDED_DIAGNOSTIC',
        preregistration_receipt_sha=hashlib.sha256((ROOT/'audit/PREREGISTRATION.json').read_bytes()).hexdigest(),
        all_realized_duration_inputs='SIMULATOR_ONLY;POST_EXECUTION_MASS_AUDIT_NEVER_FED_BACK',
        E1_E2_continuation='NOT_SUPPORTED_FAIL_CLOSED;NO_NEW_R0_ON_RELOAD',
        policy_implementation_vs_scientific_assumptions=dict(PR224='COMPLETED_BUGFIX_UNCHANGED',
            PR225='HOURLY_Q90_WORK_SERVICE_QUEUE_CORRECTION_WITH_STRICT_RIGHTS',
            C='USER_APPROVED_EXPLICIT_RESEARCH_QOS_AND_PARTICIPATION_CONTRACTS'),
        performance_evolution=[dict(source='4a13796f69a39dc8b7e5c6159747a402561ec5661f0edda9cbfadef35d7a6bff',
            scope='ABORTED_FULL96_PERFORMANCE_PROBE_NO_RESULT;VALID_TWO_SLOT_PRE_CACHE_PREFIX'),
            dict(source='aac397455fc3344efb61016ef4fcede668437fa490852c46fab74d4df9d04c0a',
                scope='EXACT_CACHE_TWO_SLOT_ENGINEERING_EQUIVALENCE'),
            dict(source=freeze['source_sha'],scope='FINAL_BYTE_SOURCE_WITH_COMMENT_AND_PACKAGED_AUTHORITY_FALLBACK')],
        B2_B3_M_HOLD=True,May31_HOLD=True,new_Native_Optimize_calls=0,new_AC_calls=0)
    (ROOT/'audit/SCIENTIFIC_SOURCE_SUPERSESSION.json').write_text(json.dumps(original,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(final_source=freeze['source_sha'],new_case_count=len(cases['cases']),D_commit_separate=True)))
if __name__=='__main__':main()
