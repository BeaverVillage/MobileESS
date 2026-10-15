"""Freeze separate R1/R2 contracts and prerequisite sensitivity; no Actual/AC."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record, _write
from v42_integration.policy import digest
from v42_integration.current_ac_admission import epoch
from v42_integration.research_presite_contract import ResearchPresiteProvider, make_spec, source_authority

RAW = Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01')
RC = ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'
OUT = RC/'RC03/PRESITE_CONTRACTS'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT)
    output=parser.parse_args().output
    global_scope(output)


def global_scope(OUT):
    if OUT.exists():
        raise FileExistsError('RESEARCH_CONTRACT_FREEZE_MUST_NOT_OVERWRITE')
    OUT.mkdir(parents=True)
    source_record = file_record(RAW/'ACTUAL_INPUT_BUNDLE.json')
    native_record = file_record(RAW/'NATIVE_INPUT_TEMPLATE_B1.json')
    core = [file_record(ROOT/p) for p in ('v42_integration/research_presite_contract.py',
        'v42_integration/experimental_qos.py','v42_integration/release_actual.py')]
    sources = [source_record,native_record,*core]
    native = read(native_record['path']); wan=native['WAN']
    raw = read(source_record['path'])
    placement_path=RC/'RC01/AIDC/REPLAY02/C1/INITIAL_PLACEMENT_LEDGER.json'
    placements=read(placement_path)
    # This is retrospective prerequisite audit of observed RC01 arrivals only.
    # Neither this table nor a future UID list is passed to the live provider.
    actual_rows={str(r['job_uid']):r for r in raw['post_issue_arrivals']}
    begin=epoch('2025-05-01T00:00:00+10:00')
    all_after=[r for r in actual_rows.values() if epoch(r['submit_time']) >= begin]
    source_audit=dict(source=source_record,future_Unknown_total=len(all_after),
        raw_field_presence={k:sum(k in r for r in all_after) for k in (
            'can_prestart_place','batch_eligible','protected','qos','preplacement_data','payload_bytes','source_site')},
        nonnull_source_sites=sum(r.get('source_site') is not None for r in all_after),
        driver_default_false_is_explicit_customer_denial=False,
        research_batch_model='EXISTING_EXPERIMENTAL_ASSUMED_NORMAL_BATCH_FLEX30_SUBSET',
        additional_QoS_delay_or_migration_authority_reused=False, Native_calls=0,
        audit_is_controller_future_population_input=False)
    _write(OUT/'SOURCE_REQUEST_PERMISSION_AUDIT.json',source_audit)
    scenarios=[('R1_SHARED_READY',dict(scenario='R1',ready_delay_slots=0))]
    scenarios += [('R2_P%g_B%g_T%d'%(payload,bw,prepare),dict(scenario='R2',
        payload_multiplier=payload,bandwidth_fraction=bw,preparation_seconds=prepare))
        for payload in (.25,1.,4.) for bw in (.25,1.) for prepare in (0,900)]
    summary=[]
    for label,parameters in scenarios:
        spec=make_spec(source_records=sources,native_wan_sha=digest(wan),shared_sites=sorted(native['capacities']),**parameters)
        provider=ResearchPresiteProvider(spec,native_wan=wan)
        _write(OUT/label/'RESEARCH_CONTRACT.json',dict(spec=spec,science_sha=provider.science_sha,
            case_sha=digest(dict(science_sha=provider.science_sha,base_source=sources,
                observed_initial='5df25289619221a8ed1f7ee6d13a00e73ad5a4e38ac0cf08228e93c3fb67c573'))))
        rows=[];members=set();destinations=0;reasons=Counter();delays=[]
        for event in placements:
            source=actual_rows[event['uid']]
            now=max(begin,((event['time_seconds']+899.999999)//900)*900)
            m=dict(uid=event['uid'],submit_seconds=epoch(source['submit_time']),gpu=source['GPU_gang'],
                compatible_sites=source['compatible_sites'],reference_site=event['basic_site'],state='PENDING',
                origin_unknown=True,accumulated_compute_seconds=0.,t50_seconds=source['Q50_total_seconds'],
                qos=source.get('qos','UNCONFIRMED'),protected=source.get('protected'),
                batch_eligible=source.get('batch_eligible'),can_prestart_place=False)
            provider.register_observed(m,source_authority(source,source_record,now=now),now=now)
            # Preserve the current original source-only zero additional delay.
            # These are prerequisite scenarios, not newly issued QoS receipts.
            qos=dict(allowed_starts_seconds=[],latest_start_seconds=now,budget_seconds=0.)
            for site in sorted(set(m['compatible_sites'])-{event['basic_site']}):
                proposal=provider.propose(m,site,now,day_begin=begin,qos_receipt=qos)
                if proposal['eligible']:
                    members.add(m['uid']);destinations+=1
                if proposal['ready_at_seconds'] is not None:
                    delays.append(max(0.,proposal['ready_at_seconds']-now))
                reasons[proposal['reason'] or proposal['status']]+=1
                rows.append(proposal)
        _write(OUT/label/'PREREQUISITE_SENSITIVITY_NOT_ACTUAL.json',dict(
            scope='RC01_ALREADY_OBSERVED_ARRIVALS_CONTRACT_PREREQUISITES_ONLY',
            actual_execution=False,candidate_AC_executed=False,GPU_rack_feasibility_certified=False,
            real_QoS_receipts_reissued=False,scenario_science_sha=provider.science_sha,
            observed_arrivals=len(placements),eligible_research_UIDs=len(members),
            eligible_research_destinations=destinations,reasons=dict(reasons),
            data_delay_min_seconds=min(delays) if delays else None,
            data_delay_max_seconds=max(delays) if delays else None,candidates=rows,
            performance_improvement_claimed=False,Native_calls=0,AC_calls=0))
        summary.append(dict(label=label,science_sha=provider.science_sha,
            observed_arrivals=len(placements),research_contract_eligible_UIDs=len(members),
            eligible_destination_prerequisites=destinations,reasons=dict(reasons),
            ready_delay_min_seconds=min(delays) if delays else None,
            ready_delay_max_seconds=max(delays) if delays else None,
            actual_changed_UIDs='NOT_RUN',Changed_GPUh='NOT_RUN',candidate_AC='NOT_RUN',
            performance='NOT_RUN',parameters=parameters))
    _write(OUT/'CONTRACT_PREPARATION.json',dict(status='PASS_CONTRACT_AND_PREREQUISITE_SCOPE_ONLY',
        scenarios=summary,Native_calls=0,AC_calls=0,Actual_calls=0,
        existing_Source_and_Raw_unchanged=all(file_record(r['path'])==r for r in sources),
        source_strict_result_overwritten=False,
        original_WAN_bytes_per_GPU=wan['bytes_per_gpu'],
        input_payload_is_assumed_proxy_not_measured=True,
        shared_storage_is_assumed_not_observed=True,
        physical_voltage_gate='FAIL_PRESERVED_SEPARATELY',audit_tool=file_record(__file__)))
    text='''# R1/R2 연구 계약 준비

기존 `PUBLIC_UNKNOWN_PRESTART_COMPATIBLE_SITE_STUDY_V1`은 기본 배치 연구 권한입니다. 기존 CurrentEvent 준비 로직은 관측된 Destination·Source SHA·준비 시각·WAN Path·Bandwidth·Payload 근거를 요구합니다. 최초 배치 연구 권한을 관측된 데이터 이동 권한으로 승격하지 않습니다.

새 R1/R2는 사용자의 별도 연구 시나리오 지시에 따른 계약입니다. 기존 Experimental FLEX30의 UID/Episode 가입 규칙과 ASSUMED_NORMAL_BATCH 분류만 재사용합니다. 미확인 Batch 분류는 연구 가정으로 표시하고, 원본의 명시적 보호·비배치·이동/접근 금지는 우선합니다. 기존 QoS 추가 지연·Checkpoint 권한은 재사용하지 않습니다. 원본 strict QoS와 기본 배치는 그대로입니다.

R1은 FLEX30 적격 작업만, Source-Compatible 대상과 명시된 shared_sites 교집합에서 도착 후 첫 제어 시각부터 입력에 접근 가능하다고 가정합니다. R1에는 실제 WAN 전송 인증이 없습니다. C0/C1 모두 같은 접근 환경이며 Pre-site 행동만 다릅니다.

R2는 기존 WAN 모델의 Path·슬롯 용량·최대 동시 전송 1개를 그대로 사용합니다. 기존 80 GB/GPU는 실행 상태 전송 모델의 값이므로 입력 Payload 관측값으로 주장하지 않습니다. 입력 크기의 명시적 ASSUMED proxy로만 0.25/1/4배를 비교하고, 병목 Bandwidth 0.25/1배 및 준비 0/900초를 구분합니다. 실제 QoS 지연 권한이 없으면 전송을 시작하지 않고 STAY를 유지합니다.

준비 표는 이미 RC01에서 도착 관측된 217 UID의 계약 전제 민감도 감사입니다. GPU/Rack·후보 AC·Actual 변경·성능 결과는 이 표로 인증하지 않습니다. 실제 C0/C1 실행은 별도 원장에 기록합니다. 기존 전압 위반 Gate는 FAIL로 유지합니다.
'''
    (OUT/'CONTRACT_SCOPE_KO.md').write_text(text,encoding='utf8')
    print(json.dumps(dict(status='CONTRACT_PREPARED',scenarios=len(summary),
        eligible_UIDs=summary[0]['research_contract_eligible_UIDs'],Native_calls=0,AC_calls=0)))


if __name__=='__main__':
    main()
