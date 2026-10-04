"""Native adapter diagnostic, no A1 solve and no campaign/day PASS receipt."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import numpy as np
import pandas as pd
from v42_b1_production.common import *
from v42_b1_production.replay import fresh,actual


def main():
    root=Path('C:/v42_b1_audit'); day='2025-05-01'
    fixture=root/'native_fixture';fixture.mkdir(exist_ok=False)
    plan=fixture/'planning';plan.mkdir();act=fixture/'actual';act.mkdir();out=fixture/'fresh';out.mkdir()
    b=read(root/'inputs'/day/'NATIVE_INPUT.json'); sites=sorted(b['capacities'])
    coefficients=pd.read_csv(Path(b['current_day_folder'])/'C1_PLANNING_COEFFICIENTS.csv')
    power=read(Path(b['current_day_folder'])/'POWER_AUTHORITY.json')
    idle=power['current_IT_idle_kW_per_installed_GPU']
    p=np.zeros((96,12));q=np.zeros((96,12))
    for r in coefficients.itertuples():
        i=sites.index(r.aidc_id);p[r.slot,i]=r.slope*idle*b['capacities'][r.aidc_id]+r.intercept_kw
    q=p*np.tan(np.arccos(.95))
    freeze=dict(days=[day],run_id='SYNTHETIC_PORT_DIAGNOSTIC_ONLY',Git_SHA='a'*40,
                scientific_SHA='b'*64,day_input_SHA={day:sha(root/'inputs'/day/'NATIVE_INPUT.json')})
    decision=dict(status='PASS',arm='B1',day=day,capacity_GPU=780,known_job_actions={},
        SYNTHETIC_ONLY=True,A1_SOLVES=0,NOT_A_PRODUCTION_RESULT=True,
        site_PCC_power_trajectory=[dict(slot=t,AIDC=s,PCC_P_kW=p[t,i],PCC_Q_kvar=q[t,i]) for t in range(96) for i,s in enumerate(sites)],
        site_IT_power_trajectory=[dict(slot=t,AIDC=s,IT_power_kW=idle*b['capacities'][s]) for t in range(96) for s in sites],
        site_GPU_trajectory=[dict(slot=t,AIDC=s,active_GPU=0) for t in range(96) for s in sites])
    atomic(plan/'V42_DAYAHEAD_DECISION_FREEZE.json',dict(identity=identity(freeze,day,'PLANNING_FREEZE'),decision=decision,DA_decision_SHA256=digest(decision)))
    actual(plan,identity(freeze,day,'PLANNING_FREEZE'),act)
    r=fresh(root,day,plan,act,out,freeze,lambda p:None)
    controls=read(out/'RAW_CONTROL_LOG.json');physical=read(out/'RAW_PHYSICAL_INPUT_LOG.json')
    assert len(controls['slots'])==96 and len(physical['slots'])==96
    assert all(x['all_7_RegControls_enabled'] and x['CapControl_count']==0 and not x['Planning_tap_replay'] for x in controls['slots'])
    with np.load(out/'fresh/OPENDSS_PHASE_ARRAYS.npz') as z:
        assert np.all(z['capacitor_states']==1)
        assert sum(z['branch_kinds']=='transformer')==120
    receipt=dict(adapter_diagnostic_PASS=True,SYNTHETIC_ONLY=True,production_days_PASS=0,A1_solves=0,
                 historical_results_reused=0,fresh_slots=96,source_initial_controls=True,
                 current_checker_SHA=CHECKER,NormalAmps_TX_rows=120,physical_summary=r['summary'])
    atomic(ROOT/'docs/v42_may_b1_production_31d/NATIVE_PORT_DIAGNOSTIC.json',receipt)
    print(json.dumps(receipt))

if __name__=='__main__':main()
