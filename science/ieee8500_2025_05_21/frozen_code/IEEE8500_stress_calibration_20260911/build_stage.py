"""Build new stage files before execution; read immutable prior code without edits."""
import sys,ast,json
from pathlib import Path
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parent;PREV=R/'IEEE8500_source_grid_compatibility_20260911';COMPAT=R/'IEEE8500_production_compatibility_20260911'
def main():
    prior=json.loads((PREV/'SOURCE_GRID_RULE.json').read_text(encoding='utf-8'))
    rule=dict(authority_type='IEEE8500_STRESS_CALIBRATION_PREREGISTRATION',preserved_voltage_feasible_authority={'source_pu':1.045,'alpha8500':0.25,'role':'Voltage-feasible compatibility authority; immutable, not overwritten or reclassified'},source_grid=[1.0450,1.0425,1.0400,1.0375,1.0350],all_regulator_Vreg_grid_V=[125.,124.5,124.,123.5],alpha_grid=[.4,.45,.5,.55,.6],target_max_phase_line_loading_pu=.85,target_interpretation='A priori stressed-but-feasible large-feeder B0 baseline; not a target to exactly reproduce IEEE123 results',allowed_calibration_parameters=['Vsource.source.pu','Common forward Vreg on all 12 native RegControls','Native demand and proportionally allocated PV alpha'],fixed_conditions=prior['resource_and_topology_policy']+' All capacitor control logic, PTRatio=60, band=2 V and tap limits unchanged; CAPBank3 OFF.',selected_date=prior['selected_date'],inputs=prior['inputs'],limits=prior['limits'],limit_scope=prior['limit_scope'],solver_policy=prior['solver_policy'],selection_rule='Discard physically infeasible cases, then ascending lexicographic key [abs(max_phase_line_loading_pu-0.85),abs(Vreg_V-125),abs(source_pu-1.05),-alpha]. Use unrounded double-precision metrics with no target/tie rounding. All four key components are frozen. No grid refinement.',execution='All 100 combinations are freshly evaluated. Five isolated source workers; Vreg descending and alpha ascending within each worker. Each case has a fresh engine and 96 sequential snapshots with accepted native tap/cap state carry. Completion order is not a selection input.',independent_replay='Selected case only, in a separate clean process/fresh context for 96 chronological slots. Independently reconstruct all phase metrics through scalar bus/element APIs. Require hard feasibility, maximum phase-array difference <=1e-10 pu, matching accepted tap/cap states and no static drift; otherwise stop without authority/tuning.',canonical_IEEE8500_reproduction=False,B1_B2_B3_reads_or_runs_allowed=False,extra_tuning_allowed=False)
    (H/'STRESS_CALIBRATION_RULE.json').write_text(json.dumps(rule,indent=2),encoding='utf-8')
    source=(PREV/'control_telemetry.py').read_text(encoding='utf-8').replace('def control_state(d,t,expected_source):','def control_state(d,t,expected_source,expected_vreg):').replace("r['Vreg']==125", "r['Vreg']==expected_vreg")
    (H/'stress_control_telemetry.py').write_text(source,encoding='utf-8')
    for source in rule['source_grid']:
        for vreg in rule['all_regulator_Vreg_grid_V']:
            path=H/'overlays'/f'Source_{source:.4f}_Vreg_{vreg:.1f}.dss';path.parent.mkdir(exist_ok=True)
            path.write_text(f'! B0 stress calibration adaptation; not canonical IEEE8500 reproduction.\nRedirect "{COMPAT / "IEEE8500_Compatibility_Adaptation.dss"}"\nEdit Vsource.source pu={source:.4f}\nBatchEdit RegControl..* Vreg={vreg:.1f}\n',encoding='utf-8')
    # Reuse the validated chronological runner locally, with explicit calibrated parameters.
    original=(PREV/'screen_source_grid.py').read_text(encoding='utf-8');tree=ast.parse(original);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_case');fn=ast.get_source_segment(original,node)
    fn=fn.replace('def run_case(source,a,folder,data):','def run_case(source,vreg,a,folder,data):').replace('H / f"Source_{source:.3f}_Compatibility.dss"','overlay_path(source,vreg)').replace('allowed_audit(native,adapted,source)','allowed_audit(native,adapted,source,vreg)').replace('states.append(control_state(d,t,source))','states.append(control_state(d,t,source,vreg));rows[-1]["vreg_V"]=vreg')
    start=fn.index('    # Fresh 1.050 runs')
    end=fn.index('    d.Basic.ClearAll()',start)
    fn=fn[:start]+'''    # Read-only reproduction check for the 15 common old/new grid cases.
    if vreg==125. and source in [1.045,1.04,1.035]:
        with np.load(PREV/'screen'/f'source_{source:.3f}'/f'alpha_{a:.2f}'/'B0_ALL_PHASE_ARRAYS.npz') as z:delta={k:float(np.max(np.abs(z[k]-np.array(v)))) for k,v in zip(KEYS,values)}
        save(folder/'PREVIOUS_125V_CASE_REPRODUCTION.json',dict(status='PASS' if max(delta.values())<=1e-10 else 'FAIL',max_absolute_differences=delta));assert max(delta.values())<=1e-10,delta
'''+fn[end:]
    (H/'case_runner.py').write_text('import time\nimport numpy as np\nfrom stress_common import *\n\n'+fn+'\n',encoding='utf-8')
    # Retain the already validated independent scalar measurement implementation.
    replay=(PREV/'independent_replay.py').read_text(encoding='utf-8').replace('import screen_source_grid as s','import stress_common as s').replace('PROVISIONAL_LEXICOGRAPHIC_SELECTION.json','PROVISIONAL_STRESS_SELECTION.json').replace("source,a=chosen['source_pu'],chosen['alpha']", "source,vreg,a=chosen['source_pu'],chosen['vreg_V'],chosen['alpha']").replace('H / f"Source_{source:.3f}_Compatibility.dss"','s.overlay_path(source,vreg)').replace('s.allowed_audit(native,adapted,source)','s.allowed_audit(native,adapted,source,vreg)').replace("H/'screen'/f'source_{source:.3f}'/f'alpha_{a:.2f}'",'s.case_folder(source,vreg,a)').replace('state=s.control_state(d,t,source);states.append(state)','state=s.control_state(d,t,source,vreg);states.append(state);rows[-1]["vreg_V"]=vreg').replace('source_pu=source,alpha8500=a,simulation_slots=96','source_pu=source,vreg_V=vreg,alpha8500=a,simulation_slots=96')
    (H/'independent_stress_replay.py').write_text(replay,encoding='utf-8')
    print('Built stress rule, 20 overlays, chronological case runner and independent replay; no simulations run.')
if __name__=='__main__':main()
