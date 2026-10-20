"""Installed-GPU power envelope; never an actual feasible job schedule."""
from .preflight import *
import pandas as pd

def prepare():
    p=Path('D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/INPUT/BUNDLE/DAY_20250501')
    authority=json.loads((p/'POWER_AUTHORITY.json').read_text(encoding='utf-8-sig'))
    c1=p/'C1_PLANNING_COEFFICIENTS.csv'
    if sha(c1)!=authority['planning_C1']['sha256']:raise ValueError('C1_POWER_AUTHORITY_DRIFT')
    native=json.loads(Path('D:/MobileESS_V42/runtime/v42_may_campaign/candidate_20261009_implementation01/inputs/B1/2025-05-01/NATIVE_INPUT.json').read_text())
    rows=[]
    for slot,group in pd.read_csv(c1,float_precision='round_trip').groupby('slot'):
        low=high=0.
        for r in group.itertuples():
            cap=native['capacities'][r.aidc_id]
            low+=r.slope*authority['current_IT_idle_kW_per_installed_GPU']*cap+r.intercept_kw
            high+=r.slope*(authority['current_IT_idle_kW_per_installed_GPU']+authority['current_IT_swing_kW_per_active_GPU'])*cap+r.intercept_kw
        rows.append(dict(slot=int(slot),pcc_lower_kw=low,pcc_upper_kw=high,
            qcc_lower_kvar=low*np.tan(np.arccos(.95)),qcc_upper_kvar=high*np.tan(np.arccos(.95)),
            scope='Installed_GPU_envelope_only_not_Job_schedule',job_feasible=False))
    csvout('AIDC_POWER_ENVELOPE.csv',rows)
    save('AIDC_POWER_ENVELOPE_AUTHORITY.json',dict(source=str(c1),sha256=sha(c1),
        power_authority=str(p/'POWER_AUTHORITY.json'),power_authority_sha256=sha(p/'POWER_AUTHORITY.json'),
        GPU_count=sum(native['capacities'].values()),scaling=1,exact_Actual_C1_replay=False,virtual_envelope_not_feasible_control=True))

if __name__=='__main__':prepare()
