"""Actual Gurobi file IO on the verified workspace alias; no solve."""
import uuid
import numpy as np
from .stage_common import *
from .stage_gurobi_io import scope,ascii_path
from .prestart_native import native_zero
from .stage_resources import campaign_scope,apply_solver_memory_policy


def certify():
    import gurobipy as gp
    with measured('GUROBI_ASCII_FILE_IO_CERTIFICATION.json') as (report,start),scope(),native_zero() as denied,campaign_scope():
        folder=WORK/('NATIVE_IO_'+uuid.uuid4().hex[:8]);folder.mkdir()
        model=gp.Model('V2_ADD_REAL_FILE_IO_NATIVE0');model.Params.OutputFlag=0
        try:
            model.Params.LogFile=str(folder/'NATIVE.log');model.setParam('NodefileDir',str(folder))
            model.Params.Threads=4;model.Params.TimeLimit=300.;model.Params.MIPGap=.03
            memory=apply_solver_memory_policy(model)
            x=model.addVar(lb=0.,ub=1.,vtype='B',obj=1.,name='literal_binary')
            model.addConstr(x<=1.,name='literal_row');model.update();model.write(str(folder/'MODEL.lp'))
            assert model.NumVars==model.NumConstrs==model.NumNZs==1 and model.SolCount==0
            assert model.getA()[0,0]==1. and x.LB==0. and x.UB==1. and x.VType=='B'
            assert str(model.Params.LogFile).isascii() and str(model.Params.NodefileDir).isascii()
            assert (folder/'MODEL.lp').exists() and (folder/'NATIVE.log').exists()
            assert (model.Params.Threads,model.Params.TimeLimit,model.Params.MIPGap)==(4,300.,.03)
            rejected=False
            try:ascii_path('C:/unrelated_작업/no_write.log')
            except PermissionError:rejected=True
            assert rejected
            report.update(PASS=True,actual_model_write_and_native_log_succeeded=True,
                canonical_receipt_path=record(folder/'MODEL.lp'),Native_LogFile=model.Params.LogFile,
                Native_NodefileDir=model.Params.NodefileDir,unrelated_Unicode_alias_rejected=True,
                original_model_matrix_domain_objective_and_nonpath_parameters_unchanged=True,
                official_memory_parameters=memory,denied_attempts=denied)
        finally:model.dispose()


if __name__=='__main__':certify()
