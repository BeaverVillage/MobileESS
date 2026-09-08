"""Bounded infrastructure measurement, never a scientific policy solution."""
from pathlib import Path
import sys,time,threading
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import gurobipy as gp
from dayahead.paper_analysis.storage import write_json
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.data import RUNTIME
from dayahead.v41r1.migration_memory import process_measure,measure
folder=RUNTIME/'pre_policy_attempts/sparse_memory_diagnostic';folder.mkdir(parents=True,exist_ok=True)
source=OUT/'PRE_MAY01_ONE_SHOT_AUDIT/MODEL/PRIMARY_MODEL.mps'
stop=threading.Event();samples=[]
def monitor():
    while not stop.is_set():
        samples.append(dict(at=time.time(),**process_measure()))
        write_json(folder/'HOST_PROCESS_MEMORY.json',dict(samples=samples,scientific_run=False))
        stop.wait(1)
t=threading.Thread(target=monitor,daemon=True);t.start()
try:
    m=gp.read(str(source));m.Params.OutputFlag=1;m.Params.LogToConsole=0
    m.Params.LogFile=str(folder/'SOLVER.log');m.Params.Threads=4;m.Params.Seed=20260905
    m.Params.MIPGap=0;m.Params.MIPGapAbs=0;m.Params.FeasibilityTol=1e-9
    m.Params.IntFeasTol=1e-9;m.Params.OptimalityTol=1e-9
    m.Params.SoftMemLimit=8;m.Params.NodefileStart=.5
    node=folder/'gurobi_nodefiles';node.mkdir(exist_ok=True);m.Params.NodefileDir=str(node)
    m.Params.WorkLimit=60
    before=measure(m,folder/'SOLVER.log');m.optimize()
    write_json(folder/'RESULT.json',dict(scientific_run=False,diagnostic_work_limit=60,
        source=record(source),before=before,after=measure(m,folder/'SOLVER.log'),
        status=int(m.Status),solution_count=m.SolCount,runtime=m.Runtime,work=m.Work))
    m.dispose()
finally:
    stop.set();t.join()
