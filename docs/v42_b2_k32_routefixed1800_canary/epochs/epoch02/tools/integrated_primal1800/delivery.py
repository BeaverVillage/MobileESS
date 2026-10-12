"""Render the final Korean report from audited receipts; no solver imports."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import csv, hashlib, json, subprocess
ROOT=Path(__file__).resolve().parents[2]
DOCS=ROOT/'docs/v42_b2_integrated_primal1800_canary'
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def table(head,rows):
    return '\n'.join(['|'+'|'.join(head)+'|','|'+'|'.join(['---']*len(head))+'|']+['|'+'|'.join(str(x) for x in row)+'|' for row in rows])
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def peak(call,key):
    samples=[call.get(k,{}) for k in ('build_memory_before','build_memory_after','after_native_memory')]
    samples += [x.get('sample',{}) for x in call.get('resource_samples',[])]
    return max([0]+[s.get(key,0) for s in samples])/2**30
def main():
    cert=read(DOCS/'FINAL_INDEPENDENT_CERTIFICATE.json');assert cert['PASS']
    assert read(DOCS/'POSTPROCESS_RECEIPT.json')['PASS']
    state=read(DOCS/'FINAL_STATE.json');plans=read(DOCS/'ORIGINAL_OPERATING_PLAN_COMPARISON.json')['plans']
    grid=read(DOCS/'CRITICAL_GRID_COMPARISON.json')['stages'];calls=state['calls']
    trajectory=read(DOCS/'VERIFIED_UB_TRAJECTORY.json')['points']
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4.2))
    ax.step([p['Native_discovery_seconds'] for p in trajectory],[p['Best_UB'] for p in trajectory],where='post',label='Fresh FULL-verified best UB')
    ax.axhline(cert['Global_LB'],color='green',linestyle='--',label='Existing certified K48 LB')
    ax.axhline(.5461621302242249,color='gray',linestyle=':',label='PR216 N1 reference only')
    ax.set(xlabel='Cumulative Native Optimize seconds',ylabel='rho_max',title='IEEE123 B2 May01 integrated cold-start canary',xlim=(0,state['Native_used']+50))
    ax.legend(fontsize=8);ax.grid(alpha=.25);fig.tight_layout()
    fig.savefig(DOCS/'UB_TRAJECTORY.png',dpi=180);fig.savefig(DOCS/'UB_TRAJECTORY.svg');plt.close(fig)
    stage=[];detail=[];scope=[];physical=[];timing=[]
    validations=[v for it in state['iterations'] for v in it.get('validated',[])]
    for label in ('INITIALIZE','U4','N1','N2+','N3+','FINAL'):
        p=plans[label];cc=[c for c in calls if c['method']==label]
        stage.append([label,len(cc),f"{sum(c['Native_Runtime'] for c in cc):.6f}",f"{p['verified_UB']:.16g}",p['move_count'],f"{p['charging_kWh']:.6f}",f"{p['discharging_kWh']:.6f}"])
    for i,c in enumerate(calls):
        native=Path(c['receipt']['path']).parent
        ident=read(native/'ADAPTER_MODEL_IDENTITY.json');spec=read(native/'NEIGHBORHOOD.json');rs=ident['restrictions']
        windows=spec.get('node_windows',{})
        detail.append([i+1,c['method'],f"{c['effective_TimeLimit']:.3f}",f"{c['Native_Runtime']:.6f}",c['Status'],c.get('ObjVal'),c.get('ObjBound'),c.get('MIPGap'),c.get('NodeCount'),c.get('root_completed_Native_seconds'),f"{c['model_build_wall_seconds']:.3f}",f"{peak(c,'Peak_RSS_bytes'):.3f}",f"{peak(c,'Peak_Private_Commit_bytes'):.3f}"])
        scope.append([i+1,c['method'],','.join(spec.get('selected_units',[])) or 'Source fixed',str(windows).replace('|','/'),ident['model_rows'],ident['model_columns'],ident['total_binary'],rs['free_binary_count'],rs.get('fixed_continuous_route_count',len(spec.get('fixed_route_columns',[]))),rs.get('hamming_columns',0),spec.get('hamming_radius',0)])
    for u,p in plans['FINAL']['units'].items():
        physical.append([u,p['initial_location'],p['original_terminal_location'],p['move_count'],f"{p['travel_energy_kWh']:.6f}",f"{p['charging_kWh']:.6f}",f"{p['discharging_kWh']:.6f}",p['charge_mode_1_count'],f"{p['Q_max_absolute_kvar']:.6f}",f"{p['SOC_min_kWh']:.3f}/{p['SOC_max_kWh']:.3f}",f"{p['SOC_initial_kWh']:.3f}/{p['SOC_terminal_kWh']:.3f}",f"{p['maximum_energy_balance_residual_kWh']:.3g}"])
    for label in ('INITIALIZE','U4','N1','N2+','N3+'):
        pp=[p for p in trajectory if p['method']==label]
        timing.append([label,min(p['Native_discovery_seconds'] for p in pp),next((p['Native_discovery_seconds'] for p in pp if p['moves']), 'NOT_FOUND'),sum(x['validation_wall_seconds'] for it in state['iterations'] if it['method']==label for x in it.get('validated',[]))])
    duplicates=sum(it.get('state')=='DUPLICATE_SKIP' for it in state['iterations'])
    assert duplicates==135 and len(calls)==28
    # Independently bind all replay dispositions and exactly one model signature per Optimize.
    signatures=[]
    for c in calls:
        native=Path(c['receipt']['path']).parent
        spec=read(native/'NEIGHBORHOOD.json')
        if c['method'] in ('N2+','N3+'):signatures.append(spec['mathematical_model_signature'])
    assert len(signatures)==len(set(signatures))
    for item in validations:
        assert sha(item['raw']['path'])==item['raw']['sha256']
        assert sha(item['replay']['path'])==item['replay']['sha256']
    csv_counts={}
    for path in (DOCS/'operating_plans').glob('*_SOURCE96_PLAN.csv'):
        with path.open(encoding='utf-8-sig',newline='') as stream: csv_counts[path.name]=len(list(csv.DictReader(stream)))
    assert len(csv_counts)==6 and set(csv_counts.values())=={384}
    # Directory creation is an observable workspace timestamp, not user-request arrival time.
    ps=subprocess.check_output(['powershell','-NoProfile','-Command',"(Get-Item -LiteralPath '"+str(ROOT)+"').CreationTimeUtc.ToString('o')"],text=True).strip()
    start=datetime.fromisoformat(ps.replace('Z','+00:00'));end=datetime.now(timezone.utc)
    wall=dict(PASS=True,observed_workspace_creation_UTC=ps,report_generation_UTC=end.isoformat(),observed_elapsed_seconds=(end-start).total_seconds(),scope='Observed directory creation to report generation; includes preparation, failures, guard recovery, pause, Native, replay and reporting. Not an exact user-message timestamp.',epoch01_controller_wall_seconds=state['epoch01_controller_wall_seconds'],epoch02_controller_wall_seconds=state['controller_wall_seconds'],actual_Native_seconds=state['Native_used'],FULL_replay_wall_seconds=sum(x['validation_wall_seconds'] for x in validations),model_build_wall_seconds=sum(c['model_build_wall_seconds'] for c in calls),postprocess_wall_seconds=read(DOCS/'POSTPROCESS_RECEIPT.json')['postprocess_wall_seconds'],CSV_row_counts=csv_counts)
    save(DOCS/'WORK_WALL_RECEIPT.json',wall)
    # Static inspection binds the untouched accepted -> freeze -> actual -> fresh contract.
    import ast
    source=ROOT/'v42_may_campaign_native90/operations.py';raw=source.read_text(encoding='utf-8');tree=ast.parse(raw)
    functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    actual=read(DOCS/'ACTUAL_FRESH_INTERFACE_COMPATIBILITY.json')
    actual['inspected_contract_functions']={name:dict(first_line=functions[name].lineno,last_line=functions[name].end_lineno) for name in ('_accepted','freeze_planning','actual','fresh','run')}
    run=ast.get_source_segment(raw,functions['run'])
    assert run.index('_accepted(')<run.index('freeze_planning(')<run.index('actual(')<run.index('fresh(')
    actual['source_sha256_independently_rechecked']=sha(source)
    assert actual['source_sha256_independently_rechecked']==actual['existing_actual_source']['sha256']
    save(DOCS/'ACTUAL_FRESH_INTERFACE_COMPATIBILITY.json',actual)
    save(DOCS/'DELIVERY_INDEPENDENT_CHECK.json',dict(PASS=True,Native_calls=0,all_raw_and_replay_hashes_match=True,route_Optimize_models_all_unique=True,actual_calls=len(calls),duplicate_skips=duplicates,all_CSVs_384_rows=True,source_generation_UTC=end.isoformat()))
    ub=cert['verified_final_UB'];lb=cert['Global_LB'];gain=.6760534504652341-ub
    warnings=Counter(cert['numeric_warnings'])
    body=[
      '# B2 통합 Primal 1,800초 Cold-Start Canary 최종 보고',
      f"판정은 **COLD_START_N1_REPRODUCED**다. 새 Cold Start에서 FULL 검증 UB **{ub:.16g}**을 확보했다. 기존 U4 대비 **{100*gain/.6760534504652341:.8f}%** 개선됐지만 N2+/N3+의 추가 경로 이득은 **0**이다. 기존 인증 K48 LB **{lb:.16g}** 대비 Gap은 **{cert['Global_gap_percent']:.8f}%**이며 **3% 미달**이다. 최종 이동은 **0회**, Actual은 **ACTUAL_NOT_RUN**이다.",
      '## 1. Source와 실행 범위',
      f"Base는 PR216 `{cert['base']}`, Source18r은 `{cert['source_sha']}`다. Case SHA `{cert['case_sha']}`, 원본 FULL matrix SHA `{cert['original_matrix_sha']}`, domain SHA `{cert['original_domain_sha']}`를 대조했다. PR207/209/210/211/214/215/216, B1 PR212/213의 HEAD와 보호 증거는 최종 자원·Source 감사에서 유지됐다. 새 연구 브랜치의 독립 Adapter만 추가했다. B1 재개·예약·전체 5월 캠페인·B3·IEEE8500 실행은 0회다.",
      'Source18r의 stationary_paths/values_for에서 초기 이산 대표값을 생성했다. 첫 Native의 실제 NumStart는 0이며 과거 U4/N1 NPZ를 새 Solver Start로 사용하지 않았다. 첫 초기화의 Binary type은 원본대로 유지했다. 과거 continuous fixed-representative 초기화 5.328초와 계산 구성이 다르며, 이번 실측 80.046초를 그대로 예산에 포함했다. 후속 Start는 이번 Canary에서 새로 FULL Replay PASS를 받은 Raw만 사용했다.',
      '## 2. 수학적 영역과 원본 물리',
      '기존 인증 Dense 모델 715,596행 × 354,277열, Binary 9,322개를 그대로 사용했다. 원본 FULL 1,130,336행 × 344,967열로의 역좌표 검증도 기존 PR216 검증기를 사용했다. 초기화는 추가 Hamming 행이 없고 나머지 호출은 1행을 추가했다. Binary 수는 fixed Binary를 포함한 모델 전체 수다.',
      '4대 MESS·24개 위치·96슬롯·97개 SOC 경계·원본 Route DAG/ETA/이동에너지·PCS16·Mode·초기/종단 SOC·이동 중 P/Q 금지와 원본 전체 Grid를 유지했다. Grid에는 전압·Thermal/NormalAmps·변압기·SVR11·Fixed Capacitor·고정 AIDC/PCC가 포함된다. 원본 행·RHS·목적·nonroute 연속 Bounds의 Readback을 검증했다. 차량을 가상 ESS로 합치지 않았다.',
      'N1은 모든 Route/Node/continuous route와 alias를 고정하고 384개 Mode 및 4대 P/Q/SOC를 개방한다. N2+는 1대 Route, N3+는 2대 Route를 개방하며 두 유형 모두 **384개 Mode 전체를 자유롭게** 둔다. Node Hamming만 각각 radius 48/96을 적용하고 Mode 계수는 0이다. 나머지 차량 Route만 고정한다. N1의 radius 384는 모든 Mode 변경을 허용한다.',
      '각 모델은 원본 Bounds 안에서 좌표를 고정하고 Hamming 제약을 추가한 Primal 제한 문제다. 따라서 역좌표에서 가능영역은 원본 FULL의 부분집합이며 새 FULL 중심점은 항상 포함된다. unselected Arc/alias 의존성은 별도로 검사했다. 원본 종단 의미는 slot96 flow이며 출발 위치 복귀 제약을 추가하지 않았다. 창 밖 Node 고정은 해당 Neighborhood의 tail을 제한한다. Restricted ObjBound는 Global LB로 사용할 수 없다. 자세한 증명은 [영역 계약](PRIMAL_DOMAIN_CONTRACT_KO.md)에 있다.',
      '## 3. 단계별 결과',
      table(['단계','Optimize 수','Native 초','FULL UB','이동','충전 AC kWh','방전 AC kWh'],stage),
      f"U4 대비 절대 UB 개선은 {gain:.12f}다. PR216 참고 N1 UB 0.5461621302242249를 이번 새 N1에서 재현했다. N2+ 14회와 N3+ 11회의 최선 FULL UB는 동일하다. 최종 Best의 파일은 N2+의 같은 목적값 점이지만 UB 개선을 만든 단계는 N1이다.",
      '## 4. 모든 Native 호출과 자원',
      table(['호출','유형','TL 초','Native 초','Status','Incumbent','제한 Bound','제한 Gap','Nodes','Root 완료 초','Build wall 초','Peak RSS GiB','Peak Private GiB'],detail),
      f"실제 Optimize 누적은 **{state['Native_used']:.6f}초 / 1,800초**다. 초기화·U4·N1도 포함하며 이전 PR216 시간은 포함하지 않았다. 1 Worker × Threads=1, GPU 사용 0, 다른 Solver 강제 종료 0이다. 최소 RAM 4GiB/Commit 6GiB와 max(2GiB, 모델 생성 private 증가량의 4배)를 추가 Reserve로 검사했다. Peak RSS={max(peak(c,'Peak_RSS_bytes') for c in calls):.3f}GiB, Peak Private Commit={max(peak(c,'Peak_Private_Commit_bytes') for c in calls):.3f}GiB다. 이는 worker 전체 메모리이고 Gurobi MaxMemUsed와 구분한다.",
      'Status 2는 설정된 MIPGap 0.005에서 OPTIMAL, 9는 TIME_LIMIT이다. Root 완료 None는 완료 기록이 없다는 뜻이다. TIME_LIMIT의 유한 Restricted Bound를 표에 그대로 보존했으며 Global LB로 합산하지 않았다. 반환 초과 시간도 자르지 않고 실측 Runtime으로 계산했다.',
      table(['경고 원문','관측 수'],list(warnings.items())),
      '초기화에는 큰 Kappa 경고도 있었다. 경고와 Raw를 보존했고 Status12는 없었다. 모든 채택점은 기존 원본 FULL 검증기의 수치 기준으로 PASS했다. Grid/flow 1e−8, 기타 행 1e−6, Bounds/정수 1e−8의 기존 기준을 바꾸지 않았다. Raw 반올림·clipping·P/Q repair는 0회이며 연속 가능성을 정확한 유리수 인증으로 주장하지 않는다.',
      '## 5. Neighborhood 및 비반복 감사',
      table(['호출','유형','차량','Node 창 [시작,끝]','행','열','Binary 전체','free Binary','fixed continuous Route','Hamming 열','radius'],scope),
      f"종료 사유는 **{state['stopped_reason']}**다. 비중복 실제 Optimize 28회, Native 없이 중복 건너뛰기 {duplicates}회였다. 예산 잔여 {1800-state['Native_used']:.6f}초를 자동 연장하거나 재시도에 사용하지 않았다. N1은 최적 종료 뒤 재실행하지 않았다.",
      f"목적값이 같은 FINAL_RAW를 중심으로 전달하는 정책 때문에 중심 재선정이 {len(state['center_reselections'])}회 발생했다. P/Q/Mode 퇴화 및 NPZ 파일 SHA 변화로 후보 큐가 재생성됐고 많은 후보가 중복으로 걸러졌다. 실제 모델의 lower/upper Bounds와 Hamming 열·계수·RHS signature를 별도로 비교해 같은 수학적 모델의 Optimize 재실행은 없음을 확인했다. 이 정책은 성능 개선을 만들지 못했고 wall 비용을 늘렸다. 후속 개발에서는 개선 없는 동등 중심 재선정을 줄이는 것이 후보이나 이번 실행 코드는 변경하지 않았다.",
      '새 중심에서 814,560개 원본 Security 행을 다시 스캔하고 response auxiliary·injection·고정항을 포함한 signed Pch/Pdis/Q와 PCS16 support로 후보를 선정했다. 원본 실제 Arc/ETA/에너지만 사용했다. DAG witness는 SOC/PCS/Grid 가능성 증명이 아니다. Route 개방은 시간 창·radius·순위에 제한되므로 이동 0 결과가 이동의 전역적 무용성을 증명하지 않는다.',
      table(['단계','최대 thermal facet','Line','Phase','Slot'],[[k,d['critical']['rho_scaled_loading'],d['critical']['metadata']['asset'],d['critical']['metadata']['phase'],d['critical']['slot']] for k,d in grid.items()]),
      '## 6. 최종 4대 운전과 SOC/Rebound',
      table(['차량','초기 위치','종단 위치','이동','이동 kWh','충전 AC kWh','방전 AC kWh','Mode1 슬롯','최대 |Q| kvar','SOC min/max','초기/종단 SOC','에너지 잔차 kWh'],physical),
      '6개 단계별 [원본 96슬롯 CSV/97SOC JSON](operating_plans)을 제공한다. CSV는 각각 4대×96=384행이다. 이동 Arc/출발/도착/ETA는 JSON에 보존되며 최종 계획에는 이동이 없어 이동에너지가 0이다. Mode1 슬롯과 Pch 양수 슬롯은 같다고 가정하지 않는다. 사전 충전과 혼잡 구간 방전, 이후 충전/SOC 복원은 원본 에너지 보존 및 전체 시간 Grid 안에서 재최적화했다. 같은 UB라도 충방전 총량과 Mode가 다를 수 있으므로 PR216 운전량을 복사하지 않았다.',
      '## 7. 발견 시간과 wall',
      table(['단계','첫 FULL Raw 발견 누적 Native 초','첫 이동 FULL 발견 누적 Native 초','FULL Replay wall 합계 초'],timing),
      f"N1의 첫 개선 시점은 [검증 UB 궤적](VERIFIED_UB_TRAJECTORY.json)에 있다. epoch01 controller wall {state['epoch01_controller_wall_seconds']:.3f}초, epoch02 {state['controller_wall_seconds']:.3f}초다. Build wall 합계 {wall['model_build_wall_seconds']:.3f}초, FULL Replay wall 합계 {wall['FULL_replay_wall_seconds']:.3f}초다. 준비·Native0·오류 복구·대기·보고까지 포함한 관측 작업 wall은 {wall['observed_elapsed_seconds']:.3f}초이며 디렉터리 생성 시각부터 보고 생성까지 측정했다. 사용자 메시지 수신 시각과 동일하다고 주장하지 않는다. [별도 wall 영수증](WORK_WALL_RECEIPT.json)을 참조한다.",
      '## 8. LB와 3% 목표',
      f"같은 Source/Case의 기존 K32 LB 0.46497617639758426과 K48 LB {lb:.16g}를 원본 독립 인증 bytes와 대조했다. 새 LB Optimize·CG·무제한 전체 Global B&B는 0회다. Gap=(UB−LB)/UB={cert['Global_gap_percent']:.8f}%. 3% 달성을 위해 현재 UB에 필요한 LB는 **{cert['LB_needed_for_3pct']:.16g}**, 현재 LB에서 필요한 UB는 **{cert['UB_needed_for_3pct']:.16g}**다. FULL 가능해 확보=True, Global Gap≤3%=False를 별도 기록했다.",
      '## 9. Native0와 Guard 사건 보존',
      '역사적 N1 callback 점의 미세 Bounds 잔차는 strict box 회귀 검사에서 거부됐다. 별도 저장 FINAL_RAW를 코드 회귀에만 사용했고 clipping하지 않았다. U4 legacy PCS selector의 indptr 요구는 Lazy FULL에서 Native0 실패로 발견됐다. 검증된 원본 FULL CSR을 Solver 없는 선정 scope에서만 읽는 Adapter로 해결했다.',
      '새 초기화 후 U4 실행 전 Guard가 controller의 Gurobi DLL을 검출해 실행을 막았다. 기존 selector import가 DLL을 로드한 원인이었으며 해당 U4 Optimize는 0회였다. 27개 기존 epoch 증거와 80.046초 초기화는 보존했다. 선정 subprocess의 종료를 확인한 뒤 Native를 시작하도록 분리했고 Guard 면제·U4 모델 변경·초기화 재실행·예산 reset은 없었다. seal 완료 전의 성급한 재개도 SHA Guard가 막았으며 추가 Optimize는 없었다. 실패 로그/독립 회계/두 실행 epoch seal을 모두 제공한다.',
      '## 10. Actual 및 후속 판단',
      '기존 operations.py의 _accepted→freeze_planning→actual→fresh 경로를 읽기 전용으로 검토했다. B2의 승인 stage에는 Gap≤3%, 동일 고정 AIDC와 해당 계획의 자체 Planning 동결 입력이 필요하다. 이번 계획은 Gap gate를 충족하지 못했고 자체 frozen interface도 없어 동일 계약 실행을 인증하지 못했다. 따라서 Fresh AC96 0회, **ACTUAL_NOT_RUN**이다. Planning FULL PASS를 Actual PASS로 승격하지 않는다. 새로운 AC 위반값을 만들거나 과거 Planning control state로 대체하지 않았다.',
      'Q1: 새 Cold N1 재현 성공. Q2/Q3: 이번 N2+/N3+에서 이동을 동반한 추가 UB 개선은 없었다. Q4: 1,592.383초 내 FULL UB 0.54616213 확보, Global Gap 14.8632%로 목표 미달. Q5: 최종 이동 0, 이동에너지 0이며 경로 탐색의 미관측 이득을 주장하지 않는다. N1은 검증된 Mode 활성화 후보로 잠정 유지한다. 이번 통합 Route 탐색의 확대 채택은 성능 근거가 없어 보류한다. Production 동결 및 May02/03·전체 5월 외삽은 하지 않는다.',
      '## 11. 인증 및 그래프',
      '[독립 인증](FINAL_INDEPENDENT_CERTIFICATE.json) · [자원/보호 Source 최종 감사](FINAL_RESOURCE_SOURCE_AUDIT.json) · [LB 출처](LB_PROVENANCE_REUSE.json) · [Actual 호환성](ACTUAL_FRESH_INTERFACE_COMPATIBILITY.json) · [운전 비교](ORIGINAL_OPERATING_PLAN_COMPARISON.json) · [최종 검산](DELIVERY_INDEPENDENT_CHECK.json)',
      '![FULL 검증 UB](UB_TRAJECTORY.png)', '![실측 Native 시간](NATIVE_RUNTIME.png)'
    ]
    (DOCS/'B2_INTEGRATED_PRIMAL_1800_CANARY_FINAL_KO.md').write_text('\n\n'.join(body)+'\n',encoding='utf-8')
    (DOCS/'PR_DESCRIPTION_KO.md').write_text(f'''Source18r IEEE123 B2 May01에서 저장된 N1을 Solver Start로 사용하지 않고 새 초기화→U4→N1→N2+/N3+ 통합 Canary를 실행했다. 새 N1 FULL UB {ub:.16g}을 재현했고 U4 대비 {100*gain/.6760534504652341:.4f}% 개선했다. 25개 Route/Mode Neighborhood에서 추가 이득은 없었다. 기존 K48 LB 대비 Global Gap {cert['Global_gap_percent']:.8f}%로 3% 목표는 미달이다.

실제 Native {state['Native_used']:.6f}s/1800s, 28회 Optimize 후 비중복 후보 소진으로 종료했다. N2+/N3+는 384 Mode 전체를 개방하고 Node에만 Hamming을 적용했다. 135개 중복은 Native 없이 제외했으며 실제 동일 수학적 모델을 재실행하지 않았다. 동등 목적값 중심 재선정 및 Guard 정지/재개 증거를 공개했다.

원본 모든 물리/Grid·FULL validator·Source18r 및 기존 PR/B1/HOLD를 보존했다. 각 Raw FULL Replay와 독립 SHA/영역/예산 검산 PASS. 새 LB Optimize 0회. Actual 동결 계약 미충족으로 ACTUAL_NOT_RUN.

Base PR216 `{cert['base']}`. 전체 Native 로그, 96슬롯 CSV/97SOC, peak RAM/Commit, 실패 epoch, 그래프와 한국어 최종 보고서는 `docs/v42_b2_integrated_primal1800_canary/`에 있다.
''',encoding='utf-8')
    print(json.dumps(dict(PASS=True,calls=len(calls),duplicates=duplicates,UB=ub,Native=state['Native_used'],peak_RSS_GiB=max(peak(c,'Peak_RSS_bytes') for c in calls),peak_Private_GiB=max(peak(c,'Peak_Private_Commit_bytes') for c in calls))))
if __name__=='__main__':main()
