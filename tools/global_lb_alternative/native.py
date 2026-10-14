"""One sequential native worker, immutable prefix accounting and durable latches."""
from pathlib import Path
from fractions import Fraction as F
import math
import os
import time

import numpy as np
from scipy import sparse

from tools.physical_global_lb_pilot import read, write, file_sha
from tools.global_lb_alternative.math import require, rounding_error, directed
from tools.joint_critical_grid_lb.pilot import memory, admission
from tools.b2_root_lp_tightening.resources import inventory, heavy_candidates


class NativeBudget:
    def __init__(self, out):
        self.path = Path(out) / 'NATIVE_RUNTIME_BUDGET_LEDGER.json'

    def remaining(self, algorithm):
        p = read(self.path)
        require(p['budget_proven'] and not p.get('STOP') and p['inflight'] is None, 'NATIVE_BUDGET_NOT_ADMITTED')
        for record in p['prefix_records']:
            require(file_sha(Path(record['path'])) == record['sha256'], 'HISTORICAL_LEDGER_DRIFT')
        spent = sum(c['Native_Runtime'] for c in p['calls'])
        local = sum(c['Native_Runtime'] for c in p['calls'] if c['algorithm'] == algorithm)
        return min(p['original_ceiling'] - p['prefix_Native_Runtime'] - spent,
                   600 - spent, (360 if algorithm == 'A' else 240) - local)

    def begin(self, algorithm, label, limit):
        require(limit <= self.remaining(algorithm) - 1, 'NATIVE_OVERSHOOT_RESERVE')
        p = read(self.path)
        calls = [c for c in p['calls'] if c['algorithm'] == algorithm]
        require(not any(c['label']==label for c in calls),'DUPLICATE_NATIVE_SIGNATURE')
        require(algorithm != 'A' or len(calls) < 24, 'A_NATIVE_CALL_LIMIT')
        require(algorithm != 'B' or label != 'STRENGTHENED_LP' or
                not any(c['label'] == label for c in calls), 'B_ONLY_ONE_STRENGTHENED_EVALUATION')
        p['inflight'] = dict(algorithm=algorithm, label=label, TimeLimit=limit, pid=os.getpid())
        write(self.path, p)

    def finish(self, runtime, error=None):
        p = read(self.path)
        require(p['inflight'] is not None, 'MISSING_INFLIGHT')
        if runtime is None or not math.isfinite(runtime) or runtime<0:
            p['calls'].append(dict(**p['inflight'],Native_Runtime=None,error=error or 'UNKNOWN_NATIVE_RUNTIME'))
            p['inflight']=None
            p['research_Native_Runtime']=None
            p['effective_cumulative_Native_Runtime']=None
            p['STOP']=True
            write(self.path,p)
            return
        p['calls'].append(dict(**p['inflight'], Native_Runtime=runtime, error=error))
        p['inflight'] = None
        p['research_Native_Runtime'] = sum(c['Native_Runtime'] for c in p['calls'])
        p['effective_cumulative_Native_Runtime'] = p['prefix_Native_Runtime'] + p['research_Native_Runtime']
        if error or p['research_Native_Runtime'] > 600 or p['effective_cumulative_Native_Runtime'] > p['original_ceiling']:
            p['STOP'] = True
        for a, cap in (('A', 360), ('B', 240)):
            if sum(c['Native_Runtime'] for c in p['calls'] if c['algorithm'] == a) > cap:
                p['STOP'] = True
        write(self.path, p)


def solve(out, A, d, c_exact, start, budget, algorithm, label, limit=29., maximize=False, lp=False):
    import gurobipy as gp
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    pre = memory()
    peers, errors = inventory()
    other = heavy_candidates(peers)
    write(out/'RESOURCE_BEFORE.json', dict(memory=pre, peers=peers, errors=errors, heavy=other))
    require(not errors and not other and admission(pre), 'RESOURCE_OR_PEER_GATE')
    c = np.zeros(A.shape[1])
    for j, v in c_exact.items():
        c[int(j)] = float(v)
    error = rounding_error(c_exact, c, d['lb'], d['ub'], maximize)
    sparse.save_npz(out/'A.npz', A)
    types = np.full(len(c), 'C') if lp else d['vtypes']
    np.savez_compressed(out/'DATA.npz', **dict(d, c=c, vtypes=types))
    write(out/'EXACT_OBJECTIVE.json', dict(terms={str(j): str(v) for j,v in c_exact.items()},
                                          rounding_correction=str(error), maximize=maximize))
    model = None
    entered = False
    began = time.perf_counter()
    try:
        model = gp.Model(label)
        # Keep the current PR222 scientific acceptance tolerance. Gap0 here
        # requests an exact local solve; it does not relax acceptance tolerances.
        params = dict(Threads=1, TimeLimit=limit, FeasibilityTol=1e-9, OptimalityTol=1e-9,
                      IntFeasTol=1e-8, NumericFocus=3, ScaleFlag=2, OutputFlag=1,
                      LogFile=str(out/'NATIVE.log'))
        if lp:
            params['Method'] = 1
        else:
            params.update(MIPGap=0., MIPGapAbs=0.)
        for k, v in params.items():
            model.setParam(k, v)
        x = model.addMVar(len(c), lb=d['lb'], ub=d['ub'], obj=c, vtype=types)
        model.addMConstr(A, x, d['senses'], d['rhs'])
        model.ModelSense = -1 if maximize else 1
        model.ObjCon = float(d.get('constant', 0))
        if start is not None and not lp:
            x.Start = start
        model.update()
        B = model.getA().tocsr()
        checks = dict(CSR=all(np.array_equal(getattr(A,k),getattr(B,k)) for k in ('data','indices','indptr')),
                      RHS=np.array_equal(model.getAttr('RHS'), d['rhs']),
                      senses=np.array_equal(model.getAttr('Sense'), d['senses']),
                      lower=np.array_equal(x.LB,d['lb']), upper=np.array_equal(x.UB,d['ub']),
                      types=np.array_equal(x.VType,types), objective=np.array_equal(x.Obj,c),
                      ObjCon=model.ObjCon==float(d.get('constant',0)),
                      sense=model.ModelSense==(-1 if maximize else 1), Threads=model.Params.Threads==1,
                      TimeLimit=model.Params.TimeLimit==limit)
        write(out/'READBACK.json',dict(PASS=all(checks.values()), checks=checks, parameters=params,
                                     build_wall_seconds=time.perf_counter()-began))
        require(all(checks.values()), 'NATIVE_READBACK_FAIL')
        del B
        post = memory()
        growth = max(2*1024**3, 4*max(0,post['Private_Commit_bytes']-pre['Private_Commit_bytes']))
        peers, errors = inventory()
        require(admission(post,growth) and not errors and not heavy_candidates(peers), 'POST_BUILD_RESOURCE_GATE')
        samples, problems = [post], []
        last = 0.
        last_peer = 0.
        def callback(m, where):
            nonlocal last,last_peer
            now = time.monotonic()
            if now-last >= 1:
                last = now
                sample = memory()
                samples.append(sample)
                if not admission(sample,0):
                    problems.append('MEMORY_RESERVE')
                    m.terminate()
            if now-last_peer>=2:
                last_peer=now
                peers,errors=inventory()
                if errors or heavy_candidates(peers):
                    problems.append('EXTERNAL_LOADED_SOLVER_OR_INVENTORY_UNKNOWN')
                    m.terminate()
            if where == gp.GRB.Callback.MESSAGE:
                msg = m.cbGet(gp.GRB.Callback.MSG_STRING)
                if any(s in msg.lower() for s in ('numerical trouble','numeric error','out of memory')):
                    problems.append(msg.strip())
                    m.terminate()
        budget.begin(algorithm,label,limit)
        # A durable per-call latch and inflight prefix prohibit automatic replay.
        write(out/'STARTED.json',dict(pid=os.getpid(),label=label,TimeLimit=limit))
        entered = True
        model.optimize(callback)
        runtime = float(model.Runtime)
        status_valid=model.Status in (2,9,11)
        budget.finish(runtime, '|'.join(problems) if problems else None if status_valid else 'INVALID_SOLVER_STATUS')
        entered = False
        require(not problems and model.Status in (2,9,11), 'NUMERIC_RESOURCE_OR_STATUS_FAIL')
        incumbent = float(model.ObjVal) if model.SolCount else None
        if not lp:
            raw_bound,raw_bound_c=float(model.ObjBound),float(model.ObjBoundC)
            bound = (max if maximize else min)(raw_bound,raw_bound_c)
            require(math.isfinite(bound) and abs(bound)<gp.GRB.INFINITY, 'NO_GLOBAL_BOUND')
            if incumbent is not None:
                require(bound >= incumbent-1e-8 if maximize else bound <= incumbent+1e-8, 'GLOBAL_BOUND_ORDER')
            corrected = F(bound)+error
        else:
            bound = corrected = None
            raw_bound=raw_bound_c=None
        if model.SolCount:
            point = x.X
            np.savez_compressed(out/'POINT.npz',point=point)
            residual = A@point-d['rhs']
            violation = np.where(d['senses']=='=',abs(residual),np.where(d['senses']=='<',residual,-residual))
            point_replay = dict(max_row_violation=float(max(violation)),
                                max_bound_violation=float(max(np.max(d['lb']-point),np.max(point-d['ub']),0)),
                                max_integer_violation=0. if lp else float(max(abs(point[types!='C']-np.rint(point[types!='C'])),default=0.)))
        else:
            point_replay = None
        if lp and model.Status==2:
            np.savez_compressed(out/'DUAL.npz',pi=model.getAttr('Pi'),rc=x.RC)
        samples.append(memory())
        result = dict(status=int(model.Status),Native_Runtime=runtime,wall_seconds=time.perf_counter()-began,
                      TimeLimit=limit,Incumbent=incumbent,Global_Bound=bound,
                      raw_ObjBound=raw_bound,raw_ObjBoundC=raw_bound_c,
                      exact_corrected_bound=str(corrected) if corrected is not None else None,
                      corrected_bound=directed(corrected,maximize) if corrected is not None else None,
                      rounding_correction=str(error),point_replay=point_replay,SolCount=int(model.SolCount),
                      NodeCount=float(model.NodeCount),
                      peak_RSS_bytes=max(s['Peak_RSS_bytes'] for s in samples),
                      peak_private_commit_bytes=max(s['Peak_Private_Commit_bytes'] or s['Private_Commit_bytes'] for s in samples),
                      exact_BB_proof_trace=False,solver_numerical_bound_contract=not lp,
                      scope='Certified local support/bound; incumbent is never a FULL UB or a bound.')
        write(out/'MEMORY_TRACE.json',dict(samples=samples,problems=problems))
        write(out/'RESULT.json',result)
        return result
    except BaseException as exc:
        if entered:
            try:
                failed_runtime=float(model.Runtime)
            except BaseException:
                failed_runtime=None
            budget.finish(failed_runtime,repr(exc))
        write(out/'ERROR.json',dict(error=repr(exc),entered_native=entered))
        raise
    finally:
        if model is not None:
            model.dispose()
