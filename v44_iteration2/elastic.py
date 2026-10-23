"""Exact dyadic elastic witnesses; original raw variables and tolerance stay fixed."""
from fractions import Fraction
import numpy as np
from .io import atomic,now

def exact_residual(snapshot,x,row):
 a,b=snapshot.matrix.indptr[row:row+2]
 return sum((Fraction(float(v))*Fraction(float(x[j])) for j,v in zip(snapshot.matrix.indices[a:b],snapshot.matrix.data[a:b])), -Fraction(float(snapshot.rhs[row])))

def replay_with_exact(original):
 def replay(snapshot,point,tolerance=1e-6):
  result=original(snapshot,point,tolerance)
  # Only auxiliary Phase-I snapshots get a cancellation-resistant fallback.
  # Every original-objective/physical replay keeps the original implementation.
  if result['PASS'] or snapshot.objectives[0].name!='Phi' or result['max_bound_violation']>tolerance:return result
  x=np.asarray(point);activity=snapshot.matrix@x-snapshot.rhs
  violations=np.where(snapshot.senses=='<',np.maximum(activity,0),np.where(snapshot.senses=='>',np.maximum(-activity,0),abs(activity)))
  bad=np.flatnonzero(violations>tolerance);maximum=0.;limit=Fraction(float(tolerance))
  for row in bad:
   residual=exact_residual(snapshot,x,int(row));sense=snapshot.senses[row]
   violation=max(Fraction(0),residual) if sense=='<' else max(Fraction(0),-residual) if sense=='>' else abs(residual)
   maximum=max(maximum,float(violation))
   if violation>limit:return result
  return dict(result,PASS=True,max_row_violation=max(maximum,float(violations[violations<=tolerance].max(initial=0))),
   exact_dyadic_rows_replayed=len(bad),floating_cancellation_rechecked=True,tolerance=tolerance,
   raw_point_rounded_or_clipped=False)
 return replay

def artificial_point(master,original_point):
 from v42_a_stage_phase1.core import primal_replay
 n=master.original.matrix.shape[1];original=np.asarray(original_point)
 x=np.r_[original,np.zeros(len(master.artificial_rows))]
 residual=master.original.matrix@original-master.original.rhs
 locations={}
 for j,(row,sign) in enumerate(zip(master.artificial_rows,master.artificial_signs)):
  x[n+j]=max(0.,-residual[row]/sign);locations[row,sign]=n+j
 initial=primal_replay(master.snapshot,x);replay=initial;changed=0
 if not replay['PASS']:
  activity=master.snapshot.matrix@x-master.snapshot.rhs;senses=master.snapshot.senses
  violations=np.where(senses=='<',np.maximum(activity,0),np.where(senses=='>',np.maximum(-activity,0),abs(activity)))
  for row in np.flatnonzero(violations>1e-6):
   value=exact_residual(master.original,original,int(row));sign=-1. if value>0 else 1.
   column=locations.get((int(row),sign))
   if column is None:raise ValueError('PHASE_I_HARD_ROW_CANNOT_BE_REPAIRED_BY_ARTIFICIAL')
   magnitude=abs(value);hi=float(magnitude)
   if Fraction(hi)<magnitude:hi=float(np.nextafter(hi,np.inf))
   x[column]=hi
   opposite=locations.get((int(row),-sign))
   if opposite is not None:x[opposite]=float(Fraction(hi)-magnitude)
   changed+=1
  replay=primal_replay(master.snapshot,x)
 if not replay['PASS']:raise ValueError('PHASE_I_IMPLEMENTATION_INVALID_CONSTRUCTED_ELASTIC_POINT')
 if not np.array_equal(x[:n],original):raise ValueError('ELASTIC_REPAIR_CHANGED_ORIGINAL_RAW_POINT')
 if changed or replay.get('floating_cancellation_rechecked'):
  from .adapters import ACTIVE
  request=ACTIVE.get()
  if request:
   from pathlib import Path
   atomic(Path(request['output'])/'ITERATION2_ELASTIC_LIFT_LAST.json',dict(UTC=now(),PASS=True,
    initial_replay=initial,final_replay=replay,auxiliary_rows_reconstructed=changed,
    original_raw_variables_changed=False,original_matrix_bounds_objective_changed=False,
    exact_dyadic_arithmetic=True,acceptance_tolerance_relaxed=False,Native_calls=0))
 return x,replay
