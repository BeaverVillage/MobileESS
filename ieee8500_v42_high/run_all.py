"""Recomputed same-population screening followed by fixed-scenario validation."""
import shutil
from .common import *
from .screen import run_day,fresh_compare
from .schedule import stationary_schedule,audit_ac_ports


def run_recomputed_screen():
    preregister();results=[]
    preserved=REPORT/'fixed_occupancy_AC_preserved';preserved.mkdir(parents=True,exist_ok=True)
    for name in ('BG_AIDC_SCALE_SCREENING.csv','PLANNING_SCENARIO_SELECTION.json'):
        if not (preserved/name).exists():shutil.copyfile(REPORT/name,preserved/name)
    for cap in CAPACITY_CANDIDATES:
        path=ROOT/'ieee8500_v42_high/data/facility/recomputed'/f'{cap}_PLANNING_INPUTS.npz'
        assert path.is_file()
        for bg in BG_CANDIDATES:
            result=run_day(f'E1R_{cap}_BG{bg:.3f}',bg,cap,input_path=path)
            results.append(result);table(REPORT/'BG_AIDC_SCALE_SCREENING.csv',results)
    eligible=[r for r in results if r['capacity']=='C0' and r['grid_hard_PASS'] and .75<=r['rho_max']<=.85]
    selected=min(eligible,key=lambda r:(abs(r['rho_max']-.8),r['bg'])) if eligible else None
    decision=dict(selected=selected,rule=read(REPORT/'SCENARIO_PREREGISTRATION.json')['candidate_priority'],
        authoritative_scope='same original jobs, capacity-specific reference/queue/occupancy/C1/PCC recomputation',
        historical15_trials_preserved=True,authoritative_Planning_trials=15,Actual_outcomes_used=False,
        selection_before_MESS_effects=True,C1_C2_hardware_NOT_PROMOTED=True,target_PASS=selected is not None,
        final_Production_freeze=False)
    write(REPORT/'PLANNING_SCENARIO_SELECTION.json',decision)
    if not selected:return decision
    import numpy as np
    with np.load(BALANCED_REPORT/'ac/BALANCED_PLANNING/AC_96.npz') as old,np.load(REPORT/'ac/E1R_C0_BG0.552/AC_96.npz') as current:
        diff={k:float(np.abs(old[k]-current[k]).max()) for k in old.files}
    assert max(diff.values())<1e-6
    write(REPORT/'PR197_RECOMPUTED_REGRESSION.json',dict(PASS=True,maximum_errors=diff))
    return decision


def run_validations(decision):
    assert decision['selected'] and not decision['Actual_outcomes_used'];bg=decision['selected']['bg'];capacity=decision['selected']['capacity']
    schedule=stationary_schedule();records=[]
    for day,prefix in [('2025-05-01','FINAL'),('2025-05-02','VALIDATION')]:
        for source in ('PLANNING','ACTUAL'):
            input_path=(ROOT/'ieee8500_v42_high/data/facility/recomputed'/f'{capacity}_{source}_INPUTS.npz') if day=='2025-05-01' else inputs(capacity,source,day)
            for controlled in (False,True):
                tag=f'{prefix}_{"MESS" if controlled else "B0"}_{source}'
                first=run_day(tag,bg,capacity,source,day,schedule=schedule if controlled else None,input_path=input_path)
                fresh=run_day(tag+'_FRESH',bg,capacity,source,day,schedule=schedule if controlled else None,input_path=input_path)
                comparison=fresh_compare(tag,tag+'_FRESH')
                if controlled:
                    audit_ac_ports(tag,schedule);audit_ac_ports(tag+'_FRESH',schedule)
                records.append(dict(day=day,source=source,controlled=controlled,first=first,fresh=fresh,Fresh=comparison))
                write(REPORT/'RUN_RECEIPT.json',dict(selection=decision,records=records,Native_calls=0,
                    fixed_common_policy=True,Actual_retuning=False,synthetic_jobs=0,algorithm_edits=0))
    return records


if __name__=='__main__':
    selection=run_recomputed_screen()
    if selection['target_PASS']:run_validations(selection)
