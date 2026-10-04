"""Sparse full-scale specialization of the exact PR144 persistent registry policy."""
from v42_dw_runtime.rmp import PersistentRMP
from v42_dw_resume.audit import Master
from v42_degen.identity import digest
from .common import *
import numpy as np
class FullScalePersistentRMP(PersistentRMP):
 def __init__(self,master):
  self.master=master;self.model=master.model;self.registry=tuple(c['key'] for c in master.column_data)
 def append(self,columns):
  start=time.perf_counter()
  for c in columns:self.master.add(c['unit'],c['x'],c['a'],c['c'],c['key'])
  self.model.update();self.registry=tuple(c['key'] for c in self.master.column_data)
  return time.perf_counter()-start
 def identity(self):return sparse_identity(self.model)
 def solve(self,callback=None):
  self.model.reset(0);self.model.Params.LPWarmStart=0;start=time.perf_counter();self.model.optimize(callback)
  return dict(status=self.model.Status,optimize_seconds=time.perf_counter()-start,warm_basis_selected=False)
def sparse_identity(model):
 model.update();a=model.getA().tocsr()
 return dict(rows=model.NumConstrs,columns=model.NumVars,nnz=model.NumNZs,matrix_shape=list(a.shape),indptr=digest(a.indptr),indices=digest(a.indices),data=digest(a.data),row_names=digest(np.asarray(model.getAttr('ConstrName'))),names=digest(np.asarray(model.getAttr('VarName'))),rhs=digest(np.asarray(model.getAttr('RHS'))),senses=digest(np.asarray(model.getAttr('Sense'))),lb=digest(np.asarray(model.getAttr('LB'))),ub=digest(np.asarray(model.getAttr('UB'))),objective=digest(np.asarray(model.getAttr('Obj'))),types=digest(np.asarray(model.getAttr('VType'))),constant=model.ObjCon,sense=model.ModelSense)
