"""Prepare observed D0 Table V FullFlex descriptors; Native/build/Actual zero."""
from collections import Counter
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.release_date_case import compile_date_case
from v42_integration.table_v_flex_planning import (compile_table_v_flex_context,audit_basic_a1_reuse,
    b1_b3_a1_math_equivalence)
from v42_integration.m_engine import _write,file_record
from v42_integration.actual_validation import read
from v42_integration.policy import digest

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'


def prepare(output):
    if output.exists():raise FileExistsError('TABLE_V_FLEX_PREP_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True)
    basic=compile_date_case('2025-05-01',output=output/'BASE_PUBLIC_D0')
    context=compile_table_v_flex_context(basic,output=output/'FULL_FLEX')
    from v42_integration.table_v_reference import make_reference
    if context['input_audit']['status']=='PASS':
        make_reference(context,output=output/'REFERENCE')
        print('REFERENCE_READY',str(output/'REFERENCE'),flush=True)
    flex=context['tablev_flex'];audit=context['input_audit']
    _write(output/'PUBLIC_REFERENCE_RECORDS.json',dict(schema='TABLE_V_PUBLIC_D0_CAUSAL_REFERENCE_RECORDS_V1',
        day='2025-05-01',reference_sha=flex['reference_sha'],records=flex['reference_records'],
        observed_records=flex['known_observed_records'],initial_source=context['manifest']['initial_record'],
        slots=96,slot_seconds=900,D0_begin=context['state']['begin_epoch_seconds'],native_internal_offset=24,
        native_to_actual='Actual_epoch=D0_begin+(native_slot-24)*900',
        future_Unknown_UIDs_used=False,Actual_truth_read=False,Native_calls=0,model_builds=0))
    if audit['status']=='PASS':
        saved=read(BASE/'RC01/A1_P1_120/A1_P1_RESULT.json')
        reuse=audit_basic_a1_reuse(context,saved)
        equivalence=b1_b3_a1_math_equivalence(context)
        _write(output/'BASIC_A1_REUSE_AUDIT.json',reuse)
        _write(output/'B1_B3_A1_MATH_EQUIVALENCE.json',equivalence)
    rows=flex['domain_mask'];reasons=Counter()
    for row in rows:
        if not row['participant']:reasons['OUTSIDE_EXISTING_FLEX30']+=1
        elif not row['eligible']:reasons['SOURCE_PROTECTED_OR_NONBATCH']+=1
    summary=dict(status=audit['status'],scope='PUBLIC_FULL_FLEX_DESCRIPTOR_AND_DOMAIN_CONFIGURATION_ONLY',
        identity=context['manifest']['identity'],source_sha=context['manifest']['source_sha'],
        initial_Known=len(flex['known_issued_receipts']),native_positive_service_jobs=len(rows),
        FLEX30_eligible_UIDs=sum(r['eligible'] for r in rows),
        positive_E1_delay_UIDs=sum(r['budget_seconds']>0 for r in rows),
        movable_time_window_UIDs=sum(r['state']=='PENDING' and len(r['allowed_native_starts'])>1 for r in rows),
        checkpoint_eligible_UIDs=sum(r['checkpoint_authorized'] for r in rows),
        RUNNING_checkpoint_eligible_UIDs=sum(r['checkpoint_authorized'] and r['state']=='RUNNING' for r in rows),
        delay_budget_distribution=dict(Counter(r['budget_seconds'] for r in rows)),reasons=dict(reasons),
        domain_geometry_and_migration_candidate_counts='DEFERRED_ROOT_SERIAL_BUILD_ADMISSION',
        issues=audit['issues'],R2='HOLD',P2_calls=0,Native_calls=0,native_model_builds=0,Actual_calls=0,AC_calls=0,
        source_records=context['manifest']['source_freeze']['files'],tool=file_record(__file__))
    _write(output/'TABLE_V_FLEX_PREPARATION.json',summary)
    print({k:summary[k] for k in ('status','initial_Known','FLEX30_eligible_UIDs','movable_time_window_UIDs',
        'checkpoint_eligible_UIDs','RUNNING_checkpoint_eligible_UIDs','Native_calls','native_model_builds')},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=BASE/'RC04/TABLE_V/FLEX_PLANNING/PREP01')
    prepare(parser.parse_args().output)
