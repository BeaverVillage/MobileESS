"""Saved evidence RCA; no solver, AC replay, equipment or Worker mutation."""
from pathlib import Path
import sys,json,re
import numpy as np
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify

def run(root):
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json')
    row=ledger['dates']['B2/2025-05-18'];result=Path(row['result']);r=read(result)
    assert record(result)['sha256']==row['result_SHA'] and not r['PASS']
    assert r['source_SHA']==m['execution_SHA'] and r['physical_failures']
    receipts=[record(result),record(root/'CAMPAIGN_MANIFEST.json')];contexts=[]
    for ar in r['metrics']['evidence']:
        assert record(ar['path'])==ar
        a=read(ar['path']);sr=a['slots_receipt'];assert record(sr['path'])==sr
        slots=read(sr['path']);assert [s['slot'] for s in slots]==list(range(96))
        bad=[dict(slot=s['slot'],nodes=[n for n in s['physical']['nodes'] if not .95<=n['voltage_pu']<=1.05])
            for s in slots if any(not .95<=n['voltage_pu']<=1.05 for n in s['physical']['nodes'])]
        assert len(bad)==1 and bad[0]['slot']==51 and len(bad[0]['nodes'])==3
        assert {n['node_phase'] for n in bad[0]['nodes']}=={'81.2','idc_idc10_pcc.2','mess_idc10_pcc.2'}
        s=slots[51];ns={n['node_phase']:n['voltage_pu'] for n in s['physical']['nodes']}
        banks=[]
        for d in s['svr']['devices']:
            if d['id'] not in ('BUS79','BUS82','BUS86'):continue
            banks.append(dict(id=d['id'],sensed_bus=d['sensed_bus'],downstream_bus=d['downstream_bus'],
                hardware_PASS=d['hardware_PASS'],phase2={k:d['phases'][1][k] for k in ('tap','tap_range_PASS','autonomous_control_enabled','terminals')}))
        contexts.append(dict(namespace=a['namespace'],violations=bad,all96_AC_converged=all(s['settled_original_controls']['solution_converged'] for s in slots),
            all96_controls_complete=all(s['control_actions_done_as_of_current_time'] for s in slots),
            metrics=r['metrics']['environments'][a['namespace']],
            nearby_phase2_voltages={n:ns[n] for n in ('78.2','79.2','80.2','81.2','82.2','86.2','idc_idc10_pcc.2','mess_idc10_pcc.2')},
            banks=banks,original_taps={p['name']:p['initial_tap'] for p in s['settled_original_controls']['original_regulators']},
            time={k:s['time_control'][k] for k in ('start_seconds','end_seconds','last_solve_seconds','physical_solve_count','manual_tap_or_cap_actions')}))
        receipts.extend([ar,sr])
    out=result.parent/'output/OPERATIONS';input_log=out/'PLANNING/FORECAST_FRESH/RAW_PHYSICAL_INPUT_LOG.json'
    inp=read(input_log)['slots'][51];coeff=root/'models/2025-05-18/COEFFICIENTS.npz'
    with np.load(coeff) as z:
        names=list(map(str,z['control_names']));nodes=list(map(str,z['node_names']));u=np.zeros(len(names));u[:12]=inp['PCC_P_kw']
        for i,site in enumerate(inp['MESS_locations']):
            if site=='TRANSIT':continue
            u[names.index('mess_p_kw['+site+']')]+=inp['MESS_P_kw'][i]
            u[names.index('mess_q_kvar['+site+']')]+=inp['MESS_Q_kvar'][i]
        w=z['voltage_constant'][51]+u@z['voltage_matrix'][51];assert (w>0).all()
        linear={n:float(np.sqrt(w[nodes.index(n)])) for n in ('78.2','80.2','81.2','82.2','idc_idc10_pcc.2','mess_idc10_pcc.2')}
    receipts.extend([record(input_log),record(coeff)])
    population=[]
    for rr in ledger['dates'].values():
        if rr['status'] not in ('PASS','FAIL') or not rr.get('result'):continue
        parent=Path(rr['result']).parent/'output'
        ps=[p for p in parent.rglob('OPENDSS_PHASE_ARRAYS.npz')
            if not any(k in str(p.relative_to(parent)).upper() for k in ('FORECAST','DAYAHEAD','PLANNING'))]
        assert len(ps)==1
        with np.load(ps[0]) as z:
            axis=list(map(str,z['node_names']));v=z['voltage_pu'][:,axis.index('81.2')];assert v.shape==(96,) and np.isfinite(v).all()
            ix=int(v.argmax());population.append(dict(arm=rr['arm'],day=rr['day'],status=rr['status'],
                peak_Bus81B=float(v[ix]),slot=ix,violation_cells=int((v>1.05).sum()),raw_arrays=record(ps[0])))
    from v42_regcontrol.authority import source
    assets=source()['assets'];master=Path(assets.master);pcc=Path(assets.pcc)
    lines=[line.strip() for line in master.read_text().splitlines() if re.search(r'\bLine\.l(?:7[6-9]|8[012])\b',line,re.I)]
    pcc_lines=pcc.read_text().splitlines();connections=[]
    for i,line in enumerate(pcc_lines):
        if 'New Transformer.' in line and any(n in line for n in ('IDC_IDC10_TX','MESS_IDC10_TX','MESS_STA12_TX')):
            connections.append([line.strip(),pcc_lines[i+1].strip()])
    receipts.extend([record(master),record(pcc)])
    failed_dates=sorted({v['day'] for v in population if v['violation_cells']})
    audit=dict(schema='SVR11_BUS81_SAVED_VOLTAGE_CAUSE_V1',source_SHA=m['execution_SHA'],
        equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],result=record(result),
        confirmed_physical_FAIL='B2/2025-05-18',slot_0based=51,slot_1based=52,
        interval_fixed_AEST='2025-05-18 12:45–13:00 UTC+10',upper_voltage_limit=1.05,contexts=contexts,
        current_equipment_terminal_population=len(population),population=population,distinct_Bus81B_violation_dates=failed_dates,
        topology_original_DSS_lines=lines,IDC10_and_STA12_connections=connections,
        topology_conclusion='Line79 78→79 and Line77 76→86 are sibling branches. Line80 78→80 and Line81 80→81 supply IDC10. Existing BUS82 is on Line82 terminal1 at81, controlling remote82; it does not regulate upstream81/IDC10. STA10 and IDC10 are distinct sites.',
        planning_setpoints=inp,diagnostic_frozen_coefficient_voltage_prediction=linear,
        Forecast_Fresh_Bus81B=next(c for c in contexts if c['namespace']=='DAYAHEAD')['nearby_phase2_voltages']['81.2'],
        interpretation='Genuine physical FAIL reproduced in independent Forecast/Actual contexts. All96 AC/control checks and finite ratings/taps pass. Upstream unregulated81 rises above its normal78/80 parents while regulated82 remains near1pu. Capacitive Q export on BUS82 primary and changed original automatic taps are observed. Local secants evaluated on an unperturbed Forecast prefix do not globally reproduce the optimized full-day nonlinear automatic-control trajectory. Individual causal contributions have not been isolated.',
        conservative_candidate_only='If repeated structural failures make equipment change unavoidable: consider relocating the existing BUS82 bank upstream to original Line80 terminal1, retaining remote82 sensing,11 banks, all finite400A/kVA/settings and original line physics. Examine78 input/80/81/84/82/83 voltages, originalRC interactions and all phases. No candidate installation or safety certification has been performed.',
        decision='One distinct failing date so far; retain strict FAIL and FAIL-CONTINUE. No immediate SVR addition, relocation, tolerance or per-date tuning. Examine subsequent independent dates and the Forecast model/automatic-control discrepancy before selecting a remedy. Any equipment change needs a new common epoch and recomputation of all affected policy results/models.',
        retry_without_verified_change=False,scientific_workers_terminated=0,Native_calls=0,OpenDSS_solves=0,
        settings_or_tolerance_changed=False,Planning_or_Actual_setpoints_modified=0,source_receipts=receipts,UTC=now())
    assert all(record(p['path'])==p for p in receipts)
    atomic(root/'BUS81_MAY18_VOLTAGE_CAUSE_AUDIT.json',audit)
    (root/'BUS81_MAY18_VOLTAGE_CAUSE_AUDIT.md').write_text(
        '# B2 May18 Bus81 voltage failure\n\nActual1.0510300258122456pu; Forecast1.0508904420339138pu, slot51 (0-based). Bus81 B phase and both IDC10/MESS PCC B phases fail the unchanged1.05pu limit. All96 AC/control checks and current/kVA/taps pass.\n\n'
        'Original topology:78→80→81 supplies IDC10. Bus79 and Bus86 regulators are on sibling branches. Existing BUS82 regulator is downstream of81 and senses82, which remains1.00348pu. STA10 is a different site from IDC10.\n\n'
        f'Frozen-coefficient diagnostic predicts Bus81 B{linear["81.2"]:.9f}pu; Forecast Fresh AC gives1.050890442pu. Local unperturbed-prefix sensitivities do not certify the optimized nonlinear automatic-tap trajectory. Observed capacitive return and changed original taps are evidence, not an isolated causal attribution.\n\n'
        f'Across{len(population)} completed same-equipment Actual trajectories, the only Bus81 B violating date is May18. Keep this physical FAIL, continue other dates/policies, and do not rerun unchanged physics or alter limits. Existing BUS82 relocation beforeLine80 is a conservative candidate only if repeated structural evidence makes it unavoidable; no installation or safety claim. A physical change requires separate common epoch and affected-result recomputation.\n',encoding='utf8')
    print(json.dumps({k:audit[k] for k in ('confirmed_physical_FAIL','slot_0based','current_equipment_terminal_population','distinct_Bus81B_violation_dates','diagnostic_frozen_coefficient_voltage_prediction','Forecast_Fresh_Bus81B','Native_calls','OpenDSS_solves','settings_or_tolerance_changed')},ensure_ascii=False))

if __name__=='__main__':run(sys.argv[1])
