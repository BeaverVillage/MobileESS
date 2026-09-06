"""Read-back gates before any revised May01 policy execution; no Actual access."""
from pathlib import Path
import json
import shutil
import xml.etree.ElementTree as ET
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v41.preflight import ROOT, OUT, record
from dayahead.v41.persistence import table, verify_table
from dayahead.v41.data import SOURCE_REPO
from .terminal import attach, check, authorized_options, residual_coordinates, CARRY_IN


def run():
    from .audit import OLD, old_files
    from dayahead.v39d.evaluate import _load_capacity
    old_out=OLD/'dayahead/artifacts/v41_final_ml_interface_may_campaign'
    source=OLD/'frozen_artifacts/v41_may_campaign/inputs/2025-05-01/common/COMMON_B0_REFERENCE_JOBS.json'
    capacity=_load_capacity(SOURCE_REPO)[0]
    jobs=attach(read(source));rows=[];carry=[];cross=[];peak=[]
    for row in jobs:
        if row['state_at_issue']!='PENDING':continue
        opts=authorized_options(row,capacity)
        for site,start in opts:
            check(row,{**row,'AIDC_site':site,'start_slot':start,'end_slot':start+row['safe_duration_slots']})
        if row['terminal_reference_selected'] and row['start_slot']<24:
            assert opts==[(row['AIDC_site'],row['start_slot'])]
            carry.append(row['job_uid'])
        if not row['terminal_reference_selected'] or row['start_slot']<24:continue
        for site,start in opts:
            residual=residual_coordinates(start,row['safe_duration_slots'])
            assert residual<=row['terminal_reference_remaining_slots']
            rows.append(dict(job_id=row['job_uid'],site=site,start_issue=start,start_day=start-24,
                duration_slots=row['safe_duration_slots'],residual_day=residual,
                residual_issue=max(0,start+row['safe_duration_slots']-120),
                terminal_reference=row['terminal_reference_remaining_slots']))
        if row['terminal_reference_remaining_slots']>0:
            cross.append((row,opts))
            if row['start_slot']==96:peak.append((row,opts))
    assert len(carry)==215 and len(cross)==300 and len(peak)==156
    import pandas as pd
    coordinate_table=table(OUT/'diagnostic/SLOT_COORDINATE_ALL_MOVABLE_OPTIONS.parquet',pd.DataFrame(rows))
    frame=verify_table(coordinate_table)
    assert (frame.residual_day==frame.residual_issue).all()
    pre_day_cross=[r['job_uid'] for r in jobs if r['job_uid'] in carry and r['terminal_reference_remaining_slots']>0]
    def flexible(items):
        return dict(total=len(items),time=sum(len({t for s,t in opts})>1 for row,opts in items),
            site=sum(len({s for s,t in opts})>1 for row,opts in items),
            either=sum(len(opts)>1 for row,opts in items))
    prior=ROOT/'dayahead/artifacts/v41r1_premay_voltage_security_margin'
    pairing=read(prior/'V41R1_PREMAY_VOLTAGE_PAIRING_AUDIT.json')
    freeze=read(prior/'V41R1_VOLTAGE_SECURITY_MARGIN_FREEZE.json')
    firewall=read(prior/'V41R1_VOLTAGE_MARGIN_DATA_FIREWALL.json')
    stop='V41R1_PREMAY_VOLTAGE_MARGIN_AUTHORITY_INSUFFICIENT'
    assert pairing['status']==stop and pairing['N_preMay_policy_days']==0
    assert freeze['EPSILON_V_UP'] is None and freeze['status']=='NOT_FROZEN'
    assert firewall['May_calibration_rows']==0 and not firewall['May_based_retuning']
    def verify_refs(value):
        if isinstance(value,dict):
            if {'path','sha256','bytes'}<=value.keys():
                assert record(value['path'])=={k:value[k] for k in ('path','sha256','bytes')}
            else:
                for item in value.values():verify_refs(item)
        elif isinstance(value,list):
            for item in value:verify_refs(item)
    # Re-open and hash every retained pre-May authority leaf. No May numerical
    # voltage arrays are read or used to choose epsilon.
    verify_refs(pairing);verify_refs(freeze)
    legacy=read(prior/'V41R1_HISTORICAL_ACTUAL_CANDIDATE_ROWS.json')['rows']
    assert len(legacy)==51 and all(r['compatibility_status']=='REJECTED' for r in legacy)
    preserved=read(prior/'V41_EXPOSED_PRE_MARGIN_PILOT_PRESERVATION.json')['files']
    assert preserved==old_files()
    unchanged=('dayahead/v41/actual.py','dayahead/v41/actual_dispatch.py','dayahead/v41/snapshot.py',
        'dayahead/v41/scalars.py','dayahead/v41/runtime.py','dayahead/v41/workload.py','dayahead/v41/reserve.py',
        'dayahead/v41/objectives.py','dayahead/v40g_segments/b3.py','dayahead/v40h/mobility.py',
        'dayahead/v40h/recourse.py','dayahead/v40a/grid.py','dayahead/v40e/mapping.py')
    unchanged_evidence=[]
    for path in unchanged:
        if not (ROOT/path).exists():continue
        assert record(ROOT/path)['sha256']==record(OLD/path)['sha256'],path
        unchanged_evidence.append(record(ROOT/path))
    xml=OUT/'V41_TEST_RESULTS.xml';suite=ET.parse(xml).getroot()
    assert not list(suite.iter('failure')) and not list(suite.iter('error'))
    cases=list(suite.iter('testcase'));assert len(cases)>=196
    registry=read(old_out/'V41_POLICY_REGISTRY_FREEZE.json')
    registry['terminal_revision']=dict(contract='V41R1_PER_JOB_TERMINAL_RESIDUAL_V1',H=96,
        independent_days=True,common_reference='AUTHORITATIVE_DAY_D_REFERENCE',
        issue_begin=24,issue_end_exclusive=120,per_job_residual_nonincrease=True,pre_day_PENDING=CARRY_IN,
        post_H_power_grid_MESS_variables=0,voltage_margin_status='CANCELLED_BY_USER',voltage_margin_active=False,
        EPSILON_V_UP='NOT_INTRODUCED',NEW_VOLTAGE_MARGIN='NONE')
    write_json(OUT/'V41_POLICY_REGISTRY_FREEZE.json',registry)
    fixture='V41_LEGACY_MIGRATION_REGRESSION_FIXTURE.json'
    if not (OUT/fixture).exists():shutil.copyfile(old_out/fixture,OUT/fixture)
    assert record(old_out/fixture)['sha256']==record(OUT/fixture)['sha256']
    result=dict(status='PASS',May01_scientific_rerun_started=False,
        slot_coordinate_audit=dict(status='PASS',H=96,issue_begin=24,issue_end_exclusive=120,
            critical_time='2025-05-01T18:00:00+10:00',critical_day_slot=72,critical_issue_slot=96,
            all_movable_option_rows=coordinate_table,off_by_24_regression='test_off_by_24_issue_and_day_coordinates'),
        pre_D00_jobs=dict(status='PASS',count=len(carry),classification=CARRY_IN,job_ids=carry,
            frozen=['reference start','reference site','admission','pre-day execution authority'],
            new_migration_decisions=0,Day_D_occupancy='Exact overlap of fixed full-service intervals with [24,120)'),
        cross_midnight=dict(total_reference=300,pre_D00_fixed_subset=len(pre_day_cross),
            pre_D00_fixed_job_ids=pre_day_cross,in_day=flexible(cross),critical_156=flexible(peak),
            checked_constraints=['existing earliest/latest window','reference per-job residual','site capacity',
                'eligible physical rack pool','frozen admission','no new PENDING migration type'],
            meaning='Legal individual choice-domain alternatives, not a claim all changes can be jointly selected under grid/capacity constraints'),
        old_post_H_freeze=dict(status='PASS',R1_path_unreachable=True,
            replaced_paths=['v40a.feedback.authorized_options','v40g.domain.audit','v40g_segments.canonical.terminal_audit','v40h.feedback.candidates'],
            implementation=record(ROOT/'dayahead/v41r1/terminal.py'),legacy_caller_behavior_retained=True),
        terminal_no_dumping=dict(status='PASS',violations=0,maximum_positive_residual_delta=0,
            implementation='Each job choice filtered independently before variable creation; no aggregate offset or objective term'),
        voltage_margin=dict(VOLTAGE_SECURITY_MARGIN_REVISION='CANCELLED_BY_USER',
            EPSILON_V_UP='NOT_INTRODUCED',NEW_VOLTAGE_MARGIN='NONE',
            active=False,May_based_tuning=False,existing_upper_limit_pu=1.05,
            prior_historical_audit_classification=stop,historical_Actual_candidates=51,
            rejection_reasons={reason:sum(reason in r['reasons'] for r in legacy)
                for reason in ('KNOWN_LEGACY_DUPLICATED_MAPPER','NO_CORRECTED_MAPPER_GENERATION_ATTESTATION')},
            corrected_April_reason=pairing['corrected_April']['reason'],
            evidence=[record(prior/name) for name in ('V41R1_PREMAY_VOLTAGE_PAIRING_AUDIT.json',
                'V41R1_HISTORICAL_ACTUAL_CANDIDATE_ROWS.json','V41R1_VOLTAGE_MARGIN_DATA_FIREWALL.json','V41R1_VOLTAGE_SECURITY_MARGIN_FREEZE.json')]),
        unchanged_scientific_authorities=unchanged_evidence,old_May01_preservation=dict(status='PASS',files=len(preserved)),
        tests=dict(status='PASS',count=len(cases),junit=record(xml)),
        scientific_scope='INDEPENDENT_DAILY_COUNTERFACTUAL_EVALUATION',
        stage_ownership=dict(A0_B1='Pending choice domain and per-job residual cap',A1_B3='Same common residual cap; RUNNING/M1 frozen',
            B0_B2='Same common reference/admission/full duration; no new timing authority',
            M1_MF_Fresh_Actual='No new terminal scheduling authority'),
        full_May_authorized=False)
    write_json(OUT/'V41R1_PRE_MAY01_RERUN_GATE.json',result)
    print(json.dumps({k:result[k] for k in ('status','cross_midnight','terminal_no_dumping','voltage_margin','tests')},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':run()
