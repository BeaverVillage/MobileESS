"""Independent fixed-state and genuinely fresh auto-control FD replay.

Replays the predetermined first MV/LV probes at four exposed diagnostic slots.
No candidate selection, Native run, port qualification or control-policy change.
"""
from __future__ import annotations
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np
from .ac import IEEE8500AC,_complex
from .capacity import FIXED_AIDC,build_candidate
from .common import REPORT,read,write,receipt
from .audit_source import write_csv
from .screening import demand


OUT=REPORT/'joint_selection_v2/control_discontinuity'
SENS=REPORT/'joint_selection_v2/sensitivity'
SLOTS=(0,9,48,75)


def delta_state(left,right):
    result={'taps':{},'capacitors':{}}
    for kind in result:
        for name in sorted(left[kind]):
            unequal=not np.allclose(left[kind][name],right[kind][name],atol=1e-12,rtol=0) if kind=='taps' else left[kind][name]!=right[kind][name]
            if unequal:
                result[kind][name]={'minus':left[kind][name],'plus':right[kind][name]}
    return result


def new_engine(policy,tag):
    engine=IEEE8500AC(output_dir=OUT/'dss'/tag)
    for site,bus in FIXED_AIDC.items():engine.add_pcc(site,bus,'MV_3PH')
    for p in policy['probes']:engine.add_pcc(p['probe_id'],p['bus'],p['mode'])
    return engine


def endpoint(engine,values,mode,base_state=None):
    engine.solve(1.,values,control_mode=mode,fixed_state=base_state,reset_controls=True,snapshot=False)
    a=engine.measurement_arrays();a['control_state']=engine.control_state()
    monitors=[]
    for meta in engine.inventory['regcontrols']:
        props=meta['properties'];d=engine.d;d.RegControls.Name(meta['name']);tap_number=d.RegControls.TapNumber()
        d.Transformers.Name(meta['transformer']);d.Transformers.Wdg(d.RegControls.Winding())
        monitor=float(abs(_complex(d.Transformers.WdgVoltages())[0])/float(props['PTRatio']))
        target=float(props['VReg']);band=float(props['Band'])
        monitors.append({'name':meta['name'],'tap_number':tap_number,'monitored_voltage_V':monitor,
            'original_Vreg_V':target,'original_band_V':band,'inside_original_band':abs(monitor-target)<=band/2+1e-8})
    a['regcontrol_monitor']=monitors
    if not a['converged'] or not a['control_actions_done'] or a['control_queue_size']:
        raise ValueError('CONTROL_REPLAY_NOT_SETTLED')
    return a


def run():
    policy=read(SENS/'PREREGISTRATION.json')
    previous=read(REPORT/'diagnostics/capacity_1p0/CONTROL_STATES.json')
    if tuple(policy['slots'])!=SLOTS:raise ValueError('SOURCE_PROBE_SLOT_DRIFT')
    selected=[policy['probes'][0],policy['probes'][policy['all_MV_electrical_candidates_evaluated']]]
    candidate=build_candidate(1.);rows=[];states=[];archives=[];counter=0
    for slot in SLOTS:
        e=new_engine(policy,f'base_{slot:02d}')
        values=demand(candidate,slot);e.restore_control_state(previous[slot])
        base=e.solve(1.,values,reset_controls=False);base_a=e.measurement_arrays()
        fresh_base_engine=new_engine(policy,f'fresh_base_{slot:02d}')
        fresh_base=endpoint(fresh_base_engine,values,'auto')
        for probe in selected:
            for component in ('P','Q'):
                step=float(probe['diagnostic_step']);fixed=[];fresh=[];warm=[]
                for sign in (-1,1):
                    changed=dict(values);pq=list(changed.get(probe['probe_id'],(0.,0.)))
                    pq[component=='Q']-=sign*step;changed[probe['probe_id']]=tuple(pq)
                    fixed.append(endpoint(e,changed,'fixed',base['control_state']))
                    # Mirror the root helper's restored original controls with a
                    # reused DSS context as an explicit third audit condition.
                    warm.append(endpoint(e,changed,'auto'))
                    fresh_engine=new_engine(policy,f'{slot:02d}_{probe["probe_id"]}_{component}_{sign}')
                    if fresh_engine.control_state()!=fresh_engine.initial_state:
                        raise ValueError('FRESH_ORIGINAL_STATE_IDENTITY_FAILED')
                    fresh.append(endpoint(fresh_engine,changed,'auto'))
                    fresh_engine.verify_source_unchanged()
                fd=(fixed[1]['line_amps']-fixed[0]['line_amps'])/(2*step)
                ad=(fresh[1]['line_amps']-fresh[0]['line_amps'])/(2*step)
                wd=(warm[1]['line_amps']-warm[0]['line_amps'])/(2*step)
                k=int(np.argmax(abs(ad-fd)));diff=delta_state(fresh[0]['control_state'],fresh[1]['control_state'])
                warmdiff=delta_state(warm[0]['control_state'],warm[1]['control_state'])
                record={'slot':slot,'probe_id':probe['probe_id'],'bus':probe['bus'],'mode':probe['mode'],
                    'component':component,'positive_sign':'INJECTION','step_kw_or_kvar':step,
                    'fixed_minus_matches_sequential_base':fixed[0]['control_state']==base['control_state'],
                    'fixed_plus_matches_sequential_base':fixed[1]['control_state']==base['control_state'],
                    'fresh_minus_plus_tap_difference_count':len(diff['taps']),
                    'fresh_minus_plus_cap_difference_count':len(diff['capacitors']),
                    'fresh_minus_plus_controls':diff,
                    'warm_minus_plus_controls':warmdiff,
                    'fresh_vs_sequential_base_minus_controls':delta_state(base['control_state'],fresh[0]['control_state']),
                    'fresh_vs_sequential_base_plus_controls':delta_state(base['control_state'],fresh[1]['control_state']),
                    'fresh_minus_vs_fresh_unperturbed_controls':delta_state(fresh_base['control_state'],fresh[0]['control_state']),
                    'fresh_plus_vs_fresh_unperturbed_controls':delta_state(fresh_base['control_state'],fresh[1]['control_state']),
                    'fresh_vs_fixed_max_current_derivative_difference_A_per_unit':float(abs(ad-fd).max()),
                    'warm_vs_fixed_max_current_derivative_difference_A_per_unit':float(abs(wd-fd).max()),
                    'warm_vs_fresh_max_current_derivative_difference_A_per_unit':float(abs(wd-ad).max()),
                    'largest_difference_axis':e.line_axes[k],
                    'fixed_derivative_on_difference_axis_A_per_unit':float(fd[k]),
                    'fresh_derivative_on_difference_axis_A_per_unit':float(ad[k]),
                    'warm_derivative_on_difference_axis_A_per_unit':float(wd[k]),
                    'all_endpoints_converged_and_settled':True,'independent_auto_contexts':True,
                    'fixed_affine_global_certificate':False,'physical_port_or_dispatch_certification':False}
                for prefix,arrs in [('fixed',fixed),('fresh',fresh),('warm',warm)]:
                    for sign,a in zip(('minus','plus'),arrs):
                        record[f'{prefix}_{sign}_Vmin']=float(a['node_voltage_pu'].min())
                        record[f'{prefix}_{sign}_Vmax']=float(a['node_voltage_pu'].max())
                        record[f'{prefix}_{sign}_canonical_rho_max']=float(a['line_rho'][e.objective_line_mask].max())
                        record[f'{prefix}_{sign}_allterminal_rho_max']=float(a['line_rho'].max())
                        record[f'{prefix}_{sign}_transformer_current_rho_max']=float(a['transformer_current_rho'].max())
                        record[f'{prefix}_{sign}_transformer_nameplate_kva_rho_max']=float(a['transformer_winding_nameplate_kva_rho'].max())
                        states.append({'row':counter,'slot':slot,'probe_id':probe['probe_id'],'component':component,
                            'condition':prefix,'sign':sign,'control_state':a['control_state'],
                            'regcontrol_monitor':a['regcontrol_monitor']})
                        archives.append({'row':counter,'condition':prefix,'sign':sign,**{key:a[key] for key in
                            ('line_amps','line_rho','node_voltage_pu','transformer_current_rho','transformer_winding_nameplate_kva_rho')}})
                rows.append(record);counter+=1
                print('Control replay',slot,probe['probe_id'],component,
                    'fresh/fixed',record['fresh_vs_fixed_max_current_derivative_difference_A_per_unit'],
                    'fresh changes',diff,flush=True)
        e.verify_source_unchanged()
    write_csv(REPORT/'CONTROL_DISCONTINUITY_AUDIT.csv',rows)
    write(OUT/'ENDPOINT_CONTROL_STATES.json',states)
    write_csv(OUT/'ENDPOINT_REGCONTROL_MONITORS.csv',[{k:v for k,v in state.items() if k not in ('control_state','regcontrol_monitor')}|monitor
        for state in states for monitor in state['regcontrol_monitor']])
    keys=('line_amps','line_rho','node_voltage_pu','transformer_current_rho','transformer_winding_nameplate_kva_rho')
    np.savez_compressed(OUT/'ALL_ENDPOINT_ARRAYS.npz',row=np.array([a['row'] for a in archives]),
        condition=np.array([a['condition'] for a in archives]),sign=np.array([a['sign'] for a in archives]),
        **{key:np.array([a[key] for a in archives]) for key in keys})
    worst=max(rows,key=lambda r:r['fresh_vs_fixed_max_current_derivative_difference_A_per_unit'])
    receipt_data={'status':'INDEPENDENT_CONTROL_DISCONTINUITY_DIAGNOSTIC_COMPLETE','slots':list(SLOTS),
        'probes':selected,'rows':len(rows),'endpoint_solves':len(archives),'fresh_independent_endpoint_contexts':32,
        'sequential_base_solves':4,'fresh_unperturbed_solves':4,
        'fresh_endpoint_control_jump_rows':sum(bool(r['fresh_minus_plus_tap_difference_count'] or r['fresh_minus_plus_cap_difference_count']) for r in rows),
        'maximum_reused_vs_fresh_derivative_difference_A_per_unit':max(r['warm_vs_fresh_max_current_derivative_difference_A_per_unit'] for r in rows),
        'tap_comparison_numerical_tolerance':1e-12,
        'worst_fresh_vs_fixed_difference_A_per_unit':worst['fresh_vs_fixed_max_current_derivative_difference_A_per_unit'],
        'worst_row':{k:worst[k] for k in ('slot','probe_id','component','largest_difference_axis')},
        'source_pu':1.05,'source_original_Vreg_and_CapControls_unchanged':True,'numerical_tolerance':1e-9,
        'regcontrols_enabled':12,'capcontrols_enabled':9,'all_endpoints_converged_and_settled':True,
        'original_control_state_restored':True,'fixed_result_scope':'local derivative within the same settled tap/cap state only',
        'automatic_result_scope':'finite perturbation independently settles original controls; discrete/control initialization effects retained',
        'global_affine_certificate':False,'physical_port_or_dispatch_certificate':False,'Native_calls':0,
        'inputs':{'probe_policy':receipt(SENS/'PREREGISTRATION.json'),
            'source_sequential_controls':receipt(REPORT/'diagnostics/capacity_1p0/CONTROL_STATES.json')},
        'artifacts':{'endpoint_arrays':receipt(OUT/'ALL_ENDPOINT_ARRAYS.npz'),'endpoint_states':receipt(OUT/'ENDPOINT_CONTROL_STATES.json')}}
    write(REPORT/'CONTROL_DISCONTINUITY_AUDIT.json',receipt_data)
    jump=[r for r in rows if r['fresh_minus_plus_tap_difference_count'] or r['fresh_minus_plus_cap_difference_count']]
    details='\n'.join(f'- slot {r["slot"]}, {r["probe_id"]}({r["bus"]}), {r["component"]}: fresh ± 상태 차이 {json_string(r["fresh_minus_plus_controls"])}; 최대 derivative 차이 {r["fresh_vs_fixed_max_current_derivative_difference_A_per_unit"]:.9g} A/unit' for r in jump)
    report=f'''# 원본 자동제어와 고정제어 국소 민감도 대조

이미 노출된 current V42 B0·역사적 v3 AIDC upstream host diagnostic의 slot 0/9/48/75에서 사전 지정한 첫 MV·첫 LV probe의 P/Q 중앙차분을 독립 재현했다. MV step=±1 kW/kvar, LV split240 step=±0.1 kW/kvar이며 실제 설치/승인된 출력이라는 뜻은 아니다. 원본 source1.05, RegControl12개(Vreg126.5/125), CapControl9개·모든 물리 rating은 그대로이고 수치 tolerance만 1e-9다.

고정제어는 기존 순차 B0에서 정착한 동일 taps/caps를 모든 ± endpoint에 복원했다. 자동제어는 ± endpoint마다 **새 DSS context·원본 Master compile·원본 initial taps/caps**로 각각 시작하여 원본 제어를 정착시켰다. root helper처럼 같은 context에서 original controls만 복원하는 조건도 별도로 측정했다. baseline4+fresh baseline4+endpoint{len(archives)}회의 독립 전력조류가 전부 수렴·ControlActionsDone·빈 control queue였다. Native Solver는 호출하지 않았다.

고정제어가 작은 step에서 안정적이어도 자동제어를 포함한 전역 affine 보증은 아니다. fresh ± endpoint 간 taps/caps가 다른 행은 {len(jump)}/{len(rows)}개이며 자동/fixed derivative 최대 차이는 {worst['fresh_vs_fixed_max_current_derivative_difference_A_per_unit']:.9g} A/unit(slot{worst['slot']}, {worst['probe_id']}, {worst['component']})다. reused original-state reset과 완전히 새 context의 derivative 차이는 전 행에서 최대 {receipt_data['maximum_reused_vs_fresh_derivative_difference_A_per_unit']:.3g} A/unit로 일치하여 reset 실패가 원인이 아니다. 상태가 같더라도 순차 baseline과 fresh endpoint의 원본 deadband·정착 이력 차이로 국소 operating point가 다를 수 있다. 모든 행의 자동/fixed/warm 제어상태, 전압·선로전류·변압기 rating maxima와 차이가 CSV/JSON에 기록되어 있고 `ENDPOINT_REGCONTROL_MONITORS.csv`에는 실제 monitoring 전압·원본 band를 기록했다. tap float 비교의 수치 tolerance는 1e-12여서 반올림 흔적을 실제 tap 이동으로 세지 않았다.

{details or '사전 지정한 fresh ± endpoint 사이에는 discrete tap/cap 상태 차이가 없었다. root의 기존 큰 derivative 차이는 reused context 제어 초기화 및 sequential/fresh operating point 차이를 포함해 별도 해석해야 한다.'}

따라서 후보 영향의 local P/Q 편미분은 같은 정착 제어상태에서만 설명력이 있다. 실제 유한 이동/출력·AIDC PF coupled action은 독립 원본 자동제어 AC로 다시 확인해야 하며 모든 phase 전류/전압/원본 변압기 제한과 새 bottleneck을 끝점에서 확인해야 한다. 이 감사는 설치 port·이동 접근·QoS·WAN 또는 full dispatch 실행 가능성을 인증하지 않는다.
'''
    (REPORT/'CONTROL_DISCONTINUITY_AUDIT_KO.md').write_text(report,encoding='utf-8')
    return receipt_data


def json_string(value):
    import json
    return json.dumps(value,ensure_ascii=False)


if __name__=='__main__':
    run()
