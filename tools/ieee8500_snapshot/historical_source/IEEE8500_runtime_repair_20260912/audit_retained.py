import sys,json,time,hashlib
from pathlib import Path
HERE=Path(__file__).absolute().parent
OLD=HERE.parent/'IEEE8500_v41r4_production_20260911_r2'
sys.path.insert(0,str(OLD))
import common8500 as c
c.P=HERE
from dayahead.tools.run_v35r3e_r1_beam import _restore_slots
import numpy as np
def main():
    manifest=c.read(OLD/'PRODUCTION_RELEASE.json')
    for row in manifest['code']:assert c.sha(row['path'])==row['sha256'],row['path']
    source=OLD/'B2/beam/2025-05-21/B2/B2/FINAL_RESULT.json'
    result=c.read(source)
    with np.load(OLD/'B0/POWER.npz') as z:pcc=z['pcc'].copy()
    rows=[]
    for i,s in enumerate(result['retained_final_states']):
        c.state(status='DIAGNOSING',stage='B2_RETAINED_EXACT_REPLAY',retained_index=i)
        ac=c.exact(pcc,tuple(_restore_slots(s['trajectory_slots'])),HERE/f'retained_{i}_exact')
        row=dict(state_id=s['beam_state_id'],original_model_P1=s['current_planning_objective'],status=ac['status'],metrics=ac['metrics'],violating_slots=[r['slot'] for r in ac['slots'] if not r['feasible']])
        rows.append(row);print(json.dumps(row),flush=True)
    c.save(HERE/'RETAINED_BEAM_AC_AUDIT.json',dict(original_result=c.record(source),rows=rows,source_code_unchanged=True,no_settings_or_limits_changed=True))
if __name__=='__main__':main()
