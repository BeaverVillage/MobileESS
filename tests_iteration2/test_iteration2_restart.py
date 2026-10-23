import unittest,tempfile,json
from pathlib import Path
from types import SimpleNamespace
from contextvars import ContextVar
from fractions import Fraction
from unittest.mock import patch
import numpy as np
import scipy.sparse as sp
from v44_iteration2 import config as c,adapters,numerical
from v44_iteration2.voltage_audit import check_rows,check_plan,verify_result
from v44_iteration2.io import atomic,record


def fixture(root,band=(.955,1.045)):
 names=[f'voltage_lower[{t},0]' for t in range(96)]+[f'voltage_upper[{t},0]' for t in range(96)]
 d=dict(row_names=np.asarray(names),rhs=np.r_[np.full(96,band[0]**2-1),np.full(96,band[1]**2-1)],sense=np.asarray(['>']*96+['<']*96))
 np.savez_compressed(root/'FULL_DATA.npz',**d)
 coefficient=SimpleNamespace(voltage_constant=np.array([1.]),voltage_matrix=np.zeros((1,1)),control_names=['aidc_load_kw[AIDC01]'])
 return SimpleNamespace(original_d=d,output=root,anchor=dict(controls=np.zeros((96,1))),coefficients=[coefficient]*96,identity=dict(day='2025-05-01'),case_sha='test')


class ActualVoltageRows(unittest.TestCase):
 def test_original_grid_compilers_build_the_tight_rhs_after_nested_authority(self):
  import gurobipy as gp
  from v44_iteration2.bootstrap import equipment
  from v42_integrated import contract
  from v42_native import voltage as v
  from v42_native.grid import GridAuthority,add_grid
  from v42_m1_sparse.grid import add_compressed
  coefficient=SimpleNamespace(slot=0,coefficient_sha256='0'*64,control_names=['p'],anchor=np.zeros(1),
   voltage_constant=np.ones(1),voltage_matrix=np.ones((1,1)),branch_limits=np.empty(0),branch_names=[],
   flow_p_constant=np.empty(0),flow_q_constant=np.empty(0),flow_p_matrix=np.empty((0,1)),flow_q_matrix=np.empty((0,1)),
   current_constant=np.empty(0),current_matrix=np.empty((1,0)),transformer_ratings=[])
  for stage in ('M2','M3','M4'):
   with equipment.scope(),adapters.voltage(stage),contract.physical_authority():
    policy=v.voltage_for(v.Stage.M2);lower,upper=c.band(stage)
    authority=GridAuthority(*(['0'*64]*4),policy.lower_squared,policy.upper_squared,True,v.Stage.M2)
    for compressed in (False,True):
     with gp.Env(empty=True) as env:
      env.setParam('OutputFlag',0);env.start()
      with gp.Model(env=env) as model:
       x=model.addVar(lb=-1,ub=1,name='p')
       if compressed:add_compressed(model,[coefficient],[[x]],authority,'M1-F3',[],[])
       else:add_grid(model,[coefficient],[[x]],authority)
       model.update()
       self.assertAlmostEqual(model.getConstrByName('voltage_lower').RHS,lower**2-1,places=12)
       self.assertAlmostEqual(model.getConstrByName('voltage_upper').RHS,upper**2-1,places=12)

 def test_inherited_equipment_reset_cannot_remove_M2_or_M3_margin(self):
  from v44_iteration2.bootstrap import equipment
  from v42_integrated import contract
  from v42_native import voltage as v
  before=dict(v._MAPPING)
  for stage in ('M2','M3','M4'):
   with equipment.scope(),adapters.voltage(stage),contract.physical_authority():
    for public in (v.Stage.M1,v.Stage.M2):
     p=v.voltage_for(public);self.assertEqual((p.lower_pu,p.upper_pu),c.band(stage))
    self.assertEqual(v.voltage_for(v.Stage.ACTUAL),before[v.Stage.ACTUAL])
   self.assertEqual(v._MAPPING,before)

 def test_actual_matrix_ignores_claimed_policy_and_rejects_old_bounds(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);case=fixture(root,(.95,1.05));case.identity['voltage_band']=[.955,1.045]
   for stage in ('M2','M3'):
    with self.assertRaisesRegex(ValueError,'ACTUAL_VOLTAGE_RHS'):check_rows(case,stage)
   self.assertTrue(check_rows(case,'M4')['PASS'])

 def test_tight_matrix_checks_every_slot_and_saved_bytes(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);case=fixture(root)
   for day in c.DAYS:
    case.identity['day']=day
    for stage in ('M2','M3'):
     proof=check_rows(case,stage);self.assertEqual(proof['lower_rows'],96);self.assertEqual(proof['voltage_band'],[.955,1.045])
   saved=dict(case.original_d);saved['rhs']=saved['rhs'].copy();saved['rhs'][-1]+=.01
   np.savez_compressed(root/'FULL_DATA.npz',**saved)
   with self.assertRaisesRegex(ValueError,'SAVED_FULL'):check_rows(case,'M2')

 def test_actual_plan_has_to_meet_tight_voltage_not_only_original_band(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   case=fixture(Path(folder));payload=dict(planning=dict(sites=['AIDC01'],PCC_P_kw=np.zeros((96,1))));plan=dict(plan_sha='test')
   self.assertTrue(check_plan(case,payload,plan,'M2')['PASS'])
   for coefficient in case.coefficients:coefficient.voltage_constant=np.array([1.049**2])
   with self.assertRaisesRegex(ValueError,'TIGHT_M_PLAN'):check_plan(case,payload,plan,'M2')
   self.assertTrue(check_plan(case,payload,plan,'M4')['PASS'])

 def test_missing_or_tampered_matrix_proof_cannot_be_a_downstream_parent(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   root=Path(folder);case=fixture(root);payload=dict(planning=dict(sites=['AIDC01'],PCC_P_kw=np.zeros((96,1))));plan=dict(plan_sha='test')
   check_rows(case,'M2');check_plan(case,payload,plan,'M2')
   result=dict(case_sha=case.case_sha,MESS_plan=plan,iteration2_voltage_rows=record(root/'ITERATION2_FULL_VOLTAGE_ROWS.json'),iteration2_voltage_plan=record(root/'ITERATION2_PLAN_VOLTAGE.json'))
   self.assertTrue(verify_result(result,'M2'))
   with self.assertRaises(ValueError):verify_result(result,'M4')
   result.pop('iteration2_voltage_plan')
   with self.assertRaises(KeyError):verify_result(result,'M2')
   result['iteration2_voltage_plan']=record(root/'ITERATION2_PLAN_VOLTAGE.json')
   with (root/'FULL_DATA.npz').open('ab') as stream:stream.write(b'tamper')
   with self.assertRaises(ValueError):verify_result(result,'M2')


class PhaseIPrecision(unittest.TestCase):
 def test_only_phase_I_solver_precision_changes_without_relaxing_acceptance(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   context=ContextVar('test',default=None);stable=SimpleNamespace(_solve=context)
   model=SimpleNamespace(Params=SimpleNamespace(FeasibilityTol=1e-6,OptimalityTol=1e-6,Threads=1,MIPGap=.005))
   model.setParam=lambda k,v:setattr(model.Params,k,v)
   def base_factory(fn):return lambda m,a,g:dict(FeasibilityTol=m.Params.FeasibilityTol,OptimalityTol=m.Params.OptimalityTol)
   apply=numerical.policy_wrapper(base_factory,stable)(None)
   for component,want in [('LOCAL_PRICING',1e-6),('PHASE_I',1e-9)]:
    model.Params.FeasibilityTol=1e-6;model.Params.OptimalityTol=1e-6
    token=context.set(dict(component=component,folder=Path(folder),repair=False))
    try:value=apply(model,{},None)
    finally:context.reset(token)
    self.assertEqual(model.Params.FeasibilityTol,want);self.assertEqual(model.Params.OptimalityTol,want)
    self.assertEqual((model.Params.Threads,model.Params.MIPGap),(1,.005))
   self.assertEqual(numerical.ZERO,Fraction(1,100000000))

 def test_small_residual_polishes_same_snapshot_and_charges_both_calls(self):
  with tempfile.TemporaryDirectory(dir=c.ROOT) as folder:
   stable=SimpleNamespace(_solve=ContextVar('test',default=None));seen=[]
   snapshot=SimpleNamespace(objectives=[SimpleNamespace(constant=Fraction(0),coefficients=lambda:{0:Fraction(1)})],fingerprint=lambda:'same')
   class Previous:
    def __init__(self):self.native=SimpleNamespace(remaining=lambda:100,solve=self.polish)
    def solve(self,snapshot,folder,component):return dict(native_seconds=2.,status=2),dict(X=np.array([2e-8]))
    def polish(self,actual,folder,component):
     seen.append(actual);self.assert_context=stable._solve.get()['iteration2_polish']
     return dict(native_seconds=3.,status=2),dict(X=np.array([0.]))
    def assess(self,*args):return dict(PASS=True)
   cls=numerical.precision_native(Previous,stable);worker=cls()
   with patch('v42_a_stage_phase1.core.primal_replay',return_value=dict(PASS=True)):
    record,raw=worker.solve(snapshot,Path(folder),'PHASE_I')
   self.assertIs(seen[0],snapshot);self.assertEqual(record['native_seconds'],5.);self.assertEqual(raw['X'][0],0.)
   self.assertTrue(worker.assert_context)

 def test_no_polish_for_zero_or_real_positive_residual(self):
  stable=SimpleNamespace(_solve=ContextVar('test',default=None))
  snapshot=SimpleNamespace(objectives=[SimpleNamespace(constant=Fraction(0),coefficients=lambda:{0:Fraction(1)})])
  class Previous:
   def solve(self,snapshot,folder,component):return dict(native_seconds=1),dict(X=np.array([self.phi]))
  cls=numerical.precision_native(Previous,stable)
  for phi in (0.,1.,1e-9):
   worker=cls();worker.phi=phi
   self.assertEqual(worker.solve(snapshot,None,'PHASE_I')[0]['native_seconds'],1)


if __name__=='__main__':unittest.main()
