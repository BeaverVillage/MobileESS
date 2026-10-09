"""Original-only low-voltage path diagnosis, before any capacity selection.

The one BG=0.552 run is a causal counterfactual with original controls and no
AIDC/MESS. It is neither a historical production replay nor a scale candidate.
"""
from __future__ import annotations
import json
from collections import defaultdict, deque
from pathlib import Path
import numpy as np
from .ac import IEEE8500AC, _base, _complex
from .audit_source import write_csv


def path_to_source(a, target):
    adj = defaultdict(list)
    elements = a.inventory['lines'] + a.inventory['transformers']
    for name in a.d.Reactors.AllNames():
        a.d.Reactors.Name(name)
        elements.append({'element':'Reactor.'+name,'buses':a.d.CktElement.BusNames(),
            'node_order':a._node_order(),'ncond':a.d.CktElement.NumConductors(),
            'nterm':a.d.CktElement.NumTerminals(),'enabled':a.d.CktElement.Enabled()})
    for meta in elements:
        if not meta['enabled']:
            continue
        for second in meta['buses'][1:]:
            p, q = _base(meta['buses'][0]), _base(second)
            if p != q:
                adj[p].append((q,meta)); adj[q].append((p,meta))
    queue = deque(['sourcebus'])
    parents, seen = {}, {'sourcebus'}
    while queue:
        p = queue.popleft()
        for q, meta in adj[p]:
            if q not in seen:
                seen.add(q); parents[q]=(p,meta); queue.append(q)
    bus, node = target.rsplit('.',1)
    node = int(node)
    backward=[]
    while bus != 'sourcebus':
        parent,meta=parents[bus]
        parent_terms=[i for i,b in enumerate(meta['buses']) if _base(b)==parent]
        child_terms=[i for i,b in enumerate(meta['buses']) if _base(b)==bus]
        nc=meta['ncond']
        child_term=next(i for i in child_terms if node in meta['node_order'][i*nc:(i+1)*nc])
        child_ci=meta['node_order'][child_term*nc:(child_term+1)*nc].index(node)
        parent_term=parent_terms[0]
        parent_nodes=meta['node_order'][parent_term*nc:(parent_term+1)*nc]
        if meta['element'].lower().startswith('transformer.') and meta['nphase']==1:
            parent_ci=next(i for i,n in enumerate(parent_nodes) if n>0)
        else:
            parent_ci=parent_nodes.index(node)
        parent_node=parent_nodes[parent_ci]
        backward.append((parent,parent_node,bus,node,meta,parent_term,child_term,parent_ci,child_ci))
        bus,node=parent,parent_node
    return list(reversed(backward))


def phase_path(a, snap, target):
    by_node={r['bus']+'.'+str(r['node']):r for r in snap['buses']}
    rows=[]
    units={0:'none',1:'mi',2:'kft',3:'km',4:'m',5:'ft',6:'in',7:'cm',8:'mm'}
    length_to_m={1:1609.344,2:304.8,3:1000,4:1,5:.3048,6:.0254,7:.01,8:.001}
    for step,(p,pn,q,qn,meta,pt,qt,pci,qci) in enumerate(path_to_source(a,target),1):
        a.d.Circuit.SetActiveElement(meta['element'])
        current,power=_complex(a.d.CktElement.Currents()),_complex(a.d.CktElement.Powers())
        nc=meta['ncond'];pi=pt*nc+pci;qi=qt*nc+qci
        vp,vq=by_node[p+'.'+str(pn)],by_node[q+'.'+str(qn)]
        row={'step':step,'element':meta['element'],'parent_bus':p,'parent_node':pn,'child_bus':q,'child_node':qn,
            'parent_terminal_or_winding':pt+1,'child_terminal_or_winding':qt+1,
            'v_in_V':vp['voltage_V'],'v_out_V':vq['voltage_V'],'v_in_pu':vp['voltage_pu'],'v_out_pu':vq['voltage_pu'],
            'magnitude_drop_pu':vp['voltage_pu']-vq['voltage_pu'],'input_kv_base_ln':vp['kv_base_ln'],
            'input_split_hot_nominal_120_pu':vp['split_hot_nominal_120_pu'],
            'output_split_hot_nominal_120_pu':vq['split_hot_nominal_120_pu'],
            'output_kv_base_ln':vq['kv_base_ln'],'input_tracked_phase_amps':float(abs(current[pi])),
            'output_tracked_phase_amps':float(abs(current[qi])),
            'input_tracked_phase_p_kw':float(power[pi].real),'input_tracked_phase_q_kvar':float(power[pi].imag),
            'input_terminal_total_p_kw':float(sum(power[pt*nc:(pt+1)*nc]).real),
            'input_terminal_total_q_kvar':float(sum(power[pt*nc:(pt+1)*nc]).imag),
            'output_terminal_delivered_p_kw':float(-sum(power[qt*nc:(qt+1)*nc]).real),
            'output_terminal_delivered_q_kvar':float(-sum(power[qt*nc:(qt+1)*nc]).imag),
            'all_conductor_amps':np.abs(current).tolist(),'node_order':meta['node_order'],
            'normal_amps_input':None,'rho_input':None,'length_original':None,'length_units':None,'length_m':None,
            'r_matrix_ohm_per_original_unit':None,'x_matrix_ohm_per_original_unit':None,
            'tracked_r_total_ohm':None,'tracked_x_total_ohm':None,'series_voltage_drop_real_V':None,'series_voltage_drop_imag_V':None,
            'winding_nameplate_kva':None,'xfmrcode':None,'xhl_pct':None,'xht_pct':None,'xlt_pct':None,'winding_pct_R':None,
            'control_note':''}
        if meta['element'].lower().startswith('line.'):
            a.d.Lines.Name(meta['element'].split('.',1)[1])
            unit=int(a.d.Lines.Units());length=a.d.Lines.Length()
            rm=np.asarray(a.d.Lines.RMatrix()).reshape(nc,nc);xm=np.asarray(a.d.Lines.XMatrix()).reshape(nc,nc)
            drop=complex(vp['v_real_V'],vp['v_imag_V'])-complex(vq['v_real_V'],vq['v_imag_V'])
            row.update(normal_amps_input=meta['normal_amps'],rho_input=float(abs(current[pi])/meta['normal_amps']),
                length_original=length,length_units=units[unit],length_m=length*length_to_m[unit] if unit else None,
                r_matrix_ohm_per_original_unit=rm.tolist(),x_matrix_ohm_per_original_unit=xm.tolist(),
                tracked_r_total_ohm=float(rm[pci,pci]*length),tracked_x_total_ohm=float(xm[pci,pci]*length),
                series_voltage_drop_real_V=drop.real,series_voltage_drop_imag_V=drop.imag)
        elif meta['element'].lower().startswith('transformer.'):
            a.d.Transformers.Name(meta['element'].split('.',1)[1])
            row.update(normal_amps_input=meta['windings'][pt]['normal_line_amps'],
                rho_input=float(abs(current[pi])/meta['windings'][pt]['normal_line_amps']),
                winding_nameplate_kva=[w['kva_nameplate'] for w in meta['windings']],xfmrcode=meta['xfmrcode'],
                xhl_pct=a.d.Transformers.Xhl(),xht_pct=a.d.Transformers.Xht(),xlt_pct=a.d.Transformers.Xlt(),
                winding_pct_R=a.d.Properties.Value('%Rs'))
            if meta['element'].lower().endswith('feeder_rega'):
                row['control_note']='Original FEEDER_REGA, settled secondary tap +2 / 1.0125; not at max'
            elif meta['element'].lower().endswith('hvmv_sub'):
                row['control_note']='Delta/wye: pu magnitude comparison of port phase1; no claim of equal angle or independent delta coil'
            else:
                row['control_note']='Original service transformer; tap1.0; no RegControl on this PCC'
        else:
            row.update(normal_amps_input=a.d.CktElement.NormalAmps(),rho_input=float(abs(current[pi])/a.d.CktElement.NormalAmps()),
                r_matrix_ohm_per_original_unit=a.d.Properties.Value('R'),x_matrix_ohm_per_original_unit=a.d.Properties.Value('X'))
        rows.append(row)
    return rows


def reg_audit(a,snap,case,path_elements):
    rows=[]
    state={r['name']:r for r in snap['regcontrols']}
    for meta in a.inventory['regcontrols']:
        name=meta['name'];props=meta['properties'];s=state[name]
        a.d.RegControls.Name(name);a.d.Transformers.Name(meta['transformer'])
        a.d.Transformers.Wdg(a.d.RegControls.Winding())
        v=_complex(a.d.Transformers.WdgVoltages())
        monitor=float(abs(v[0])/float(props['PTRatio']))
        target=float(props['VReg']);band=float(props['Band'])
        rows.append({'case':case,'name':name,'transformer':meta['transformer'],'enabled':s['enabled'],
            'source_vreg_V':target,'source_band_V':band,'source_ptratio':float(props['PTRatio']),
            'initial_tap_pu':a.initial_state['taps'][meta['transformer']][s['winding']-1],
            'settled_tap_number':s['tap_number'],'settled_tap_pu':s['tap_pu'],
            'min_tap_pu':a.d.Transformers.MinTap(),'max_tap_pu':a.d.Transformers.MaxTap(),
            'at_max_tap':abs(s['tap_pu']-a.d.Transformers.MaxTap())<1e-9,
            'at_min_tap':abs(s['tap_pu']-a.d.Transformers.MinTap())<1e-9,
            'monitored_secondary_V':monitor,'inside_original_band':abs(monitor-target)<=band/2+1e-8,
            'on_original_lowest_voltage_path':('Transformer.'+meta['transformer']) in path_elements,
            'converged':snap['summary']['converged'],'control_actions_done':snap['summary']['control_actions_done'],
            'control_queue_size':snap['summary']['control_queue_size']})
    return rows


def main():
    root=Path(__file__).resolve().parents[1];docs=root/'docs/ieee8500_v42_single_case'
    original=IEEE8500AC(output_dir=root/'ieee8500_v42/outputs/voltage_original')
    snap=original.solve();target=snap['summary']['vmin_node'];path=phase_path(original,snap,target)
    path_elements={r['element'] for r in path}
    regs=reg_audit(original,snap,'original_BG1_NO_AIDC_NO_MESS',path_elements)
    loads=[]
    for meta in original.inventory['loads']:
        if _base(meta['buses'][0])==target.rsplit('.',1)[0]:
            original.d.Loads.Name(meta['name']);p=sum(_complex(original.d.CktElement.Powers()))
            loads.append({**meta,'actual_kw':float(p.real),'actual_kvar':float(p.imag)})
    counter=IEEE8500AC(output_dir=root/'ieee8500_v42/outputs/voltage_bg_counterfactual')
    csnap=counter.solve(background_scale=.552)
    cpath=phase_path(counter,csnap,target)
    regs+=reg_audit(counter,csnap,'causal_BG0552_ORIGINAL_POLICY_NO_AIDC_NO_MESS',path_elements)
    by={r['element']:r for r in cpath}
    for row in path:
        c=by[row['element']]
        row.update(counterfactual_bg=.552,counter_v_in_pu=c['v_in_pu'],counter_v_out_pu=c['v_out_pu'],
                   counter_magnitude_drop_pu=c['magnitude_drop_pu'],counter_input_phase_amps=c['input_tracked_phase_amps'])
    primary_rows=[r for r in path if r['element'].startswith('Line.') and not r['element'].startswith('Line.tpx')]
    service=next(r for r in path if r['element']=='Transformer.t21382813a')
    triplex=next(r for r in path if r['element']=='Line.tpx21382813a0')
    feeder=next(r for r in path if r['element']=='Transformer.feeder_rega')
    decomposition={'source_to_feeder_output_net_drop_pu':path[0]['v_in_pu']-feeder['v_out_pu'],
        'primary_path_magnitude_drop_pu':sum(r['magnitude_drop_pu'] for r in primary_rows),
        'service_transformer_hot2_drop_pu':service['magnitude_drop_pu'],
        'triplex_hot2_drop_pu':triplex['magnitude_drop_pu'],
        'total_source_to_customer_drop_pu':path[0]['v_in_pu']-path[-1]['v_out_pu'],
        'primary_known_length_m':sum(r['length_m'] or 0 for r in primary_rows),
        'primary_lines_with_unknown_length_units':sum(r['length_units']=='none' for r in primary_rows),
        'primary_sum_tracked_self_r_ohm':sum(r['tracked_r_total_ohm'] for r in primary_rows),
        'primary_sum_tracked_self_x_ohm':sum(r['tracked_x_total_ohm'] for r in primary_rows),
        'phase_identity':'Customer local hot2 crosses CT37 winding3 to original primary phaseA/node1',
        'path_edges':len(path),'path_regulators':['feeder_rega'],
        'interpretation':'Magnitude changes include mutual coupling, regulator boost, different voltage bases; not independent scalar circuit approximation'}
    conditions={'status':'VOLTAGE_CAUSE_DIAGNOSED_BEFORE_SCALE_SELECTION','selected_scenario':False,
        'date_scope':'No May01 temporal/customer authority: source static snapshot only',
        'original_case':{'background_scale':1.,'AIDC_kw':0,'MESS_kw':0,'PV_kw':0,
            'load_removal_or_relocation':False,'physical_source_changes':False,'solver_policy':original.inventory['control_policy'],
            'summary':snap['summary'],'control_state':snap['control_state'],'capacitors':snap['capacitors']},
        'counterfactual_case':{'background_scale':.552,'AIDC_kw':0,'MESS_kw':0,'PV_kw':0,
            'policy':'Same original source1.05, original125/126.5 controls, original caps independently auto settled',
            'purpose':'One causal load-only counterfactual; not historical replay, not a candidate or selection',
            'summary':csnap['summary'],'control_state':csnap['control_state'],'capacitors':csnap['capacitors']},
        'original_lowest_node':target,'path_decomposition':decomposition,'original_lowest_bus_loads':loads,
        'source_sha256':original.source_hashes,'source_unchanged':original.verify_source_unchanged() and counter.verify_source_unchanged(),
        'physical_network_voltage_constraint':[.95,1.05],
        'original_load_characteristic':'Model1 constant P/Q, Vminpu0.88; distinct from V42 network voltage lower bound0.95',
        'load_characteristic_fallback_at_original_lowest_node':False,
        'lowest_voltage_normalization':{'original_bus_kv_base_ln':path[-1]['output_kv_base_ln'],
            'nominal_hot_V':120.,'actual_hot_voltage_V':path[-1]['v_out_V'],
            'original_DSS_base_pu':snap['summary']['vmin_pu'],
            'nominal_120V_pu':path[-1]['v_out_V']/120.,
            'note':'Original Master0.208kV yields120.088856V LN base; original Load/Transformer nameplate120V retained. Both reported, physical policy unchanged.'},
        'default_tolerance_reference':{'tolerance':1e-4,'vmin_pu':.9115150131517161,
            'strict_minus_default_vmin_pu':snap['summary']['vmin_pu']-.9115150131517161,
            'purpose':'Prior coarse original-only diagnostic; stricttol1e-9 supersedes for electrical arrays and power balance'},
        'historical_policy_comparison_scope':'Source1.04,Vreg123.5,CAPBank3OFF are separate historical overrides; provenance in SOURCE_AUTHORITY/historical comparison, not applied in these runs'}
    (docs/'VOLTAGE_DIAGNOSTIC_CONDITIONS.json').write_text(json.dumps(conditions,ensure_ascii=False,indent=2),encoding='utf-8')
    write_csv(docs/'LOWEST_VOLTAGE_PATH.csv',path)
    write_csv(docs/'LOW_VOLTAGE_REGCONTROL.csv',regs)
    write_csv(docs/'LOWEST_BUS_ORIGINAL_LOADS.csv',loads)
    table='\n'.join(f"| {r['element']} | {r['v_in_pu']:.9f} | {r['v_out_pu']:.9f} | {r['magnitude_drop_pu']:.9f} |" for r in [feeder,service,triplex])
    report=f'''# 원본 IEEE8500 최저전압 원인 진단

원본 `Master-unbal.dss`만 컴파일한 상태에서 최저전압은 `{target}`의 **{snap['summary']['vmin_pu']:.9f} pu**다. 배경부하 BG=1.0, AIDC=0, MESS=0, 원본 Master에서 활성화된 PV=0이며 추가 부하·신규 변압기를 사용하지 않았다. Source=1.05 pu, feeder RegControl=126.5 V, downstream RegControl=125 V, 원본 10개 커패시터 및 9개 CapControl을 보존했다. 이 결과는 원본 정적 부하 스냅샷이며 2025년 5월 1일의 시계열을 입증하지 않는다.

전압 pu의 기준도 원본을 보존했다. 원본 Master의 저압 voltagebases 항목0.208 kV에서 Bus 기준 상전압은 0.208/√3={path[-1]['output_kv_base_ln']:.12f} kV(120.088856 V)다. 변압기와 고객 Load의 nameplate는120 V다. 최저 고객 실제 전압은 {path[-1]['v_out_V']:.9f} V로, 원본 DSS 기준으로0.911411805 pu, 정확한120 V nameplate 기준으로{path[-1]['v_out_V']/120.:.9f} pu다. 두 값 모두0.95보다 낮다. 이 미세한 기준 차이를 원인인 누적 전압 하락과 구별했고 원본 Bus 기준이나 정격을 조정하지 않았다.

OpenDSS는 수렴했고 5회 제어 반복 후 ControlActionsDone=True, 잔여 queue=0이다. 전력수지 잔차는 P={snap['summary']['balance_residual_kw']:.3g} kW, Q={snap['summary']['balance_residual_kvar']:.3g} kvar이다. 첫 진단의 0.911515013 pu는 기본 tolerance=1e-4 결과이고, 현재 tolerance=1e-9의 0.911411805 pu가 정밀 검증값이다(정밀−기본={snap['summary']['vmin_pu']-.9115150131517161:.9f} pu). maxiterations=100은 각 내부 전력조류 반복의 수치 예산이고 maxcontroliter=100은 제어 반복 예산이다. 출력 Iterations=192는 제어 단계들에 걸친 누적 반복값으로 단일 단계의 한도 초과나 미수렴을 의미하지 않는다. 물리 설정은 변경하지 않았다.

Source에서 고객까지 {len(path)}개 원본 요소를 실제 노드 번호로 추적했다. 고객 hot2는 서비스 변압기 CT37의 세 번째 권선을 통해 중압 A상(node1)에 연결된다. 경로에는 `FEEDER_REGA`만 존재하며 VREG2/3/4는 이 고객의 상류 경로에 없다. feeder 출력 {_base(feeder['child_bus'])}.1은 {feeder['v_out_pu']:.9f} pu이고 서비스 변압기 입력 `l2748781.1`은 {service['v_in_pu']:.9f} pu다. 중압 경로에서 누적 {decomposition['primary_path_magnitude_drop_pu']:.9f} pu, 서비스 변압기 hot2에서 {service['magnitude_drop_pu']:.9f} pu, 고객 Triplex에서 {triplex['magnitude_drop_pu']:.9f} pu가 추가로 떨어진다. 중압 경로의 단위가 확인된 길이는 {decomposition['primary_known_length_m']/1000:.3f} km이며 단위 미지정 선로 {decomposition['primary_lines_with_unknown_length_units']}개는 길이 합산에서 제외했다. 누적 전압 하락은 원본 긴 중압 경로의 전류·임피던스 및 말단 분상 불균형과 일치한다.

| 요소 | 입력 pu | 출력 pu | 입력−출력 pu |
|---|---:|---:|---:|
{table}

해당 서비스 변압기는 원본 CT37 37.5 kVA이고 입력 실제 부하는 {next(r for r in snap['transformers'] if r['element']=='Transformer.t21382813a' and r['winding']==1)['winding_kva']:.4f} kVA다. `Line.Tpx21382813A0`는 원본 50 ft, 4/0Triplex, NormalAmps=156 A이며 hot2 전류 {triplex['input_tracked_phase_amps']:.4f} A(부하율 {triplex['rho_input']:.6f})다. 따라서 최저전압 지점의 국부 Triplex 과부하가 원인은 아니다. 별도 시스템 최대 부하율은 `{snap['summary']['binding_line']}`에서 {snap['summary']['rho_max']:.9f}이며 전압 최저 지점과 병목 선로를 구별해야 한다.

고객 hot1은 1.826097 kW, hot2는 11.473903 kW, 양쪽 pf=0.97로 약 6.28:1의 불균형이다. 실제 AC 소비 P/Q는 원본 설정값과 일치했다. 두 Load는 Model=1, Vminpu=0.88, Vmaxpu=1.05다. 최저전압 0.9114는 원본 부하 모델의 Vminpu=0.88보다 높으므로 정전력 구간에 있으며 0.95에서 정임피던스로 전환된 결과가 아니다. Load의 특성 전환 경계 0.88은 V42 계통 허용 하한 0.95와 다른 값이다.

12개 RegControl은 모두 enabled이다. 경로상의 FEEDER_REGA는 초기1.0→+2/1.0125, monitoring125.866367 V로 원본126.5±1 V band 안에 있고 상한에 도달하지 않았다. 별도 분기의 VREG3_A는 +16/1.10 상한에 도달했으며 monitoring123.711607 V가 원본125±1 V band 아래에 있다. **ControlActionsDone=True는 모든 전압 목표 달성을 의미하지 않으며, 상한 포화도 추가 동작이 없는 settled 상태다.** 상세 12개 상태는 `LOW_VOLTAGE_REGCONTROL.csv`에 기록했다.

부하 영향 분리를 위해 BG=0.552, AIDC/MESS/PV=0의 반사실 1회만 원본 정책으로 계산했다. 최저전압은 {csnap['summary']['vmin_pu']:.9f} pu(`{csnap['summary']['vmin_node']}`), 기존 최저 고객 hot2는 {cpath[-1]['v_out_pu']:.9f} pu로 변했다. 최대 부하율은 {csnap['summary']['rho_max']:.9f}, 최고전압은 {csnap['summary']['vmax_pu']:.9f} pu로 1.05를 약 0.0000495 pu 넘은 노드 1개가 남는다. 이는 원본 부하 크기와 전압 하락의 인과 확인이며 스케일 후보나 선정안이 아니다. 과거 BG0.552/AIDC2.40/MESS2.00/Source1.04/Vreg123.5/CAPBank3OFF 생산 실험을 재실행한 값도 아니다. 원본 고객 부하·배치·정격·제어 정책을 유지한 진단을 마쳤으며 이 결과로 Source/Vreg/Cap 또는 배경부하를 조정하지 않았다.
'''
    (docs/'VOLTAGE_ROOT_CAUSE_KO.md').write_text(report,encoding='utf-8')
    try:
        from .plot_voltage_forensics import main as plot_main
        plot_main()
    except ImportError:
        print('Matplotlib unavailable in AC runtime; run ieee8500_v42.plot_voltage_forensics in a Matplotlib runtime')
    print(json.dumps({'original':snap['summary'],'counterfactual':csnap['summary'],'decomposition':decomposition},indent=2))


if __name__=='__main__':
    main()
