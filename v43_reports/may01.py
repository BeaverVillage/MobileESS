"""Evidence-only May01 tables and plot; unavailable measurements stay empty."""
from pathlib import Path
import csv

from v43.common import DOC,read,record,verify_records,now

ATTEMPTS={'B1':Path('D:/MobileESS_V43/runtime/gate_b_c0_c1_actual96_attempt001'),
    'B0':Path('D:/MobileESS_V43/runtime/may01_B0_C0_C1_actual96_attempt002')}


def table(name,rows):
    with (DOC/name).open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def run():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    gold=read(DOC/'GOLDEN003_CERTIFIED_NUMERICAL_CASE.json')
    verify_records([gold['result'],gold['native_ledger'],gold['planning_freeze']])
    summary=[];fresh_rows=[];runtime=[];curves={};metrics={}
    for arm in ('B0','B1','B2','B3'):
        row=dict(arm=arm,day='2025-05-01',Planning_status='NOT_RUN',Planning_FULL='NOT_CERTIFIED',
            Planning_UB=None,Planning_LB=None,Planning_Global_Gap_percent=None,
            Planning_linear_P1_percent=None,Golden_fixed_decision_Fresh_peak_percent=None,
            Planning_Fresh_peak_line_phase_loading_percent=None,
            C0_Actual96='NOT_RUN',C0_Fresh96='NOT_RUN',C0_peak_line_phase_loading_percent=None,
            C1_Actual96='NOT_RUN',C1_Fresh96='NOT_RUN',C1_peak_line_phase_loading_percent=None,
            C0_Unknown_Submitted=None,C0_Unknown_Started=None,C0_Unknown_Completed=None,C0_Unknown_Carryout=None,
            C1_Unknown_Submitted=None,C1_Unknown_Started=None,C1_Unknown_Completed=None,C1_Unknown_Carryout=None,
            C0_Presite_Eligible=None,C0_Presite_Started=None,C0_Presite_Changed_GPUh=None,
            C1_Presite_Eligible=None,C1_Presite_Started=None,C1_Presite_Changed_GPUh=None,
            Unknown_Source_permission='STRICT_SOURCE',initial44='MODEL_ASSUMED',
            FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED')
        if arm=='B1':
            row.update(Planning_status='A1_GOLDEN003_PASS',Planning_FULL='PASS',
                Planning_UB=gold['UB'],Planning_LB=gold['independent_Global_LB'],
                Planning_Global_Gap_percent=gold['global_gap_percent'],Planning_linear_P1_percent=100*gold['UB'],
                Golden_fixed_decision_Fresh_peak_percent=100*gold['Fresh_AC96']['rho_max_AC'])
            runtime.append(dict(arm=arm,stage='A1',scope='PLANNING_AND_FIXED_DECISION_FRESH',Native_seconds=gold['Native_seconds'],
                build_seconds=gold['build_wall_seconds'],wall_seconds=gold['total_wall_seconds'],validation_seconds=None,
                note='Recorded Golden003; wall residual is not relabelled validation'))
        elif arm=='B0':row.update(Planning_status='REFERENCE_NATIVE0_PASS_AC_PENDING',Planning_FULL='REFERENCE_NO_OPTIMIZATION')
        attempt=ATTEMPTS.get(arm)
        independent=attempt/'INDEPENDENT_ACTUAL_REPORT.json' if attempt else None
        audited={} if not independent or not independent.exists() else {s['variant']:s for s in read(independent)['summaries']}
        progress=read(attempt/'progress.json') if attempt and (attempt/'progress.json').exists() else {}
        planning=attempt.with_name(attempt.name+'.PLANNING_AC96.json') if attempt else None
        if planning and planning.exists():
            value=read(planning);steps=value['physical_steps']
            row.update(Planning_status='REFERENCE_FRESH_PASS' if value['PASS'] else 'PHYSICAL_FAIL',
                Planning_Fresh_peak_line_phase_loading_percent=100*max(s['maximum_phase_line_loading'] for s in steps))
            curves[arm,'PLANNING']=[100*s['maximum_phase_line_loading'] for s in steps]
        for variant in ('C0','C1'):
            source=attempt/variant/'RESULT.json' if attempt else None
            status='NOT_RUN';peak=None;vmin=None;vmax=None;converged=None;violations=None
            if attempt and not (attempt/'RESULT.json').exists() and progress.get('variant')==variant:
                row[variant+'_Actual96']='RUNNING'
            if source and source.exists():
                result=read(source);data=read(attempt/variant/'FRESH_ORIGINAL7_AC.json');steps=data['physical_steps'][24:]
                status='PASS' if result['Fresh96_physical_PASS'] else 'PHYSICAL_FAIL'
                peak=100*max(s['maximum_phase_line_loading'] for s in steps)
                vmin=min(s['voltage_min_pu'] for s in steps);vmax=max(s['voltage_max_pu'] for s in steps)
                converged=sum(s['converged'] for s in steps)
                violations=sum(sum(s['violations'].values()) for s in steps)
                curves[arm,variant]=[100*s['maximum_phase_line_loading'] for s in steps]
                metrics[arm,variant]=peak
                row[variant+'_Actual96']='PASS' if result['Actual96_execution_PASS'] else 'FAIL'
                row[variant+'_Fresh96']=status;row[variant+'_peak_line_phase_loading_percent']=peak
                if variant in audited:
                    a=audited[variant]
                    row.update({variant+'_Unknown_Submitted':a['Unknown_Submitted_UID'],
                        variant+'_Unknown_Completed':a['Unknown_Completed_UID'],variant+'_Unknown_Carryout':a['Unknown_Terminal_Carryout_UID'],
                        variant+'_Presite_Eligible':a['Pre_site_Eligible_UID'],variant+'_Presite_Started':a['Pre_site_Actually_Started_UID'],
                        variant+'_Presite_Changed_GPUh':a['Pre_site_Changed_GPUh']})
                    event=read(attempt/variant/'ACTUAL_EVENT_LEDGERS.json')
                    row[variant+'_Unknown_Started']=sum(r['origin_unknown'] and r['admitted_time'] is not None for r in event['queue_ledger'])
                runtime.append(dict(arm=arm,stage=variant,scope='PREFIX24_ACTUAL96_PLUS_FRESH',Native_seconds=0.,
                    build_seconds=None,wall_seconds=result['elapsed_wall_seconds'],validation_seconds=None,
                    note='Controller and Current AC/Fresh wall; no Global MILP'))
            fresh_rows.append(dict(arm=arm,variant=variant,status=status,converged_slots=converged,
                peak_line_phase_loading_percent=peak,Vmin_pu=vmin,Vmax_pu=vmax,total_physical_violations=violations,
                original_RegControl=7,control_contract='SNAPSHOT_STATIC',delayed_TIME_actuation='NOT_CERTIFIED'))
        summary.append(row)
    comparison=[]
    for variant in ('C0','C1'):
        for left,right,effect in (('B1','B0','AIDC'),('B2','B0','MESS'),('B3','B1','JOINT_VS_AIDC'),('B3','B2','JOINT_VS_MESS')):
            complete=(left,variant) in metrics and (right,variant) in metrics
            comparison.append(dict(scope='ACTUAL_DDAY96_FRESH',comparison=left+'-'+right,variant=variant,
                effect=effect,status='MEASURED' if complete else 'NOT_RUN',
                difference_percentage_points=metrics[left,variant]-metrics[right,variant] if complete else None))
    for arm in ('B0','B1','B2','B3'):
        complete=all((arm,v) in metrics for v in ('C0','C1'))
        comparison.append(dict(scope='ACTUAL_DDAY96_FRESH',comparison=arm+' C1-C0',variant='C1-C0',effect='UNKNOWN_PRESITE',
            status='MEASURED' if complete else 'NOT_RUN',difference_percentage_points=metrics[arm,'C1']-metrics[arm,'C0'] if complete else None))
    table('V43_MAY01_FOUR_ARM_RESULTS.csv',summary)
    table('V43_MAY01_C0_C1_ACTUAL_COMPARISON.csv',comparison)
    table('V43_MAY01_FRESH_AC96_RESULTS.csv',fresh_rows)
    table('V43_MAY01_RUNTIME_BREAKDOWN.csv',runtime)
    fig,axes=plt.subplots(1,2,figsize=(12,4),sharey=True)
    for ax,variant in zip(axes,('C0','C1')):
        for arm in ('B0','B1','B2','B3'):
            if (arm,variant) in curves:ax.plot([t/4 for t in range(96)],curves[arm,variant],label=arm)
        ax.set(title='Actual '+variant,xlabel='May01 AEST hour',xlim=(0,24));ax.grid(alpha=.25)
        if ax.lines:ax.legend()
        else:ax.text(.5,.5,'NOT RUN / IN PROGRESS',ha='center',transform=ax.transAxes)
    axes[0].set_ylabel('Original maximum line/phase loading (%)')
    fig.suptitle('V43 May01: available Fresh96 measurements; missing arms are not zero')
    fig.tight_layout();fig.savefig(DOC/'V43_MAY01_ACTUAL_LINE_LOADING.png',dpi=160);plt.close(fig)
    text='# V43 May01 중간 검토\n\n'+now()+' 기준. 네 비교군 전체 완료가 아니다.\n\n'
    text+='Golden003 B1 A1은 Original FULL/독립 Gap/Fresh96 PASS이고 재실행하지 않는다. B3 A2 인증으로 이전하지 않는다. '
    text+='CSV는 존재하는 새 실행 증거만 집계하고 미실행 칸은 비워 둔다. 차이는 %p이며 Planning과 Actual은 별도다.\n\n'
    text+='Golden 고정 결정 Fresh는 이벤트 Actual과 다르며 원본 receipt의 ACTUAL namespace를 보존한다. 이를 Planning forecast Fresh loading으로 옮기지 않았다. Planning 선형 P1과도 별도 열이다.\n\n'
    for row in summary:text+=f"- {row['arm']}: Planning {row['Planning_status']}; C0 {row['C0_Actual96']}/{row['C0_Fresh96']}; C1 {row['C1_Actual96']}/{row['C1_Fresh96']}\n"
    text+='\nSource 권한·44 MODEL_ASSUMED·R1 미실행·R2 HOLD·FULL·Global Gap·Actual·Fresh를 분리한다. Forecast causal availability와 delayed TIME actuation은 NOT_CERTIFIED다. May02~31은 실행하지 않는다.\n'
    (DOC/'V43_MAY01_FINAL_REVIEW_KO.md').write_text(text,encoding='utf8')
    return summary


if __name__=='__main__':print(run())
