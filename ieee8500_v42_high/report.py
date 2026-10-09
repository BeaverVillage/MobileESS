"""Preserved high-load comparator reporting; no policy-result site selection."""
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .common import *


def run():
    receipt0=read(REPORT/'RUN_RECEIPT.json');comparisons=[];audits=[];controls=[]
    for r in receipt0['records']:
        b=r['first'];tag=b['tag'];folder=REPORT/'ac'/tag
        audits.append(dict(case=tag,day=b['day'],source=b['source'],grid_hard_PASS=b['grid_hard_PASS'],
            Vmin=b['Vmin'],Vmax=b['Vmax'],line_overload_cells=b['line_overload_cells'],CT_current_overload_cells=b['CT_current_overload_cells'],
            CT_nameplate_overload_cells=b['CT_nameplate_overload_cells'],voltage_violation_cells=b['voltage_violation_cells'],
            fresh_PASS=r['Fresh']['PASS'],all_original_ratings=True,field_GIS_protection_access='UNVERIFIED',
            AIDC_QoS_dispatch='NOT_CERTIFIED',Production=False))
        comparisons.append(dict(day=b['day'],source=b['source'],control='MESS_RESEARCH_STATIONARY' if r['controlled'] else 'B0',
            rho_all=b['rho_max'],rho_Primary=b['Primary_rho_max'],rho_Triplex=b['Triplex_rho_max'],
            Vmin=b['Vmin'],Vmax=b['Vmax'],binding=b['binding_line'],peak_slot=b['peak_slot'],
            Primary_binding_slots=b['Primary_binding_slots'],Triplex_binding_slots=b['Triplex_binding_slots']))
        if not r['controlled']:
            baseline=b;controlled=next(x['first'] for x in receipt0['records'] if x['day']==b['day'] and x['source']==b['source'] and x['controlled'])
            for case in ('AIDC_ONLY','MESS_ONLY','JOINT'):
                output=controlled if case!='AIDC_ONLY' else baseline
                controls.append(dict(case=case,day=b['day'],source=b['source'],B0_rho=baseline['rho_max'],new_rho=output['rho_max'],
                    daily_global_relief_pu=baseline['rho_max']-output['rho_max'],daily_global_relief_percentage_points=100*(baseline['rho_max']-output['rho_max']),
                    nonzero_AIDC_reduction_certified=False,AIDC_action_kw=0.,
                    schedule_scope='zero AIDC reference replay; research stationary SOC+ETA+600s MESS replay' if case!='AIDC_ONLY' else 'zero AIDC reference replay only',
                    full_original_QoS_certificate=False,field_installation_certified=False,Native_policy_performance=False))
    table(REPORT/'PRIMARY_TRIPLEX_LOADING_COMPARISON.csv',comparisons);table(REPORT/'PHYSICAL_CONSTRAINT_AUDIT.csv',audits)
    for case in ('AIDC_ONLY','MESS_ONLY','JOINT'):table(REPORT/(case+'_CONTROLLABILITY.csv'),[r for r in controls if r['case']==case])
    shutil.copyfile(REPORT/'ac/FINAL_B0_PLANNING/SLOTS.csv',REPORT/'B0_SCENARIO_PLANNING_AC_96.csv')
    shutil.copyfile(REPORT/'ac/FINAL_B0_ACTUAL_FRESH/SLOTS.csv',REPORT/'B0_SCENARIO_ACTUAL_FRESH_AC_96.csv')
    plots();b=read(REPORT/'ac/FINAL_B0_PLANNING/RECEIPT.json');a=read(REPORT/'ac/FINAL_B0_ACTUAL/RECEIPT.json')
    c=read(REPORT/'ac/FINAL_MESS_PLANNING/RECEIPT.json');energy=pd.read_csv(REPORT/'AIDC_FACILITY_SCENARIO_ENERGY.csv')
    lines=['# 고부하 기존 입지 비교 사례','',
        f'Planning만으로 선택한 기존 입지 C0/780GPU, BG0.85의 전체 최대ρ는 {b["rho_max"]:.12f}이다. Actual은 {a["rho_max"]:.12f}이며 값을 보고 BG/GPU를 다시 맞추지 않았다.',
        f'전압은 Planning {b["Vmin"]:.9f}–{b["Vmax"]:.9f}, Actual {a["Vmin"]:.9f}–{a["Vmax"]:.9f} pu다. 모든 원본 전압·양단 도체·변압기 권선 정격 검사에서 위반0건이며 Fresh 배열/제어상태가 일치했다.',
        f'기존 6개 초기 LV포트의 grid-blind 8슬롯충전/8슬롯방전은 각5kW/3.655125kW, η=.855, E1140→1148.55→1140kWh다. Planning 일최대ρ 개선은 {100*(b["rho_max"]-c["rho_max"]):.9f}%p다. 5월2일 Planning 개선은0으로, 방전 시간대를 결과에 맞춰 바꾸지 않았다.',
        'AIDC의 비영96슬롯 Job/QoS/WAN/checkpoint 인증은 없다. 원 WINDOW 밖 시작1024개 등 기존 계약 불일치를 보존했으며, source-mask 순간상한은 실제 성과가 아니다. 인증된 비영 유연전력=0은 물리적 잠재력0이라는 주장이 아니다.',
        '원본 Job UID·GPU gang·Runtime·submit·required GPU-h를 보존했다. 설치용량마다 같은 모집단의 FCFS Reference/Queue/occupancy/C1/PCC를 재계산했다. 이전 고정점유율15개 AC를 보존한 뒤 최신 지시에 따른15개 재계산 AC를 추가했다.',
        '']
    lines+=['|GPU|Source|설치증가|당일 실행 GPU-h|원본 required GPU-h|인증 유연전력 증가|','|---:|---|---:|---:|---:|---:|']
    for r in energy.to_dict('records'):
        compute=r.get('executed_realized_Dday_GPUh',float('nan'))
        if not np.isfinite(compute):compute=r['processed_Dday_GPUh']
        lines.append(f'|{r["installed_GPU"]}|{r["source"]}|{r["installed_GPU_increase"]}|{compute:.6f}|{r["same_original_exact_required_nominal_GPUh"]:.6f}|0(미인증)|')
    lines+=['','C1의150GPU는 동종4GPU 서버 정수구성 FAIL이며, 모든 실물rack/PSU/냉각/시설접속변압기 정격은 UNVERIFIED다. GPU 증설 후보를 물리적 설치 PASS로 승격하지 않았다.',
        '기존 STA상위proxy12개는 모두 단상이어서 동일proxy MV연계는 FAIL이다. AIDC 고정606후보의 전proper회전 불가능 증명과 AIDC 고정해제24MV 형상증거는 별도로 보존했다. 고정해제·분산형 최종 연구는 docs/ieee8500_v42_joint_pcc_reselection/에서 계속한다.',
        '5월1일은 개발일, 5월2일은 이미 IEEE123 및 이 비교 사례에서 노출된 별도 날짜다. 향후 공동 입지의5월2일 검증을 미노출 holdout이라고 부르지 않는다.',
        'Production 승격은 GIS/접근/보호/연계하드웨어/as-of/Native 인터페이스/QoS 인증이 없어 차단한다. 기존 알고리즘·DSS·정격·Job·교통·활성캠페인을 변경하지 않았고 Native/B1/B2/B3 장시간 호출은0이다.']
    text='\n'.join(lines)+'\n'
    (REPORT/'FINAL_SCENARIO_DECISION_KO.md').write_text(text,encoding='utf8')
    (REPORT/'FINAL_REVIEW_KO.md').write_text(text+'\n기존 입지 고부하 비교 결과를 보존한 중간 보고이며 공동 분산 입지의 최종 결과는 별도 보고서에 기록한다.\n',encoding='utf8')


def plots():
    folder=REPORT/'figures';folder.mkdir(exist_ok=True);plt.rcParams.update({'font.size':10,'svg.fonttype':'none'})
    p=pd.read_csv(REPORT/'ac/FINAL_B0_PLANNING/SLOTS.csv');a=pd.read_csv(REPORT/'ac/FINAL_B0_ACTUAL/SLOTS.csv')
    m=pd.read_csv(REPORT/'ac/FINAL_MESS_PLANNING/SLOTS.csv');x=np.arange(96)/4
    def save(fig,name):
        fig.tight_layout();fig.savefig(folder/(name+'.svg'));fig.savefig(folder/(name+'.png'),dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4))
    for key in ('rho_max','Primary_rho_max','Triplex_rho_max'):ax.plot(x,p[key],label=key)
    ax.plot(x,a.rho_max,'--',label='Actual global');ax.axhspan(.75,.85,color='#aaa',alpha=.15);ax.set(xlabel='Hour AEST',ylabel='Original line loading pu');ax.legend(ncol=4);save(fig,'LINE_LOADING_96')
    fig,ax=plt.subplots(figsize=(11,4));ax.plot(x,p.Vmin,label='Planning min');ax.plot(x,p.Vmax,label='Planning max');ax.plot(x,a.Vmin,'--',label='Actual min');ax.plot(x,a.Vmax,'--',label='Actual max');ax.axhline(.95,color='red');ax.axhline(1.05,color='red');ax.set(xlabel='Hour AEST',ylabel='All-node voltage pu');ax.legend();save(fig,'VOLTAGE_96')
    d=dict(np.load(ROOT/'ieee8500_v42_high/data/facility/recomputed/C0_PLANNING_INPUTS.npz'))
    fig,ax=plt.subplots(figsize=(11,4));ax.plot(x,d['PCC_P_kw'].sum(1),label='PCC total');ax.plot(x,d['installed_idle_IT_kw'].sum(1),label='Installed idle IT');ax.plot(x,d['workload_IT_kw'].sum(1),label='Workload IT');ax.plot(x,d['cooling_and_facility_kw'].sum(1),label='Cooling/facility');ax.plot(x,d['source_mask_P_upper_bound_kw'].sum(1),label='Mask relaxation (not dispatch)');ax.set(xlabel='Hour AEST',ylabel='kW');ax.legend(ncol=2);save(fig,'AIDC_POWER_96')
    soc=pd.read_csv(REPORT/'MESS_SCHEDULE_SOC_96.csv');u=soc[soc.unit=='MESS01'];fig,axs=plt.subplots(2,1,figsize=(11,6),sharex=True);axs[0].plot(x,u.P_charge_AC_kw,label='charge per unit');axs[0].plot(x,-u.P_discharge_AC_kw,label='discharge per unit');axs[0].plot(x,u.Q_kvar,label='Q kvar');axs[0].legend();axs[0].set_ylabel('kW / kvar');axs[1].plot(x,u.E_after_kwh,label='battery energy');axs[1].axhline(1140,ls='--');axs[1].set(xlabel='Hour AEST',ylabel='kWh');save(fig,'MESS_PQ_SOC_96')
    fig,ax=plt.subplots(figsize=(11,4));ax.plot(x,100*(p.rho_max-m.rho_max),label='MESS-only; Joint same zero AIDC');ax.axhline(0,label='AIDC control not certified');ax.set(xlabel='Hour AEST',ylabel='Instant slot rho relief (% points)');ax.legend();save(fig,'CONTROL_RELIEF_96')
    controls=pd.read_csv(REPORT/'ac/FINAL_B0_PLANNING/CONTROL_STATES_96.csv');fig,axs=plt.subplots(2,1,figsize=(11,6),sharex=True)
    for name,g in controls[controls.kind=='RegControl'].groupby('name'):axs[0].step(g.slot/4,g.tap_number,label=name)
    axs[0].legend(ncol=4,fontsize=7);axs[0].set_ylabel('Tap number')
    caps=controls[controls.kind=='Capacitor']
    for name,g in caps.groupby('name'):axs[1].step(g.slot/4,[int(any(__import__('json').loads(v))) for v in g.states],label=name)
    axs[1].set(xlabel='Hour AEST',ylabel='Capacitor state');save(fig,'AUTOMATIC_CONTROLS_96')


if __name__=='__main__':run()
