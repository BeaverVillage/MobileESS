"""Independent saved-artifact integrity and missing-evidence checks."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

from .audit import ROOT,DOC,R043,read,save


def main():
    if (DOC/'PREFLIGHT_GATES.json').exists():
        raise RuntimeError('Phase1 static checks are historical and reused. Use results saved-array numerical review for G2/G3.')
    checks=[]
    def check(name,ok):
        checks.append(dict(check=name,PASS=bool(ok)))
    identity=read(DOC/'V2_ADD_EXPERIMENT_IDENTITY.json')
    check('independent_version_and_MESS8',identity['experiment_id']=='V2_add' and identity['MESS']==8)
    tracked=subprocess.check_output(['git','-C',str(ROOT),'diff','--name-only',R043],text=True).splitlines()
    check('original_r043_tracked_source_unchanged',all(p.startswith(('docs/v2_add/','v2_add_preflight/')) for p in tracked))
    for r in read(DOC/'SOURCE_COPY_RECEIPTS.json'):
        check('immutable_copy:'+r['source_path'],hashlib.sha256((ROOT/r['target']).read_bytes()).hexdigest()==r['sha256'])
    frozen=np.load(DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz',allow_pickle=False)
    allocated=np.load(DOC/'input/IEEE8500_BG_ALLOCATION_CANDIDATE.npz',allow_pickle=False)
    for role,count in [('PLANNING',96),('ACTUAL',120)]:
        for q,suffix in [('P','kw'),('Q','kvar')]:
            a=allocated[f'{role}_{q}']
            b=frozen[f'{role}_BG_{q}_{suffix}']
            check(role+q+'_total_conservation',a.shape==(count,1177) and np.max(abs(a.sum(axis=1)-b.sum(axis=1)))<1e-8)
        check(role+'_site12_axis',frozen[f'{role}_AIDC_P_kw'].shape==(count,12))
    inv=read(DOC/'OFFICIAL_BALANCED_INVENTORY.json')
    check('actual_DSS_source_counts',inv['count_PASS'])
    check('official_balanced_load_structure',inv['counts']['all_loads_official_balanced_2phase_wye_208V'])
    source=read(DOC/'OFFICIAL_BALANCED_AXES.json')
    check('all_original_line_ratings_positive',all(r['normal_amps']>0 for r in source['lines']))
    proposed=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')
    check('eight_distinct_original_STA_candidates',len(proposed['initial_sites'])==8 and len(set(proposed['initial_sites'].values()))==8 and proposed['all_initial_sites_exist'])
    check('no_route_or_dispatch_forcing',not proposed['dispatch_STAY_MOVE_fixed'] and not proposed['route_ETA_energy_regeneration'])
    gate=read(DOC/'FINAL_GO_NO_GO.json');freeze=read(DOC/'SELECTED_SCENARIO_FREEZE.json')
    check('no_false_scenario_freeze',freeze['beta_BG'] is None and freeze['status']=='NOT_FROZEN')
    check('no_false_qualified_failure',not gate['qualified_scenario_search_complete'] and not gate['no_qualified_scenario_declared'])
    check('preflight_and_native_remain_gated',not gate['operating_AC_allowed'] and not gate['native_allowed'])
    fields={'BACKGROUND_SCALE_SCREENING.csv':['planning_rho','actual_rho'],
            'MV_LV_LOADING_COMPARISON.csv':['rho_MV','rho_LV','rho_global','H_daily'],
            'TOP20_GLOBAL_CRITICAL_LINES.csv':['line','rho'],
            'AIDC_MESS_SENSITIVITY.csv':['baseline_rho','controlled_rho','delta_global_pp'],
            'FEASIBLE_96SLOT_CONTROL_PILOT.csv':['AIDC_kw','MESS_P_kw','SOC_kwh','rho_global'],
            'B0_B1_B2_B3_COMPARISON.csv':['planning_rho','actual_rho','UB','LB','gap']}
    for name,columns in fields.items():
        rows=list(csv.DictReader((DOC/name).open(encoding='utf-8')))
        check('missing_values_not_invented:'+name,all(r['status']=='NOT_VERIFIED' and all(r[k]=='' for k in columns) for r in rows))
    figure=read(DOC/'FIGURE_READINESS.json')
    check('all3703_original_lines_drawn',figure['topology']['line_segments_drawn']==3703)
    save('ARTIFACT_VERIFICATION.json',dict(PASS=all(r['PASS'] for r in checks),checks=checks,
         note='Integrity/readiness checks are not physics, feasible-pilot or optimization certification'))
    print(json.dumps(dict(PASS=all(r['PASS'] for r in checks),checks=len(checks),failed=[r for r in checks if not r['PASS']]),indent=2))
    if not all(r['PASS'] for r in checks):raise SystemExit(1)


if __name__=='__main__':main()
