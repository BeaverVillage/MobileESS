from concurrent.futures import ProcessPoolExecutor
import time,numpy as np
from electrical_engine import *
from numerical_coefficients import build,predictions,AX
def validate_slot(t):
    out=H/'signed_validation'/f'slot_{t:02}';out.mkdir(parents=True,exist_ok=False);start=time.perf_counter();e=Engine(out/'runtime')
    e.inputs(t);state=read(H/'B0_REPLAY/CONTROL_STATES.json')[t];e.hold(state)
    c=build(t);rows=[];rule=read(H/'PREFLIGHT_RULE.json');labels=[AX['nodes'],AX['line'],AX['tx'],AX['winding']]
    for k in range(60):
        for sign in [-1,1]:
            x=c.anchor.copy();x[k]+=sign*rule['validation_signed_step'];e.controls(x);e.solve();a=e.arrays();pred=predictions(c,x)
            exact=[np.sqrt(a[0]),np.abs(a[1]),np.abs(a[2]),np.abs(a[3])/np.asarray(AX['winding_rating_kVA'])]
            errors={};witness={}
            for key,y,lab in zip(['voltage','line','tx','winding'],exact,labels):
                err=np.abs(pred[key]-y);i=int(err.argmax());errors[key]=float(err[i]);witness[key]=dict(axis=lab[i],predicted=float(pred[key][i]),exact=float(y[i]))
            okay=errors['voltage']<=rule['maximum_absolute_voltage_prediction_error_pu'] and max(errors[k] for k in ['line','tx','winding'])<=rule['maximum_absolute_loading_prediction_error_pu']
            rows.append(dict(slot=t,column=k,control_name=NAMES[k],signed_delta=float(sign*rule['validation_signed_step']),AIDC_Q_delta=float(sign*10*PF_TAN) if k<12 else 0.,max_abs_error=errors,error_witness=witness,P1_predicted=float(pred['line'].max()),P1_exact=float(exact[1].max()),pass_criteria=okay,converged=True))
    after=e.state(t)
    unchanged=all(a['tap_number']==b['tap_number'] for a,b in zip(state['regulators'],after['regulators'])) and all(a['step_states']==b['step_states'] for a,b in zip(state['capacitors'],after['capacitors']))
    assert unchanged;e.close();save(out/'VALIDATION.json',dict(status='PASS' if all(r['pass_criteria'] for r in rows) else 'FAIL_CLOSE',rows=rows,controls_held_unchanged=unchanged,independent_context=True,wall_seconds=time.perf_counter()-start));return rows
def main():
    assert read(H/'COEFFICIENT_GENERATION.json')['status']=='GENERATED_PENDING_VALIDATION';start=time.perf_counter();rule=read(H/'PREFLIGHT_RULE.json')
    with ProcessPoolExecutor(max_workers=4) as p:groups=list(p.map(validate_slot,rule['validation_slots']))
    rows=[r for group in groups for r in group];assert len(rows)==600
    result=dict(status='PASS' if all(r['pass_criteria'] for r in rows) else 'FAIL_CLOSE',signed_tests=len(rows),controls=60,AIDC_sites=12,MESS_sites=24,AIDC_independent_Q_variables=0,maximum_absolute_error={k:max(r['max_abs_error'][k] for r in rows) for k in ['voltage','line','tx','winding']},thresholds=dict(voltage=rule['maximum_absolute_voltage_prediction_error_pu'],loading=rule['maximum_absolute_loading_prediction_error_pu']),failed_cases=[r for r in rows if not r['pass_criteria']],wall_seconds=time.perf_counter()-start,old_coefficients_used=False,optimizer_runs=0)
    save(H/'SIGNED_PERTURBATION_VALIDATION.json',result);print('SIGNED_VALIDATION',result,flush=True)
    assert result['status']=='PASS'
if __name__=='__main__':main()
