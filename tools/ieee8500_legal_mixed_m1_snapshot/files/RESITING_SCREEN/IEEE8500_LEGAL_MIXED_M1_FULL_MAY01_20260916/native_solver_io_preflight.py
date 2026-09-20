"""Check native solver I/O in this run's ASCII alias before expensive setup."""
from bootstrap import *

def main():
 protect()
 assert str(H).isascii(), 'LAUNCH_WITH_EXISTING_ASCII_RUN_ALIAS'
 import gurobipy as gp
 from evidence_path_binding import install
 install()
 from dayahead.v41r1.migration_factor import verify_gate
 assert verify_gate()['status']=='PASS'
 out=H/'native_solver_io_preflight';out.mkdir(exist_ok=True)
 nodes=out/'gurobi_nodefiles';nodes.mkdir(exist_ok=True)
 with gp.Env(empty=True) as env:
  env.setParam('Threads',4);env.setParam('LogFile',str(out/'ENV.log'));env.start()
  with gp.Model('NATIVE_IO_SMOKE',env=env) as model:
   model.Params.Threads=4;model.Params.NodefileDir=str(nodes.resolve())
   model.Params.NodefileStart=.5;model.Params.LogFile=str((out/'SOLVER.log').resolve())
   x=model.addVar(lb=1,name='x');model.setObjective(x);model.optimize()
   assert model.Status==gp.GRB.OPTIMAL and abs(x.X-1)<1e-9
   model.write(str(out/'IO_MODEL.mps'));model.write(str(out/'IO_SOLUTION.sol'))
 assert all((out/n).stat().st_size>0 for n in ('ENV.log','SOLVER.log','IO_MODEL.mps','IO_SOLUTION.sol'))
 save(out/'PASS.json',dict(status='PASS',run_path=str(H),ascii_native_path=True,threads=4,original_equivalence_gate='PASS',production_decisions_modified=False))
 print('NATIVE_SOLVER_IO_PREFLIGHT_PASS',flush=True)

if __name__=='__main__':main()
