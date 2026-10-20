"""Assemble the priority source-lineage report and explicit blocked outputs."""
import csv
import gzip
import json
from pathlib import Path
import shutil
import io
import numpy as np
from ac import ROOT,DOC,RUN,save,csvout
from authority import read,record


def main():
    save('EXPERIMENT_IDENTITY.json',dict(experiment_id='V1_add',version='V1_add',independent_experiment=True,
        baseline_project='V44 r043',baseline_commit='affc7226a519adbe072d7debbc3ae25ea71c3487',
        baseline_role='Frozen algorithm and original input authority only',
        branch='codex/v1-add-gso-substation2-preflight',worktree=str(ROOT),runtime=str(RUN),
        production_source_or_workers_modified=False,V44_campaign_outputs_overwritten=False,
        V1_add_official_AC_results_available=False))
    recursive=read(DOC/'SOURCE_LINEAGE_RECURSIVE.json')
    # Keep the complete receipt graph compact and retain every failed edge.
    full=DOC/'SOURCE_LINEAGE_RECURSIVE.csv'
    if not full.exists():full=RUN/'SOURCE_LINEAGE_RECURSIVE.csv'
    with full.open(encoding='utf-8-sig',newline='') as f:edges=list(csv.DictReader(f))
    # Certificates frequently contain both an absent original path and a sealed
    # byte-identical dependency copy. Reconcile by SHA only after that copy has
    # independently passed the full file hash; never infer an alias by filename.
    bysha={e['actual_sha256']:e for e in edges if e['status']=='PASS'}
    relocations=[]
    for e in edges:
        e['resolution_method']='DECLARED_PATH_OR_VERIFIED_PATH_RELOCATION'
        e['declared_path_note']=''
        if e['status']=='PASS':continue
        good=bysha.get(e['expected_sha256'])
        if good and (not e['expected_bytes'] or e['expected_bytes']==good['actual_bytes']):
            e['declared_path_note']=e.get('reason','')
            e.update(resolved_path=good['resolved_path'],actual_sha256=good['actual_sha256'],
                actual_bytes=good['actual_bytes'],status='PASS_CONTENT_MIRROR',reason='',
                resolution_method='INDEPENDENTLY_SHA_VERIFIED_CONTENT_IDENTICAL_COPY')
            relocations.append(dict(original_path=e['original_path'],verified_copy=good['resolved_path'],
                expected_sha256=e['expected_sha256'],verified_sha256=good['actual_sha256']))
    fields=list(edges[0]);buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=fields)
    writer.writeheader();writer.writerows(edges)
    packed=DOC/'SOURCE_LINEAGE_RECURSIVE.csv.gz';packed.write_bytes(gzip.compress(buffer.getvalue().encode('utf-8-sig'),compresslevel=9,mtime=0))
    csvout('SOURCE_LINEAGE_CONTENT_RELOCATIONS.csv',relocations,
        ['original_path','verified_copy','expected_sha256','verified_sha256'])
    unique={}
    for e in edges:
        key=(e['original_path'],e['expected_sha256'])
        if key not in unique:unique[key]=dict(e,reference_count=0)
        unique[key]['reference_count']+=1
    csvout('SOURCE_LINEAGE_UNIQUE_RECEIPTS.csv',unique.values())
    failures=[e for e in unique.values() if not e['status'].startswith('PASS')]
    csvout('SOURCE_LINEAGE_UNVERIFIED_UNIQUE.csv',failures,list(next(iter(unique.values()))))
    target=RUN/'SOURCE_LINEAGE_RECURSIVE.csv'
    assert target.resolve().is_relative_to(RUN.resolve())
    if full.resolve()!=target.resolve():full.replace(target)
    recursive['content_verified_mirror_edges']=len(relocations)
    recursive['unverified_after_content_relocation']=sum(not e['status'].startswith('PASS') for e in edges)
    recursive['unverified_before_content_relocation']=recursive.get('unverified_before_content_relocation',recursive['unverified'])
    recursive['unverified']=recursive['unverified_after_content_relocation']
    recursive['verified']=len(edges)-recursive['unverified']
    recursive['status']='NOT_VERIFIED' if failures else 'PASS_RECEIPT_BYTES_ONLY'
    boundaries=recursive.pop('May01_scope_boundaries',[])
    if boundaries:
        boundary_fields=['path','status','field','day','dates','other_days_excluded','reason']
        csvout('SOURCE_LINEAGE_SCOPE_BOUNDARIES.csv',[
            {k:json.dumps(r[k],ensure_ascii=False) if isinstance(r.get(k),(list,dict)) else r.get(k,'') for k in boundary_fields}
            for r in boundaries],boundary_fields)
    boundary_file=DOC/'SOURCE_LINEAGE_SCOPE_BOUNDARIES.csv'
    scope_count=len(boundaries) if boundaries else recursive.get('scope_boundary_count',0)
    recursive['scope_boundary_count']=scope_count
    recursive['scope_boundary_file']=str(boundary_file)
    save('SOURCE_LINEAGE_SUMMARY.json',dict(status=recursive['status'],edges=recursive['edges'],
        unique_receipts=len(unique),unique_unverified=len(failures),JSON_documents=recursive['JSON_documents_processed'],
        complete_edge_graph=record(packed),unverified_list=record(DOC/'SOURCE_LINEAGE_UNVERIFIED_UNIQUE.csv'),
        content_verified_mirror_edges=len(relocations),mirror_resolution=record(DOC/'SOURCE_LINEAGE_CONTENT_RELOCATIONS.csv'),
        experiment_id='V1_add',scope_boundary_count=scope_count,scope_boundary_file=record(boundary_file) if boundary_file.exists() else None,
        primary_May01_receipts='36/36 PASS',
        explicit_receipt_audit_finished=True,full_ancestral_input_certification=False))
    # The long repeated failure list remains in compressed CSV, not duplicate JSON.
    recursive['unverified_receipts_file']='SOURCE_LINEAGE_UNVERIFIED_UNIQUE.csv'
    recursive.pop('unverified_receipts',None);save('SOURCE_LINEAGE_RECURSIVE.json',recursive)
    inv=read(DOC/'NETWORK_INVENTORY.json')
    inventory=[]
    for group,lo,hi in [('LV',0,1),('MV',1,35),('HV',35,1000)]:
        bs=[b for b in inv['bus_rows'] if lo<=b['kv_ll']<hi]
        inventory.append(dict(category=group,buses=len(bs),electrical_nodes=sum(len(b['nodes']) for b in bs),
            lines='',transformers='',loads='',regcontrols='',capacitors='',PV='',meaning='Static equipment inventory; not operating power'))
    inventory.append(dict(category='TOTAL',buses=inv['buses'],electrical_nodes=inv['nodes'],lines=inv['lines'],
        transformers=inv['transformers'],loads=inv['loads'],regcontrols=inv['regcontrols'],capacitors=inv['capacitors'],PV=inv['pv'],
        meaning='Original disabled lines retained; 9 disabled / 5640 enabled'))
    csvout('GREENSBORO_NETWORK_INVENTORY.csv',inventory)
    downloads=read(RUN/'DOWNLOAD_MANIFEST.json')
    for r in downloads['files']:
        assert record(r['path'])['sha256']==r['sha256']
    save('SMARTDS_SOURCE_AND_SUBSTATION_ID.json',dict(version='v1.0',scenario='base_peak',
        substation='uhs2_1247',feeders=['uhs2_1247--udt10746','uhs2_1247--udt12473','uhs2_1247--udt9312'],
        official_catalog='https://data.openei.org/submissions/2981',
        equipment_only=True,SMARTDS_operating_timeseries_used=False,source_files=downloads['files'],
        nominal_loads_used_only_as_fixed_spatial_weights=True,nodes=inv['nodes'],buses=inv['buses']))
    reason='INPUT_MAPPING_NOT_VERIFIED: PV/PCC mapping and full lineage gate not certified'
    csvout('ORIGINAL_AC_96_RESULTS.csv',[dict(slot=t,status='NOT_EXECUTED',rho_max='',voltage_min='',voltage_max='',
        transformer_max='',converged='',reason=reason) for t in range(96)])
    csvout('B0_PHYSICAL_SCREENING.csv',[dict(slot=t,status='B0_NOT_BUILT',PCC_mapping='',rho_max='',
        target_60_85='',voltage_pass='',line_pass='',transformer_pass='',reason=reason) for t in range(96)])
    csvout('GLOBAL_LINE_SENSITIVITY.csv',[dict(status='NOT_VERIFIED',slot='',PCC='',line='',phase='',
        d_rho_dP_per_kw='',d_rho_dQ_per_kvar='',no_op_noise='',reason=reason)])
    native=read('D:/MobileESS_V42/runtime/v42_may_campaign/candidate_20261009_implementation01/inputs/B1/2025-05-01/NATIVE_INPUT.json')
    csvout('MESS8_PQ_CONTROLLABILITY.csv',[dict(unit=f'MESS{k:02d}',initial_STA=native['initial_MESS_sites'].get(f'MESS{k:02d}',''),
        P_limit_kw=300,Q_limit_kvar=250,PCS_kva=400,SOC_min_kwh=440,SOC_max_kwh=1080,SOC_initial_kwh=760,SOC_terminal_kwh=760,
        eta_charge=.95,eta_discharge=.95,polygon_faces=16,
        feasible_daily_control='FEASIBLE_MESS_CONTROL_NOT_VERIFIED',delta_global_pp='',reason=reason) for k in range(1,9)])
    save('JOINT_CONTROLLABILITY_REPORT.json',dict(experiment_id='V1_add',status='NOT_VERIFIED',B0_status='B0_NOT_BUILT',
        AIDC_only=dict(global_rho=None,delta_pp=None,status='NOT_VERIFIED'),
        MESS_only=dict(global_rho=None,delta_pp=None,status='FEASIBLE_MESS_CONTROL_NOT_VERIFIED'),
        joint=dict(global_rho=None,delta_pp=None,status='NOT_VERIFIED'),
        independent_sensitivities_summed=False,optimization_runs=0,reason=reason))
    gates=[('G1','PASS','Official uhs2_1247: 6572 buses / 12749 electrical nodes / three feeders'),
        ('G2','PASS','Original AIDC12/STA12 identities and traffic input receipts retained; no final electrical assignment'),
        ('G3','NOT_VERIFIED','63 three-phase LV transformer candidates; no complete PCC acceptance or spatial witness'),
        ('G4','PASS','780 GPU, 2498-job FCFS, site power scale 1.0 and source receipts preserved'),
        ('G5','NOT_VERIFIED','B0_NOT_BUILT; no admissible B0 maximum'),
        ('G6','NOT_VERIFIED','Input mapping gate blocks operating AC'),
        ('G7','NOT_VERIFIED','Permission flags are not a feasible job-control pilot'),
        ('G8','NOT_VERIFIED','Eight ports, new four initial sites, route/SOC pilot not verified'),
        ('G9','NOT_VERIFIED','No admitted B0/control pilot; no claimed improvement'),
        ('G10','NOT_VERIFIED','Static four-unit guards and 7/43-versus-1 physical control mismatch; no eight-unit model build')]
    save('FINAL_GO_NO_GO.json',dict(experiment_id='V1_add',independent_from_V44=True,decision='INSUFFICIENT_EVIDENCE',input_status='INPUT_MAPPING_NOT_VERIFIED',
        gates={k:dict(status=s,reason=r) for k,s,r in gates},B0_status='B0_NOT_BUILT',
        control_contract=dict(IEEE123_Planning_RegControl=7,IEEE123_Actual_RegControl=43,
            Greensboro_original_RegControl=1,identical_hardware_contract='FAIL_WITH_UNMODIFIED_ORIGINAL_EQUIPMENT'),
        new_AC_or_optimizer_authorized_by_this_report=False,production_modified=False))
    primary=[]
    with (DOC/'PRIMARY_MAY01_SOURCE_AUTHORITY.csv').open(encoding='utf-8-sig') as f:primary=list(csv.DictReader(f))
    source_rows='\n'.join(f"| {r['role']} | `{r['resolved_path'] or r['source_path']}` | `{r['expected_sha256']}` | {r['status']} |" for r in primary)
    lineage=read(DOC/'SOURCE_LINEAGE_SUMMARY.json')
    report=f'''# V1_add — 독립 확장실험의 May01 Source Lineage 우선 감사

실험명/버전은 **V1_add**다. V44 r043은 동결 알고리즘·입력의 기준 출처다. V1_add는 별도 브랜치·worktree·runtime·산출물·실행 기록을 갖는 독립 실험이며, V44 Production 캠페인/버전/결과를 수정하거나 V1_add 결과와 합치지 않는다. 경로에 남아 있는 r043 표기는 출처 기준을 나타낸다.

현재 판정은 **INPUT_MAPPING_NOT_VERIFIED / B0_NOT_BUILT / INSUFFICIENT_EVIDENCE**다. Greensboro 최대 선로부하율과 민감도의 공식 결과는 없다. 최신 지시 이후 운영 AC와 최적화는 실행하지 않았다. 앞서 잘못된 전력 크기와 PV=0으로 계산한 AC 및 PCC 여유 결과는 별도 runtime의 `quarantine_before_input_correction`에 격리했고 판정에서 제외했다.

기준 Git 커밋은 `affc7226a519adbe072d7debbc3ae25ea71c3487`이다. 독립 worktree와 runtime만 사용했고 Production Worker·Source·원장·Native 예산·PID를 수정하지 않았다.

## 1. 실제 원본과 재귀 확인

May01 직접 입력/모델/교통 관련 **36개 receipt는 36개 모두 SHA 일치**다. 다른 날짜·연도를 May01 운영 입력으로 대체하지 않았다. 24 Prefix를 위한 원본 4월 말 raw 관측은 기존 r043 observer가 사용한 범위로만 유지했다.

재귀 명시적 receipt 감사는 {lineage['JSON_documents']}개 JSON, {lineage['edges']}개 참조 edge를 처리했다. 중복 제거한 receipt는 {lineage['unique_receipts']}개이며 {lineage['unique_unverified']}개가 미확인이다. 따라서 **전체 ancestral lineage PASS를 선언하지 않는다**. 누락/다른 SHA 가능성이 있는 경로는 `SOURCE_LINEAGE_UNVERIFIED_UNIQUE.csv`, 모든 edge는 `SOURCE_LINEAGE_RECURSIVE.csv.gz`에 남겼다. 다른 날짜의 과거 실험 문서는 참조 파일의 SHA 확인과 May01 운영 입력 채택을 구분했다. bare path/semantic digest는 파일 SHA로 인증하지 않았다.

| 역할 | 실제 확인 경로 | 원본 SHA-256 | 상태 |
|---|---|---|---|
{source_rows}

## 2. 최종 IEEE123 입력과 계수 적용

`IEEE123_FROZEN_ELECTRICAL_INPUTS.npz`에 Planning 96슬롯과 Actual 120슬롯(24 Prefix+96 평가)을 분리했다. 배경부하 P/Q, PV P/Q, AIDC12 P/Q, 버스·상/사이트 축, 전체 순부하 P/Q가 포함된다. `ELECTRICAL_ARRAY_SHA256.json`에 dtype/shape/단위/.npy 직렬화 SHA를, `IEEE123_FINAL_POWER_TOTALS_216.csv`에 모든 총량을 기록했다. 사이트별 IT·Cooling/aux·P/Q는 `IEEE123_AIDC12_POWER_2592.csv`에 있다. 순부하는 gross background + AIDC − PV이며 MESS가 없는 B0 입력 정의다. 계통 손실을 포함한 변전소 유입 전력과 구분한다.

| 96 평가 슬롯 범위 | Planning | Actual |
|---|---:|---:|
| 배경 P kW | 1772.844526~2705.984027 | 1765.562270~2712.793328 |
| 배경 Q kvar | 683.742979~1570.647080 | 686.007971~1624.377654 |
| PV P 최대 kW | 320.738595 | 327.947863 |
| PV Q kvar | 0 | 0 |
| AIDC 총 P kW | 228.141568~568.257478 | 461.451308~568.257491 |
| 전체 순 P kW | 1757.845077~3135.580088 | 2027.722516~3271.676384 |

`POWER_AUTHORITY.json`의 `alpha_BG=1.15`는 May01 원본에도 있다. `V41_ELECTRICAL_CERTIFICATE.json`의 날짜 결합 → `v41r4_electrical.py` → 최종 `V41R3_BACKGROUND_SCALE_AUTHORITY.json` → 저장된 ORIGINAL_DAYAHEAD_BACKGROUND 계보를 확인했다. export된 최종 P/Q에는 원래 적용이 이미 반영돼 있다. Greensboro에는 export된 최종 총량을 직접 분배하므로 alpha_BG/alpha_grid를 다시 곱하지 않는다. April runner를 호출하거나 새 계수 선택의 근거로 사용하지 않았다. 코드의 transitive import가 과거 runner로 이어진다는 사실은 별도로 기록했다.

V16.2의 alpha_grid, 3490/7100.2615 수요 정규화, 698.000002861023/4021.226 PV 정규화, 기존 residual/Q lookup, P/Q에만 적용되는 원래 1.15, GPU IT idle/swing, C1의 NLR equivalent scale와 normalization, PF0.95는 `NORMALIZATION_AND_APPLICATION_ORDER.json`에 모두 기록했다. C1 normalization은 원래 함수 내부에서 적용되며 사후 추가 배율을 사용하지 않았다.

Actual은 raw as-of 관측을 사용하는 r043 실행 경로를 재현했다. 새 AC를 풀지 않고 load/generator setpoint를 읽어 **120/120 슬롯에서 저장된 Actual setpoint SHA와 정확히 일치**했다. `DERIVED_AEMO_ACTUAL`과 `DERIVED_NOAA_ACTUAL`도 SHA를 확인하고 보존했지만, interval-end/보간 derivative를 원래 online as-of 값 대신 넣지 않았다. 차이는 `ACTUAL_RAW_ASOF_VS_DERIVED_AUDIT.csv`에 보인다. Planning은 D-1 forecast와 GFS를 사용하고 Actual 정보는 Planning으로 넘기지 않았다. 기존 Forecast ingestion의 인과성 미인증 한계는 유지한다. 별도 Planning 24-prefix 배열을 새로 만들지 않았다.

2,498개 Job의 독립 FCFS 재생은 capacity violation 0, dropped 0, Native 호출 0이다. Actual GPU/IT/P/Q는 기존 비전기적 B0 trace와 최대 차이 0이다. 이는 **Greensboro AC 인증이 아니다**. 초기 Running 위치에 남아 있는 원래 연구 가정도 유지한다.

## 3. Greensboro 연결 규칙과 보존량

SMART-DS에서는 v1.0 base_peak의 토폴로지·임피던스·정격·부하 접속점/상·원본 제어설비만 확보했다. 2016~2018 운영 시계열을 사용하지 않는다. 원본은 **6572 buses / 12749 electrical nodes / 5649 lines / 931 transformers / RegControl 1 / capacitor 5 / PVSystems 0**이다. 피더는 `uhs2_1247--udt10746`, `uhs2_1247--udt12473`, `uhs2_1247--udt9312`다. 공식 파일 URL/바이트/SHA는 `SMARTDS_SOURCE_AND_SUBSTATION_ID.json`에 있다.

P/Q 공간 분배의 후보 가정은 `wP_i=P_nom_i/sum(P_nom)`, `wQ_i=Q_nom_i/sum(Q_nom)`이다. 원본 부하의 버스·상·전압 연결을 유지하고 시간에 불변인 가중치만 사용한다. 원본 nominal load를 운영 부하로 더하지 않는다. 매 슬롯 수신량을 기존 load setpoint의 대체값으로 정의하므로 이중 투입을 하지 않는다. float64 fsum 총량의 잔여 반올림은 최대 가중치 수신점에서 보정하며 오차 기준/물리 허용치를 변경하지 않는다.

**216행 모두 P/Q 총량 최대 절대 오차=0, 상대 오차=0**이다(Planning96+Actual120). 두 운영 역할 각각의 96 평가 슬롯 비교는 `INPUT_IDENTITY_METRICS_96.csv`에 있다. 새 공간 배열의 SHA는 원본과 다르며 가중치·배열별 SHA를 별도로 봉인했다. AIDC12 P/Q는 사이트 축 identity binding으로 최대 오차 0이다. Job UID/GPU/QoS/Deadline과 route ETA/energy는 원본 native/windows/request/Route Table 전체 파일의 SHA를 유지하며 다시 작성하지 않는다. 이는 물리 PCC 수용성을 인증하지 않는다.

**PV P/Q 및 전체 순부하 동일성은 NOT_VERIFIED**다. 원본 PV는 상별 2.4kV `Generator Model=1`, Q=0의 기존 전력 모델이다. Greensboro bus의 kV_LN은 약 0.120089/0.277128/7.199558/39.837169이며 직접 2.4kV 접속 대응을 확인하지 못했다. 원본에 PVSystem이 없다는 이유로 기존 PV를 0으로 만들거나 net load에 숨기지 않았다. 적격 PCC/위상·전압 변환·변압기/선로 정격 및 모델 계약의 대응이 필요하다. 승인되지 않은 재배치를 인증된 입력으로 사용하지 않는다.

3상 LV 변압기 후보는 63개, nameplate 400kVA 이상은 2개다. 이는 후보 목록이며 실제 site headroom, 접속 포트, AIDC 공간 순서, 8대 동시 접속 PASS가 아니다. 기준/분산/혼잡 배치 모두 최종 선정하지 않았다. 원본 AIDC12+STA12의 SUMO 좌표·ID·경로는 유지했다.

## 4. 실행 Gate와 남은 검증

`INPUT_MAPPING_GATE.json`과 `INPUT_IDENTITY_CERTIFICATION.json`은 AC_ALLOWED=false다. 미확인 항목은 재귀 ancestral receipt, PV의 전기적 이전, AIDC12+STA12 전체 PCC와 AIDC 공간 순서다. B0, 전체 물리 제약, Top-K/무교란/양방향 민감도, 실행 가능한 Job/MESS/joint pilot은 NOT_VERIFIED다. `B0_NOT_BUILT`를 배경망 PASS 또는 NO_QUALIFIED_B0_SCENARIO로 바꾸지 않았다. 차단된 결과 CSV에는 수치 대신 빈 값과 사유가 있다.

r043 Planning의 RegControl 7개와 Actual의 SVR12 포함 43개는 Greensboro 원본 1개와 일치하지 않는다. 동일 물리 계약을 원본 설비 그대로 구현했다고 주장할 수 없다. 복사·설비 개조를 하지 않았다. 차량 4대의 상위 입출력/guard 하드코딩과 8대의 추정 차원은 `V44_R043_8MESS_PORT_AUDIT.md`에 있으며 실제 8대 모델 생성/성능 측정과 구분했다.

현재 최종 질문의 답은 **동일 입력에서 전역 최대 선로부하율을 실제 제어할 수 있는지 아직 인증하지 못했다**이다. 핵심 직접 원본과 실제 적용값은 확보됐지만, 전체 계보·PV/PCC 입력 Gate가 닫혀 있다. A1/M1/A2/M2, K48, Beam, Joint MILP와 캠페인은 실행하지 않았다.

`WORKLOAD_ROUTE_IDENTITY.json`은 UID/GPU/원래 window·QoS/Deadline provider 입력 및 원본 route travel/connection-ready/energy 배열의 논리 SHA를 별도로 기록한다. 입력은 동일 파일 참조로 유지하며 없는 hard deadline을 생성하지 않는다.

재현 순서: 독립 `v1_add_preflight`의 `fetch.py`(공식 정적 설비만) → `ac.py`(설비 inventory만) → `replay_jobs.py`(독립 FCFS) → `authority.py`(원본 적용값 readback) → `mapping.py`(P/Q 후보 산술) → `export_arrays.py` → `source_stage.py` → `contracts.py` → `lineage.py` → `figures.py` → `finalize.py`. `measure()`는 현재 Gate에서 예외를 발생시킨다. `lineage.py`는 격리 runtime의 ijson 3.4.0으로 큰 JSON을 streaming하고 Production lock/ledger를 사용하지 않는다. 원본 전기 입력과 정적 계통도 그림만 제공하며, 생성되지 않은 AC/민감도/pilot 그림을 실측 결과로 표현하지 않았다.
'''
    (DOC/'FINAL_PREFLIGHT_REVIEW_KO.md').write_text(report,encoding='utf8')
    (DOC/'SOURCE_LINEAGE_REVIEW_KO.md').write_text(report,encoding='utf8')
    save('SOURCE_AND_INPUT_SHA256.json',dict(experiment_id='V1_add',pinned_commit='affc7226a519adbe072d7debbc3ae25ea71c3487',
        original_static_grid=downloads['files'],primary_May01_sources=primary,
        original_electrical_arrays=read(DOC/'ELECTRICAL_ARRAY_SHA256.json'),
        candidate_arrays=read(DOC/'CANDIDATE_ARRAY_SHA256.json'),
        workload_route_identity=read(DOC/'WORKLOAD_ROUTE_IDENTITY.json'),
        input_comparison_digest_file=record(DOC/'INPUT_COMPARISON_ARRAY_DIGESTS.json'),
        recursive_lineage=read(DOC/'SOURCE_LINEAGE_SUMMARY.json'),
        new_study_code=[record(p) for p in sorted(Path(__file__).parent.glob('*.py'))],
        invalidated_previous_results=dict(path=str(RUN/'quarantine_before_input_correction'),
            status='INVALIDATED_NOT_SCIENTIFIC_RESULTS',manifest=record(RUN/'quarantine_before_input_correction/INVALID.json'))))
    print('assembled; primary36 PASS; recursive unverified unique',len(failures),'of',len(unique))


if __name__=='__main__':main()
