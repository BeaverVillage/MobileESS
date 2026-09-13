import sys,csv,json
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
sys.dont_write_bytecode=True
import stress_common as s
from case_runner import run_case
H=s.H
def scan_source(source):
    data=s.input_authorities();rule=s.read(H/'STRESS_CALIBRATION_RULE.json');rows=[]
    for vreg in rule['all_regulator_Vreg_grid_V']:
        for a in rule['alpha_grid']:
            rows.append(run_case(source,vreg,a,s.case_folder(source,vreg,a),data));s.table(H/'screen'/f'source_{source:.4f}'/'SOURCE_SCREEN_TABLE.csv',rows);s.save(H/'screen'/f'source_{source:.4f}'/'SOURCE_SCREEN_TABLE.json',rows)
    return rows
def main():
    s.check_freeze();rule=s.read(H/'STRESS_CALIBRATION_RULE.json');assert not (H/'EXECUTION_START.json').exists();s.save(H/'EXECUTION_START.json',dict(utc=datetime.now(timezone.utc).isoformat(),pre_execution_manifest_sha256=s.sha(H/'PRE_EXECUTION_FREEZE_MANIFEST.json'),workers=5,cases=100,chronological_slots_per_case=96,B1_B2_B3_reads_or_runs=0))
    with ProcessPoolExecutor(max_workers=5) as pool:groups=list(pool.map(scan_source,rule['source_grid']))
    rows=[r for group in groups for r in group];assert len(rows)==100;s.table(H/'STRESS_CALIBRATION_SCREEN_TABLE.csv',rows);s.save(H/'STRESS_CALIBRATION_SCREEN_TABLE.json',rows)
    feasible=sorted([r for r in rows if r['feasible']],key=s.ranking_key);chosen=feasible[0] if feasible else None
    s.save(H/'PROVISIONAL_STRESS_SELECTION.json',dict(status='FEASIBLE_STRESS_CASE_PENDING_INDEPENDENT_REPLAY' if chosen else 'NO_FEASIBLE_CASE_ON_FROZEN_STRESS_CALIBRATION_GRID',final_authority=False,selected=chosen,feasible_case_count=len(feasible),target_max_phase_line_loading_pu=.85,ranked_feasible_cases=feasible,rule_sha256=s.sha(H/'STRESS_CALIBRATION_RULE.json'),B1_B2_B3_runs=0))
    s.table(H/'RANKED_FEASIBLE_CASES.csv',[dict(rank=i+1,**r) for i,r in enumerate(feasible)])
    allrows=[]
    for r in rows:
        with (s.case_folder(r['source_pu'],r['vreg_V'],r['alpha'])/'B0_96_SLOT_EXTREMA.csv').open(encoding='utf-8',newline='') as f:allrows.extend(csv.DictReader(f))
    s.table(H/'B0_9600_SLOT_EXTREMA.csv',allrows);print('STRESS_GRID_COMPLETE',json.dumps(chosen),flush=True)
if __name__=='__main__':main()
