from pathlib import Path
import json,csv,math,hashlib
from collections import Counter,defaultdict
import numpy as np
from run_b0_screen import HERE,ROOT,OVERLAY,read,save,table,rec,sha

def rows(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
    status=read(HERE/'SELECTED_ALPHA_AND_B0_STATUS.json');screen=read(HERE/'ALPHA_SCREEN_TABLE.json');spec=read(HERE/'OPERATING_POINT_PREREGISTRATION.json')
    assert status['selected_alpha'] is None and len(screen)==21 and [s['alpha'] for s in screen]==spec['alpha_grid_descending']
    assert all(s['converged_slots']==s['native_control_complete_slots']==96 and not s['feasible'] for s in screen)
    loads=rows(HERE/'NATIVE_LOAD_AND_PV_ALLOCATION.csv');P=np.array([float(r['base_kw']) for r in loads]);Q=np.array([float(r['base_kvar']) for r in loads]);phase=np.array([r['primary_phase'] for r in loads]);pf=np.array([float(r['base_pf']) for r in loads]);weights=np.array([float(r['PV_weight']) for r in loads]);ratio=read(HERE/'PV_PENETRATION_RATIO_AUTHORITY.json')['ratio'];f=read(HERE/'D1_AEMO_VIC1_FORECAST_AUTHORITY.json');md=np.array(f['demand_mw_96'])/max(f['demand_mw_96']);mpv=np.array(f['pv_mw_96'])/max(f['pv_mw_96'])
    assert abs(weights.sum()-1)<1e-12 and np.allclose(weights,P/P.sum(),atol=1e-15,rtol=0)
    phasebase=[dict(primary_phase=p,native_loads=int((phase==p).sum()),base_P_kw=float(P[phase==p].sum()),base_Q_kvar=float(Q[phase==p].sum()),share_P=float(P[phase==p].sum()/P.sum()),PV_peak_kw_at_alpha1=float(ratio*P[phase==p].sum())) for p in 'ABC']
    table(HERE/'PRIMARY_PHASE_CONSERVATION_BASE.csv',phasebase)
    phasedaily=[];allslots=[];witness=[];maxerr=0.;pferr=0.
    with np.load(HERE/'V41R4_B0_AIDC_POWER_UNCHANGED.npz') as z:aidcp=z['pcc'].copy();aidcq=z['qcc'].copy()
    for s in screen:
        a=s['alpha'];folder=HERE/'screen'/f'alpha_{a:.2f}';rr=rows(folder/'B0_96_SLOT_EXTREMA.csv');assert len(rr)==96
        assert not read(folder/'NATIVE_STATIC_DEFINITION_AUDIT.json')['changed_definitions']
        for t,r in enumerate(rr):
            pp=a*md[t]*P;qq=a*md[t]*Q;pv=a*ratio*mpv[t]*P
            if a>0:pferr=max(pferr,float(abs(pp/np.hypot(pp,qq)-pf).max()))
            maxerr=max(maxerr,abs(pp.sum()-float(r['native_P_scheduled_kw'])),abs(qq.sum()-float(r['native_Q_scheduled_kvar'])),abs(pv.sum()-float(r['PV_scheduled_kw'])))
            assert abs(float(r['AIDC_P_scheduled_kw'])-aidcp[t].sum())<1e-9 and abs(float(r['AIDC_Q_scheduled_kvar'])-aidcq[t].sum())<1e-9
            for p in 'ABC':phasedaily.append(dict(alpha=a,slot=t,primary_phase=p,native_P_kw=float(pp[phase==p].sum()),native_Q_kvar=float(qq[phase==p].sum()),PV_P_kw=float(pv[phase==p].sum()),PV_Q_kvar=0.))
            allslots.append(r)
        for metric,axis,direction in [('voltage_min_pu','voltage_min_node',min),('voltage_max_pu','voltage_max_node',max),('line_phase_current_max_pu','line_max_asset',max),('transformer_phase_current_max_pu','transformer_current_max_asset',max),('transformer_total_kva_max_pu','transformer_kva_max_asset',max)]:
            r=direction(rr,key=lambda r:float(r[metric]));witness.append(dict(alpha=a,metric=metric,value=float(r[metric]),slot=int(r['slot']),asset=r[axis]))
    assert maxerr<1e-8 and pferr<1e-12
    table(HERE/'SPATIAL_PHASE_CONSERVATION_ALL_SCREEN_SLOTS.csv',phasedaily);table(HERE/'B0_96_SLOT_EXTREMA_ALL_ALPHAS.csv',allslots);table(HERE/'B0_DAILY_EXTREMA_WITNESSES.csv',witness)
    conservation=dict(status='PASS',native_load_count=len(loads),native_base_kw=float(P.sum()),native_base_kvar=float(Q.sum()),native_status_counts=dict(Counter(r['status'] for r in loads)),native_phase_count_counts=dict(Counter(r['phases'] for r in loads)),native_primary_phase_counts=dict(Counter(phase)),native_PF_values=sorted(set(pf)),native_definition_bus_phase_connection_status_model_and_ratings_changes=0,native_base_PQ_restored_after_each_trajectory=True,maximum_phase_and_total_scheduled_PQ_PV_conservation_error_kw_kvar=maxerr,maximum_PF_error_over_positive_alpha_scheduled_loads=pferr,alpha_zero_PF='No power draw; original stored native PF is retained in baseline and restored after screening',PV_allocation_rule='Exactly proportional to native base kW at identical native bus/nodes/connection/voltage; native split-phase legs stay separate',PV_peak_penetration_ratio=ratio,PV_peak_kw_at_alpha1=float(P.sum()*ratio),PV_reactive_power_kvar=0.,AIDC_power_identical_for_all_alphas=True,AIDC_MESS_scale_changes=0,host_PCC_topology_changes=0,temporal_profiles_Actual_reads=0)
    save(HERE/'SPATIAL_PHASE_CONSERVATION_AUDIT.json',conservation)
    # Verify retained source and ALL topology/PCC evidence against pre-run hashes and mtimes.
    before=read(HERE/'IMMUTABLE_AUTHORITIES_BEFORE.json');bad=[]
    for r in before:
        p=Path(r['path']);st=p.stat()
        if st.st_size!=r['bytes'] or st.st_mtime_ns!=r['mtime_ns'] or sha(p)!=r['sha256']:bad.append(r['path'])
    assert not bad
    sources=read(HERE/'DATE_SELECTION_SOURCES.json');sources+=list(read(HERE/'PREFLIGHT_INPUT_FREEZE.json')[k] for k in ['specification','date','forecast','PV_ratio','AIDC','resources','allocation'])
    bound=read(HERE/'FORECAST_CAUSALITY_AND_INPUT_BINDING.json');sources += [bound['forecast_cache'],bound['B0_exogenous']]+bound['raw_forecast_sources']
    resources=read(HERE/'UNCHANGED_RESOURCE_SCALE_AUTHORITY.json');sources += [resources[k] for k in ['AIDC_power','AIDC_GPU_authority','MESS_constants_source','MESS_command_source']]
    assert all(sha(Path(r['path']))==r['sha256'] for r in sources)
    save(HERE/'IMMUTABILITY_AND_SOURCE_RECHECK.json',dict(status='PASS',protected_IEEE8500_source_selection_and_overlay_files=len(before),changed_files=bad,hash_and_size_and_mtime_verified=True,source_input_hash_rechecks=len(sources),V41R4_files_written=0,topology_host_changes=0,PCC_overlay_changes=0))
    save(HERE/'EXECUTION_AND_DATA_FIREWALL_AUDIT.json',dict(status='B0_ONLY_SCREEN_COMPLETE_NO_FEASIBLE_ALPHA',date_selection='31 days of B0 DAYAHEAD Fresh line arrays; all bound to archive member SHA256 before date freeze',selected_date='2025-05-21',forecast_construction='Selected-date D-1 VIC1 forecast JSON and exact forecast ZIP rows only',old_model_PV_transfer='Only selected B0 exogenous aggregate PV/background peak ratio; old spatial mapping, old gross demand+PV formula and old sensitivities not transferred',AIDC='Selected B0 frozen GPU/IT/PCC/Q arrays copied unchanged',MESS='Selected B0 four-unit P=Q=0 commands and energy state unchanged',B1_B2_B3_result_payload_reads=0,B1_B2_B3_optimization_calls=0,Actual_demand_or_PV_inputs_read=0,source_proximity_or_site_selection_reruns=0,screen_96_slot_trajectories=21,screen_explicit_operating_solves=2016,independent_slot0_scalar_measurement_validation_solves=3,validation_attempts_note='First two independent slot0 checks completed the physical solve and confirmed scalar/vector metrics, then stopped on an extra 1-W terminal-power residual assertion. Third check reports the 2.004-W native terminal-power numerical residual rather than imposing it as an unrequested hard limit. No screening results, physical criteria or operating inputs changed.',pre_operating_setup_failures=4,setup_note='Fixed-status native loads require direct per-load P/Q scaling; five disabled native tie lines have no initialized NodeOrder and are zero-current excluded from active axes, with disabled status unchanged. All four setup attempts ended before any explicit operating solve.',native_control_state_behavior='Unchanged native autonomous controls, fresh canonical initial states at each alpha, chronological within-day carry-forward',hard_limits_relaxed=False,alpha_grid_refinement=False,selected_alpha=None,final_mapping_PCC_authority_unchanged=True))
    bestmax=min(screen,key=lambda s:s['voltage_max_pu']);firstline=next(s for s in screen if s['max_phase_line_loading_pu']<=1+1e-9);a1=screen[0]
    phase_lines='\n'.join(f"| {p['primary_phase']} | {p['native_loads']} | {p['base_P_kw']:.6f} | {p['base_Q_kvar']:.6f} | {p['PV_peak_kw_at_alpha1']:.6f} |" for p in phasebase)
    screen_lines='\n'.join(f"| {s['alpha']:.2f} | {s['voltage_min_pu']:.6f} | {s['voltage_max_pu']:.6f} | {s['max_phase_line_loading_pu']:.6f} | {s['max_transformer_phase_current_pu']:.6f} | {s['max_transformer_total_kva_pu']:.6f} | FAIL |" for s in screen)
    report=f'''# IEEE8500 one-day operating-point construction — B0 only

**Status: NO_FEASIBLE_ALPHA_ON_FROZEN_GRID. Selected date: 2025-05-21. Selected alpha: null.**

The requested construction and complete frozen-grid screening are finished. No alpha in 1.00, 0.95, ..., 0.00 satisfies all four hard limits. No feasible operating-point authority is asserted. This is a grid-specific result; no claim is made about off-grid values, changed controls, or other dates. FINAL AIDC/STA mapping, PCC overlay, native source and all selection evidence remain unchanged.

## Date and causal inputs

The date is the argmax of the 31 May B0 DAYAHEAD Fresh daily phase-line maxima, with earliest-date tie-breaking preregistered. On 2025-05-21 the maximum is **0.8498557617902092 pu**, line.l10 / phase A / slot 31. Both the summary and phase arrays for each B0 day match the archived member SHA256. Date freeze occurred before construction or alpha screening. B1/B2/B3 result payloads and optimization were not accessed.

VIC1 demand was issued **2025-05-20 17:32:29 AEST**, predispatch sequence 2025052028/run 1; rooftop PV was issued **2025-05-20 18:00:00 AEST**. Both meet the D-1 18:00 cutoff. The 48 half-hour rows were checked directly against each original forecast ZIP and exactly reproduce the 96-slot cached forecast by repetition. Slots use fixed AEST (UTC+10), interval starts 00:00–23:45 and ends 00:15–24:00. Demand peak is 7388.6 MW; PV forecast peak is 2300.042 MW. Actual data is absent from construction.

`m_D(t) = demand_DA(t)/7388.6`. For every native load, nominal scheduled P and Q are `alpha*m_D(t)*P_native` and `alpha*m_D(t)*Q_native`. The original 2306 Variable and 48 Fixed statuses are retained, so assignments are made individually with LoadMult=1. Base definitions are restored after each complete trajectory and audited.

The B0 exogenous PV/background gross peak ratio is **{ratio:.16f} ({100*ratio:.9f}%)**. The denominator is gross native/background demand including its already applied V41R4 factor 1.15, excluding AIDC; the numerator is PV peak, not installed PV capacity. Only this ratio is transferred. IEEE8500 PV peak is `alpha*{total if False else P.sum()*ratio:.12f}` kW, with normalized D-1 rooftop-PV shape, Q=0 and deterministic base-kW proportional allocation to the identical native load bus and phase connection. The old gross-demand-plus-PV formula is not used in IEEE8500.

## Conservation and unchanged resources

Native load totals are **{P.sum():.6f} kW / {Q.sum():.9f} kvar**, 2354 loads. Bus, local split-phase leg, upstream primary phase, connection, nominal voltage, native PF and model are audited. Local secondary node 2 is a split-phase leg, not automatically primary phase B. Conservation error across all screened slot/phase totals is at most {maxerr:.3g} kW/kvar; PF error at positive alpha is at most {pferr:.3g}.

| Upstream phase | Loads | Native kW | Native kvar | PV peak kW at alpha=1 |
|---|---:|---:|---:|---:|
{phase_lines}

The selected B0 GPU/IT/PCC/Q arrays are byte-identical to V41R4: 12 AIDC, 780 GPU capacity with the original per-site vector, fixed P/Q schedule and PF=0.95. Four MESS units retain the original zero-P/Q B0 commands and 1200-kWh capacity / 760-kWh initial energy. The current source-bound MESS runtime specifies 300-kW active limit and 400-kVA PCS; the older PCC design reference mentions 700 kVA, which is not substituted for the current runtime limit. All immutable 12×1500-kVA AIDC and 24×750-kVA MESS service PCC transformers are preserved. No resource optimization or rescaling is performed.

## Physical scope and screen

Each alpha starts a clean OpenDSS context and executes 96 chronological B0 snapshots with native regulator/capacitor controls and unchanged settings; native control states carry between slots. All **2016/2016** screened slots converged with control actions complete. Native/PCC static definitions compare unchanged after restoring scheduled load P/Q. Resource objects use existing buses: **4912 buses / 8639 electrical nodes / 1226 transformers / 3703 lines**, including five originally disabled tie lines whose current is verified zero. New objects are 12 AIDC loads and 2354 separate PV generators; MESS external injection remains zero.

Hard limits are 0.95–1.05 pu at every electrical node, line phase current ≤ unchanged NormAmps, all transformer winding phase currents ≤ nameplate current and winding total kVA ≤ nameplate kVA. Both line terminals and every transformer winding are checked. Ground conductors are excluded from phase-current ratios; each winding's total complex terminal power is measured independently. Numerical boundary tolerance is 1e-9. No emergency rating allowance or control retuning is used.

| Alpha | Vmin | Vmax | Line current max pu | TF current max pu | TF kVA max pu | All limits |
|---:|---:|---:|---:|---:|---:|---|
{screen_lines}

Alpha 1.00 fails voltage and line current limits. The first downward grid point passing line current is **{firstline['alpha']:.2f}**, but its Vmax is **{firstline['voltage_max_pu']:.9f}**. The smallest daily Vmax among all tested alphas occurs at **{bestmax['alpha']:.2f}**, **{bestmax['voltage_max_pu']:.9f} pu**, still above 1.05. Transformer limits pass throughout. Thus decreasing background demand alone does not produce a feasible 96-slot B0 under this exact immutable model and rule.

Independent scalar OpenDSS reads of all 4935 enabled PDElements exactly match vectorized current/power measurements and the saved alpha1 slot0 voltage/line/transformer metrics (maximum difference 0). The native terminal-power numerical residual in that spot check is about 0.002004 kW; input P/Q and PF assertions pass. This residual is reported and is not an additional hard criterion or a relaxation of the requested voltage/current limits. Original voltage-dependent Model1 behavior is retained outside its constant-PQ voltage range.

## Files and freeze

- `SELECTED_DATE_FREEZE.json`, `MAY_B0_FRESH_DAILY_LINE_MAXIMA.csv`: date authority and 31-day B0 evidence.
- `DEMAND_PV_TEMPORAL_PROFILES.csv`, `FORECAST_CAUSALITY_AND_INPUT_BINDING.json`, `PV_PENETRATION_RATIO_AUTHORITY.json`: temporal forecasts, raw ZIP verification and ratio.
- `NATIVE_LOAD_AND_PV_ALLOCATION.csv`, `SPATIAL_PHASE_CONSERVATION_AUDIT.json`, `SPATIAL_PHASE_CONSERVATION_ALL_SCREEN_SLOTS.csv`: load/phase/PF and PV conservation.
- `ALPHA_SCREEN_TABLE.csv`, `SELECTED_ALPHA_AND_B0_STATUS.json`: full descending screen and explicit null selection.
- `B0_96_SLOT_EXTREMA_ALL_ALPHAS.csv`, `B0_DAILY_EXTREMA_WITNESSES.csv`, `screen/alpha_*/B0_ALL_PHASE_ARRAYS.npz`: all slot extrema and phase measurements. There is no selected-alpha 96-slot file because no alpha is feasible.
- `IMMUTABILITY_AND_SOURCE_RECHECK.json`: all **{len(before)}** protected source, topology-selection and PCC files match SHA, size and mtime; no V41R4 writes.
- `OPERATING_POINT_FREEZE_MANIFEST.json` and `.sha256`: frozen construction, unsuccessful feasibility screen and evidence. The freeze does not authorize a feasible operating point or B1/B2/B3 execution.
'''
    (HERE/'IEEE8500_ONE_DAY_B0_OPERATING_POINT_REPORT.md').write_text(report,encoding='utf-8')
    manifest=dict(status=status['status'],selected_date='2025-05-21',selected_alpha=None,source_PCC_mapping_immutable=True,B1_B2_B3_optimization_calls=0,files=[dict(path=p.relative_to(HERE).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name not in ('OPERATING_POINT_FREEZE_MANIFEST.json','OPERATING_POINT_FREEZE_MANIFEST.sha256') and '__pycache__' not in p.parts])
    save(HERE/'OPERATING_POINT_FREEZE_MANIFEST.json',manifest);h=sha(HERE/'OPERATING_POINT_FREEZE_MANIFEST.json');(HERE/'OPERATING_POINT_FREEZE_MANIFEST.sha256').write_text(h+'  OPERATING_POINT_FREEZE_MANIFEST.json\n',encoding='ascii')
    assert all(sha(HERE/r['path'])==r['sha256'] for r in manifest['files'])
    print(json.dumps(dict(status=status['status'],selected_date='2025-05-21',selected_alpha=None,protected_files=len(before),frozen_files=len(manifest['files']),manifest_sha256=h,smallest_screen_Vmax=bestmax['voltage_max_pu'])))
if __name__=='__main__':main()
