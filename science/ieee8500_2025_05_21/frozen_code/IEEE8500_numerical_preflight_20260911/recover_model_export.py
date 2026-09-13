"""Recover only Gurobi's Unicode-path serialization; preserve validated evidence."""
import numpy as np,time
import gurobipy as gp
from electrical_engine import *
from numerical_coefficients import Coefficients,AX
from full_electrical_rows import FullElectricalRegistry,evaluate_grid,original_row_audit
from frozen_binding import context
from v41r4_ieee8500_adapter import original_solver_binding
from dayahead.v40a import grid
from dayahead.v41r1 import feasible_seed,migration_memory
from dayahead.v40g import optimizer
from run_full_model_seed import ASCIIOutputPath,digest,expression,calls

class RecheckedRegistry(FullElectricalRegistry):
    def audit_seed(self,model,values):
        core=original_row_audit(model,values);assert core['status']=='PASS'
        previous=read(H/'FULL_LOGICAL_B1_SEED_AUDIT.json');assert previous['status']=='PASS' and core==previous['original_core_audit']
        with np.load(H/'full_model/core/POLICY_FEASIBLE_SEED.npz') as z:
            assert z['names'].tolist()==model.getAttr('VarName',model.getVars())
            assert np.array_equal(z['values'],values)
        bound,coefficients,controls,rho=self.registration;assert bound is model
        by=dict(zip(model.getAttr('VarName',model.getVars()),values))
        seedreport=read(H/'full_model/core/POLICY_FEASIBLE_SEED_AUDIT.json')
        for t,c in enumerate(coefficients):
            assert c.coefficient_sha256==seedreport['electrical']['coefficient_SHAs'][t]
            folder=H/f'full_model/electrical_blocks/slot_{t:02}'
            with np.load(folder/'RHS_AND_SEED.npz') as z:
                names=[controls[t][j].VarName for j in range(12)]+[rho.VarName]
                assert z['shared_global_names'].tolist()==names
                assert np.array_equal(z['seed'],np.array([by[n] for n in names]))
                assert all(float(controls[t][j])==z['fixed_controls'][j] for j in range(12,60))
            assert read(folder/'BLOCK_AUDIT.json')['status']=='PASS'
        self.audit=previous
        save(H/'export_recovery/SHARED_MODEL_SEED_IDENTITY.json',dict(status='PASS',new_original_core_row_audit=core,all_global_seed_values_byte_identical=True,all_96_coefficient_SHAs_identical=True,all_96_electrical_block_bindings_identical=True,pre_export_seed_evidence=record(H/'full_model/core/POLICY_FEASIBLE_SEED_AUDIT.json')))
        return dict(core,full_electrical_blocks='PASS',full_electrical_linear_rows=previous['electrical_linear_rows'],full_logical_joint_model_seed='PASS')

def main():
    frozen_check();start=time.perf_counter();ctx=context();ctx.coefficients=Coefficients();ctx.nodes=AX['nodes']
    out=H/'export_recovery/core';assert not out.exists()
    registry=RecheckedRegistry(H/'export_recovery')
    old=(grid.add_grid,grid.evaluate_grid,feasible_seed.row_audit,feasible_seed.complete_start,migration_memory.Path)
    grid.add_grid=registry.add_grid;grid.evaluate_grid=evaluate_grid;feasible_seed.row_audit=registry.audit_seed
    migration_memory.Path=ASCIIOutputPath
    def complete(model,jobs,context,output,**kw):
        values,report=old[3](model,jobs,context,output,**kw)
        vs=model.getVars();varrows=[(v.VarName,v.VType,float(v.LB),float(v.UB)) for v in vs if v.VarName!='rho_max']
        prior=read(H/'NON_ELECTRICAL_IDENTITY_IN_FULL_MODEL.json')
        assert digest(varrows)==prior['variable_SHA']
        assert [digest(expression(e)) for e in kw['objective_expressions'][1:]]==prior['P2_P3_P4_P5_SHA']
        assert digest([(v.VarName,float(x)) for v,x in zip(vs,values) if v.VarName!='rho_max'])==prior['non_electrical_seed_SHA']
        return values,report
    feasible_seed.complete_start=complete
    try:
        with original_solver_binding(ctx,'B1',out) as solver:
            assert solver.__code__ is optimizer.solve.__code__
            solver.__globals__.update(add_grid=registry.add_grid,evaluate_grid=evaluate_grid,Path=ASCIIOutputPath)
            print('BUILD_ONLY_EXPORT_RECOVERY',flush=True)
            solver(ctx.reference,ctx.power['pcc'],ctx,out,build_only=True)
            assert ctx.v41_policy_budget.loop_started is None
        assert not calls and read(out/'MODEL_PERSISTENCE.json')['status']=='PASS'
        save(H/'FULL_MODEL_SEED_COMPLETE.json',dict(status='PASS',original_model_build_only=True,original_B1_non_electrical_source_unchanged=True,full_electrical_seed_audit=record(H/'FULL_LOGICAL_B1_SEED_AUDIT.json'),non_electrical_identity=record(H/'NON_ELECTRICAL_IDENTITY_IN_FULL_MODEL.json'),Gurobi_optimization_calls=0,B1_search_started=False,wall_seconds=time.perf_counter()-start,initial_export_failure='Gurobi Unicode resolved path; original completed seed audits preserved unchanged',export_recovery='Only migration_memory.Path and solver output Path use the same ASCII junction path; source code and scientific model unchanged',recovery_seed_identity=record(H/'export_recovery/SHARED_MODEL_SEED_IDENTITY.json'),core_model_persistence=record(out/'MODEL_PERSISTENCE.json'),core_MPS=record(out/'PRIMARY_MODEL.mps.gz'),logical_full_model_representation='One original joint AIDC core plus 96 complete electrical CSR blocks; exact shared global PCC/rho names and identical validated seed; affine auxiliary elimination only'))
        print('FULL_MODEL_SEED_AND_EXPORT_PASS',flush=True)
    finally:grid.add_grid,grid.evaluate_grid,feasible_seed.row_audit,feasible_seed.complete_start,migration_memory.Path=old
if __name__=='__main__':main()
