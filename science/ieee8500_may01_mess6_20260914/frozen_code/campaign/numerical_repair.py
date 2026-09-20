"""Strict numerical retry after the original fixed-candidate retry stalls.

No changes to model rows, objective, candidate order, or certificate thresholds.
Certified cache entries remain valid under the original unchanged certificate.
"""
import hashlib,json,time
from pathlib import Path
import numpy as np
H=Path(__file__).absolute().parent

def matrix_sha(model):
 model.update();a=model.getA()
 h=hashlib.sha256(a.data.tobytes()+a.indices.tobytes()+a.indptr.tobytes())
 for attr in ('RHS','LB','UB','Obj'):h.update(np.asarray(model.getAttr(attr),dtype=float).tobytes())
 for attr in ('Sense','VType'):h.update(''.join(model.getAttr(attr)).encode())
 h.update(repr((model.ObjCon,model.ModelSense)).encode())
 return h.hexdigest()

def install():
 from dayahead.tools import run_v35r3e_r1_beam as beam
 from dayahead.v35r3 import algorithm as alg
 if getattr(beam.solve_fixed_candidate_certified,'_strict_repair',False):return
 proof=json.loads((H/'recovery_stall/NUMERICAL_REPAIR_PROOF.json').read_text(encoding='utf-8-sig'))
 assert proof['status']=='PASS' and proof['model_objective_constraints_bounds_unchanged']
 original=beam.solve_fixed_candidate_certified
 def repaired(item,*,max_separation_rounds=20):
  try:return original(item,max_separation_rounds=max_separation_rounds)
  except RuntimeError as error:
   if 'CERTIFICATE_STALLED' not in str(error) or item.model.Params.NumericFocus!=3:raise
   model=item.model;before=matrix_sha(model)
   record=dict(candidate=item.candidate.candidate_id,error=str(error),unix=time.time(),matrix_before=before,old_quality=dict(ConstrVio=model.ConstrVio,BoundVio=model.BoundVio),certificate_tolerance=alg.NUMERIC_TOLERANCE)
   model.Params.FeasibilityTol=1e-9;model.Params.OptimalityTol=1e-9;model.Params.IntFeasTol=1e-9
   model.reset()
   result=original(item,max_separation_rounds=50)
   record.update(status='PASS',evaluation=result[1],matrix_after=matrix_sha(model),new_quality=dict(ConstrVio=model.ConstrVio,BoundVio=model.BoundVio),solver_parameters=dict(FeasibilityTol=1e-9,OptimalityTol=1e-9,IntFeasTol=1e-9,reset_solution=True))
   assert result[1]['exact_optimality_certificate']
   # Original separation may append valid rows; the existing model is never relaxed.
   with (H/'recovery_stall/NUMERICAL_RETRIES.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')
   print('STRICT_NUMERICAL_RETRY_PASS',item.candidate.candidate_id,flush=True)
   return result
 repaired._strict_repair=True
 beam.solve_fixed_candidate_certified=repaired
