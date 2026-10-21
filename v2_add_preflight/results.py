"""Review saved numerical arrays and publish V2_add G1-G3 findings."""
import csv
import json
import os
from pathlib import Path
import numpy as np
from .audit import DOC,ROOT,read,save,table,sha
from .physical import RUNTIME


def topology_influence():
    source=read(DOC/'OFFICIAL_BALANCED_AXES.json')
    mapping=list(csv.DictReader((DOC/'AIDC12_STA12_PCC_MAPPING.csv').open(encoding='utf-8')))
    byline={'line.'+r['name'].lower():r for r in source['lines']}
    edges=[]
    for r in source['lines']+source['transformers']:
        if not r.get('enabled',True):continue
        buses=[v.split('.')[0].lower() for v in r['buses']]
        edges.extend((buses[0],b) for b in buses[1:] if b!=buses[0])
    top=list(csv.DictReader((DOC/'TOP20_GLOBAL_CRITICAL_LINES.csv').open(encoding='utf-8')))
    output=[]
    for critical in top:
        if critical['role']!='ACTUAL' or float(critical['beta_BG'])!=1.5:continue
        r=byline[critical['line'].lower()];a,b=[v.split('.')[0].lower() for v in r['buses']]
        adj={}
        for x,y in edges:
            if {x,y}=={a,b}:continue
            adj.setdefault(x,set()).add(y);adj.setdefault(y,set()).add(x)
        seen={'_hvmv_sub_lsb'};queue=list(seen)
        while queue:
            x=queue.pop()
            for y in adj.get(x,()):
                if y not in seen:seen.add(y);queue.append(y)
        is_bridge=(a in seen)!=(b in seen)
        for site in mapping:
            output.append(dict(rank=critical['rank'],line=critical['line'],phase=critical['phase'],
                site=site['location_id'],role=site['role'],PCC_bus=site['candidate_bus'],
                topological_downstream=is_bridge and site['candidate_bus'].lower() not in seen,
                radial_bridge=is_bridge,scope='topology only; actual AC response and Job/SOC feasibility are separate'))
    table('TOP20_PCC_DOWNSTREAM_INFLUENCE.csv',list(output[0]),output)


def review_arrays():
    receipts=read(DOC/'B0_AC_ARCHIVE_RECEIPTS.json');checks=[];corrections=[];controls=[]
    for r in receipts:
        path=Path(r['axes_path']);axes=read(path);changed=False
        for line in axes['line']:
            included=line['node']>0
            if 'legacy_parent_objective_included' not in line:
                line['legacy_parent_objective_included']=line.get('objective_included')
                line['objective_included']=included
                line['objective_scope']='V2_add all original real-phase conductors, both terminals; disabled originals retained at zero current'
                changed=True
        if changed:
            old=r['axes_sha256'];path.write_text(json.dumps(axes),encoding='utf-8')
            r['axes_sha256']=sha(path.read_bytes())
            corrections.append(dict(case=r['case'],old_axes_sha256=old,new_axes_sha256=r['axes_sha256'],
                reason='Inherited vendor parent-terminal metadata flags corrected to actual V2 all-terminal mask; no numerical arrays or objective changed'))
            (path.parent/'RECEIPT.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
        a=np.load(r['archive_path']);rows=read(r['rows_path']);states=read(r['states_path'])
        mask=np.array([v['node']>0 for v in axes['line']]);mv=np.array([v['node']>0 and v['group']=='Primary' for v in axes['line']]);lv=mask&~mv
        global_rho=a['line_rho'][:,mask].max(1)
        difference=max(float(np.max(abs(global_rho-[v['rho_global'] for v in rows]))),
            float(np.max(abs(a['line_rho'][:,mv].max(1)-[v['rho_MV'] for v in rows]))),
            float(np.max(abs(a['line_rho'][:,lv].max(1)-[v['rho_LV'] for v in rows]))))
        assert difference<1e-12
        assert len({v['element'] for v in axes['line']})==3703
        checks.append(dict(case=r['case'],slots=len(rows),max_loading_arithmetic_difference=difference,
            original_line_count=3703,disabled_originals_retained=5,all_terminals_included=True,
            physics_PASS=all(v['physics_PASS'] for v in rows)))
        if not r['case'].endswith('_FRESH'):
            for t,state in enumerate(states):
                row=dict(beta_BG=r['beta_BG'],role=r['role'],slot=t,evaluation_slot=t-(24 if r['role']=='ACTUAL' else 0))
                row.update({f'TAP_{name}':json.dumps(v) for name,v in state['taps'].items()})
                row.update({f'CAP_{name}':json.dumps(v) for name,v in state['capacitors'].items()})
                controls.append(row)
    save('B0_AC_ARCHIVE_RECEIPTS.json',receipts)
    if corrections:save('AXIS_METADATA_CORRECTION.json',corrections)
    save('B0_NUMERICAL_ARRAY_REVIEW.json',dict(PASS=True,cases=checks,
        note='Independent saved-array arithmetic review, not more bootstrap/static tests'))
    table('B0_TAP_CAP_TIME_SERIES.csv',list(controls[0]),controls)


def figures():
    os.environ['MPLCONFIGDIR']=str(RUNTIME/'matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    out=DOC/'figures';out.mkdir(exist_ok=True)
    s=list(csv.DictReader((DOC/'BACKGROUND_SCALE_SCREENING.csv').open(encoding='utf-8')))
    beta=np.array([float(r['beta_BG']) for r in s]);mv=np.array([float(r['actual_MV'])*100 for r in s]);lv=np.array([float(r['actual_LV'])*100 for r in s])
    fig,ax=plt.subplots(figsize=(9,5),layout='constrained')
    ax.axhspan(75,85,color='#cce8da',alpha=.6,label='Preferred B0 band 75-85%')
    ax.axhspan(70,75,color='#e7efcb',alpha=.6,label='Fallback 70-75%')
    ax.plot(beta,mv,'o-',color='#265f87',label='Actual MV / global maximum')
    ax.plot(beta,lv,'s-',color='#c78139',label='Actual LV / Triplex maximum')
    ax.plot(beta,[float(r['planning_rho'])*100 for r in s],'--',color='#688d9b',label='Planning global maximum')
    ax.set(xlabel='Additional background scale beta_BG',ylabel='Daily maximum line loading (%)',ylim=(0,90),
           title='V2_add | Actual IEEE8500 B0 screening, all original lines')
    ax.grid(alpha=.2);ax.legend(fontsize=8)
    for ext in ('svg','png'):fig.savefig(out/f'B0_SCALE_MV_LV.{ext}',dpi=160)
    plt.close(fig)
    pilots=list(csv.DictReader((DOC/'CONTROL_PILOT_GLOBAL_COMPARISON.csv').open(encoding='utf-8')))
    fig,ax=plt.subplots(figsize=(9,5),layout='constrained')
    for kind,marker in [('MESS_ONLY','o'),('JOINT','s')]:
        rows=[r for r in pilots if r['role']=='ACTUAL' and r['control']==kind]
        ax.plot([float(r['amplitude']) for r in rows],[float(r['delta_global_pp']) for r in rows],
                marker+('--' if kind=='JOINT' else '-'),label='MESS + unchanged AIDC' if kind=='JOINT' else kind)
    aidc=next(r for r in pilots if r['role']=='ACTUAL' and r['control']=='AIDC_ONLY')
    ax.axhline(float(aidc['delta_global_pp']),color='#9a693e',linestyle='--',label='AIDC reference replay; no nonzero Actual witness')
    ax.axhline(0,color='black',linewidth=.6);ax.set(xlabel='Fixed SOC-feasible MESS schedule amplitude',ylabel='Global maximum reduction (percentage points)',title='V2_add | Feasible 96-slot pilots at beta=1.50; not B3')
    ax.grid(alpha=.2);ax.legend()
    for ext in ('svg','png'):fig.savefig(out/f'FEASIBLE_PILOT_GLOBAL_REDUCTION.{ext}',dpi=160)
    plt.close(fig)
    # Whole-horizon max retains rebound, plus the site-resolved power witness.
    receipts=read(DOC/'CONTROL_PILOT_ARCHIVE_RECEIPTS.json')
    fig,axs=plt.subplots(2,1,figsize=(10,7),layout='constrained',sharex=True)
    baseline=next(r for r in read(DOC/'B0_AC_ARCHIVE_RECEIPTS.json') if r['beta_BG']==1.5 and r['role']=='ACTUAL' and not r['case'].endswith('_FRESH'))
    br=read(baseline['rows_path'])[24:];axs[0].plot(np.arange(96)/4,[r['rho_global']*100 for r in br],color='black',label='B0')
    for kind in ('AIDC_ONLY','MESS_ONLY','JOINT'):
        candidates=[r for r in receipts if r['role']=='ACTUAL' and r['kind']==kind and not r['fresh'] and r['physics_PASS']]
        if not candidates:continue
        best=min(candidates,key=lambda r:r['rho']);rr=read(best['rows_path'])[24:]
        labels={'AIDC_ONLY':'AIDC reference replay','MESS_ONLY':'MESS pilot','JOINT':'MESS + unchanged AIDC'}
        styles={'AIDC_ONLY':':','MESS_ONLY':'-','JOINT':'--'}
        axs[0].plot(np.arange(96)/4,[r['rho_global']*100 for r in rr],linestyle=styles[kind],label=labels[kind])
        if kind=='JOINT':
            axs[1].plot(np.arange(96)/4,[r['fleet_P_kw'] for r in rr],label='MESS net demand (charge positive)')
            axs[1].plot(np.arange(96)/4,[r['AIDC_delta_total_kw'] for r in rr],label='AIDC delta incl. rebound')
    axs[0].set(ylabel='All-line max loading (%)',title='V2_add | Actual beta1.50, entire daily maximum and rebound')
    axs[1].set(xlabel='AEST hour',ylabel='Power (kW)')
    for ax in axs:ax.grid(alpha=.2);ax.legend(fontsize=8)
    for ext in ('svg','png'):fig.savefig(out/f'ACTUAL_CONTROL_PILOT_TIME_SERIES.{ext}',dpi=160)
    plt.close(fig)
    # Original static drawing coordinates, color every original line by measured
    # beta1.50 Actual daily maximum; all 3703 originals remain in this view.
    source=read(DOC/'OFFICIAL_BALANCED_AXES.json');coords={k:(r['x'],r['y']) for k,r in source['buses'].items()}
    aa=np.load(baseline['archive_path'])['line_rho'][24:];axes=read(baseline['axes_path'])['line']
    byline={}
    for j,r in enumerate(axes):
        if r['node']>0:byline[r['element'].lower()]=max(byline.get(r['element'].lower(),0),float(aa[:,j].max()))
    segments=[];color=[]
    for r in source['lines']:
        a,b=[v.split('.')[0].lower() for v in r['buses']]
        segments.append([coords[a],coords[b]]);color.append(100*byline['line.'+r['name'].lower()])
    fig,ax=plt.subplots(figsize=(10,9),layout='constrained');lc=LineCollection(segments,cmap='viridis',linewidths=.8);lc.set_array(np.array(color));lc.set_clim(0,60);ax.add_collection(lc);ax.autoscale();ax.set_aspect('equal');ax.set_axis_off()
    ax.set_title('V2_add | All 3,703 original lines, Actual beta1.50 daily maxima');fig.colorbar(lc,ax=ax,label='Maximum line loading (%)',shrink=.7)
    mapping=list(csv.DictReader((DOC/'AIDC12_STA12_PCC_MAPPING.csv').open(encoding='utf-8')))
    for role,marker,c in [('AIDC','o','#e76541'),('STA','s','#d57cff')]:
        chosen=[r for r in mapping if r['role']==role];xy=np.array([coords[r['candidate_bus']] for r in chosen]);ax.scatter(xy[:,0],xy[:,1],s=20,marker=marker,color=c,label=role+'12')
    top=list(csv.DictReader((DOC/'TOP20_GLOBAL_CRITICAL_LINES.csv').open(encoding='utf-8')))
    critical={r['line'].lower() for r in top if float(r['beta_BG'])==1.5 and r['role']=='ACTUAL'}
    overlay=[segments[i] for i,r in enumerate(source['lines']) if 'line.'+r['name'].lower() in critical]
    ax.add_collection(LineCollection(overlay,colors='#e53737',linewidths=1.8,label='Top20 original critical lines'))
    ax.legend(loc='lower left')
    for ext in ('svg','png'):fig.savefig(out/f'B0_LOADING_HEATMAP_TOP20_PCC.{ext}',dpi=160)
    plt.close(fig)


def reports():
    rows=list(csv.DictReader((DOC/'BACKGROUND_SCALE_SCREENING.csv').open(encoding='utf-8')))
    pilots=list(csv.DictReader((DOC/'CONTROL_PILOT_GLOBAL_COMPARISON.csv').open(encoding='utf-8')))
    gates=read(DOC/'PREFLIGHT_GATES.json');job=read(DOC/'AIDC_FEASIBLE_CANDIDATE_AUDIT.json')
    if not job['actual_job_changes']:
        gates['G3'].update(status='PARTIAL_MESS_PASS_ACTUAL_AIDC_NONZERO_NOT_VERIFIED',
            planning_job_witness_count=len(job['planning_job_changes']),actual_job_witness_count=0)
        save('PREFLIGHT_GATES.json',gates)
        for row in pilots:
            if row['role']=='ACTUAL' and row['control']=='AIDC_ONLY':row['scope']='REFERENCE_REPLAY_NO_NONZERO_ACTUAL_JOB_WITNESS'
            if row['role']=='ACTUAL' and row['control']=='JOINT':row['scope']='MESS_PLUS_UNCHANGED_AIDC_NOT_NONZERO_JOINT_WITNESS'
        table('CONTROL_PILOT_GLOBAL_COMPARISON.csv',list(pilots[0]),pilots)
    scope=read(DOC/'G3_DIAGNOSTIC_SCOPE.json')
    scope['AIDC']='original B0 reference/FCFS bounded single-GPU same-site delays; no legacy optimized schedule admitted'
    scope['Actual_AIDC_nonzero_witness']='NOT_VERIFIED; reference replay is not a nonzero AIDC pilot'
    save('G3_DIAGNOSTIC_SCOPE.json',scope)
    endpoints=list(csv.DictReader((DOC/'STA_P300_Q250_AC_ENDPOINTS.csv').open(encoding='utf-8')))
    binding=read(DOC/'V44_R043_INPUT_BINDING_AUDIT.json')
    binding.setdefault('phase1_status',binding['status'])
    binding['status']='INPUT_AND_PHYSICAL_MAPPING_PASS_PHASE2'
    binding['PV']='PASS: fixed PR197 hot-leg installation weights; exact original V44 slot totals, Model1/Q0/.12kV; all G2 AC balance checked'
    binding['phase2_scope']='May01 actual operating AC; May02-07 authority receipts retained but no day expansion'
    save('V44_R043_INPUT_BINDING_AUDIT.json',binding)
    initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')
    initial.setdefault('phase1_status',initial['status']);initial['status']='MAPPING_PASS_LIMITED_AC_WITNESSES_CERTIFIED'
    initial['physical_port_occupancy_and_PQ_acceptance']='Eight distinct original STA ports; G3 feasible daily witnesses; full PCS box not universally AC-safe'
    initial['feasible_96slot_energy']='See MESS8_PILOT_UNIT_TRAJECTORIES.csv and per-case AC PASS; includes charge rebound and terminal SOC'
    save('MESS8_INITIAL_STATES_AND_PORTS.json',initial)
    pv_audit=read(DOC/'PV_MAPPING_AUDIT.json')
    pv_audit.update(status='PASS_ALL_G2_SLOTS',G2_actual_PV_total_error_max_kw=max(float(r['PV_abs_max']) for r in rows),
        G2_PQ_balance_error_max=max(float(r['balance_abs_max']) for r in rows),
        G2_operating_solve_count=gates['G2']['operating_solve_count'])
    save('PV_MAPPING_AUDIT.json',pv_audit)
    eligible=[r for r in rows if r['target_70_85']=='True' and r['status']=='MEASURED_PASS']
    assert not eligible,'Review scenario selection explicitly if a target-eligible candidate appears'
    best={}
    for role in ('PLANNING','ACTUAL'):
        for kind in ('AIDC_ONLY','MESS_ONLY','JOINT'):
            options=[r for r in pilots if r['role']==role and r['control']==kind and r['physics_PASS']=='True']
            if options:best[role+'_'+kind]=min(options,key=lambda r:float(r['controlled_rho']))
    peaks=[]
    for key,b in best.items():
        rr=next(r for r in read(DOC/'CONTROL_PILOT_ARCHIVE_RECEIPTS.json') if r['role']==b['role'] and r['kind']==b['control'] and r['amplitude']==float(b['amplitude']) and not r['fresh'])
        vals=read(rr['rows_path']);offset=24 if b['role']=='ACTUAL' else 0
        peak=max(vals[offset:],key=lambda r:r['rho_global'])
        peaks.append(dict(role=b['role'],control=b['control'],amplitude=b['amplitude'],
            peak_slot=peak['evaluation_slot'],peak_line=peak['binding_line'],phase=peak['binding_physical_phase'],
            rho_global=peak['rho_global'],rho_MV=peak['rho_MV'],rho_LV=peak['rho_LV'],
            MESS_fleet_P_kw_at_peak=peak['fleet_P_kw'],AIDC_delta_kw_at_peak=peak['AIDC_delta_total_kw']))
    table('CONTROL_PILOT_NEW_BOTTLENECKS.csv',list(peaks[0]),peaks)
    electrical=list(csv.DictReader((DOC/'AIDC_MESS_SENSITIVITY.csv').open(encoding='utf-8')))
    electrical_summary=[]
    for prefix,kind in [('AIDC','P_PF095'),('STA','P'),('STA','Q')]:
        vals=[float(r['delta_global_pp']) for r in electrical if float(r['beta_BG'])==1.5 and r['role']=='ACTUAL'
              and r['site'].startswith(prefix) and r['perturbation']==kind and r['controls']=='NATIVE_AUTO'
              and (float(r['delta_demand_P_kw'])<0 or kind=='Q' and float(r['delta_demand_Q_kvar'])<0)]
        electrical_summary.append(dict(resource=prefix,perturbation=kind,size=5.,
            minimum_global_reduction_pp=min(vals),maximum_global_reduction_pp=max(vals),
            scope='electrical response only, not Job/SOC-feasible dispatch'))
    save('ELECTRICAL_PERTURBATION_SUMMARY.json',electrical_summary)
    save('FINAL_GO_NO_GO.json',dict(experiment_id='V2_add',decision='NO_QUALIFIED_HIGH_CONTROLLABILITY_SCENARIO',
        G1='PASS',G2='COMPLETE_ALL9_PHYSICS_AND_FRESH_PASS',G3=gates['G3']['status'],G4='NOT_VERIFIED_NOT_EXECUTED',
        reason='All preregistered beta candidates produce B0 Actual below 70%; no qualified primary in allowed range',
        primary_beta=None,diagnostic_beta=1.5,native_allowed=False,new_solver_calls=0,
        B0_operating_solves=gates['G2']['operating_solve_count'],
        pilot_best=best,extrapolation_is_not_an_executed_scenario=True))
    save('SELECTED_SCENARIO_FREEZE.json',dict(experiment_id='V2_add',status='NOT_SELECTED_NO_QUALIFIED_SCENARIO',
        beta_BG=None,PCC='original preregistered C2 unchanged',physical_configuration='PHYSICAL_CONFIGURATION_FREEZE.json',
        diagnostic_beta=1.5,selection_did_not_use_B1_B2_B3_performance=True,
        reason='No allowed beta reaches fallback 70% B0 Actual; no larger beta run'))
    comparisons=[]
    for role in ('PLANNING','ACTUAL'):
        base=float(read(DOC/'B0_CASE_SUMMARIES.json')['1.50'][role]['rho'])
        comparisons.append(dict(day='2025-05-01',arm='B0',beta_BG=1.5,role=role,rho=base,status='MEASURED_B0_DIAGNOSTIC_SCENARIO'))
        for arm in ('B1','B2','B3'):
            comparisons.append(dict(day='2025-05-01',arm=arm,beta_BG='',role=role,rho='',status='NOT_EXECUTED_G4_NO_PRIMARY_SCENARIO'))
    table('B0_B1_B2_B3_COMPARISON.csv',list(comparisons[0]),comparisons)
    table_text='| beta | Planning 최대 | Actual 최대/MV | Actual LV/Triplex | MV−LV |\n|---:|---:|---:|---:|---:|\n'
    table_text+=''.join(f"| {float(r['beta_BG']):.2f} | {float(r['planning_rho'])*100:.4f}% | {float(r['actual_rho'])*100:.4f}% | {float(r['actual_LV'])*100:.4f}% | {float(r['H_daily_actual'])*100:.4f}%p |\n" for r in rows)
    pv=gates['G1'];allslots=list(csv.DictReader((DOC/'MV_LV_LOADING_COMPARISON.csv').open(encoding='utf-8')))
    high=rows[-1];low=rows[-2];slope=(float(high['actual_rho'])-float(low['actual_rho']))/(float(high['beta_BG'])-float(low['beta_BG']))
    estimated=1.5+(.75-float(high['actual_rho']))/slope
    pilot_text='| 역할 | 진단 제어 | amplitude | B0 전역 최대 | Pilot 전역 최대 | 전역 감소 |\n|---|---|---:|---:|---:|---:|\n'
    for key,r in best.items():
        pilot_text+=f"| {r['role']} | {r['control']} | {float(r['amplitude']):.2f} | {float(r['baseline_rho'])*100:.4f}% | {float(r['controlled_rho'])*100:.4f}% | {float(r['delta_global_pp']):.4f}%p |\n"
    text=f'''# V2_add — IEEE8500 실제 B0 Scale Screening 및 제어 Pilot

**판정: NO_QUALIFIED_HIGH_CONTROLLABILITY_SCENARIO.** G1 매핑 PASS, G2 사전 후보9개 실제 AC/Fresh 완료, G3 MESS/Planning-AIDC 제한된 Pilot 완료·Actual 비영 AIDC witness 미검증, G4 최적화기 이식 미실행이다. 허용 beta 범위에서 B0 Actual이70%에 도달하지 않아 Primary Scenario를 선정하지 않았다. 이는 계통 매핑 실패나 제어력 부재 판정이 아니다. 진단용 beta1.50을 Primary로 동결하지 않는다.

## PV 매핑과 전력수지

PR197의 2,354개 Hot Leg Generator를 같은 버스/상, .12kV 단상 wye, Model1, Q=0, Vmin=.88/Vmax=1.05로 구현했다. 설치용량 총 {pv['PV_installed_kva']:.9f} kVA와 각 hot 설치용량은 그대로다. V44의 최종 PV 총량만 고정 설치용량 가중치로 배분하며 2.4kV Generator를 LV에 붙이거나 기존 PV를 중복 투입/부하 차감하지 않았다. 전 슬롯 최대 설치용량 대비 지령 비율은 {pv['per_slot_capacity_ratio_max']*100:.4f}%다.

각 beta Planning96/Actual Prefix24+96 및 독립 Fresh에서 실제 PV P/Q와 BG/PCC/Capacitor/손실/Source 전력수지를 측정했다. 기본 B0 전 케이스의 PV 실제 총량 최대 오차 {max(float(r['PV_abs_max']) for r in rows):.3g} kW, P/Q 전력수지 최대 절댓값 {max(float(r['balance_abs_max']) for r in rows):.3g} kW/kvar다. 용량 가중치가 고정되어 개별 PV 출력 제한도 전수 유지된다. 원본 입력·복원·SHA 59개 정적 검증은 재실행하지 않고 재사용했다.

## PCC/MESS와 고정 전압제어

C2의 AIDC12는 원래 3상 MV PCC에, STA12는 PR199의 동일한 12.47kV delta→480V grounded-wye 750kVA 전용 변압기에 연결했다. 원본 선로/변압기 정격을 수정하지 않았다. STA 접속 인터페이스는 기존 600kVA/721.688A이며 차량은 P±300kW/Q±250kvar/PCS400kVA와 원본 PCS16 부등식을 따른다. P/Q box는 PCS16 안에 있지만 전체 box의 모든 계통 운전점을 무조건 허용하지 않는다.

beta1.50에서 단일 STA 및 초기 8대 동시 P/Q corner를 Planning/Actual 각각 AC로 검사했다. 총 {len(endpoints)}개 순간점 중 {sum(r['physics_PASS']=='True' for r in endpoints)}개가 전체 물리 제약을 통과했다. 실패점은 STA_P300_Q250_AC_ENDPOINTS.csv에 그대로 남겼다. 이 순간 endpoint는 SOC/96슬롯 보장이 아니다. 아래 일일 Pilot은 8대 동시 접속·충방전·SOC·재충전·전체 계통 제약을 따로 만족한 사례다.

초기 MESS01~04의 STA01/12/08/06을 유지하고 추가 차량은 이미 제안한 STA02/03/04/05를 사용했다. 모두 서로 다른 기존 STA 포트다. 원본 Route Table의 8×96개 same-site stay 행에서 ETA/ready/이동 에너지 0을 확인했다. 교통망·ETA·에너지 재생성은 없다. 정지 Pilot은 제한된 진단 후보이며 이후 최적화기의 MOVE/STAY를 강제하지 않는다. 전용 변압기·인버터 접속은 연구용 정상상태 AC 모델 가정이며 현장 보호·GIS·제조사 인증으로 확대하지 않는다.

P5는 **Source1.04pu, RegControl12개 Vreg123.5V, CAPBank3 초기 OFF, 원래 CapControl9개**로 사전에 동결했다. 모든 beta/진단 비교군에서 동일하다. 시간별 Tap/Cap 상태는 B0_TAP_CAP_TIME_SERIES.csv에 있다. 각 Planning/Actual은 별도 초기 context를 사용하고 Actual은 Prefix24를 포함해 native 제어 상태를 이어간다. Fresh는 새 context로 동일 순서를 독립 재생한다.

IEEE123의 Planning7/Actual43/SVR12 하드웨어를 숫자 그대로 복사하지 않았다. 이 단계는 PR197/199의 P5 native **static automatic settling**을 사용한다. V44 Actual의 지연을 가진 TIME 제어·Actual 전용 SVR12와 물리 의미가 다르며, 해당 TIME/지연 계약과 IEEE8500의 최종 알고리즘 검증 연결은 G4 잔여 과제다. 이번 결과를 기존 IEEE123 물리 계약과 완전히 같은 설정이라고 주장하지 않는다.

## 실제 B0 결과

{table_text}

전체 원본 3,703개 선로의 실제 상 도체와 양단을 목적함수/검증에 포함했다. 원래 disabled인 스위치 선로 5개도 축에서 보존하고 전류0으로 포함했다. 원래 Kron-reduced Triplex의 별도 정격이 없는 가상 neutral은 새 정격 도체로 만들지 않았다. 원래 Triplex hot 두 상과 원본 NormalAmps는 모두 포함한다. Primary/MV와 LV 지표는 원본 전압 계급 분류를 따른다.

모든 9개 beta에서 선로·노드 전압·변압기·포트 위반은 0이었다. 전체 전압 범위는 {min(min(float(r['planning_Vmin']),float(r['actual_Vmin'])) for r in rows):.6f}~{max(max(float(r['planning_Vmax']),float(r['actual_Vmax'])) for r in rows):.6f} pu(Planning/Actual 전체와 Prefix 포함)다. 독립 Fresh {gates['G2']['independent_Fresh_pairs']}쌍이 전수 통과했으며 B0 운전 Solve는 {gates['G2']['operating_solve_count']}회다. Source 초기화용 solve는 이 횟수와 별개다.

75~85% 및 완화한70~85%에 해당하는 후보가 없다. V44 최종 BG 피크는 약2.713MW이며 beta1.50에서도 약4.069MW다. 원본 IEEE8500의 약10.773MW 명목 부하를 운영 크기로 다시 더하거나 PR197 BG=.552/PR199 BG=.85를 beta와 혼용하지 않았다. 작은 입력 총량이 낮은 혼잡 수준의 주요 원인이다. 마지막 두 beta 사이의 국부 secant만 외삽하면75%에는 beta약{estimated:.2f}가 필요하지만, 이는 Tap/Cap 및 병목 전환을 검증하지 않은 추정치다. 범위 밖 AC는 실행하지 않았다.

## 실제 전기적 민감도와 96슬롯 Pilot

beta1.00과1.50의 Planning/Actual B0 피크에서 24 PCC를 ±5kW/kvar로 교란했다. AIDC의 P 교란은 PF=.95의 Q를 함께 적용했다. 고정 Tap/Cap과 native auto 응답을 구분했고 무제어 재계산 noise를 따로 기록했다. 이 국부 전기적 교란을 Job/SOC 실현 가능한 제어량으로 해석하지 않는다.

beta1.50 Actual native-auto에서 AIDC5kW 감소(PF연동)의 전역 감소는 {electrical_summary[0]['minimum_global_reduction_pp']:.6f}~{electrical_summary[0]['maximum_global_reduction_pp']:.6f}%p, STA5kW 주입은 {electrical_summary[1]['minimum_global_reduction_pp']:.6f}~{electrical_summary[1]['maximum_global_reduction_pp']:.6f}%p, STA5kvar 주입은 {electrical_summary[2]['minimum_global_reduction_pp']:.6f}~{electrical_summary[2]['maximum_global_reduction_pp']:.6f}%p다. 무제어 재계산 noise의 최대 절댓값은 약4.08e-8%p다. beta1.50 Actual 최상위 병목의 위상적 하류에는 AIDC12/STA12가 모두 있지만, 이는 실제 가용 Job이나 하루 SOC 제어량을 보장하지 않는다. Top20별 하류 PCC 목록을 별도 CSV로 남겼다.

별도의96슬롯 Pilot은 beta1.50에서 AIDC-only/MESS-only/Joint를 비교했다. MESS는 사전에 고정한08~15슬롯 충전,68~75슬롯 방전의 원래 C2 진단 시간대를 재사용하고, V44 SOC440~1080/초기·종단760kWh/효율.95로 amplitude .25/.50/1.00을 검사했다. 1.00의 차량당 충전168.421kW/방전152kW, SOC760→1080→760이며 각 amplitude는 같은 SOC 보존 비율이다. 모든 충전 Rebound와 다른 선로로의 병목 전환을 일일 전역 최대값에 포함했다. 차량당300kW나 합계2.4MW를 하루 보장 운전량으로 사용하지 않았다.

{pilot_text}

Actual MESS 최선 후보의 새 최대값은 슬롯76(19:00), 같은 MV Line.ln5775442-1 A상이다. 고정 방전 구간68~75가 끝난 뒤의 피크로 넘어가 전역 개선이0.2018%p에 그쳤다. LV floor로 전환된 결과가 아니다. 이 제한된 진단에서 선호 목표1%p 감소를 달성하지 못했으며 더 넓은 최적 운전의 상한을 뜻하지 않는다. amplitude1.00의8대 합계 충전/방전 에너지는2694.7368/2432kWh로 초기·종단 SOC를 함께 만족했다.

AIDC는 과거 accepted라는 이유만으로 이전 스케줄을 실행 가능하다고 간주하지 않았다. 과거 Planning 후보는 현재 원본 WINDOWS의 허용 시작점과 불일치414개, 과거 Actual 후보는 원래 의도적 지연 예산 초과192개가 발견되어 둘 다 제외했다. 이는 원본 캠페인의 모든 acceptance 변환을 재감사한 판정이 아니라, 이번 입력에 그대로 옮길 후보가 strict 조건을 통과하지 못했다는 의미다. 제약을 완화하거나 새 IEEE8500 B1 성과로 쓰지 않았다.

Planning은 원본 B0 Reference에서 같은 사이트 단일-GPU Job {len(job['planning_job_changes'])}개만 허용 시작점/서비스 슬롯/사이트 용량/WAN0 및 Rebound를 보존한 제한된 지연 witness로 구성했다. GPUh 변화는 {job['planning_GPUh_change']:.6f}이고 원래 Planning C1 affine envelope를 {job['planning_baseline_C1_reproduction_error_kw']:.3g}kW 오차로 재현했다. Actual의 exact C1로 Planning 모델을 바꾸지 않았다.

Actual은 원본 FCFS를 바탕으로 같은 사이트의 단일-GPU Job만 최대1개/사이트, 원래 허용 시작점과 QoS/Deadline/사이트 용량을 만족하는1~4슬롯 지연으로 제한해 확인했다. 피크 겹침 후보가 없어 AC 효과를 보지 않는 사전 기록된 사전순 하루 전체 후보도 확인했다. 실제 채택 Job 변경은 {len(job['actual_job_changes'])}개로 비영 Actual witness를 인증하지 못했다. 표의 Actual AIDC-only는 원본 FCFS 재생, Actual Joint는 MESS+변경하지 않은 AIDC다. 성공적인 비영 AIDC/공동 제어로 해석하지 않는다. GPUh 변화 {job['actual_GPUh_change']:.6f}, 이 제한 후보의 피크 감소는 {job['actual_peak_flexible_kw_observed']:.6f}kW이며 최대 사이트 감소/되받음은 {job['actual_max_site_power_reduction_kw']:.6f}/{job['actual_max_site_rebound_kw']:.6f}kW다. 이는 실제 최대 AIDC 제어력이0이라는 상한 증명이 아니다. 같은 exact C1을 실제 as-of 날씨에 적용해 무제어 전력을 {job['actual_baseline_C1_reproduction_error_kw']:.3g}kW 오차로 재현했다. Job 수1,024를 전력량으로 치환하지 않았다. GPU gang>1·pre-site·checkpoint migration 등 더 넓은 실제 Job 제어 witness는 잔여 과제다.

상기 개선은 **AC 진단 Pilot**이며 B3 최적화 성과가 아니다. 관측된 가장 좋은 제한 후보와 최적가능량을 구분한다. 각각의 가장 좋은 물리 PASS 후보를 새 context Fresh로 재검증했다.

## 다음 단계

현재 허용 범위에는 Primary Scenario가 없다. beta/PCC/차량 정격·Job을 임의 변경하지 않았다. G4는 기존 r043 A1/M1/A2/M2, K48, Beam/Joint MILP의8대 변수·Route/SOC/PQ/입출력·독립 FULL 검증기, 전기적 전체 민감도/행 생성, P5 및 Actual TIME 계약, UB/LB/Gap/규모 측정 연결이 남는다. A1/M1/A2/M2나 장시간 Native Solver는0회다. 기존 V44/V1_add 소스·Worker·Monitor·예산·결과는 변경하지 않았다.
'''
    (DOC/'FINAL_V2_ADD_REVIEW_KO.md').write_text(text,encoding='utf-8')
    (DOC/'IEEE8500_BALANCED_SOURCE_AUDIT.md').write_text((DOC/'IEEE8500_BALANCED_SOURCE_AUDIT.md').read_text(encoding='utf-8').split('\n## Phase2')[0]+'''\n## Phase2 G1-G3 갱신

공식 원본 계통 복원/SHA 검증을 재사용했다. PV/PCC/P5 Adapter의 물리 매핑을 G1에서 해소하고 실제 B0/독립 Fresh와 제어 Pilot을 실행했다. 최신 상태와 전압제어 의미 차이는 FINAL_V2_ADD_REVIEW_KO.md 및 PREFLIGHT_GATES.json을 따른다. 초기 보고서의 매핑 미해결 문장은 당시 준비 단계의 기록이며 현재 Gate를 뜻하지 않는다.
''',encoding='utf-8')
    (DOC/'README_KO.md').write_text('''# V2_add — PR236

실제 IEEE8500 Balanced G1 매핑·G2 B0 9개 beta·G3 제어 Pilot을 완료했다. 원래 59개 정적 검증은 재사용했다.

- [최신 한국어 결과](FINAL_V2_ADD_REVIEW_KO.md)
- [분리한 G1~G4 Gate](PREFLIGHT_GATES.json)
- [실제 Scale별 결과](BACKGROUND_SCALE_SCREENING.csv)
- [실행 가능한 Pilot의 전역 효과](CONTROL_PILOT_GLOBAL_COMPARISON.csv)
- [원본 설정 사전 동결](PHYSICAL_CONFIGURATION_FREEZE.json)

G1 PASS / G2 완료 / G3 MESS·Planning 제한 witness 완료/Actual 비영 AIDC 미검증 / G4 미실행. 허용 beta의 Actual B0가 모두70% 미만이므로 Primary Scenario는 없다.

실행 순서: `python -B -m v2_add_preflight.gates` → `screen` → `pilot` → `results`.
`screen`은 완료 case의 receipt를 재사용한다. `audit`/`verify`는 초기 준비 단계 전용이며 현 단계에서 재실행하지 않는다.
조밀한 원본 AC 배열은 독립 V2_add_runtime/phase2 아래에 보존하며 경로·SHA와 재계산 가능한 지표를 PR에 기록한다. 장시간 Native/Solver 호출은 없다.
''',encoding='utf-8')
    save('FIGURE_READINESS.json',dict(topology='prior original3703-line figure retained',PCC='fixed C2 mapping',
        MV_LV_loading_heatmap='B0_LOADING_HEATMAP_TOP20_PCC.svg',scale_MV_LV='B0_SCALE_MV_LV.svg',
        global_control='FEASIBLE_PILOT_GLOBAL_REDUCTION.svg',critical_lines_PCC='B0_LOADING_HEATMAP_TOP20_PCC.svg',
        pilot_timeseries='ACTUAL_CONTROL_PILOT_TIME_SERIES.svg',B0_B1_B2_B3_figures='NOT_EXECUTED_G4',image_generation_AI_used=False))
    (DOC/'PR_BODY.md').write_text(f'''V2_add PR236의 G1 물리 매핑을 해소하고 G2 실제 B0 Scale Screening 및 G3 제한된 제어 Pilot을 추가했습니다. 기존59개 정적 검증/190행 SHA 및 공식 계통 복원은 재사용했습니다.

- PV: PR197의2354개 Hot Leg/.12kV/설치용량/Model1/Q0를 유지하고 V44의 총량을 고정 설치용량 가중치로 배분합니다. C2 AIDC12/STA12와 기존750kVA 변압기, V44 MESS8 P300/Q250/PCS400/SOC440~1080/초기종단760을 사용합니다.
- P5 source1.04/12Vreg123.5/CAPBank3 초기OFF를 모든 beta에 고정했습니다. IEEE123 Planning7/Actual43 및 Actual TIME/SVR12와의 차이를 명시했습니다. 연구용 정상상태 AC 가정이며 field 인증이 아닙니다.
- beta9개 × Planning96/Actual120 × 독립Fresh: **{gates['G2']['operating_solve_count']} 운영 AC**, Fresh18쌍 PASS. 모든 기본 케이스의 전압/선로/변압기/포트 위반0. 모든 원본3703개 선로/1177Triplex/양단/상 포함, source disabled5개도 보존했습니다.
- Actual B0: beta1.00 **{float(rows[0]['actual_rho'])*100:.4f}%**, beta1.50 **{float(rows[-1]['actual_rho'])*100:.4f}%**. 모든 beta가70% 미만이므로 **NO_QUALIFIED_HIGH_CONTROLLABILITY_SCENARIO**입니다. 후보 범위 밖 배율을 실행하지 않았고 Primary를 동결하지 않았습니다.
- beta1.00/1.50의 고정/자동제어 민감도와 beta1.50의 제한된 SOC·Job·QoS·Rebound Pilot을 구분했습니다. 과거 후보는 Planning 허용 시작점 불일치414개/Actual 지연 예산 초과192개로 제외했습니다. 새 Planning witness Job{len(job['planning_job_changes'])}개는 GPUh 변화0으로 검증했으나 Actual 비영 AIDC witness는 미인증입니다. Actual AIDC-only는 FCFS 재생, Joint는 MESS+변경 없는 AIDC이며 공동제어 추가효과로 주장하지 않습니다. Pilot을 B3로 표시하지 않습니다.

G1 PASS / G2 COMPLETE / G3 PARTIAL(MESS·Planning witness PASS, Actual 비영 AIDC NOT_VERIFIED) / G4 NOT_VERIFIED. A1/M1/A2/M2 및 장시간 Native0회. 기존 V44/V1_add Source·Worker·Monitor·예산은 변경0입니다. 전체 scalar/Top20/TapCap CSV, raw AC 경로/SHA, 독립 saved-array 재산술, Python SVG/PNG4쌍 및 실패 endpoint를 보존했습니다.

진입점: docs/v2_add/README_KO.md. 핵심 보고: FINAL_V2_ADD_REVIEW_KO.md, PREFLIGHT_GATES.json, BACKGROUND_SCALE_SCREENING.csv. Draft 유지; merge/Production 승격 요청 없음.
''',encoding='utf-8')


def main():
    assert read(DOC/'PREFLIGHT_GATES.json')['G3']['status'] in ('COMPLETE_LIMITED_WITNESSES','PARTIAL_MESS_PASS_ACTUAL_AIDC_NONZERO_NOT_VERIFIED')
    review_arrays();topology_influence();figures();reports()
    print('Numerical review and V2_add report complete')


if __name__=='__main__':main()
