"""Read historical TimeLimit log lines and replay those exact finite limits."""
import re,time,shutil
from pathlib import Path
import numpy as np
import gurobipy as gp
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from .first_replay import OUT
from .flex_diagnostic import OLD,NEW,DAY
from .flex_model import Data,ProbeModel
from .feasible_seed import row_audit

def run():
    path=OUT/'OLD_FO_MISSED_IMPROVEMENT_REPLAY.json'
    original=OUT/'OLD_FO_MISSED_IMPROVEMENT_REPLAY_INITIAL_60S.json'
    if not original.exists():shutil.copyfile(path,original)
    result=read(original);d=Data();p=ProbeModel(d)
    try:
        for label,root in [('pre_early',OLD),('early',NEW)]:
            r=result['runs'][label];h=read(r['actual_replayed_neighborhood']['path']);a0=root/DAY/'B1/dayahead/A0'
            logfile=a0/'SOLVER.log';text=logfile.read_text()
            limits=[float(v) for v in re.findall(r'Set parameter TimeLimit to value ([^\n]+)',text)]
            assert len(limits)==len(list((a0/'bounded_checkpoints').glob('ITERATION_*.json')))
            limit=limits[h['iteration']-1];p.reset(h['free_cohorts'])
            p.temporary.append(p.m.addConstr(1000*p.rho<=h['higher_priority_locks'][0]['rhs'],name='PRIMARY_EXACT_VALUE_LOCK'))
            p.m.setObjective(gp.quicksum(p.xi)/81);p.m.Params.TimeLimit=limit;p.m.Params.MIPGap=.03
            p.m.Params.SolutionLimit=gp.GRB.MAXINT;p.m.setAttr('Start',p.vs,p.seed.tolist());p.m.update()
            p.m.Params.LogFile=str(OUT/(label+'_EXACT_LIMIT_REPLAY.log'))
            t=time.perf_counter();p.m.optimize();elapsed=time.perf_counter()-t
            r.update(TimeLimit=limit,historical_time_limit_evidence=dict(log=record(logfile),iteration=h['iteration'],
                one_to_one_iteration_parameter_log_count=len(limits)),solver_status=int(p.m.Status),
                returned_P2=float(p.m.ObjVal),best_bound=float(p.m.ObjBound),gap=float(p.m.MIPGap),runtime=elapsed,
                raw_row_audit=row_audit(p.m,p.m.getAttr('X',p.vs)))
            assert not p.decode(np.array(p.m.getAttr('X',p.vs)))
            assert p.m.Status==gp.GRB.OPTIMAL and p.m.Runtime<limit
            r['termination_reason']='RELATIVE_GAP_TARGET_REACHED_WITH_B0_ONLY; NOT_TIME_LIMIT'
            print('EXACT_LIMIT_REPLAY',label,limit,r['gap'],flush=True)
        result.update(conclusion='COMBINED_COMPUTATIONAL_ISSUE: known 0.0988 GPUh job never opened in P2; other full-row-validated P2 alternatives were missed in exact historical neighborhoods because the 3% gap stopped at B0.',
            original_60s_replay=record(original),exact_time_limit_replay_complete=True)
        write_json(path,result)
    finally:p.close();d.close()

if __name__=='__main__':run()
