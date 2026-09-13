import os,sys,json,time,hashlib,tempfile
from pathlib import Path
import numpy as np
import gurobipy as gp
from electrical_engine import H,BIND,read,save,record,frozen_check
from frozen_binding import context
from v41r4_ieee8500_adapter import original_solver_binding,validate_electrical_payload
from numerical_coefficients import Coefficients,AX
import full_electrical_rows as electrical
from dayahead.v40a import grid
from dayahead.v41r1 import feasible_seed
from dayahead.v40g import optimizer
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def expression(e):
    from collections import defaultdict
    if isinstance(e,gp.Var):return dict(constant=0.,terms=[(e.VarName,1.)])
    d=defaultdict(float)
    for i in range(e.size()):d[e.getVar(i).VarName]+=float(e.getCoeff(i))
    return dict(constant=float(e.getConstant()),terms=sorted((k,v) for k,v in d.items() if v))
calls=[]
def forbidden(*a,**kw):calls.append(1);raise RuntimeError('NO_PRODUCTION_OPTIMIZATION_IN_PREFLIGHT')
gp.Model.optimize=forbidden;gp.Model.computeIIS=forbidden
class ASCIIOutputPath(type(Path())):
    def resolve(self,strict=False):
        assert Path(self).absolute().is_relative_to(H)
        return self.absolute()
def main():
    frozen_check();assert read(H/'SIGNED_PERTURBATION_VALIDATION.json')['status']=='PASS'
    (H/'runtime_tmp').mkdir(exist_ok=True);tempfile.tempdir=str(H/'runtime_tmp');os.environ['TMP']=os.environ['TEMP']=tempfile.tempdir
    ctx=context();ctx.coefficients=Coefficients();ctx.nodes=AX['nodes']
    print('VALIDATE_NUMERICAL_60_COLUMN_PAYLOAD',flush=True);validate_electrical_payload(ctx)
    registry=electrical.FullElectricalRegistry(H/'full_model/electrical_blocks')
    old=(grid.add_grid,grid.evaluate_grid,feasible_seed.complete_start,feasible_seed.row_audit)
    grid.add_grid=registry.add_grid;grid.evaluate_grid=electrical.evaluate_grid;feasible_seed.row_audit=registry.audit_seed
    def seed(model,jobs,context,output,**kw):
        result=old[2](model,jobs,context,output,**kw)
        vs=model.getVars();vars=[(v.VarName,v.VType,float(v.LB),float(v.UB)) for v in vs if v.VarName!='rho_max']
        values=result[0];seeddigest=digest([(v.VarName,float(x)) for v,x in zip(vs,values) if v.VarName!='rho_max'])
        exp=[expression(e) for e in kw['objective_expressions'][1:]]
        expected=read(BIND/'IEEE8500_B1/STRUCTURE.json')
        check=dict(status='PASS',variable_count=len(vars),variable_SHA=digest(vars),P2_P3_P4_P5_SHA=[digest(e) for e in exp],non_electrical_seed_SHA=seeddigest,expected_variable_SHA=expected['decision_variable_sha256'],expected_P2_P3_P4_P5_SHA=expected['P2_P3_P4_P5_sha256'],expected_seed_SHA=expected['seed_non_electrical_sha256'],original_B1_function_code_object_identical=True,global_path_override='ASCII output path only; same directory; no scientific expression change')
        assert check['variable_SHA']==check['expected_variable_SHA']
        assert check['P2_P3_P4_P5_SHA']==check['expected_P2_P3_P4_P5_SHA']
        assert seeddigest==check['expected_seed_SHA']
        save(H/'NON_ELECTRICAL_IDENTITY_IN_FULL_MODEL.json',check)
        return result
    feasible_seed.complete_start=seed
    started=time.perf_counter()
    try:
        with original_solver_binding(ctx,'B1',H/'full_model/core') as solver:
            assert solver.__code__ is optimizer.solve.__code__
            solver.__globals__.update(add_grid=registry.add_grid,evaluate_grid=electrical.evaluate_grid,Path=ASCIIOutputPath)
            print('BUILD_ORIGINAL_B1_AND_VALIDATE_FULL_ELECTRICAL_SEED',flush=True)
            result=solver(ctx.reference,ctx.power['pcc'],ctx,H/'full_model/core',build_only=True)
            assert ctx.v41_policy_budget.loop_started is None
        assert registry.audit and registry.audit['status']=='PASS' and not calls
        save(H/'FULL_MODEL_SEED_COMPLETE.json',dict(status='PASS',original_model_build_only=True,original_B1_non_electrical_source_unchanged=True,full_electrical_seed_audit=record(H/'FULL_LOGICAL_B1_SEED_AUDIT.json'),non_electrical_identity=record(H/'NON_ELECTRICAL_IDENTITY_IN_FULL_MODEL.json'),Gurobi_optimization_calls=0,B1_search_started=False,wall_seconds=time.perf_counter()-started,logical_full_model_representation='One original joint AIDC core plus 96 electrical CSR blocks with exact shared global PCC/rho names; all rows independently substituted. Electrical affine auxiliary elimination is lossless.'))
        print('FULL_MODEL_SEED_PASS',flush=True)
    finally:grid.add_grid,grid.evaluate_grid,feasible_seed.complete_start,feasible_seed.row_audit=old
if __name__=='__main__':main()
