"""User-authorized CAPBank0/VREG3 root-cause diagnostics, separate from P0-P3."""
import numpy as np
from ieee8500_v42.ac import _complex
from .common import *
from .engine import StudyEngine
from .run_b0 import summary,run_day,compare


def details(e,case,source,slot):
    out=[]
    for suffix in 'abc':
        control='capbank0'+suffix+'_ctrl';e.d.CapControls.Name(control)
        props={p:e.d.Properties.Value(p) for p in e.d.CktElement.AllPropertyNames()}
        e.d.Circuit.SetActiveElement(props['Element']);nc=e.d.CktElement.NumConductors();t=int(props['Terminal'])-1
        vv=_complex(e.d.CktElement.Voltages()).reshape(-1,nc);pp=np.asarray(e.d.CktElement.Powers()).reshape(-1,nc,2)
        node=e.d.CktElement.NodeOrder()[t*nc];bus=e.d.CktElement.BusNames()[t].split('.')[0]
        v=abs(vv[t,int(props['PTPhase'])-1])/float(props['PTRatio'])
        monitored_Q=float(pp[t,:,1].sum())
        e.d.Circuit.SetActiveBus(bus);base=e.d.Bus.kVBase()*1000
        cap='capbank0'+suffix;e.d.Capacitors.Name(cap)
        cq=np.asarray(e.d.CktElement.Powers()).reshape(-1,2).sum(0)
        out.append(dict(case=case,source=source,slot=slot,CapControl=control,Capacitor=cap,
            states=json.dumps(e.d.Capacitors.States()),cap_Q_consumption_kvar=float(cq[1]),
            monitored_element=props['Element'],terminal=props['Terminal'],monitored_bus=bus,
            PTPhase=props['PTPhase'],primary_node=node,PTRatio=float(props['PTRatio']),
            actual_monitor_V=float(v),monitor_pu=float(v/base),Vmax_V=float(props['VMax']),
            Vmax_pu=float(props['VMax'])/base,Vmin_V=float(props['VMin']),
            above_Vmax_override=bool(v>float(props['VMax'])),monitored_kvar=monitored_Q,
            OnSetting_kvar=float(props['OnSetting']),OffSetting_kvar=float(props['OffSetting']),
            Delay_s=float(props['Delay']),DelayOff_s=float(props['DelayOff']),DeadTime_s=float(props['DeadTime']),
            VoltOverride=props['VoltOverride'],VBus=props['VBus']))
    return out


def diagnose():
    folder=REPORT/'emergency';folder.mkdir(parents=True,exist_ok=True)
    write(folder/'PREREGISTRATION.json',dict(trigger='user CAPBank0A/VREG3 priority instruction',
        original_P0_P3_preserved=True,scale_and_mapping_changes=0,Source=1.04,
        fixed_tap_cases=['BASE','CAP0A_OFF','CAP0B_OFF','CAP0C_OFF','CAP0ABC_OFF','CAP0ABC_ON','PV_OFF','CAP0A_OFF_PV_OFF'],
        new_policy_priority=['P4','P5'],P4='P3 + VREG3A/B/C123.5',
        P5='P3 + all9downstream Vreg123.5; historicalPR62 target, original deadband/limits',
        selection='first new Planning96 hardPASS in P4,P5 priority; Actual not used to choose',
        capacitor_7740_override_threshold_change=0,no_final_PV_removal=True))
    results=[];monitors=[]
    for source in ('PLANNING','ACTUAL'):
        old=REPORT/'ac'/('B0_'+source);slot=int(max(rows(old/'SLOTS.csv'),key=lambda r:float(r['Vmax']))['slot'])
        state=read(old/'CONTROL_STATES.json')[slot]
        with np.load(DATA/'derived'/f'{source}_INPUTS.npz') as z:data={k:z[k] for k in z.files}
        for case in read(folder/'PREREGISTRATION.json')['fixed_tap_cases']:
            e=StudyEngine('emergency_'+source+'_'+case,'P3',True)
            e.apply_inputs(slot,data['gross_factor'][slot],data['pv_factor'][slot],data['PCC_P_kw'][slot],data['PCC_Q_kvar'][slot],pv_on='PV_OFF' not in case)
            changed=json.loads(json.dumps(state))
            for suffix in 'abc':
                if case in ('CAP0ABC_OFF','CAP0ABC_ON') or 'CAP0'+suffix.upper()+'_OFF' in case:
                    changed['capacitors']['capbank0'+suffix]=[int(case=='CAP0ABC_ON')]
            a=e.settle('fixed',changed)
            e.d.Circuit.SetActiveBus('r42246');nodes=e.d.Bus.Nodes();v=_complex(e.d.Bus.PuVoltage())
            pv_actual=np.zeros(2)
            for name in e.pv_names:
                e.d.Generators.Name(name);pv_actual-=np.asarray(e.d.CktElement.Powers()).reshape(-1,2).sum(0)
            e.d.Transformers.Name('vreg3_a');pq=np.asarray(e.d.CktElement.Powers()).reshape(-1,2)
            nc=e.d.CktElement.NumConductors()
            results.append(dict(case=case,source=source,slot=slot,**summary(e,a),
                r42246_phase1_pu=float(abs(v[nodes.index(1)])),PV_actual_P_kw=float(pv_actual[0]),PV_actual_Q_kvar=float(pv_actual[1]),
                VREG3A_upstream_P_kw=float(pq[:nc,0].sum()),VREG3A_upstream_Q_kvar=float(pq[:nc,1].sum()),
                taps_fixed=True,automatic_policy=False))
            monitors.extend(details(e,case,source,slot))
    table(folder/'FIXED_TAP_CAUSAL_COUNTERFACTUALS.csv',results)
    table(folder/'CAPBANK0_PHASE_MONITOR_AUDIT.csv',monitors)
    print('fixed-tap cause results',json.dumps([{k:r[k] for k in ('source','case','Vmax','r42246_phase1_pu','VREG3A_upstream_Q_kvar')} for r in results],indent=2),flush=True)


def policies():
    results=[]
    for policy in ('P4','P5'):
        results.append(run_day('EMERGENCY_POLICY_'+policy,policy,full_audit=True))
    qualified=[r['policy'] for r in results if r['hard_constraints_PASS']]
    selected=qualified[0] if qualified else None
    write(REPORT/'emergency/PLANNING_SELECTION.json',dict(selected_policy=selected,candidates=results,
        Actual_used_for_selection=False,selection_rule=read(REPORT/'emergency/PREREGISTRATION.json')['selection']))
    if selected:
        for source in ('PLANNING','ACTUAL'):
            run_day('QUALIFIED_B0_'+source,selected,source=source,full_audit=True)
            run_day('QUALIFIED_B0_'+source+'_FRESH',selected,source=source)
            compare('QUALIFIED_B0_'+source,'QUALIFIED_B0_'+source+'_FRESH','QUALIFIED_'+source+'_FRESH_VERIFICATION.json')
    print('new Planning selection',selected,flush=True)


def final_validation():
    selection=read(REPORT/'emergency/PLANNING_SELECTION.json')
    assert selection['selected_policy']=='P4'
    rejected=read(REPORT/'ac/QUALIFIED_B0_ACTUAL/RECEIPT.json')
    assert not rejected['hard_constraints_PASS']
    # Eligibility validation may reject an initially Planning-qualified candidate.
    # P5 was registered before either candidate was run. No new setpoint is fit
    # to Actual or to B1/B2/B3 objective performance.
    write(REPORT/'emergency/VALIDATION_ESCALATION.json',dict(
        original_Planning_selection='P4',rejected_on_Actual_hard_constraints=True,
        rejected_Actual_Vmax=rejected['Vmax'],rejected_Actual_violation_cells=rejected['voltage_violation_cells'],
        next_already_preregistered_candidate='P5',new_data_fit=False,
        revised_qualification_rule='validate next predeclared candidate after hard-constraint rejection; require both96days and Fresh',
        Actual_used_as_hard_validation_gate=True,Actual_used_as_Planning_input=False,
        B1_B2_B3_outcomes_used=False,scale_and_mapping_changes=0))
    for source in ('PLANNING','ACTUAL'):
        run_day('FINAL_B0_'+source,'P5',source=source,full_audit=True)
        run_day('FINAL_B0_'+source+'_FRESH','P5',source=source)
        compare('FINAL_B0_'+source,'FINAL_B0_'+source+'_FRESH','FINAL_'+source+'_FRESH_VERIFICATION.json')
    plan=read(REPORT/'ac/FINAL_B0_PLANNING/RECEIPT.json');actual=read(REPORT/'ac/FINAL_B0_ACTUAL/RECEIPT.json')
    passed=plan['hard_constraints_PASS'] and actual['hard_constraints_PASS']
    write(REPORT/'emergency/FINAL_VALIDATION.json',dict(selected_voltage_policy='P5' if passed else None,
        B0_AC_physical_qualification_PASS=passed,Planning=plan,Actual=actual,
        final_Production_configuration_frozen=False,full_Production_ready=False,
        PV_kept=True,all_original_CapControl_thresholds_delays_unchanged=True))
    print('FINAL physical B0 qualification',passed,flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=('diagnose','policies','final'))
    args=p.parse_args()
    if args.action=='diagnose':diagnose()
    elif args.action=='policies':policies()
    else:final_validation()
