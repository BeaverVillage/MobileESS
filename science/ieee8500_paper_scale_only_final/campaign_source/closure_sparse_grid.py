"""Fixed-route electrical row generation, with the original complete separation."""
from bootstrap import *
from types import SimpleNamespace
import gurobipy as gp
import mess_grid8500 as full
from mess_grid8500_active import ActiveGrid


class FixedRouteGrid(ActiveGrid):
    def _rho_floor(self):
        # The integrated helper assumes ONE movable vehicle. Here all six P/Q
        # trajectories can move; use their full independent variable bounds.
        anchors=np.array([part[0] for part in self.parts])
        slot=int(full.evaluate_grid(self.coefficients,anchors,AX['nodes'])['critical_slot'])
        fixed,C,variables,lo,hi=self.parts[slot]
        floor=0.
        for kind,w,cons,_ in full.rows(self.coefficients[slot]):
            if kind!='line':continue
            B=w@C
            lower=cons+w@fixed+np.maximum(B,0)@lo+np.minimum(B,0)@hi
            floor=max(floor,float(lower.max())-1e-8)
        return floor


class SparseClosure:
    def __init__(self,folder):
        self.folder=Path(folder);self.active=None;self.calls=0

    def add(self,model,coefficients,controls,objective_cap=1.):
        self.calls+=1;began=time.perf_counter()
        eta=model.addVar(lb=0,ub=objective_cap,name='rho_max')
        inputs=SimpleNamespace(electrical_authority=SimpleNamespace(active_power_limit_kw=600.,pcs_kva=800.))
        self.active=FixedRouteGrid(model,coefficients,controls,eta,inputs,
            H/'COMPACT_B0_ACTIVE_SEED.json',self.folder/f'call_{self.calls:02d}')
        result=dict(status='SEED_REQUIRES_FULL_SEPARATION',full_rows=self.active.logical_rows,
            retained_rows=self.active.added_rows,rho_floor=self.active.floor,
            wall_seconds=time.perf_counter()-began,domain_changes=0)
        print('RESTORATION_SPARSE_SEED',result,flush=True)
        return eta,result

    def optimize(self,model):
        active=self.active;assert active is not None and active.model is model
        accepted={gp.GRB.OPTIMAL,gp.GRB.WORK_LIMIT,gp.GRB.TIME_LIMIT,gp.GRB.SUBOPTIMAL}
        assert model.Params.TimeLimit==600. and model.Params.WorkLimit==60.
        assert model.Params.MIPGap==.001 and model.Params.Threads==4
        assert model.Params.FeasibilityTol==1e-9
        iteration=0
        while True:
            iteration+=1;model.update()
            report=dict(iteration=iteration,rows=model.NumConstrs,columns=model.NumVars,
                binaries=model.NumBinVars,nonzeros=model.NumNZs,unix=time.time(),
                time_limit=model.Params.TimeLimit,work_limit=model.Params.WorkLimit)
            save(active.report_root/f'ITERATION_{iteration:03d}_START.json',report)
            print('RESTORATION_SPARSE_OPTIMIZE',report,flush=True)
            began=time.perf_counter();model.optimize()
            report.update(solver_status=int(model.Status),solution_count=model.SolCount,
                solve_seconds=time.perf_counter()-began)
            if not model.SolCount:
                save(active.report_root/f'ITERATION_{iteration:03d}_RESULT.json',report)
                return
            if model.Status not in accepted:raise RuntimeError('RESTORATION_UNACCEPTED_SOLVER_STATUS')
            report.update(incumbent=float(model.ObjVal),bound=float(model.ObjBound),gap=float(model.MIPGap))
            separation=active.separate();report['separation']=separation
            save(active.report_root/f'ITERATION_{iteration:03d}_RESULT.json',report)
            print('RESTORATION_FULL_SEPARATION',separation,flush=True)
            if separation['new_rows']==0:
                assert separation['all_logical_rows_checked']==31945536
                save(active.report_root/'FULL_SEPARATION_CLOSURE.json',dict(status='PASS',**report))
                return


def cached_cuts(original,folder):
    """Reuse only the identical chronological state, authority and cut payload."""
    from dayahead.v17_ac_restoration_contract import RestorationCut,ViolationType,canonical_sha256
    old=H/'diagnostic_attempts/B2_DENSE_CLOSURE_WORK60_20260922/physical_closure'
    def generate(**kwargs):
        if kwargs['iteration_index']!=1:return original(**kwargs)
        source=old/'local/round_00/CUTS.json'
        if not source.exists():return original(**kwargs)
        fresh=kwargs['fresh']
        previous=read(old/'local/round_00/fresh/VIOLATIONS.json')
        if previous!=[v.payload() for v in kwargs['violations']]:return original(**kwargs)
        with np.load(old/'local/round_00/fresh/ARRAYS.npz') as arrays:
            if not np.array_equal(arrays['x'],fresh.x):return original(**kwargs)
            for j,name in enumerate(('v2','line','tx','S')):
                if not np.array_equal(arrays[name],np.array([a[j] for a in fresh.values])):
                    return original(**kwargs)
        if read(old/'local/round_00/fresh/CONTROL_STATES.json')!=fresh.states:return original(**kwargs)
        data=read(source);cuts=[]
        for payload in data['cuts']:
            row=dict(payload);row['violation_type']=ViolationType(row['violation_type'])
            for name in ('control_names','anchor_controls','coefficients','local_radius'):row[name]=tuple(row[name])
            cut=RestorationCut(**row);assert canonical_sha256(cut.payload())==canonical_sha256(payload);cuts.append(cut)
        assert {c.violation_sha256 for c in cuts}=={v.sha256 for v in kwargs['violations']}
        save(Path(folder)/'SIGNED_CUT_CACHE_HIT.json',dict(status='PASS',source=record(source),
            identical_control_arrays=True,identical_electrical_arrays=True,identical_control_states=True,
            identical_violation_payloads=True,cut_count=len(cuts)))
        print('RESTORATION_IDENTICAL_CUT_CACHE_HIT',len(cuts),flush=True)
        return tuple(cuts),data['derivative']
    return generate
