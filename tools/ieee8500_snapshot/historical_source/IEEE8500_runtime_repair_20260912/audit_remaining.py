from audit_retained import *
from audit_retained import _restore_slots
def main():
    result=c.read(OLD/'B2/beam/2025-05-21/B2/B2/STAGE_4.json')
    with np.load(OLD/'B0/POWER.npz') as z:pcc=z['pcc'].copy()
    rows=[]
    for i,s in enumerate(result['pruned_states']):
        ac=c.exact(pcc,tuple(_restore_slots(s['trajectory_slots'])),HERE/f'pruned_{i}_exact')
        rows.append(dict(state_id=s['beam_state_id'],status=ac['status'],metrics=ac['metrics'],violating_slots=[r['slot'] for r in ac['slots'] if not r['feasible']]))
        print(json.dumps(rows[-1]),flush=True)
    c.save(HERE/'PRUNED_FINAL_BEAM_AC_AUDIT.json',dict(rows=rows,source=c.record(OLD/'B2/beam/2025-05-21/B2/B2/STAGE_4.json')))
    with np.load(OLD/'B2/final_exact/CONTROLS.npz') as z:x=z['x'].copy()
    e=c.Engine(HERE/'witness_runtime')
    try:
        for t in range(29):e.inputs(t,x[t]);e.solve()
        v=np.sqrt(e.arrays()[0]);i=int(v.argmax());coef=c.Coefficients()[28]
        pred=np.sqrt(coef.voltage_constant+coef.voltage_matrix.T@x[28]);state=e.state(28)
        base=c.read(c.PREF/'B0_REPLAY/CONTROL_STATES.json')[28]
        witness=dict(slot=28,time='07:00',node=str(e.nodes[i]),exact_pu=float(v[i]),predicted_same_node_pu=float(pred[i]),predicted_global_max_pu=float(pred.max()),voltage_upper=1.05,regulator_capacitor_state=state,B0_coefficient_anchor_control_state=base)
        c.save(HERE/'B2_OVERVOLTAGE_WITNESS.json',witness)
        print(json.dumps({k:v for k,v in witness.items() if k not in ['regulator_capacitor_state','B0_coefficient_anchor_control_state']}),flush=True)
    finally:e.close()
if __name__=='__main__':main()
