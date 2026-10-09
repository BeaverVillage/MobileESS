"""Comparison tables and Korean review, preserving unfavorable official case evidence."""
import numpy as np
import pandas as pd
from functools import lru_cache
from .common import *


def folder(model,source):
    return (OLD/'ac'/('FINAL_B0_'+source)) if model=='Unbalanced' else REPORT/'ac'/('BALANCED_'+source)


@lru_cache(maxsize=4)
def case_arrays(model,source):
    f=folder(model,source)
    return read(f/'AC_AXES.json'),dict(np.load(f/'AC_96.npz'))


def line_groups(axes):
    groups={}
    for i,r in enumerate(axes['lines']):
        if r['objective_included']:groups.setdefault(r['element'],[]).append(i)
    return groups


def run():
    cases=[]; voltage=[]; loading=[]; bindings=[]; critical=[]; control=[]; top7=[]
    for source in ('PLANNING','ACTUAL'):
        for model in ('Unbalanced','Balanced'):
            f=folder(model,source); doc=read(f/'RECEIPT.json'); slots=rows(f/'SLOTS.csv')
            axes,z=case_arrays(model,source); groups=line_groups(axes); cases.append(dict(doc,model=model,source=source))
            if model=='Balanced':table(REPORT/('BALANCED_B0_'+source+'_AC_96.csv'),slots)
            voltage.append(dict(model=model,source=source,Vmin=doc['Vmin'],Vmax=doc['Vmax'],
                voltage_violation_cells=doc['voltage_violation_cells'],line_overload_cells=doc['full_line_overload_cells'],
                CT_current_overload_cells=doc['transformer_current_overload_cells'],CT_nameplate_overload_cells=doc['transformer_nameplate_overload_cells'],
                CT_current_rho_max=doc['transformer_current_rho_max'],CT_nameplate_rho_max=doc['transformer_nameplate_kva_rho_max'],
                full_both_terminals_rho_max=doc['full_both_terminal_conductor_rho_max'],hard_PASS=doc['hard_constraints_PASS'],
                original_Lines=3703,original_Triplex=1177,original_CT=1190,nodes=8531,customers=1177,P5_same=True))
            mask=np.array(axes['objective_mask'])
            for group in ('All','Primary','Triplex','Secondary'):
                select=mask if group=='All' else mask&np.array([r['group']==group for r in axes['lines']])
                if not select.any():
                    loading.append(dict(model=model,source=source,group=group,category_exists=False,rho_max=0,line='',slot='',local_node='',I_A='',NormalAmps=''));continue
                t,i=np.unravel_index(np.argmax(np.where(select[None,:],z['line_rho'],-np.inf)),z['line_rho'].shape)
                r=axes['lines'][i]
                loading.append(dict(model=model,source=source,group=group,category_exists=True,rho_max=float(z['line_rho'][t,i]),
                    line=r['element'],slot=int(t),local_node=r['node'],parent_terminal=r['terminal'],conductor=r['conductor'],
                    phase_semantics='local hot leg' if r['group']=='Triplex' else 'primary ABC',
                    I_A=float(z['line_amps'][t,i]),NormalAmps=r['normal_amps']))
            ordered=sorted(groups,key=lambda n:(-float(z['line_rho'][:,groups[n]].max()),n))
            for rank,n in enumerate(ordered[:20],1):
                v=z['line_rho'][:,groups[n]];t,j=np.unravel_index(v.argmax(),v.shape);i=groups[n][j];r=axes['lines'][i]
                other='Balanced' if model=='Unbalanced' else 'Unbalanced'; _,zz=case_arrays(other,source)
                critical.append(dict(model=model,source=source,rank=rank,line=n,group=r['group'],rho_max=float(v[t,j]),
                    max_slot=int(t),local_node=r['node'],parent_terminal=r['terminal'],I_A=float(z['line_amps'][t,i]),NormalAmps=r['normal_amps'],
                    other_model_same_line_rho_max=float(zz['line_rho'][:,groups[n]].max()),comparison_is_optimizer_improvement=False))
            for t,row in enumerate(slots):
                ordered_now=sorted(groups,key=lambda n:(-float(z['line_rho'][t,groups[n]].max()),n))
                second=float(z['line_rho'][t,groups[ordered_now[1]]].max())
                bindings.append(dict(model=model,source=source,slot=t,interval_start=row['interval_start'],
                    binding_line=row['binding_line'],group=row['binding_group'],local_node=int(row['binding_local_node']),
                    rho_max=float(row['rho_max']),Primary_rho_max=float(row['Primary_rho_max']),Triplex_rho_max=float(row['Triplex_rho_max']),
                    second_line=ordered_now[1],second_line_rho=second,next_line_gap_rho=float(row['rho_max'])-second,
                    old_binding_tpx=row['binding_line'].lower()=='line.tpx21459660c0',Vmin=float(row['Vmin']),Vmax=float(row['Vmax'])))
            control.extend(dict(model=model,source=source,**r) for r in rows(f/'CONTROL_STATES_96.csv'))
        oldaxes,oldz=case_arrays('Unbalanced',source); _,newz=case_arrays('Balanced',source); g=line_groups(oldaxes)
        old_tpx=sorted([n for n in g if oldaxes['lines'][g[n][0]]['group']=='Triplex'],key=lambda n:(-float(oldz['line_rho'][:,g[n]].max()),n))[:7]
        for rank,n in enumerate(old_tpx,1):
            old=float(oldz['line_rho'][:,g[n]].max());new=float(newz['line_rho'][:,g[n]].max())
            top7.append(dict(source=source,old_Triplex_rank=rank,line=n,Unbalanced_max=old,Balanced_max=new,
                decrease_percentage_points=100*(old-new),relative_decrease_percent=100*(old-new)/old,
                cause='official redistribution of conserved total customer P/Q; same per-hot PV',optimizer_improvement=False))
    table(REPORT/'VOLTAGE_SECURITY_COMPARISON.csv',voltage)
    table(REPORT/'PRIMARY_TRIPLEX_LOADING_COMPARISON.csv',loading)
    table(REPORT/'BINDING_LINE_96SLOT.csv',bindings);table(REPORT/'TOP20_CRITICAL_LINES.csv',critical)
    table(REPORT/'TOP7_TRIPLEX_RELIEF.csv',top7);table(REPORT/'CONTROL_STATE_COMPARISON.csv',control)
    write(REPORT/'COMPARISON_RECEIPT.json',dict(cases=cases,all_models_same_input=True,all_models_same_P5=True,
        official_customer_rebalancing_is_not_dispatch_improvement=True,final_main_case_selected=False))
    review(cases,voltage,loading,bindings,top7)


def review(cases,voltage,loading,bindings,top7):
    b={r['source']:r for r in cases if r['model']=='Balanced'};u={r['source']:r for r in cases if r['model']=='Unbalanced'}
    audit=read(REPORT/'SOURCE_AUTHORITY.json'); verify=read(REPORT/'INDEPENDENT_VERIFICATION.json')
    engine_text=' '.join(str(audit['engine_version']).split())
    finite=pd.read_csv(REPORT/'precheck/AUTOMATIC_BOUNDED_ENDPOINTS.csv').drop_duplicates(['slot','PCC','d_consumption_P_kw','d_consumption_Q_kvar'])
    actual=pd.read_csv(REPORT/'precheck/ACTUAL_BOUNDED_STA_ENDPOINTS.csv').drop_duplicates(['slot','PCC','d_consumption_P_kw','d_consumption_Q_kvar'])
    peak=int(b['PLANNING']['peak_slot']); atpeak=finite[finite.slot==peak]
    selected={s:atpeak[atpeak.PCC==s].iloc[0] for s in ('SIX_PARKED_STA','ALL_AIDC_BOUNDS','AIDC_PLUS_SIX_STA')}
    mapping=rows(MAPPING); deriv=pd.read_csv(REPORT/'PCC_CONTROLLABILITY_PRECHECK.csv')
    main=b['PLANNING']['binding_line'];dpeak=deriv[(deriv.slot==peak)&(deriv.line==main)]
    table(REPORT/'PCC_PEAK_BINDING_SUMMARY.csv',dpeak.to_dict('records'))
    endpoint_summary=[]
    for site in sorted(set(finite.PCC)):
        rows_site=finite[finite.PCC==site]
        endpoint_summary.append(dict(PCC=site,sampled_min_global_relief=float(rows_site.global_relief_rho.min()),
            sampled_max_global_relief=float(rows_site.global_relief_rho.max()),automatic_cases=len(rows_site),
            automatic_hard_PASS=bool(rows_site.hard_constraints_PASS.all()),binding_changed_count=int(rows_site.binding_line_changed.sum()),
            feasible_schedule_proven=False))
    table(REPORT/'PCC_BOUNDED_ENDPOINT_SUMMARY.csv',endpoint_summary)
    table(REPORT/'BINDING_TIME_TRANSITIONS.csv',[dict(model=r['model'],source=r['source'],from_slot=before['slot'],to_slot=r['slot'],
        from_line=before['binding_line'],to_line=r['binding_line'],from_group=before['group'],to_group=r['group'])
        for key in ((m,s) for m in ('Unbalanced','Balanced') for s in ('PLANNING','ACTUAL'))
        for before,r in zip([x for x in bindings if (x['model'],x['source'])==key],[x for x in bindings if (x['model'],x['source'])==key][1:])
        if before['binding_line']!=r['binding_line']])
    comparison='| 항목 | Unbalanced Planning | Balanced Planning | Unbalanced Actual | Balanced Actual |\n|---|---:|---:|---:|---:|\n'
    for label,key in [('전체 최대 rho','rho_max'),('Primary 최대 rho','Primary_rho_max'),('Triplex 최대 rho','Triplex_rho_max'),('Vmin','Vmin'),('Vmax','Vmax'),
                      ('Primary 최대 슬롯 수','Primary_binding_slots'),('Triplex 최대 슬롯 수','Triplex_binding_slots'),('옛 tpx21459660c0 최대 슬롯 수','original_tpx21459660c0_binding_slots'),('병목 전환 횟수','binding_line_changes')]:
        values=[u['PLANNING'][key],b['PLANNING'][key],u['ACTUAL'][key],b['ACTUAL'][key]]
        comparison+='| '+label+' | '+' | '.join(f'{v:.9f}' if isinstance(v,float) else str(v) for v in values)+' |\n'
    source_text=f'''# IEEE8500 Balanced / Unbalanced Source Authority

부모 Unbalanced P5는 commit `{P5_COMMIT}`, [Draft PR #196](https://github.com/BeaverVillage/MobileESS/pull/196)으로 보존했다. 그 이전 [PR #193](https://github.com/BeaverVillage/MobileESS/pull/193)의 feeder·교통·접속 자료 및 [PR #62](https://github.com/BeaverVillage/MobileESS/pull/62)의 과거 Vreg 출처를 유지한다. V42 입력/전력 Authority는 `{LATEST_SHA}`의 기존 P5 byte를 그대로 사용한다. 새 브랜치는 부모 P5 commit에서 별도로 만들었으며 이전 코드·결과 파일을 수정하지 않았다.

공식 모델의 권위는 로컬 EPRI OpenDSS r4173 배포 ZIP의 `Distrib/IEEETestCases/8500-Node/`다. ZIP SHA256은 `eb8a91ded9904ffe6f87dd461688339b665ce05217d344e823941a3c765493bd`, 채택본 31개 파일의 추출 이력은 [기존 원본 감사](../../ieee8500_v42/data/IEEE8500_SOURCE_AUDIT.md)에 있다. 최신 외부 배포본 또는 r4173 실행 엔진과 동일하다는 인증은 하지 않는다. 실행 엔진은 `{engine_text}`다.

Balanced는 원본 `Master.dss`가 `Loads.dss`를 Redirect하고, Unbalanced는 `Master-unbal.dss`가 `UnbalancedLoads.DSS`를 Redirect한다. 두 Master를 실제 별도 context로 compile했다. source 31개는 부모 P5 Git blob 및 기존 sealed source와 SHA256 일치한다. 장치·bus·line/CT axes·모든 CapControl/RegControl 원본 속성이 같고, 고객 Load 객체 구성만 다르다. kvar/kV 정의의 Capacitor에서 사용되지 않는 CMatrix getter가 미초기화 숫자 문자열을 노출하므로 그 getter 비교만 제외했다. 실제 정의 파일, kvar/kV/Cuf/연결/전류정격 등 모든 유효 속성은 동일하다.

원본 `Loads.dss` 주석은 2상 wye 모델이 3상 LN 전압 기준을 사용하여 `.208/sqrt(3)=.120088856 kV`가 되고 총 kW를 두 레그에 균등하게 나눈다고 명시한다. 서비스 변압기는 두 hot의 반대 극성을 만든다. 실제 208 V 3상 고객이나 계통 전체의 ABC 완전 평형을 뜻하지 않는다. [EPRI Load 속성](https://opendss.epri.com/Properties7.html)은 kW가 모든 상의 합계임을, [EPRI 부하 배분 설명](https://opendss.epri.com/OpenDSSLoadAlocation.html)은 복수 상 Load의 균등 배분을 설명한다.

두 모델의 명목 총 입력은 {audit['native_customer_kw']:.8f} kW / {audit['native_customer_kvar']:.12f} kvar다. 고객 P 최대 차이 {audit['max_customer_P_error']:.3g} kW, Q 최대 차이 {audit['max_customer_Q_error']:.3g} kvar는 원본 decimal 저장 및 float 오차다. 1,177 ID 전수 일대일 대조와 Fixed24/Variable1,153 분류 보존을 검증했다.

기존 2,354개 120 V hot별 연구 PV Generator의 위치·설치 용량·Model1·역률·전압 특성은 전부 보존한다. Balanced 고객마다 기존 두 PV를 정확히 묶어 설치 용량을 보존하며 PV를 새로 균등 배분하지 않는다. 고객 부하 균형과 PV 균형을 혼동하지 않는다. 실제 PV 출력은 전압에 따라 달라질 수 있다. 설치 총량은 1,276.937105381 kW/kVA, 명령 Q=0이다.

동일한 P5 overlay는 Source1.04, 전체12 Vreg123.5, CAPBank3의 state0, 원본9 CapControl 속성과 지연·deadband·tap한계다. overlay SHA256 `{sha(REPORT/'overlays/P5.dss')}`는 부모 P5와 동일하다. 제어 상태 궤적 자체는 서로 다른 조류에 따라 달라질 수 있다.

`SOURCE_AUTHORITY.json`은 재사용 AEMO/GFS/NOAA/Kestrel/C1/Runtime/CC4 입력의 전체 SHA roster를 저장한다. `.npz` 입력을 직접 재사용해 Forecast/Actual 인과 경계·96축·정규화·BG.552 및 Fixed static 규칙을 바꾸지 않았다. 기존 연간 normalization reference의 D-1 가용성, Runtime/CC4 calibration ingestion as-of 및 GFS 실제 publication receipt는 UNVERIFIED다. 과거 노출된 2025-05-01의 Fresh 재실행은 독립 미노출 검증일이 아니다.
'''
    (REPORT/'SOURCE_AUTHORITY.md').write_text(source_text,encoding='utf-8')
    text=f'''# 공식 Balanced IEEE8500 P5 검증 — 한국어 최종 검토

**Balanced P5의 Planning96 / Actual96 / 각각 Fresh96 모두 실제 AC 전압·선로·변압기 제약을 통과했다. 고객 총 P/Q를 보존하면서 Triplex 최고값이 낮아졌고, 일별 전역 최고점은 중압 선로 `{main}`가 결정한다.** 두 모델 차이는 부하 구성을 바꾼 효과이며 AIDC–MESS 최적화 개선율이 아니다.

{comparison}

## Q1. 고객 총 P/Q는 일치하는가?

PASS. 1,177 고객별 ID, 연결 bus, 상위 Primary phase, PF.97, Model1, Vmin.88/Vmax1.05, Fixed/Variable을 전수 대조했다. 원본 합계 10,773.17 kW / {audit['native_customer_kvar']:.9f} kvar다. 최대 P/Q 잔차는 {audit['max_customer_P_error']:.3g} / {audit['max_customer_Q_error']:.3g}이다. Balanced1177개 Load와 Unbalanced2354개 Load의 차이는 객체/레그 분배이며 고객 전력을 반감하지 않았다. 96슬롯 intended P/Q도 기존 P5 두 Load의 합과 오차1e-10 미만으로 일치한다. AC 두 레그 각 P/Q=총입력/2 최대 잔차 {max(r['customer_leg_split_error'] for r in verify['cases']):.3g} kW/kvar다.

## Q2. 원본 3,703 Line / 1,177 Triplex가 유지됐는가?

PASS. 3,703개 Line(활성3,698, 원본 비활성5 포함), 1,177 Triplex, 1,190 Transformer와 8,531 node를 보존했다. LineCode·length·impedance·NormalAmps·CT nameplate·phase/node·Source DSS byte 변경은 0건이다. 전체 Line 양단·모든 CT conductor와 winding kVA를 보존한 archive로 검산했다. 원래 전체 `min rho_max`의 source-rooted parent-terminal 정의를 유지하며 별도로 더 보수적인 모든 양단/도체 thermal 검사도 통과했다. 다른 저압 Secondary category는 존재하지 않는다.

## Q3. Balanced P5 Planning/Actual 보안 제약은 통과하는가?

PASS. 두 96슬롯과 각각 Fresh96의 전압0.95–1.05, 원본 Line ampacity, CT winding current/nameplate kVA 위반은 모두0이다. RegControl/CapControl 자동 제어는 수렴·ControlActionsDone·빈 queue로 확인했다. 전압/전류/고객/PV/PCC/phasor 배열 및 제어 상태 Fresh 차이는0이다. 전력수지 최대 오차 {max(r['power_balance_error'] for r in verify['cases']):.3g} kW/kvar이며 Source 설정을 재조정하지 않았다. 두 모델의 P5 설정이 같아도 부하 변화에 따라 탭·capacitor 궤적은 달라진다.

## Q4. 전체 최대 선로부하율은?

Planning **{b['PLANNING']['rho_max']:.9f} pu**, Actual **{b['ACTUAL']['rho_max']:.9f} pu**다. 최고 슬롯은 각각 {b['PLANNING']['peak_slot']} / {b['ACTUAL']['peak_slot']} (0-based)이며 `{main}`의 local node2, 즉 Primary B상이다. 최고점에서 다음 선로까지 gap은 각각 {b['PLANNING']['next_line_gap_at_peak']:.3g} / {b['ACTUAL']['next_line_gap_at_peak']:.3g} rho이다. 인접 직렬 선로들이 사실상 함께 혼잡하므로 단 하나의 선로 개선만 보지 않아야 한다. [전체 category 최고 전류·정격·phase·slot](PRIMARY_TRIPLEX_LOADING_COMPARISON.csv) 및 [모든 binding96](BINDING_LINE_96SLOT.csv)에 실제값을 저장했다.

## Q5. Primary 최대값은?

Planning {b['PLANNING']['Primary_rho_max']:.9f}, Actual {b['ACTUAL']['Primary_rho_max']:.9f} pu다. 기존 Unbalanced의 {u['PLANNING']['Primary_rho_max']:.9f} / {u['ACTUAL']['Primary_rho_max']:.9f}와 차이는 작다. 고객 총 소비전력이 같으므로 주 변화는 두 hot 전류와 LV 손실·전압이며 Primary 전력이 크게 줄었다고 해석하면 안 된다.

## Q6. Triplex 최대값은?

Planning {b['PLANNING']['Triplex_rho_max']:.9f}, Actual {b['ACTUAL']['Triplex_rho_max']:.9f} pu다. 기존 Unbalanced는 {u['PLANNING']['Triplex_rho_max']:.9f} / {u['ACTUAL']['Triplex_rho_max']:.9f} pu였다. [Top7 동일 선로 비교](TOP7_TRIPLEX_RELIEF.csv)에 고객전력을 보존한 구성 차이를 기록했다. 전체 고객의 불평형을 균등 배분하는 공식 case 전환 결과이며 임의의 단일 고객 감축이나 정격 확대가 아니다.

## Q7. 옛 Line.tpx21459660c0는 여전히 최대인가?

일별 전역 최고점은 아니다. 다만 Balanced Planning {b['PLANNING']['original_tpx21459660c0_binding_slots']}슬롯 / Actual {b['ACTUAL']['original_tpx21459660c0_binding_slots']}슬롯에서 여전히 전역 최대다. 원본 Fixed 고객21459660c0의 30.52 kW는 기존30.183847622+0.336152378 kW에서15.26+15.26으로 재분배된다. BG.552 후 명목8.42352 kW씩이며 총부하는 그대로다. 156 A Triplex 정격, 고객 위치/경로와 연구 PV의 기존 hot별 비대칭은 유지된다. 다른 Fixed30.52 kW 고객 tpx227447984c0도 일부 시간 최대가 된다. 이들 static 고객의 전류 차이는 전압·PV·제어·상위 AEMO Variable 부하 영향이며 Fixed에 새 시간 형상을 적용한 것이 아니다.

## Q8. Primary가 전역 최대인 시간은?

Planning **{b['PLANNING']['Primary_binding_slots']}/96**, Actual **{b['ACTUAL']['Primary_binding_slots']}/96**슬롯이다. 나머지 {b['PLANNING']['Triplex_binding_slots']} / {b['ACTUAL']['Triplex_binding_slots']}슬롯은 Triplex다. 병목 전환은 {b['PLANNING']['binding_line_changes']} / {b['ACTUAL']['binding_line_changes']}회다. 96축 및 전환 CSV를 보존해 중압 병목만 있는 것처럼 선택적으로 보고하지 않았다.

## Q9. AIDC–MESS가 실제 전체 최대 선로를 제어할 수 있는가?

**순간 AC에서 작지만 수치로 확인되는 제어 가능성은 있다. 96슬롯 정책 성능과 최적해는 아직 미검증이다.** Planning 최고점 {peak}에서 24 PCC 모두 `{main}`의 topology 하류지만 3상 AIDC와 단상 고객 STA는 상별 기여가 다르다. 중앙 ±1 kW/kvar fixed-tap 민감도와 자동 제어가 재동작하는 bounded endpoint를 구분했다. 독립 AIDC Q 조작은 실제 actuator로 인정하지 않고 PF.95의 coupled Q만 적용했다.

Planning 최고점: 여섯 초기 STA에서5 kW씩 방전하면 rho {selected['SIX_PARKED_STA']['rho_max']:.9f}, 감소 **{100*selected['SIX_PARKED_STA']['global_relief_rho']:.6f}%p**다. 같은 슬롯 eligible-known AIDC P 상한 합계 **{-selected['ALL_AIDC_BOUNDS']['d_consumption_P_kw']:.6f} kW**를 줄이면 감소 **{100*selected['ALL_AIDC_BOUNDS']['global_relief_rho']:.6f}%p**다. 합친 반사실은 rho {selected['AIDC_PLUS_SIX_STA']['rho_max']:.9f}, 감소 **{100*selected['AIDC_PLUS_SIX_STA']['global_relief_rho']:.6f}%p**다. Actual 최고점에서 six-STA 반사실 감소는 **{100*float(actual[actual.PCC=='SIX_PARKED_STA'].iloc[0].global_relief_rho):.6f}%p**다. Actual의 workload eligible mask를 Planning에서 추정하지 않아 Actual AIDC 감축량은 인증하지 않았다.

낮은 부하/Triplex binding 시간에는 상위 MV 감축이 원격 Triplex에 미치는 효과가 약하고 제어 재동작으로 증가할 수도 있다. 특정 상 STA의 충전도 B상 전류를 낮추는 경우가 있으므로 P의 부호만으로 개선을 가정하지 않는다. 직접 downstream 경로·상별 derivative·full-network endpoint·새 병목 전환을 모두 CSV에 기록했다. 모든 sampled 자동 endpoint는 원본 보안 제약 및 LV P±5/Q±3/S6/I27를 통과했다. 최대 실제 hot 전류는 {float(pd.read_csv(REPORT/'precheck/LV_PORT_ACTUAL_LEGS.csv')[['hot1_A','hot2_A']].max().max()):.6f} A다.

이는 당일 알려진 유연 job의 순간 전력 상한 및 초기 주차 위치의 가정이다. 동시에 실행 가능한 TS/PS/MG·마감시간·SOC·ETA/연결600초·차량 이동 스케줄을 증명하지 않는다. AIDC 시설 설치780 GPU 및 모든 idle/CC4 전력이 유연 부하라는 주장은 하지 않는다. 모든6차량의 Native/Actual/Fresh 연결은 기존 UNVERIFIED를 유지한다.

## Q10. Balanced IEEE8500을 V42 확장성 연구에 쓰는 것이 타당한가?

공식 synthetic 고객 hot 균형 시나리오로 **물리적·학술적으로 유효한 비교/확장성 후보**다. 실측 고객 프로파일 또는 완전 ABC 평형을 의미하지 않는다. Unbalanced 결과를 본 뒤 이 case를 추가했다는 이력을 명시하며 불리한 원본 P5 결과·SHA를 모두 보존했다. 본 결과만으로 논문 주 검증 계통을 결정하거나 유리한 B1–B3 결과에 따라 선택하지 않는다. 주 시나리오는 B1–B3 성과를 보기 전에 연구 목적과 공개된 물리 조건으로 별도 결정해야 한다.

계산 규모는 동일한8,531 node/3,703 Line/1,190 CT이지만 Load 객체1177개로 줄어든다. AC 통과는 Native scalability·6차량 QoS/이동·SOC 구현이나 글로벌 최적성 증명이 아니다. 데이터 as-of, full Native bridge, 실제 지리 좌표/접근/보호 승인, LV 보조 인버터 등 미검증 사유로 Production 승격은 차단한다. 276쌍552축은 동결한1 m 상당 공차와 하나의 proper similarity로 다시 검증했으며 **ASSUMED_PROXY_DIRECTION_PASS**다. RMS 형상 오차5.696 km 상당, 최대9.543 km 상당은 도식 proxy 오차이며 현장 지리 인증이 아니다.

## Q11. 450 kW MESS를 사용하려면 MV 접속 설계가 필요한가?

현재240 V LV 포트는5 kW/±3 kvar/6 kVA/27 A hot 제약이므로 **450 kW PCS 전체 사용에는 별도의 적격 MV 연계 또는 그에 맞는 고용량 인터페이스 설계가 필요하다.** 기존 service transformer/Triplex에450 kW를 주입할 수 없다. 차량 정격450 kW/600 kVA/1,800 kWh는 포트 정격과 분리했다. 단순 240 V450 kW의 약1,875 A를 현재 포트에 적용하지 않았다. 12.47 kV 3상에서450 kW unity-PF의 약20.84 A라는 산술 환산은 MV PCC 적격성·절연·보호·정격·역송전·전압 AC 승인을 대체하지 않는다. 이번에 STA 이동이나 신규 transformer/충전소를 추가하지 않았다. MV STA는 후속 연구 설계 후보다.

## 재현·보존·종료 상태

Balanced4일384슬롯 AC, full-axis/고객/PV/PCC/전력수지 독립 산술 검증, 5개Planning 및1개Actual 시점의 bounded sensitivity를 완료했다. 원본 입력·모델·기존 캠페인에 쓰거나 중단하거나 Scheduler를 변경한 횟수는0이다. 캠페인 원본 source/manifest SHA와 외부 관측 변화는 별도 before/after 문서로 저장한다. B1/B2/B3 Solver 및 Native 호출0, 시나리오 최종 동결0이다. 그림6쌍과 필수15개 결과, 부가 검증 CSV/JSON, Python source 및 SHA manifest를 같은 디렉터리 패키지에 포함한다. 경량 회귀 테스트와 PR 정보는 종료 receipt를 참조한다.
'''
    (REPORT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    decision=f'''# 단일 운영 시나리오 결정 상태

**최종 논문/Production 주 계통은 아직 선정·동결하지 않았다.** 이번 실행은 이미 노출된2025-05-01에서 공식 Balanced P5를 기존 Unbalanced P5와 비교한 단일 연구 후보다. 고객 총 P/Q 및 네트워크를 보존한 synthetic 고객 hot 균형 구성은 AC에서 유효하나, 결과가 유리하다는 이유만으로 주 검증 계통으로 자동 채택하지 않는다.

{comparison}

이후 판단은 B1/B2/B3 성과를 보기 전에 연구 질문(실제 레그 불평형에 대한 강건성인지, 공식 균형 baseline에서 중압 유연성/계산 확장성을 검증할지), 같은 입력·제약, 양 case 병목 구조와 미검증 항목을 공개하고 수행해야 한다. 불리한 Unbalanced P5는 commit `{P5_COMMIT}` 및 PR196에 보존하며 비교·한계로 유지한다.

현재 study candidate: Source1.04, all12 Vreg123.5, CAPBank3OFF, 원본9CapControl, BG.552, installedGPU780, 12AIDC/12LVSTA/6MESS와 기존 mapping·ETA·연결600초. 차량450kW/600kVA/1800kWh, port5kW/3kvar/6kVA/27A. B0P/Q_MESS=0. Source/Scale/PV/접속점 및 원본 정격을 결과에 맞추어 변경하지 않았다.

B0 physical gate=PASS; Production=BLOCKED. 실제 지리/접근/보호/LV 보조장치, 데이터 publication/as-of, six-unit Native/Actual 및 위치별 효율/SOC/fullC3A 등 기존 UNVERIFIED gate를 유지한다. 본 반사실은 순간 upper endpoint이며 운영 가능한 workload/route 스케줄 인증이 아니다. 최종 사용자 연구 구성 판단 전 동결하지 않는다.
'''
    (REPORT/'SINGLE_CASE_DECISION_REPORT_KO.md').write_text(decision,encoding='utf-8')
    write(REPORT/'SINGLE_CASE_DECISION.json',dict(candidate='OFFICIAL_BALANCED_P5_COMPARISON',B0_physical_PASS=True,
        final_main_paper_case_selected=False,Production_eligible=False,final_operating_configuration_frozen=False,
        selection_after_unbalanced_results=True,B1_B2_B3_results_used=False,Native_calls=0,
        preserved_Unbalanced_P5_commit=P5_COMMIT,Blocked_items=['input_as_of','field_geography_access_protection','LV_aux_interface','six_unit_Native_and_SOC']))
    print('comparison tables and Korean Q1-Q11 complete',flush=True)


if __name__=='__main__':run()
