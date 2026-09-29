from common16 import *
old=pd.read_csv(V15/'KESTREL_SUBMISSION_SEMANTIC_FIELD_AUDIT.csv').drop_duplicates('field')
receipt=read(ROOT/'KESTREL_SOURCE_REAUDIT.json')
rows=pd.read_csv(ROOT/'RADDIT_FIELD_AUTHORITY_AUDIT.csv')
rows=rows[rows.source.eq('RADDiT historic')].to_dict('records')
for _,r in old.iterrows():
    field=r['field'];allowed=field in ['user','submit_line']
    rows.append(dict(source='Kestrel original archive',field=field,source_column=r['source_column'],
        information_class='DEPLOYABLE_SUBMISSION_TIME' if allowed else 'HISTORICAL_DIAGNOSTIC_ONLY',
        meaning=r['classification'],available_as_submission_concept=bool(r['known_at_submit']),
        archived_initial_version_proven=False,same_value_future_V42_reproducible='CONDITIONAL_ACCEPTED_RECEIPT_AND_NAMESPACE' if allowed else False,
        predictor_scope='APPROVED_SEMANTIC_CONCEPT_WITH_RECEIPT' if allowed else 'DIAGNOSTIC_ONLY',
        reason='V15 datacard immutable submitting-user/original-command concept; future inference requires accepted immutable receipt and matching namespace, not recovery of archive hashing' if allowed else r['exclusion_reason'],
        prior_audit_sha256=sha(V15/'KESTREL_SUBMISSION_SEMANTIC_FIELD_AUDIT.csv'),reaudit_sha256=receipt['output']['sha256']))
for field in ['nodes_req','processors_req','memory_req','wallclock_req','gpus_requested','submit_time','start_time','end_time','wallclock_used']:
    forbidden=field in ['start_time','end_time','wallclock_used'];a=field=='submit_time'
    rows.append(dict(source='Kestrel original archive',field=field,source_column=field,
        information_class='FORBIDDEN_OUTCOME_OR_FUTURE' if forbidden else 'DEPLOYABLE_SUBMISSION_TIME' if a else 'HISTORICAL_DIAGNOSTIC_ONLY',
        meaning='OUTCOME_OR_COMPLETION_ELIGIBILITY' if forbidden else 'EVENT_TIME' if a else 'REQUEST_SNAPSHOT',
        archived_initial_version_proven=a,same_value_future_V42_reproducible=a,
        predictor_scope='NEVER' if forbidden else 'OBSERVABLE_EVENT_TIME' if a else 'FROZEN_R0_TRACE_PROXY_NOT_RECERTIFIED',
        reason='Linkage, labels, completion eligibility only' if forbidden else 'Submission event' if a else 'Historical initial mutable request version not certified; existing R0 baseline proxy contract is preserved, not silently upgraded to source-authorized production truth'))
pd.DataFrame(rows).to_csv(ROOT/'RADDIT_FIELD_AUTHORITY_AUDIT.csv',index=False)
boundary=sum(r['UTC_April_boundary_rows_excluded'] for r in receipt['members'])
write('PREAPRIL_BOUNDARY_AUDIT.json',dict(time=now(),March_member_UTC_April_boundary_rows_read_then_excluded=boundary,
    April_named_members_opened=False,May_2025_named_members_opened=False,April_rows_used_for_training=False,April_rows_used_for_selection=False,
    first_attempt='Boundary assertion stopped before output; original failure log preserved',
    May_2024_historical_training_is_not_May_2025_holdout=True))
print('AUTHORITY',len(rows),'BOUNDARY_EXCLUDED',boundary,flush=True)
