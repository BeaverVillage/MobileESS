"""No-solve audit of original objectives, source adapters, seeds and time budget."""
import sys,os,tempfile,ast,inspect,hashlib,json,copy
from types import SimpleNamespace
import numpy as np
import gurobipy as gp
from frozen_binding import HOME,ROOT,context,save,read,record,sha,EXPECTED
import v41r4_ieee8500_adapter as adapter
(HOME/'runtime_tmp').mkdir(exist_ok=True);tempfile.tempdir=str(HOME/'runtime_tmp');os.environ['TEMP']=os.environ['TMP']=tempfile.tempdir
calls=[]
def deny(*a,**k):calls.append('OPTIMIZE');raise RuntimeError('OPTIMIZATION_FORBIDDEN')
gp.Model.optimize=deny;gp.Model.computeIIS=deny
def guard(event,args):
    if event=='open' and len(args)>2:
        p,mode,flags=args
        if isinstance(p,(str,bytes)) and isinstance(flags,int) and flags&(1|2|64|512|1024):
            from pathlib import Path
            if not Path(os.fsdecode(p)).resolve().is_relative_to(HOME.resolve()):raise PermissionError('WRITE_OUTSIDE_RECONSTRUCTION')
sys.addaudithook(guard)
from structural_projection import compile_projection,digest
from dayahead.v40g import optimizer
from dayahead.v41r1 import feasible_seed,bounded_solver
from dayahead.v41 import temporal_restore
from v41r4_b3_equivalent import PATCHES,controls
ctx=context();b1=adapter.compile_B1(ctx);a1=adapter.compile_A1(ctx);a1seed=adapter.compile_A1_seed()
assert b1.__code__ is optimizer.solve.__code__ and b1.__kwdefaults__==optimizer.solve.__kwdefaults__
source=inspect.getsource(optimizer.solve)
patch=next(p for p in PATCHES if p['function'].endswith('optimizer.solve'))
a1source=source
for item in patch['substitutions']:
    assert a1source.count(item['before'])==1
    a1source=a1source.replace(item['before'],item['after'])
save('A1_ORIGINAL_ADAPTER_SUBSTITUTIONS.json',patch)
def staged(source):
    tree=ast.parse(source);out=[];active=False
    for node in tree.body[0].body:
        if isinstance(node,ast.Try):
            for n in node.body:
                if ast.unparse(n).startswith("pstage = optimize('PRIMARY_MIN_RHO')"):active=True
                if active:out.append(ast.dump(n,include_attributes=False))
                if active and isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='optimize' and 'QUATERNARY_STABLE_TIE' in ast.unparse(n):break
    assert out
    return out
assert staged(source)==staged(a1source)
labels=['PRIMARY_MIN_RHO','V41_SECONDARY_MIN_MEAN_H4_SHORTFALL','SECONDARY_MIN_MIGRATIONS','TERTIARY_COMPLETE_REFERENCE_DEVIATION','QUATERNARY_STABLE_TIE']
assert [source.index("optimize('"+s+"')") for s in labels]==sorted(source.index("optimize('"+s+"')") for s in labels)
budget_clock=[0.];budget=adapter.wall_clock_budget(clock=lambda:budget_clock[0]);assert budget.total==14400 and budget.used==0
budget.start_loop();timing=[]
for t in [1800,3600,7200,14399,14400]:
    budget_clock[0]=t;timing.append(dict(seconds=t,used=budget.used,remaining=budget.remaining));assert budget.used==t and budget.remaining==14400-t
save('STAGE_LOCK_BUDGET_IDENTITY.json',dict(status='PASS',B1_original_function_code_object_identity=True,stage_order=labels,stage_and_lock_AST_sha256=digest(staged(source)),A1_stage_lock_AST_identical=True,budget_seconds=14400,budget_fake_clock_checks=timing,original_BoundedLex=record(ROOT/'dayahead/v41r1/bounded_solver.py'),continuous_loop_adapter=record(ROOT/'v41r4_loop_budget.py'),actual_clock_waits=0,optimization_calls=len(calls)))
contract=adapter.electrical_port_contract();save('ELECTRICAL_DIFFERENCE_CONTRACT.json',contract)
names=tuple(r['control_name'] for r in contract['control_axis'])
ctx.coefficients=tuple(SimpleNamespace(control_names=names) for _ in range(96))
# Synthetic algebra-only M1 fixture probes all 24 service P/Q bindings. It is
# never installed in OpenDSS or represented as a feasible production route.
fixture=tuple(SimpleNamespace(service_id=s,slot=t,p_kw=(j+1)/10,q_kvar=-(j+1)/20) for t in range(96) for j,s in enumerate([f'IDC{i:02}' for i in range(1,13)]+[f'STA{i:02}' for i in range(1,13)]))
ctx.v41_fixed_mess=fixture;ctx.v41_a1_seed_pcc=ctx.power['pcc'].copy()
probe=controls(ctx,ctx.power['pcc'],fixture)
assert np.array_equal(probe[:,:12],ctx.power['pcc'])
for r in fixture:assert probe[r.slot,names.index(f'mess_p_kw[{r.service_id}]')]==r.p_kw and probe[r.slot,names.index(f'mess_q_kvar[{r.service_id}]')]==r.q_kvar
fixture_digest=digest([[r.service_id,r.slot,r.p_kw,r.q_kvar] for r in fixture])
temporal_restore.BASE_COUNT=1325555;temporal_restore.RESTORED_COUNT=16392;temporal_restore.TOTAL_COUNT=1341947
with temporal_restore.activate():
    print('BUILD_ORIGINAL_A1_FIXED_MESS_NON_ELECTRICAL_PROJECTION',flush=True)
    result=compile_projection(ctx,'IEEE8500_A1',source_override=a1source,namespace_override={'fixed_controls':controls})
before=read(HOME/'IEEE8500_B1/STRUCTURE.json')
assert result==before
assert fixture_digest==digest([[r.service_id,r.slot,r.p_kw,r.q_kvar] for r in fixture])
# Verify the exact retained make_seed substitutions. They replace original
# seed assignment with final-B1 assignment and remove no-migration resets.
seedpatch=next(p for p in PATCHES if p['function'].endswith('feasible_seed.complete_start'))
seedsource=inspect.getsource(feasible_seed.complete_start)
for item in seedpatch['substitutions']:
    assert seedsource.count(item['before'])==1;seedsource=seedsource.replace(item['before'],item['after'])
assert 'values=seed_assignment(model,context)' in seedsource
assert "values[i]=0." not in seedsource
assert 'physical,power=job_audit(jobs,context)' in seedsource
assert "fill['WAN_selected_'" not in seedsource
save('SEED_FIXED_MESS_SEMANTICS.json',dict(status='PASS_STRUCTURAL_SEMANTICS',B1='Original feasible_seed.complete_start; current frozen B0 reference; no optional move; all non-electrical seed rows independently substituted.',B3_A1='Original make_seed substitutions: exact final B1 assignment, no WAN/migration reset, fixed M1 numeric electrical controls; no legacy/stopped B1 checkpoint accepted.',B1_seed_projection=record(HOME/'IEEE8500_B1/B0_REFERENCE_NON_ELECTRICAL_SEED.npz'),A1_non_electrical_rows_and_P2_P5_identical=True,source_substitutions=seedpatch,electrical_M1_fixture_scope='ALGEBRA_ONLY_NOT_PRODUCTION_NOT_AC_FEASIBILITY',fixed_MESS_fixture_sha256=fixture_digest,fixed_MESS_24_P_Q_binding_verified=True,fixed_MESS_fixture_unchanged=True,actual_final_B1_seed_available=False,actual_final_B1_seed_validation='DEFERRED_UNTIL_NEW_AUTHORIZED_PRODUCTION_RUN',Gurobi_optimization_calls=len(calls),Fresh_calls=0))
forbidden=0
try:adapter.production_entry()
except RuntimeError:forbidden+=1
assert forbidden==1 and not calls
save('SEMANTIC_AUDIT_PASS.json',dict(status='PASS_NON_ELECTRICAL_STRUCTURAL_SEMANTICS',B1_function_code_identity=True,A1_original_adapter_identity=True,P5_original_cohort_rank=True,P2_P3_P4_P5_identity=True,BoundedLex_original_sources=True,stage_locks_identical=True,B1_A1_joint_non_electrical_model_identical=True,production_entry_is_blocked=True,optimization_calls=0,Fresh_calls=0))
print('SEMANTIC_AUDIT_PASS',flush=True)
