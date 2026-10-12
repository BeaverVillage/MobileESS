"""JSON-only final Korean report. Never imports a solver or scientific model.

Run only after the three algorithms and independent post-Native audits finish.
All input bytes are pinned in a separate report receipt. This file is outside
the executed Native code epochs and does not alter their sealed artifacts.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from time import perf_counter

ROOT=Path(__file__).resolve().parents[2]
DOCS=ROOT/'docs/v42_b2_u4_primal_alns_600x3'
INITIAL=.6760534504652341
LB=.46498486997548166
ANCHOR=datetime.fromisoformat('2026-10-12T03:11:44+00:00')


def require(ok,reason):
    if not ok:raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def f(value,digits=6):
    return '—' if value is None else format(float(value),f'.{digits}f')


def full(value):
    return '—' if value is None else repr(float(value))


def scientific(value):
    return '—' if value is None else format(float(value), '.3e')


def table(headers,rows):
    clean=lambda v:str(v).replace('|','\\|').replace('\n',' ')
    return '\n'.join(['|'+'|'.join(map(clean,headers))+'|','|'+'|'.join('---' for _ in headers)+'|']+
        ['|'+'|'.join(map(clean,row))+'|' for row in rows])


def peaks(call):
    samples=[call.get(k,{}) for k in ('build_memory_before','build_memory_after','after_native_memory')]
    samples += [s.get('sample',{}) for s in call.get('resource_samples',[])]
    return {key:max([0]+[s.get(key,0) for s in samples]) for key in ('Peak_RSS_bytes','Peak_Private_Commit_bytes')}


def replay_for(algo,initial):
    best=Path(algo['best_point']['path']).resolve()
    for iteration in algo.get('iterations',[]):
        for item in iteration.get('validated_candidates',[]):
            if item.get('PASS') and Path(item['raw']['path']).resolve()==best:
                return read(item['replay']['path'])
    require(algo['final_verified_UB']==INITIAL,'MISSING_BEST_FULL_REPLAY')
    return initial


def result_inputs(args):
    paths=dict(comparison=DOCS/'COMPARISON.json',plans=DOCS/'ORIGINAL_SOURCE_OPERATING_PLAN_COMPARISON.json',
        verification=Path(args.verification),resource=Path(args.resource),result_audit=Path(args.result_audit),
        history=DOCS/'HISTORICAL_PRIMAL_ALNS_AUDIT.json',initial=DOCS/'INITIAL_U4_FULL_REPLAY.json',
        diagnostics=DOCS/'U4_K32_SIGNED_DIAGNOSTICS.json',epoch=DOCS/'N1_SOURCE_EPOCH_INCIDENT_INDEPENDENT_REVIEW.json',
        preservation=DOCS/'N1_PRESERVATION_PRE_RESUME_NATIVE0.json',resume=DOCS/'INDEPENDENT_RESUME_AFTER_N1_REVIEW.json',
        adaptive=DOCS/'ADAPTIVE_CURRENT_GRID_NATIVE0_REGRESSION.json',post_epoch=DOCS/'FINAL_POST_EPOCH_INDEPENDENT_CERTIFICATE.json',
        numeric=DOCS/'INDEPENDENT_NATIVE_RUNTIME_MEMORY_NUMERIC_AUDIT.json')
    if args.timing:paths['timing']=Path(args.timing)
    if args.grid:paths['grid']=Path(args.grid)
    paths={name:path.resolve() for name,path in paths.items()}
    data={name:read(path) for name,path in paths.items()}
    comp=data['comparison']
    require(set(comp['methods'])=={'N1','N2','N3'} and comp['total_wall_seconds'] is not None,'ALL_METHODS_COMPLETE_REQUIRED')
    require(comp['initial_UB']==INITIAL and comp['existing_Global_LB']==LB
        and comp['new_Global_LB_optimization_calls']==0 and comp['ACTUAL']=='ACTUAL_NOT_RUN','FINAL_SCIENTIFIC_SCOPE')
    for name in ('plans','verification','resource','result_audit','history','initial','epoch','preservation','resume','adaptive','post_epoch','numeric'):
        require(data[name]['PASS'] is True,'FINAL_AUDIT_NOT_PASS:'+name)
    for method,algo in comp['methods'].items():
        require(algo['initial_UB']==INITIAL and 0<=algo['actual_Native_sum']<=600.,'METHOD_BUDGET_OR_START')
        require(algo['stopped_reason'] is not None and data['plans']['candidates'][method]['PASS'],'METHOD_UNFINISHED_OR_UNVERIFIED')
    require(sum(a['actual_Native_sum'] for a in comp['methods'].values())==comp['total_actual_Native_seconds']
        and comp['total_actual_Native_seconds']<=1800.,'TOTAL_NATIVE_BUDGET')
    return paths,data


def generate(args):
    began=perf_counter();paths,d=result_inputs(args)
    comp,plans,diag=d['comparison'],d['plans']['candidates'],d['diagnostics']
    labels=['Original U4','N1','N2','N3'];best=comp['best_verified_UB'];winner=', '.join(comp['winner'])
    gain=INITIAL-best;gap=100*(best-LB)/best
    paragraphs=[
        '# B2 — U4 Primal ALNS 600초 × 3 최종 비교',
        f'최선 원본 FULL 검증 UB는 **{full(best)}**, 우승 후보는 **{winner}**다. 기존 U4 대비 절대 개선은 **{f(gain,12)}**({f(100*gain/INITIAL,6)}%)이며, 유지한 K48 Global LB **{full(LB)}** 기준 Global Gap은 **{f(gap,8)}%**다. 세 후보는 동일 U4에서 독립 시작했으며 모든 채택값은 원본 FULL Replay PASS를 거쳤다. Actual Fresh AC96는 실행하지 않았으므로 **ACTUAL_NOT_RUN**이다.',
        '## 1. Source와 공정한 시작점',
        '연구 base는 PR215 `6ca7624d7eafd45d5b061ff33e262b0de32bfe8d`이며, 원본 Source18r/PR207은 `497609b46faa14ea7e32a9483a333ab32fd264ef`다. 대상은 IEEE123/B2/2025-05-01이다. PR207의 U4 엔진과 PR207/209/210/211/214/215 및 B1 PR212/213 기존 결과는 보존했다.',
        table(['권위','값'],[
            ['Case SHA','34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'],
            ['원본 FULL matrix SHA','0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec'],
            ['원본 FULL domain SHA','9247e42b8119f60ef149d0963e31dd8a697af5426a5aaeec9450b2a2f246481e'],
            ['동일 초기 point vector SHA','c9d63854a3ec0747a65d2c6724a5d413585f9a4f6754107fc593ba69ea4eda0d'],
            ['동일 초기 point file SHA','2e4407a775ec3b10167baa05fc5aa45c2bcfd0f55ea6c5a0b921311338c1d290'],
            ['초기 FULL 검증 UB',full(INITIAL)],['Native 병렬성','순차 1 Worker × Threads=1'],
            ['각 후보/총 actual Native 상한','600초 / 1,800초']]),
        'N1의 개선점을 N2 또는 N3의 시작점으로 사용하지 않았다. 각 알고리즘은 자신의 새 FULL 검증 개선점만 다음 중심점으로 사용한다. 원본 U4의 FINAL point와 RAW00는 UB가 같지만 일부 Q가 약1e−13 다르고 SHA도 다르다. 이번 동일 초기점은 검증된 FINAL의 `c9d638…`이다.',
        '## 2. 이전 연구와 현재 U4 종료의 의미',
        (DOCS/'HISTORICAL_PRIMAL_ALNS_AUDIT_KO.md').read_text(encoding='utf-8').split('\n',2)[2],
        '## 3. 현재 U4의 실제 물리 운전',
        '권위 FINAL point에서 4대 모두 96개 charge_mode가 0이고 Pch/Pdis 및 선택 이동 Arc가 0이었다. 97개 SOC 경계는 모두760kWh다. 따라서 이 초기점은 Q를 사용하는 정지 운전이다. 이는 과거 PR169에서 추정한 현상이 아니라 현재 원본 좌표 복원값의 관측이다.',
        table(['차량','초기 위치','Mode=1','Pch/Pdis AC(kWh)','|Q| 슬롯 합(kvar)','최대 |Q|(kvar)','SOC min/max(kWh)','이동'],[
            [u,s['initial_site'],len(s['mode_one_slots']),f"{f(s['charge_AC_kWh'],3)}/{f(s['discharge_AC_kWh'],3)}",
             f(s['abs_Q_kvar_slot_sum'],3),f(s['max_abs_Q_kvar'],6),f"{f(s['SOC_min'],3)}/{f(s['SOC_max'],3)}",s['selected_move_count']]
            for u,s in diag['U4_original_physical'].items()]),
        '초기·종단 SOC가 같고 이동·충전이 없는 관측점에서는 원본 에너지 보존과 Pdis≥0가 하루 방전합0을 뜻한다. Mode를 하루 전체에서 선택하는 N1은 이런 초기 패턴에서도 사전 충전과 방전·SOC 복원을 함께 탐색할 수 있다.',
        '## 4. 세 정식화와 원본 FULL 관계',
        table(['후보','Mode','Node/경로','다른 차량','Hamming'],[
            ['N1','4대 ×96=384 전체 개방','모든 원본 Node·continuous route·alias 고정','4대 P/Q/SOC 연속 재최적화','384, 전체 Mode 변경 허용'],
            ['N2','선택 1대96 전체 개방','선택 차량 실제 경로와 관련 시간 Node 개방','다른 3대 이산 및 continuous route/alias 고정; P/Q/SOC 재최적화','48'],
            ['N3','선택 2대192 전체 개방','두 차량 실제 경로와 관련 시간 Node 공동 개방','다른 2대 이산 및 continuous route/alias 고정; P/Q/SOC 재최적화','96']]),
        '모든 후보는 원본 4-MESS·96슬롯 DAG·실제 이동 ETA/에너지·97 SOC·초기/종단 SOC·전후 에너지 보존·충방전 Mode·PCS16·이동 중 P/Q 금지·전체 Thermal/NormalAmps/변압기/전압·SVR11·고정 AIDC Forecast/PCC를 유지한다. 원래 terminal 위치 의미를 바꾸거나 출발점 복귀를 새로 강제하지 않았다. N3는 두 차량의 독립 SOC/PCS를 유지하며 가상 합산 ESS를 만들지 않았다.',
        '원본 FULL은1,130,336행×344,967열이며, Native는 기존 인증된 Dense C3A의715,596행×354,277열·9,322 Binary를 사용한다. 원본과의 변수/행 제거 및 helper lift는 기존 exact Source transport 인증으로 관계를 보존한다. Native에서 추가하는 행은 center를 포함하는 Hamming1행이고, 모든 모델에 원본 RHS/sense/type/objective를 유지한다. 원본 FULL CSR Replay는 Native model과 worker를 종료·해제한 뒤 수행한다.',
        '수학적으로 고정 bound는 원본 box 안에서 현재 FULL 가능점의 좌표에만 설정한다. 모든 free Binary의 중심 Hamming 거리는0이며, `Σ(center=0)x + Σ(center=1)(1−x) ≤ radius`로 중심을 포함한다. unselected 차량 원본 Arc는 고정 retained route/Node 및 정확한 alias만의 함수임을 독립 감사했다. 모든 비route 연속 P/Q/SOC bound는 원본과 같다. 따라서 각 제한영역은 원본 FULL 가능영역의 부분집합이며 중심점은 항상 포함된다. 제한 Solver BestBound는 원본 FULL Global LB가 아니다.',
        '## 5. Signed Grid·시간 결합·유한 적응 정책',
        '원본 U4에서814,560개 Security 행 전체를 검사하고 thermal12/변압기4/NormalAmps2/상한전압4/하한전압4개 최대26 Critical Row를 선택했다. response auxiliary·injection P/Q·고정 보정항·원본 RHS를 정확한 dyadic Fraction으로 제거해 MESS별 Pch/Pdis/Q signed 계수를 복원하고 별도 checker가 원본 NPZ scalar를 직접 대조했다.',
        table(['U4 계통 family','최대/활성 원본 행','Asset/Phase','Slot','원본 정규화 잔차','facet loading'],[
            [family,(r:=s['highest_normalized_values'][0])['name'],
                f"{r['metadata']['asset']}/{r['metadata']['phase']}",r['slot'],scientific(r['normalized_violation']),
                full(r['rho_scaled_loading']) if family=='line_thermal_face' else
                f(1+r['normalized_violation'],9) if family in ('transformer_kVA','NormalAmps') else 'hard 전압 한계 활성']
            for family,s in diag['U4_grid'].items()]),
        '변압기/NormalAmps loading은 원본 정격 대비 facet/선형 current 제약의 정규화 잔차에1을 더한 값이며 Actual AC phasor loading이 아니다. 전압은 원본 행의 활성 잔차로 표시한다. 선택한 행별 exact Pch/Pdis/Q 계수·고정항·helper closure는 SIGNED_SELECTION_CONTEXT.json과 독립 source raw packet에 보존했다.',
        '후보 점수는 현재 차량 signed 기여와 원본 PCS16의 exclusive charging/discharging support 차이를 이용하며, actual ETA와 이동에너지로 할인한다. 직접 rho를 제한하는 thermal row를 먼저 정렬하고, 단위가 다른 hard 전압/current row는 signed guard로 기록한다. 단순 절댓값 민감도나 가중치 최적화는 사용하지 않는다. 점수와 DAG witness는96슬롯 SOC/PCS/Grid 가능성을 증명하지 않으며 그 판단은 전체 원본 MILP와 FULL Replay가 수행한다.',
        '출발 후보는 현재 중심 경로의 실제 점유 DAG vertex와 원본 upper>0인 허용 Arc만 사용한다. 사전 충전 source STAY 슬롯·출발·connect ETA·Critical Slot·후속 SOC 복원 시간을 함께 기록한다. 선택 차량 Mode는96슬롯 전부 개방하므로 초기 충전 이력이 없어도 임의 한두 슬롯에 묶이지 않는다.',
        'N2는 초기 순위 MESS02→MESS04→MESS03→MESS01의4개 primary와 각1개 expanded 후보, N3는6개 실제 차량 쌍의 유한 큐다. N2 요청 cap150초, N3 cap200초를 남은 actual 예산으로 줄인다. expanded는 동일 radius48에서 Node 시간 범위만 최대16슬롯 넓히며 radius sweep을 하지 않는다. 동일 center/free set/route fix/radius signature는 Native 없이 건너뛴다. MESS02의 최초 primary가 이미[0,96]이어서 동일 중심의 expanded는 중복이며, 이를 실패한 Native처럼 실행하지 않는다.',
        '새 FULL 개선점을 채택하면 현재 원본 Security814,560행 전체를 다시 검사해 Critical Row·signed score·Node 시간 창을 갱신한다. 초기26행만 재정렬하는 방식으로 끝내지 않는다. 같은 point SHA는 캐시를 재사용하며, 다른 중심은 별도 exact projection/raw/independent audit packet을 생성한다. Native0의 다른 검증 중심 회귀에서는 기존26행 중25개와 다른 새 행을 선택했고 독립 검사 PASS를 받았다. 그 N1 point는 helper 회귀에만 사용했으며 N2/N3 초기 seed로 사용하지 않았다.',
        '## 6. 모든 Native 호출과 UB 궤적',
    ]
    calls=[];trajectory=[];attempts=[];peak_method={}
    for method in ('N1','N2','N3'):
        algo=comp['methods'][method];ppeak={'Peak_RSS_bytes':0,'Peak_Private_Commit_bytes':0}
        for it in algo['iterations']:
            if 'native_receipt' not in it:
                attempts.append([method,it['index'],it['candidate']['candidate_id'],it.get('state','PRE_NATIVE_FAILURE'),it.get('error','—'),0])
                continue
            call=read(it['native_receipt']['path']);out=Path(it['native_receipt']['path']).parent
            spec=read(out/'NEIGHBORHOOD.json');pk=peaks(call)
            ppeak={k:max(ppeak[k],pk[k]) for k in ppeak}
            build=call.get('model_build_wall_seconds')
            replay_wall=sum(v.get('validation_wall_seconds',0) for v in it.get('validated_candidates',[]))
            calls.append([method,it['index'],it['candidate']['candidate_id'],full(it['center_UB']),
                len(spec['free_binary_columns']),spec['hamming_radius'],f(call['effective_TimeLimit'],3),f(call.get('Native_Runtime'),3),
                f(build,3),f(replay_wall,3),call.get('Status',call.get('status','—')),full(call.get('ObjVal')),
                full(call.get('ObjBound')),f(None if call.get('MIPGap') is None else 100*call['MIPGap'],4),
                f(pk['Peak_RSS_bytes']/2**30,3),f(pk['Peak_Private_Commit_bytes']/2**30,3)])
            trajectory.append([method,it['index'],f(it['Native_used_before'],3),full(it['center_UB']),
                full(it.get('ending_verified_UB',it['center_UB'])),sum(v['PASS'] for v in it.get('validated_candidates',[])),
                sum(not v['PASS'] for v in it.get('validated_candidates',[]))])
        peak_method[method]=ppeak
    paragraphs += [table(['알고리즘','Iter','후보','중심UB','free B','R','TL(s)','Native(s)','build wall(s)','replay wall(s)','Status','Incumbent','제한Bound','LocalGap(%)','Peak RSS(GiB)','Peak Private(GiB)'],calls),
        'Status2는 승인한 파라미터에서의 OPTIMAL, Status9는 TIME_LIMIT이다. 표의 Incumbent·제한 Bound·LocalGap은 현재 제한 문제의 값이다. FULL UB는 독립 Replay에서만 채택한다. 미측정 속성은 “—”로 표시한다. build wall은 모델 로드·구성·readback 단계를 포함하며 전체 wall과 임의로 빼서 순수 조립 성능이라고 해석하지 않는다.',
        table(['알고리즘','Iter','이전 누적Native(s)','중심FULL UB','종료FULL UB','FULL PASS 수','FULL FAIL 수'],trajectory)]
    if attempts:paragraphs += [table(['알고리즘','Iter','후보','Native 없는 상태','보존 사유','Native calls'],attempts)]
    paragraphs += ['## 7. 동일 시작점 최종 비교',]
    rows=[]
    for title in ['초기 검증 UB','최종 검증 UB','절대 UB 개선','상대 UB 개선(%)','첫 개선 Native(s)','최선 확보 Native(s)','개선 횟수','총 Native(s)','전체 알고리즘 Wall(s)','이동 횟수','이동에너지(kWh)','충전 AC(kWh)','방전 AC(kWh)','SOC min/max(kWh)','FULL Replay','Global Gap(%)']:
        values=[]
        for label in labels:
            plan=plans[label];a=comp['methods'].get(label);ub=INITIAL if a is None else a['final_verified_UB']
            values.append({'초기 검증 UB':full(INITIAL),'최종 검증 UB':full(ub),'절대 UB 개선':f(INITIAL-ub,12),
                '상대 UB 개선(%)':f(100*(INITIAL-ub)/INITIAL,6),'첫 개선 Native(s)':'—' if a is None else f(a['first_improvement_Native_seconds'],3),
                '최선 확보 Native(s)':'역사적 기준' if a is None else f(a['best_acquired_Native_seconds'],3),'개선 횟수':'0' if a is None else a['improvement_count'],
                '총 Native(s)':'38.507 (역사적)' if a is None else f(a['actual_Native_sum'],3),
                '전체 알고리즘 Wall(s)':'역사적 값, 동일 예산 Wall 비교 아님' if a is None else f(a['overall_wall_seconds'],3),
                '이동 횟수':plan['move_count'],'이동에너지(kWh)':f(plan['travel_energy_kWh'],6),
                '충전 AC(kWh)':f(plan['charging_kWh'],6),'방전 AC(kWh)':f(plan['discharging_kWh'],6),
                'SOC min/max(kWh)':f"{f(plan['SOC_min_kWh'],6)}/{f(plan['SOC_max_kWh'],6)}",
                'FULL Replay':'PASS' if plan['PASS'] else 'FAIL','Global Gap(%)':f(100*(ub-LB)/ub,8)}[title])
        rows.append([title]+values)
    paragraphs += [table(['항목']+labels,rows),
        '첫/최선 확보 시각은 이후 FULL Replay를 통과한 Raw incumbent가 Native callback에서 발견된 누적 시각이다. FULL 검증은 해당 worker 종료 후 수행하므로 callback 시점에 원본 검증이 끝났다는 뜻은 아니다. Original U4는 역사적 실측38.507초로, 이번 각600초 상한과 같은 실제 사용예산이 아니다.',
        table(['후보','분류','중단 사유','actual Native(s)','요청 TL 합계(s)','잔여 actual 예산(s)'],[
            [m,a['classification'],a['stopped_reason'],f(a['actual_Native_sum'],3),f(a['requested_Native_sum'],3),f(600-a['actual_Native_sum'],3)] for m,a in comp['methods'].items()]),
        '## 8. 차량별 물리 운전과 Rebound',]
    for label in labels:
        paragraphs += [f'### {label}',table(['MESS','Mode1','이동','이동kWh','충전ACkWh','방전ACkWh','|Q| 슬롯 합','최대 |Q|','SOC min/max','종단SOC/위치','에너지 최대 잔차kWh'],[
            [u,s['charge_mode_1_count'],s['move_count'],f(s['travel_energy_kWh'],6),f(s['charging_kWh'],6),f(s['discharging_kWh'],6),
                f(s['Q_absolute_kvar_slot_sum'],3),f(s['Q_max_absolute_kvar'],6),f"{f(s['SOC_min_kWh'],3)}/{f(s['SOC_max_kWh'],3)}",
                f"{f(s['SOC_terminal_kWh'],3)}/{s['original_terminal_location']}",scientific(s['maximum_energy_balance_residual_kWh'])]
            for u,s in plans[label]['units'].items()])]
        moves=[[u,r['original_arc_index'],r['route_id'],r['source'],r['depart'],r['destination'],r['arrive'],r['connect'],f(r['energy_kWh'],6)]
            for u,s in plans[label]['units'].items() for r in s['move_routes']]
        paragraphs += [table(['MESS','원본Arc','Route ID','출발 위치','depart','목표','arrive','connect','이동kWh'],moves) if moves else '선택 이동 Arc는0개다.']
    paragraphs += ['Mode1은 charge_mode Binary가1인 슬롯 수이며 Pch가 양수인 슬롯 수와 같다고 가정하지 않는다. 실제 충전량은 별도 AC kWh 열로 표시했다. 차량별97개 SOC,96슬롯 Mode/P/Q, 접속/이동 상태와 원본 에너지 보존 잔차를 [operating_plans](operating_plans)에 보존했다. 종단 SOC 복원은 원본760kWh 조건을 유지하며 free boundary, SOC 합산 또는 PCS 확대가 없다. Critical 시점 이후 Rebound를 포함한 모든 슬롯의 실제 충방전과 이동에너지는 [Original_U4_SOURCE96_PLAN.csv](operating_plans/Original_U4_SOURCE96_PLAN.csv), [N1_SOURCE96_PLAN.csv](operating_plans/N1_SOURCE96_PLAN.csv), [N2_SOURCE96_PLAN.csv](operating_plans/N2_SOURCE96_PLAN.csv), [N3_SOURCE96_PLAN.csv](operating_plans/N3_SOURCE96_PLAN.csv)에서 확인하며 DAG 증거로 대체하지 않는다.']
    if 'grid' in d:
        grid=d['grid'];require(grid['PASS'],'POST_NATIVE_GRID_POINT_AUDIT')
        paragraphs += [table(['최선 FULL point','원본 최대 thermal facet loading(수치)','Line','Phase','Slot','Facet'],[
            [label,full(g['maximum_thermal_facet_loading_numerical']),g['critical_metadata']['asset'],
             g['critical_metadata']['phase'],g['critical_metadata']['slot'],g['critical_metadata']['facet']]
            for label,g in grid['candidates'].items()]),
            table(['동일 U4 Critical 행','Slot','Original U4','N1','N2','N3'],[
                [r['name'],r['slot']]+[full(r['evaluations'][label]['facet_loading']) for label in labels]
                for r in grid['identical_original_U4_thermal_rows']]),
            '같은 원본 thermal 행의 값은 fixed Forecast/보정항과 실제 Pch/Pdis/Q 기여를 exact Fraction으로 계산했다. 전체 Grid 최대값은 원본814,560행의 수치 스캔이며 새로운 UB/LB 인증을 대신하지 않는다. 차량별 signed 기여·원본 행 SHA와 새 Critical Row 증거는 ORIGINAL_CRITICAL_GRID_POINT_COMPARISON.json에 보존했다.']
    paragraphs += [
        '## 9. K32 진단과 Global LB',
        'K32 정수 incumbent rho0.4812227124583283은 Reduced Grid 진단점으로만 유지한다. 추가 Native0 스캔에서 thermal3,662행·변압기24행·상한전압222행·하한전압140행이1e−8을 초과했고 NormalAmps 위반은0행이었다. FULL 가능해가 아니므로 UB 또는 새로운 Global LB로 승격하지 않는다. 원본 경로/Mode와 차량별 이동에너지는 U4_K32_SIGNED_DIAGNOSTICS.json에 보존했으며 추가 Heavy 복구 Solve를 실행하지 않았다.',
        table(['LB 권위','인증값','이번 처리'],[['K32 / PR211',full(.46497617639758426),'기본 LB 모델 유지, 재계산 없음'],['K48 / PR211',full(LB),'같은 Source/Case 더 강한 인증 LB 보존, Global Gap에 사용'],['새 LB optimize','0','제한 ObjBound를 Global LB에 사용하지 않음']]),
        f'최종 Global Gap=(검증UB−{full(LB)})/검증UB={f(gap,8)}%다. 이번 Global LB는 상승하지 않았으며 unrestricted Full global B&B·DW·Pricing·가중치 최적화를 실행하지 않았다.',
        '## 10. Source 버전 사건과 실패 보존·독립 검증',
        'N1 실행 중 준비 파일이 최초 ready 통지 이후 수정된 사실을 발견했다. signed 후보 순위를 혼합 단위 정렬에서 direct-rho-first로 수정한 사건이다. 원본 Source18r, 이미 구성한 N1 Native 모델, 고정/개방 집합, 목적과 파라미터는 변하지 않았고 N1은 변경된 순위 함수를 호출하지 않았다. 정확한 epoch01 파일 bytes와42개 N1 증거 파일을 보존하고 실제384Mode/전체 route 고정의 수학적 제한이 같음을 독립 감사했다. N1 실제 호출과 FULL PASS를 보존했으며 재실행·예산 초기화가 없었다. N2/N3는 새로운 epoch02 Native0·회귀·Source seal 후 각각 원래 U4에서 시작했다.',
        '최초 PCS16 행 이름 가정 실패, alias 회귀 권위 읽기 실패, 목적값 인수 바인딩 실패, 혼합 단위 순위 심사, 버전 사건과 거부된 준비를 연구 디렉터리에 보존했다. 새 epoch02는 구성 전과 Optimize 직전에 실행 코드/정책 SHA를 검사하며 원본 Source 모듈을 덮어쓰지 않았다.',
        'FULL Replay는 원본 CSR/RHS/sense/bounds, 전체96슬롯 경로·ETA·이동에너지, 초기/종단 위치, SOC, Mode, PCS16, 이동 중 P/Q, 모든 Grid, SVR11/AIDC와 objective identity를 검사한다. 원래 검증기의 수치 기준을 유지한다. C3A affine tolerance는1e−8이며, 원본 FULL의 flow·terminal_location·전압·NormalAmps·thermal·변압기 행은1e−8, 기타 행은1e−6이다. bounds/integrality tolerance는1e−8이고 원본 Binary/정수 패턴과 objective transport는 엄격히 일치한다. Raw clipping·rounding·repair 및 새 정확한 유리수 연속 가능성 인증은 없다. 실패 Raw/Replay를 삭제하거나 Solver ObjVal로 FULL 검증을 대체하지 않았다.',
        '## 11. Native 예산·메모리·전체 Wall',
        '실제 Native 로그 환경은 Gurobi13.0.2(build v13.0.2rc1, win64), Windows11+(26200.2), 13th Gen Intel Core i7-13620H의10 physical/16 logical cores다. 매 호출 최대1 thread를 사용했다. 총 RAM은34,049,220,608bytes(약31.71GiB)이며 CPU 사용률 백분율은 계측하지 않았다. 아래 Peak RSS/Private Commit은 메모리 실측이다.',
        f'총 actual Native는 **{f(comp["total_actual_Native_seconds"],6)}초**, 상한은1,800초다. 각 알고리즘의 실제 Runtime을 초기화 없이 누적하며 조기 OPTIMAL에서 쓰지 않은 요청 시간은 소모로 계산하지 않는다. 따라서 요청 TimeLimit 합계{f(comp["total_requested_Native_seconds"],3)}초는 actual 예산보다 클 수 있지만 다음 호출은 잔여actual−1초 이하로 제한한다. 반환 overhead와 TimeLimit overrun을 실측 그대로 보존하며 Runtime을600으로 잘라내지 않는다.',
        table(['후보','Peak RSS(GiB)','Peak Private Commit(GiB)','build wall 합계(s)','독립FULL replay wall 합계(s)'],[
            [m,f(peak_method[m]['Peak_RSS_bytes']/2**30,3),f(peak_method[m]['Peak_Private_Commit_bytes']/2**30,3),
             f(sum(c.get('model_build_wall_seconds',0) for c in a['calls']),3),
             f(sum(v.get('validation_wall_seconds',0) for it in a['iterations'] for v in it.get('validated_candidates',[])),3)]
            for m,a in comp['methods'].items()]),
        f'비교 제어기의 두 epoch 전체 wall은{f(comp["total_wall_seconds"],3)}초다. 공유 초기 검증/Native0·N1·버전 복구 중단·epoch02·각 호출 준비와 검증을 포함하며 보고/최종 독립 감사 wall은 별도 계측한다. 최소4GiB RAM Reserve·6GiB Windows Commit Reserve 및 구성 후 예상 성장 여유를 검사했고 매 Native 전/후와 callback 자원 심사를 수행했다. Peak Private Commit과 RSS를 구분하며 Gurobi 내부 MaxMemUsed와 동일한 지표라고 해석하지 않는다.',
        f'독립 자원/수치 감사에서 관측한 최소 가용 RAM은{f(d["numeric"]["observed_minimum_RAM_available_bytes"]/2**30,3)}GiB, 최소 가용 Windows Commit은{f(d["numeric"]["observed_minimum_Commit_available_bytes"]/2**30,3)}GiB다. 13개 Native 로그의 수치 경고는 기존 PR207과 동일한 `Model contains large matrix coefficient range`였으며 추가 수치 경고나 Status12 수치 오류는 관측하지 않았다. 승인 정밀도·NumericFocus3·ScaleFlag2·Seed0를 유지했다. 최대 Native TimeLimit 실측 초과는{f(d["numeric"]["maximum_measured_Native_TimeLimit_overrun_seconds"],6)}초이며 이후 호출에서 실제 소모를 차감해 각600초 한도를 지켰다. 메모리/수치 중단은 없고 전체 Raw FULL 채택은 별도 검증이다.',
        '## 12. 채택 판단과 후속 범위',
        f'동일 Source·초기 point와 각600초 상한에서 얻은 최선 FULL 검증 UB로 판단하면 현재 우승 후보는 {winner}이다. 절대 gain≥0.005는 MATERIAL, ≥0.010는 STRONG이며 분류는 FULL 검증값을 사용한다. N1은 전체96Mode 모델의 정상 OPTIMAL로 조기 종료할 수 있고, N2/N3는 유한한 다른 차량/차량 쌍을 탐색하며 첫 작은 모델 종료만으로 전체 알고리즘을 끝내지 않는다.',
        f'실제 호출은 N1 {len(comp["methods"]["N1"]["calls"])}회, N2 {len(comp["methods"]["N2"]["calls"])}회, N3 {len(comp["methods"]["N3"]["calls"])}회다. N2는7개의 서로 다른 모델과 중복1개 skip으로 유한 정책을 소진했고, N3는6개 쌍 중5개 실행 후 actual 예산을 소진했다. N2/N3의 TIME_LIMIT 결과는 더 좋은 경로가 없다는 증명이 아니다. 제한 모델에서 OPTIMAL과 UB0.67605345를 얻은 호출도 그 particular 고정/Hamming 영역의 결과다.',
        'N1은 경로 고정 상태에서 전 차량의 Mode와 연속 에너지를 함께 선택해39.555초에 개선했다. 수천 개 Node/Mode와 실제 경로 선택을 개방한 N2/N3 모델에서는 일부 호출의 제한 Bound가 약0.29에 머물렀고 마지막 N3는0으로 기록되었다. 같은600초 상한에서 incumbent가 개선되지 않은 관측과 함께 제한 탐색의 진행 상태를 보여준다. 정식화 차이를 분리한 인과 실험은 수행하지 않았으므로 그 원인이나 원본 FULL 최적값 및 모든 이동 운전의 한계를 증명하지 않는다.',
        'N1은4대 Mode, N2는1대, N3는2대 Mode를 개방한다. 모든 차량의 연속 P/Q/SOC를 재최적화해도 세 영역은 이동 여부만 다르지 않다. 관측한 우열만으로 이동의 가치가 없거나 시험하지 않은 모든 영역이 개선하지 못한다고 결론내리지 않는다. 후속은 검증된 Mode 활성화 이득을 바탕으로 별도 승인된 실험에서 경로 연동을 평가할 후보이며 이번 Solver 추가 실행이나 U4 생산 엔진 수정은 없다.',
        '이번 결과는 B2 May01 한 날짜의 Planning FULL 연구로, 5월 모든 날짜에 직접 외삽하거나 Production/Actual PASS를 선언하지 않는다. B1 worker·Windows Task·Supervisor·예약을 활성화하지 않았으며 B1 기존 결과와 원본 Source를 보존했다. 공식5월 campaign·B3·IEEE8500·Actual Fresh AC96 실행은0회다. 결과는 후속 방법 선택의 근거이고 기존 campaign HOLD와 예약 비활성 상태를 유지한다.',
        '## 13. 검토 가능한 증거',
        '\n'.join(f'- [{path.name}]({path.relative_to(DOCS).as_posix() if path.is_relative_to(DOCS) else path.as_posix()})：`{sha(path)}`' for path in paths.values()),
    ]
    if 'timing' in d:
        timing=d['timing'];require(timing['PASS'] and timing['actual_Native_sum_seconds']==comp['total_actual_Native_seconds'],'TIMING_SCOPE_BINDING')
        timing_parts=[
            f'관측 worktree anchor부터 UTC {timing["recorded_UTC"]}의 post-run timing receipt까지{f(timing["observed_worktree_to_timing_receipt_seconds"],3)}초였다. 실행 두 epoch의 wall은{f(timing["execution_epochs_wall_seconds"],3)}초, 세 알고리즘 wall 합은{f(timing["algorithm_wall_sum_seconds"],3)}초다. 초기 setup/history의 독점 소요시간과 사람 메시지 수신 시각은 미계측이며0이라고 간주하지 않는다. 마지막 보고 생성까지의 span은 아래 render timestamp에 별도로 추가했다.',
            table(['알고리즘','알고리즘 wall(s)','Native(s)','pre-Optimize build(s)','외부 Optimize return wall(s)','return wall−Runtime(s)','FULL Replay wall(s)','neighborhood prep(s)'],[
                [m]+[f(s[key],3) for key in ('algorithm_wall_seconds','actual_Native_seconds','pre_Optimize_build_wall_seconds',
                    'external_Optimize_return_wall_seconds','external_return_minus_Runtime_seconds','candidate_FULL_replay_wall_seconds',
                    'neighborhood_preparation_wall_seconds')] for m,s in timing['methods'].items()]),
            '각 component는 포함 관계가 있는 실측 scope다. build/replay/return 값을 알고리즘 wall에 다시 더하지 않으며 동시 준비 작업에 임의의 독점 시간을 배분하지 않는다. 보고 생성과 Git 전달은 timing receipt 이후 단계다.'
        ]
        index=next(i for i,s in enumerate(paragraphs) if s=='## 12. 채택 판단과 후속 범위')
        paragraphs[index:index]=timing_parts
    text='\n\n'.join(paragraphs)
    report=DOCS/'B2_U4_PRIMAL_ALNS_600X3_FINAL_KO.md'
    rendered=datetime.now(timezone.utc)
    report_wall=perf_counter()-began
    observed=(rendered-ANCHOR).total_seconds()
    text+=f'\n\n관측 worktree 생성 UTC **2026-10-12T03:11:44Z**부터 보고 생성 UTC **{rendered.isoformat()}**까지 **{f(observed,3)}초**다. 이 span은 setup/history/실패한 준비/N1/pause/회귀/resume/post-Native/보고를 포함하며, worktree 생성 이전 chat 읽기 시간은 미계측이다. 이 생성기의 JSON 읽기·표 생성 wall은{f(report_wall,6)}초다.\n'
    report.write_text(text,encoding='utf-8')
    description=DOCS/'PR_DESCRIPTION_KO.md'
    description.write_text(f'''## 결과

Source18r B2 May01의 동일 FULL 검증 U4 point에서 N1/N2/N3를 독립 비교했다. 최선 FULL 검증 UB는{full(best)}({winner}), 기존0.6760534504652341 대비{f(gain,12)} 개선이다. 기존 K48 Global LB{full(LB)}를 유지해 Global Gap은{f(gap,8)}%다.

N1은 **UB_GAIN_STRONG**으로 UB를{f(100*gain/INITIAL,6)}% 개선했고 실제 Native는39.555초였다. N2/N3는 **NO_VALID_IMPROVEMENT**이며 각각579.006초/599.200초를 사용했다. N2는 서로 다른7개 모델의 유한 정책을 소진했고 N3는6개 쌍 중5개 실행 후 예산을 소진했다.

4대·96슬롯 원본 물리/계통을 보존하는 제한 Primal 모델만 실행했으며, 각600초/총1,800초 actual 누적 예산에서 총{f(comp['total_actual_Native_seconds'],6)}초를 사용했다. Restricted ObjBound는 Global LB로 사용하지 않았다.

## 검증과 범위

- 모든 채택 후보 원본 FULL Replay 및 독립 예산·Source·자원 감사 PASS.
- 원본 U4/PR207과 과거 연구 결과 보존. N1 버전 사건은 정확한 epoch01 증거와 실제 정식화 동등성으로 공개하고 재실행 없이 보존했으며, N2/N3는 새epoch02 검증 후 원래 U4에서 시작했다.
- 실제 중심점마다 원본814,560Security 행 재선정, exact signed helper projection, 실제DAG/ETA 및 유한 후보 정책 적용.
- 1 Worker × Threads1. B1/task/예약 비활성, 5월campaign/B3/IEEE8500 실행0. Actual=ACTUAL_NOT_RUN.

정확한 base는PR215 `6ca7624d7eafd45d5b061ff33e262b0de32bfe8d`. 상세 비교·모든 호출·운전계획·실패/버전 증거는 `docs/v42_b2_u4_primal_alns_600x3/B2_U4_PRIMAL_ALNS_600X3_FINAL_KO.md`에 있다.
''',encoding='utf-8')
    receipt=dict(PASS=True,report=str(report),report_sha256=sha(report),description_sha256=sha(description),
        JSON_only=True,Native_optimize_calls=0,source_model_imports=0,input_sha256={str(path):sha(path) for path in paths.values()},
        report_generation_wall_seconds=report_wall,observed_worktree_to_report_seconds=observed,anchor_UTC=ANCHOR.isoformat(),rendered_UTC=rendered.isoformat())
    (DOCS/'REPORT_RENDER_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--final',action='store_true')
    parser.add_argument('--verification',type=Path,default=DOCS/'FINAL_INDEPENDENT_UB_CERTIFICATE.json')
    parser.add_argument('--resource',type=Path,default=DOCS/'POST_RUN_RESOURCE_SOURCE_AUDIT.json')
    parser.add_argument('--result-audit',type=Path,default=DOCS/'INDEPENDENT_FINAL_RESULT_RESOURCE_EPOCH_AUDIT.json')
    parser.add_argument('--timing',type=Path)
    parser.add_argument('--grid',type=Path)
    args=parser.parse_args();require(args.final,'EXPLICIT_POST_NATIVE_FINAL_RENDER_REQUIRED');generate(args)


if __name__=='__main__':main()
