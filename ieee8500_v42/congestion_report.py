"""All20 predeclared targets: paths, bounded predictions and finite probes."""
import pandas as pd
from .common import REPORT,read,table,write,receipt


def run():
    folder=REPORT/'joint_selection_v3/selected_response'
    selection=REPORT/'joint_selection_v3/score_selection'
    sensitivity=pd.read_csv(selection/'SELECTED_PCC_PQ_SENSITIVITY.csv')
    potential=pd.read_csv(selection/'SELECTED_CONTROL_POTENTIAL.csv')
    actual=pd.read_csv(folder/'INSTANTANEOUS_COMPLEMENTARITY_NOT_POLICY.csv')
    single=pd.read_csv(folder/'SELECTED_STA_TARGET_LINE_EFFECT.csv')
    targets=read(REPORT/'joint_selection_v3/selection_scores/PREREGISTRATION.json')['targets']
    rows=[]
    for number,line in enumerate(targets,1):
        ss=sensitivity[sensitivity.line.eq(line)]
        pp=potential[potential.line.eq(line)]
        aa=actual[actual.line.eq(line)]
        p=pp[pp.role.eq('AIDC')].groupby('slot').predicted_reference_binding_delta_rho_pu.sum()
        q=pp[pp.role.eq('STA')].groupby('slot').predicted_reference_binding_delta_rho_pu.min()
        row=dict(target_index=number,line=line,NormalAmps=float(ss.original_line_NormalAmps.iloc[0]),
            original_reference_baseline_rho_max=float(ss.baseline_reference_rho.max()),
            selected_AIDC_downstream_path_count=int(ss[ss.role.eq('AIDC')&ss.source_path_contains_line].location_id.nunique()),
            selected_STA_downstream_path_count=int(ss[ss.role.eq('STA')&ss.source_path_contains_line].location_id.nunique()),
            AIDC_upperbound_linear_sum_best_relief_rho=float((-p).max()),
            single_STA_selected_action_linear_best_relief_rho=float((-q).max()),
            selected_STA_single_finite_actual_best_relief_rho=float(-single[single.line.eq(line)].actual_change_rho.min()),
            global_QoS_SOC_dispatch_certified=False,Bpolicy_performance_result=False)
        for name in ('AIDC_RELAXATION','SIX_INITIAL_STA','COMBINED_RELAXATION'):
            group=aa[aa.diagnostic_case.eq(name)]
            row[name+'_actual_best_target_relief_rho']=float(-group.actual_change_rho.min())
            row[name+'_actual_worst_target_relief_rho']=float(-group.actual_change_rho.max())
        rows.append(row)
    table(folder/'ALL20_TARGET_CONTROLLABILITY.csv',rows)
    group=actual[['slot','diagnostic_case','baseline_global_rho','rho_max','Vmin','Vmax','binding_line']].drop_duplicates()
    table(folder/'INSTANTANEOUS_GLOBAL_COUNTERFACTUALS.csv',group.to_dict('records'))
    text=['# 20개 원 혼잡 선로의 제어 가능성','',
        '이 표는 사전에 정한20개 선로 모두를 포함한다. original-v3 B0 개발참조점의 중앙 AC 미분과 선정된 bounded액션을 사용했다. '
        'AIDC 합은 known-only 감소 **상한의 선형 합**이며 실제 QoS/WAN 스케줄이 아니다. STA 수치는 선정액션 중 **단일 포트 최대**다. '
        '경로 밖 PCC도 전압/상호결합을 통해 응답할 수 있지만 직접 하류 제어와 구분한다. 실제선정배치의 finite값은 별도 CSV에 있다.','',
        '| 사전선로 | AIDC 하류수 | STA 하류수 | AIDC합 최대 선형relief(ρ) | 단일STA 최대 선형relief(ρ) |',
        '|---|---:|---:|---:|---:|']
    for r in rows:text.append(f"| {r['line']} | {r['selected_AIDC_downstream_path_count']} | {r['selected_STA_downstream_path_count']} | {r['AIDC_upperbound_linear_sum_best_relief_rho']:.7f} | {r['single_STA_selected_action_linear_best_relief_rho']:.7f} |")
    text+=['',
        '상위7개 Triplex 혼잡선로의 하류에 선택된 AIDC/STA는 없다. 이들 선로에는 MV 경로의 전압 변화 등 간접 효과만 있으며, '
        '선택된 고객Triplex에서 확인한 큰 국부 전류 감소를 전체 최대부하율 감소로 확대해석할 수 없다. '
        '여러 상위MV선로에는 AIDC와LV STA가 공통하류 경로를 가져 제어기여가 겹친다. '
        '이는 형태/Sourceguard/작은LV포트/실제Job규모의 제약 아래 얻은 local heuristic 후보의 한계다.','',
        '다음은 actual selected B0에서 같은 settled탭/커패시터를 고정한 순간 전기적 반사실이다. '
        '6대 MESS는 **원6개 초기STA에 계속머무르는 가정**으로만 사용했다. AIDC는 known-job footprint상한을 동시에 감소시켰다. '
        '차량route/SOC 및 Job이동·QoS/WAN의 결합 적격성을 인증하지 않았고, 모든행은 원 전역 전압이 여전히 실패한다. '
        'baseline과6대STA 또는AIDC합의전기적기여는 상호보완될 수 있지만 아래 수치는 B1/B2/B3 정책 결과가 아니다.','',
        '| slot | 반사실 | B0 전체ρ | 반사실 전체ρ | Vmax |', '|---:|---|---:|---:|---:|']
    for r in group.to_dict('records'):
        text.append(f"| {r['slot']} | {r['diagnostic_case']} | {r['baseline_global_rho']:.8f} | {r['rho_max']:.8f} | {r['Vmax']:.8f} |")
    text+=['','12개 반사실에서도 최대선로는 Line.tpx21459660c0이다. '
        '6개초기STA 액션을 합친 효과와AIDC 감소효과의 결합은 여기서의 비선형 전기적 관측이며, '
        '사후 입지·정격 변경이나 개선율 목표 맞춤에 사용하지 않았다. '
        '96슬롯 dispatch 및 새로운 병목/전압/CT의 전체 정책 적격성은 아직미검증이다.','']
    (folder/'ALL20_CONTROLLABILITY_KO.md').write_text('\n'.join(text),encoding='utf8')
    write(folder/'CONGESTION_REPORT_RECEIPT.json',dict(status='ALL20_FIXED_TARGETS_REPORTED_NO_POLICY_CLAIM',
        inputs=[receipt(selection/'SELECTED_PCC_PQ_SENSITIVITY.csv'),receipt(selection/'SELECTED_CONTROL_POTENTIAL.csv'),
                receipt(folder/'INSTANTANEOUS_COMPLEMENTARITY_NOT_POLICY.csv')],target_count=20,
        source_paths='topology metadata includes original source series Reactor',Native_calls=0))


if __name__=='__main__':run()
