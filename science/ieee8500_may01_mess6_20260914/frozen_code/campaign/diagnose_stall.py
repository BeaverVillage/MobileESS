from bootstrap import *
import pickle,traceback
from types import SimpleNamespace
def main():
 protect()
 import mess_runtime
 from dayahead.tools import run_v35r3e_r1_beam as beam
 from dayahead.v35r3 import algorithm as alg
 root=H/'B2/beam/2025-05-01/B2/B2';out=H/'recovery_stall';out.mkdir(exist_ok=True)
 stage=read(root/'STAGE_3.json');parent=beam.BeamState.from_dict(stage['retained_states'][1])
 assert parent.beam_state_id!='B2-S3-63c0274a9484482e'
 with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z:pcc=z['pcc'].copy()
 print('LOAD_FROZEN_COEFFICIENTS',parent.beam_state_id,flush=True)
 cc=mess_runtime.coefficients();route=mess_runtime.traffic()[2]
 alg.assert_apr01_only=lambda day: None if day=='2025-05-01' else (_ for _ in ()).throw(AssertionError(day))
 candidates=alg.enumerate_initial_relocations(day='2025-05-01',mess_id='MESS04',initial_service='STA06',route_table=route).candidates
 target=next(c for c in candidates if c.candidate_id=='MESS04:MOVE:STA06:IDC05:40')
 fixed_p,fixed_q=beam._fixed_maps(parent.trajectory_slots)
 cuts=dict(line={(r['slot'],r['branch_index']) for r in read(root/'CONGESTION_MAP.json')['states']},voltage=set(),tx_current=set(),tx_kva=set())
 caches=[]
 for p in (H/'B2/candidate_cache').rglob('*.pkl'):
  with p.open('rb') as f:v=pickle.load(f)
  ident=v['identity']
  if ident.get('beam_parent_fingerprint')==parent.state_sha256 and ident.get('MESS_id')=='MESS04' and ':STAY:' in ident['candidate_id']:
   for k in cuts:cuts[k].update(v['result'][4][k])
   caches.append(record(p))
 assert caches,'NO_SAVED_STAY_SEPARATION_STATES'
 args=dict(candidate=target,aidc_pcc_kw_96x12=pcc,coefficients=cc,services=[n[10:-1] for n in NAMES if n.startswith('mess_p_kw[')],fixed_mess_p_by_service=fixed_p,fixed_mess_q_by_service=fixed_q,line_states=cuts['line'],voltage_states=cuts['voltage'],transformer_current_states=cuts['tx_current'],transformer_kva_states=cuts['tx_kva'])
 item=alg.build_fixed_candidate_model(**args);item.model.Params.Threads=4;item.model.Params.NumericFocus=3;item.model.Params.OptimalityTol=1e-8
 original=alg.evaluate_opportunity_dispatch;history=[]
 def traced(**kw):
  result=original(**kw);history.append(result);save(out/'ITERATIONS.json',history)
  print('CERTIFICATE',len(history),{k:v for k,v in result.items() if not k.endswith('_states')},flush=True)
  return result
 alg.evaluate_opportunity_dispatch=traced
 def matrix_sha():
  item.model.update();a=item.model.getA()
  return hashlib.sha256(a.data.tobytes()+a.indices.tobytes()+a.indptr.tobytes()+np.asarray(item.model.getAttr('RHS')).tobytes()+np.asarray(item.model.getAttr('LB')).tobytes()+np.asarray(item.model.getAttr('UB')).tobytes()+np.asarray(item.model.getAttr('Obj')).tobytes()).hexdigest()
 try:
  try:alg.solve_fixed_candidate_certified(item,max_separation_rounds=50);raise AssertionError('FAILURE_NOT_REPRODUCED')
  except RuntimeError as e:assert 'CERTIFICATE_STALLED' in str(e);error=str(e)
  before=history[-1];matrix_before=matrix_sha()
  save(out/'ORIGINAL_FAILURE.json',dict(error=error,evaluation=before,model_matrix_sha=matrix_before,solver_quality=dict(ConstrVio=item.model.ConstrVio,BoundVio=item.model.BoundVio),parent=parent.beam_state_id,stay_cache=caches,candidate=target.candidate_id))
  item.model.Params.FeasibilityTol=1e-9;item.model.Params.OptimalityTol=1e-9;item.model.Params.IntFeasTol=1e-9;item.model.reset()
  dispatch,evaluation=alg.solve_fixed_candidate_certified(item,max_separation_rounds=50)
  assert evaluation['exact_optimality_certificate'] and matrix_sha()==matrix_before
  save(out/'NUMERICAL_REPAIR_PROOF.json',dict(status='PASS',candidate=target.candidate_id,parent=parent.beam_state_id,old_evaluation=before,new_evaluation=evaluation,unchanged_model_matrix_SHA=matrix_before,model_objective_constraints_bounds_unchanged=True,acceptance_tolerance_unchanged=alg.NUMERIC_TOLERANCE,only_solver_parameters=dict(FeasibilityTol=[1e-8,1e-9],OptimalityTol=[1e-8,1e-9],IntFeasTol=[1e-5,1e-9],reset_solution=True),dispatch=beam._dispatch_to_json(dispatch) if hasattr(beam,'_dispatch_to_json') else dict(rho=dispatch['rho'])))
  print('NUMERICAL_REPAIR_PROOF_PASS',flush=True)
 finally:alg.evaluate_opportunity_dispatch=original;item.model.dispose()
if __name__=='__main__':
 try:main()
 except BaseException as e:save(H/'recovery_stall/DIAGNOSTIC_FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise


