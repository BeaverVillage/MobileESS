"""Bind the existing IEEE8500 local/fallback closure to May01 six-MESS inputs."""
from bootstrap import *
import ast,inspect,types
from dataclasses import asdict
from contextlib import nullcontext
from types import SimpleNamespace

def close(policy,pcc,initial,jobs,primary):
 import common8500 as c
 import mess_runtime,mess_grid8500
 from closure_numeric_entry import bind as numeric_entry_binding
 from closure_sparse_grid import SparseClosure,cached_cuts
 # A resumed process must not overwrite certificates from the completed search.
 mess_grid8500.COUNT=max([mess_grid8500.COUNT]+[int(p.stem) for p in (H/'MESS_grid_certificates').glob('*.json') if p.stem.isdigit()])
 import mission_ac_cut_restore as local
 import restoration_revision_v1 as revision
 from dayahead.v40h import recourse
 from dayahead.v33m.mess_trajectory import MessTrajectory
 from dayahead.v17_ac_restoration_contract import ACViolation,RestorationCut,ViolationType,RHO,canonical_sha256
 from dayahead.v40a.grid import controls_from_trajectory
 folder=H/policy/'physical_closure';folder.mkdir(parents=True,exist_ok=False)
 source=H.parents[1]/'IEEE8500_B2_physical_closure_20260912_r2/closure8500.py'
 rule_source=Path(revision.__file__).parent/'frozen_artifacts/v41r4_restoration_revision_v1/RULE_FREEZE.json'
 rule=read(rule_source)
 for row in rule['code']+[rule['local_margin']]:assert sha(row['path'])==row['sha256'],row['path']
 wanted={'discrete','clone','physical_values','exact_frozen','signed_cuts','local_binding','fallback_binding'}
 source_text=source.read_text(encoding='utf-8')
 tree=ast.parse(source_text.replace("'2025-05-21','B2'","'2025-05-01',POLICY"))
 body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in wanted]
 ns=dict(globals(),c=c,HERE=folder,POLICY=policy,original_local=local,original_revision=revision,recourse=recourse,mess_grid8500=mess_grid8500,ACViolation=ACViolation,RestorationCut=RestorationCut,ViolationType=ViolationType,RHO=RHO,canonical_sha256=canonical_sha256,ALLOWED_CHANGED_FIELDS={'p_kw','q_kvar','battery_energy_kwh','soc_fraction'})
 exec(compile(ast.Module(body=body,type_ignores=[]),str(source)+'::may01_six','exec'),ns)
 # The inherited command serializer had a remaining 384-row assertion.
 # Preserve its data construction exactly, replacing only fleet cardinality.
 old_arrays=local.command_arrays;array_src=inspect.getsource(old_arrays)
 assert array_src.count('384')==2
 array_ns=dict(old_arrays.__globals__)
 exec(compile(array_src.replace('384','576'),str(H/'physical_closure.py')+'::command_arrays_6','exec'),array_ns)
 old_make=local.make_frozen
 local.make_frozen=ns['clone'](old_make,command_arrays=array_ns['command_arrays'])
 power=dict(pcc=pcc,qcc=pcc*PF_TAN)
 try:
  frozen=local.make_frozen('2025-05-01',policy,jobs,power,initial);frozen.validate()
  assert frozen.mess_p_kw.shape==(96,6) and set(frozen.mess_ids)==set(fleet_binding.IDS)
  np.testing.assert_allclose(local.control_matrix({'control_names':NAMES},frozen),controls_from_trajectory(Coefficients(),pcc,initial.slots),rtol=0,atol=1e-10)
  ds=ns['discrete'](initial.slots)
  save(folder/'RULE_BINDING.json',dict(status='PASS',date='2025-05-01',fleet=6,legacy_adapter=record(source),original_rule=record(rule_source),binding=record(Path(__file__)),primary=primary,discrete_sha=ds,command_shape=[96,6],control_binding='PASS',route_search_calls=0,AIDC_optimization_calls=0,local_K_MAX=local.K_MAX,original_fallback_rule_unchanged=True,source_Vreg_tap_cap_ratings_unchanged=True))
  state(status='RUNNING',stage=policy+':PHYSICAL_CLOSURE_PREPARATION')
  ctx=SimpleNamespace(coefficients=mess_runtime.coefficients(),nodes=AX['nodes'],electrical=SimpleNamespace(voltage={'control_names':NAMES,'node_names':AX['nodes']}),v41_electrical_certificate=record(H/'IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json'),revision_pcc=pcc)
  fallback=False
  state(status='RUNNING',stage=policy+':LOCAL_FIXED_DISCRETE_RESTORATION')
  try:
   sparse=SparseClosure(folder/'sparse_electrical')
   restore=ns['clone'](ns['local_binding'](),add_grid=sparse.add,
       local_fresh_ac_restoration_cuts=cached_cuts(ns['signed_cuts'],folder))
   restore=numeric_entry_binding(restore,ns['clone'],folder,optimize=sparse.optimize)
   final,info=restore('2025-05-01',policy,jobs,power,initial,ctx,folder/'local')
   assert info['status']=='PASS'
  except AssertionError as error:
   info=error.args[0] if error.args else None
   if not(isinstance(info,tuple) and info[0]=='CUT_RECOURSE_FAILURE' and info[1].get('status_code')==3):raise
   save(folder/'LOCAL_INFEASIBLE.json',dict(status='INFEASIBLE',solver=info[1],strict_fallback_gate_pass=True))
   fallback=True;state(status='RUNNING',stage=policy+':FULL_PHYSICAL_PQ_FALLBACK')
   final,_=ns['fallback_binding']()('2025-05-01',policy,{'AIDC_decision':jobs},power,initial,ctx,folder/'full_pq')
  assert ns['discrete'](final.slots)==ds
  physics=recourse.validate_physics(final);assert physics['status']=='PASS'
  state(status='RUNNING',stage=policy+':CLOSURE_CLEAN_96_AC')
  ac=exact(pcc,final.slots,folder/'accepted_clean_exact');assert ac['status']=='PASS',ac['metrics']
  lin=evaluate_grid(ctx.coefficients,controls_from_trajectory(ctx.coefficients,pcc,final.slots),ctx.nodes)
  save(folder/'ACCEPTANCE.json',dict(status='PASS',primary=primary,AC=ac['metrics'],P1=lin['rho_max'],trajectory_slots=[asdict(r) for r in final.slots],unchanged_discrete_sha=ds,physics=physics,full_physical_PQ_fallback=fallback,beam_selection_unchanged=True))
  return final,ac,lin['rho_max']
 finally:local.make_frozen=old_make
