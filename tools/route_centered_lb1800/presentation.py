"""Final read-only presentation audit after post.py; no solver imports/calls."""
from pathlib import Path
import hashlib,json
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
DOC=ROOT/'docs/v42_b2_route_centered_local_branching1800'
def read(name):return json.loads((DOC/name).read_text(encoding='utf-8'))
def table(headers,rows):
    return '\n'.join(['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(map(str,r))+'|' for r in rows])

def main():
    state=read('FINAL_STATE.json');plan=read('BEST_PLAN_AUDIT.json');grid=read('CRITICAL_GRID_ANALYSIS.json')
    review=read('FINAL_INDEPENDENT_REVIEW.json');assert review['PASS']
    rows=[[u,p['move_count'],f"{p['travel_energy_kWh']:.6f}",f"{p['charging_kWh']:.6f}",f"{p['discharging_kWh']:.6f}",p['SOC_min_kWh'],p['SOC_max_kWh'],p['SOC_initial_kWh'],p['SOC_terminal_kWh']] for u,p in plan['units'].items()]
    samples=[]
    for c in state['calls']:
        samples.extend(c[k] for k in ('build_memory_before','build_memory_after','after_native_memory') if k in c)
        samples.extend(s['sample'] for s in c['resource_samples'])
    mem=read('MEMORY_NUMERIC_AUDIT.json')
    mem.update(peak_scope='Native worker Peak RSS/Private Commit; system totals separately reported',
        maximum_sampled_system_RAM_used_bytes=max(s['system']['RAM_used'] for s in samples),
        maximum_sampled_system_commit_total_bytes=max(s['system']['Commit_total'] for s in samples),
        sampled_system_high_water_not_continuous_peak=True)
    (DOC/'MEMORY_NUMERIC_AUDIT.json').write_text(json.dumps(mem,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    replay=read('ORIGINAL_FULL_REPLAY_CERTIFICATES.json')
    failures=sum(not item['PASS'] for it in state['iterations'] for item in it['validated'])
    passes=sum(item['PASS'] for it in state['iterations'] for item in it['validated'])
    assert failures==1 and passes==27
    report=DOC/'ROUTE_CENTERED_LB1800_FINAL_KO.md';text=report.read_text(encoding='utf-8')
    # Idempotent addition; optimization evidence and the preregistered source seal are unchanged.
    text=text.split('\n## 최종 수치 상세 및 해석')[0]
    text=text.replace('R5는 앞 Local Branching 단계의 정체 때만 Beam을 보조적으로 사용하며 기존56개 route-fixed 평가를 재시작하지 않았다.',
        'R2에서 유의 개선이 나왔으므로 이번 실행의 Beam 호출은 0회다. 사전등록 정책에 따라 예비 6개 corridor를 새 중심의 ADAPTIVE 단계로 실행했다. 기존 56개 route-fixed 평가를 재시작하지 않았다.')
    text=text.replace('사전등록21개모델의정의한비중복후보가소진되어조기종료했으며원본전체경로공간소진을뜻하지않는다. 같은모델을반복해1800초를채우지않았다.',
        '사전등록한 21개 모델의 비중복 후보를 모두 실행해 조기 종료했다. 원본 전체 경로 공간을 소진했다는 뜻은 아니다. 같은 모델을 반복해 1,800초를 채우지 않았다.')
    text+='\n## 최종 수치 상세 및 해석\n\n'+table(['차량','MOVE','이동 kWh','충전 AC kWh','방전 AC kWh','SOC min','SOC max','초기 SOC','종단 SOC'],rows)+'\n\n'
    before=grid['PR219_CENTER']['maximum_thermal']['metadata'];after=grid['BEST_GLOBAL']['maximum_thermal']['metadata']
    oldplan=read('PR219_CENTER_PLAN_AUDIT.json')
    text+=f"총 이동에너지는 {plan['travel_energy_kWh']:.9f} kWh로 PR219의 {oldplan['travel_energy_kWh']:.9f} kWh보다 증가했다. UB 개선을 이동에너지 절감으로 설명할 수 없다. 원본 ETA와 에너지를 사용하면서 4대의 P/Q/Mode/SOC를 함께 재최적화한 결과다. 초기 임계 Line/Phase/Slot은 {before['asset']}/{before['phase']}/{before['slot']}, 최종은 {after['asset']}/{after['phase']}/{after['slot']}다.\n\n"
    text+='Q5의 비용 비교: 기존 PR219는 cold 탐색 1,795.025 Native초를 사용했다. 이번 warm 탐색은 229.208초에서 추가 UB 감소 0.0023459114를 인증했고, 전체 724.821초를 사용했다. 이 실행에서는 더 낮은 UB를 얻었지만 동일 초기조건의 반복 비교가 아니므로 일반적인 알고리즘 효율 우위를 증명하지 않는다.\n\n'
    text+='Q9의 실제 관측: R2_LATE_SMALL은 Root를 해당 호출의 28.370 Native초에 완료했고 NodeCount 1, 종료 restricted MIPGap 0.276431%였다. R3의 24-Site 모델은 TIME_LIMIT, NodeCount 1, restricted MIPGap 46.390541%로 종료했으며 Root 완료 로그가 없다. 나머지 완료 판정과 시간은 LOCAL_BRANCHING_ITERATIONS.json에 보존했다. OPTIMAL은 원본 MIPGap 0.005 정책에 따른 제한 문제의 solver 상태이며 정확한 전역 최적성 인증이 아니다.\n\n'
    text+=f"신규 Raw FULL Replay: PASS {passes}개, FAIL {failures}개. 최초 개선 callback Raw는 STRICT_LITERAL_INTEGER_GATE_FAILED로 거절했다. 이를 반올림하거나 복구하지 않았으며 동일 호출의 FINAL_RAW가 원본 FULL PASS 후 최선 해로 채택됐다. 독립 재검증의 추가 Optimize는 0회다.\n\n"
    text+=f"Native worker 최대 Peak RSS {mem['peak_RSS_bytes']/2**30:.6f} GiB, Private Commit {mem['peak_private_commit_bytes']/2**30:.6f} GiB. 시스템 전체의 샘플링 중 최대 RAM 사용 {mem['maximum_sampled_system_RAM_used_bytes']/2**30:.6f} GiB, Commit 총사용 {mem['maximum_sampled_system_commit_total_bytes']/2**30:.6f} GiB다. 시스템 수치는 샘플 사이의 연속 peak를 보장하지 않는다.\n"
    report.write_text(text,encoding='utf-8')
    figures=[]
    for name in ('BEST_MESS_ROUTES.png','BEST_SOC_P_Q_PLAN.png','UB_GAP_VS_NATIVE.png'):
        path=DOC/name
        with Image.open(path) as img: size=list(img.size);img.verify()
        figures.append(dict(file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),dimensions=size,visually_inspected=True,legible_labels=True))
    required=('SOURCE_CASE_AUTHORITY.json','PR219_WARM_START_CERTIFICATE.json','THREE_MOVE_ABLATION.json','ROUTE_NEIGHBORHOOD_CONTRACT_KO.md','ROUTE_DAG_CLOSURE_AUDIT.json','NATIVE_MODEL_READBACK.json','ORIGINAL_FULL_REPLAY_CERTIFICATES.json','BEST_UB_TRAJECTORY.json','GLOBAL_GAP_TRAJECTORY.json','NATIVE_RUNTIME_LEDGER.json','MEMORY_NUMERIC_AUDIT.json','FINAL_INDEPENDENT_REVIEW.json','BEST_96_SLOT_MESS_PLAN.csv')
    assert all((DOC/f).is_file() for f in required)
    audit=dict(PASS=True,Optimize_calls=0,required_files_present=True,figures=figures,report_sha256=hashlib.sha256(report.read_bytes()).hexdigest())
    (DOC/'FIGURE_AND_DELIVERY_QA.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(PASS=True,Optimize_calls=0,Raw_PASS=passes,Raw_FAIL=failures)))

if __name__=='__main__':main()
