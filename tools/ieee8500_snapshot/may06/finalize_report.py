"""Aggregate saved B0 evidence only; no new power-flow/optimization calls."""
import csv,json,hashlib,datetime
from pathlib import Path
H=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
rows=read(H/'BACKGROUND_SCREEN_TABLE.json');out=read(H/'BACKGROUND_SELECTION.json')
assert out['status']=='NO_FEASIBLE_B0_ON_USER_GRID' and len(rows)==3 and not any(r['exact_AC_feasible'] for r in rows)
evidence=[]
for r in rows:
 p=H/'background_screen'/f'alpha_{r["alpha_BG"]:.2f}'/'SLOT_EXTREMA.csv'
 with p.open(encoding='utf-8-sig',newline='') as f:slots=list(csv.DictReader(f))
 assert len(slots)==96 and all(s['converged']=='True' and s['controls_settled']=='True' for s in slots)
 high=max(slots,key=lambda s:float(s['max_phase_line_loading']));low=min(slots,key=lambda s:float(s['Vmin']))
 evidence.append(dict(alpha_BG=r['alpha_BG'],line_violation_slots=sum(float(s['max_phase_line_loading'])>1+1e-9 for s in slots),voltage_violation_slots=sum(float(s['Vmin'])<.95-1e-9 or float(s['Vmax'])>1.05+1e-9 for s in slots),max_line_witness=high['line_witness'],max_line_slot=int(high['slot']),minimum_voltage_node=low['Vmin_node'],minimum_voltage_slot=int(low['slot']),source=str(p)))
(H/'FAILURE_WITNESSES.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
md=['# May06 IEEE8500 independent screening','','**NO_FEASIBLE_B0_ON_USER_GRID** — 지정한 세 background alpha 모두 B0 exact AC hard limits를 위반했습니다.','','- 날짜:2025-05-06; scope:Day-Ahead exact OpenDSS AC,96 chronological slots/case.','- source1.0400pu, all Vreg123.5V, CAPBank3 OFF. Native topology/ratings/PCC/controlled capacitor settings unchanged.','- AIDC scale1.00; MESS OFF for B0. Authorized later MESS fleet remains4×300kW/400kVA.','- PV interpretation adopted before screening: May06 forecast and B0 exogenous penetration ratio, with PV capacity fixed at inherited alpha0.50. Only native load P/Q varied with alpha. PV proportional-to-alpha was not tested.','- Comparison scope was provisionally Day-Ahead exact AC while the optional user scope question remained unanswered. No B1/B2/B3 ranking or scale selection was performed.','- This is outcome-conditioned exploratory screening; no general policy-superiority claim is made.','','| αBG | AIDC scale | B0 max line(pu) | Vmin | Vmax | transformer current(pu) | winding kVA(pu) | feasible | runtime(s) |','|---:|---:|---:|---:|---:|---:|---:|---|---:|']
for r in rows:md.append(f'| {r["alpha_BG"]:.2f} |1.00| {r["B0_max_phase_line_loading"]:.9f} | {r["Vmin"]:.9f} | {r["Vmax"]:.9f} | {r["transformer_phase_current_max"]:.9f} | {r["transformer_winding_kVA_max"]:.9f} |FAIL| {r["runtime_s"]:.3f} |')
md+=['','All288 slots converged and controls settled. Feasibility failed because of line overload; alpha0.65 and0.70 additionally had undervoltage. Runtime is per-case setup through96 solves and static checks, before output-array compression; preparation/source-hash validation excluded.','','## Stop gate','','No feasible alpha was selected. AIDC scales1.25/1.50, B1, B2, B3 and new Actual replays were not executed. Their values and adjacent differences are NA in BACKGROUND_SCREEN_TABLE.csv. No additional alpha, source, Vreg, capacitor or rating tuning was attempted.','','## Critical witnesses','']
for e in evidence:md.append(f'- alpha{e["alpha_BG"]:.2f}: line witness `{e["max_line_witness"]}`, zero-based slot{e["max_line_slot"]}; line violating slots={e["line_violation_slots"]}, voltage violating slots={e["voltage_violation_slots"]}.')
md+=['','## Preservation','','All72 prebound model/input/helper files passed SHA256, size and mtime rechecks. Each case additionally verified unchanged static native/PCC definitions after restoring scheduled native loads. Existing May21 results and active B2 Actual/export processes were not modified, stopped or reused as May06 outcomes.','The PRE_EXECUTION_FREEZE.json and B0_STAGE_OUTPUT_SHA256.json remain unchanged. Raw voltage/current/kVA arrays, control states and per-slot extrema are retained under background_screen/.','']
(H/'SCREENING_REPORT.md').write_text('\n'.join(md),encoding='utf-8')
files=[]
for p in sorted(H.rglob('*')):
 if p.is_file() and p.name!='FINAL_SCREENING_MANIFEST.json':files.append(dict(path=str(p.relative_to(H)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(H/'FINAL_SCREENING_MANIFEST.json').write_text(json.dumps(dict(status=out['status'],files=files,aggregation_scientific_execution_count=0,total_exact_AC_slots=288,B1_B2_B3_runs=0,timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(status=out['status'],files=len(files),report=str(H/'SCREENING_REPORT.md'),witnesses=evidence),ensure_ascii=False))
