"""One frozen-setting continuous P1 diagnostic per eligible full model."""
import gc,re,threading
from time import perf_counter
import gurobipy as gp,psutil,numpy as np
from .common import *
from .data import prepare
from .native import build
from .profile import Census,column_profile
def measure(kind):
    destination=OUT/(kind+'_ROOT_LP.json')
    if destination.exists():raise ValueError('DIAGNOSTIC_ALREADY_RECORDED:'+kind)
    class DiagnosticContext(Context):
        def __init__(self):self.folder=LOCAL/('DIAGNOSTIC_'+kind);self.folder.mkdir(parents=True,exist_ok=True)
        def progress(self,d):atomic(self.folder/'build_progress.json',d)
    context=DiagnosticContext()
    frozen();data=prepare();started=perf_counter();print('diagnostic full build',kind,flush=True)
    if kind in ('F2','F2-BASE'):
        with Census() as census:m,units,levels,controls,bindings=build(context,data,kind)
        rows,maxdensity=census.rows(m);table('ROOT_LP_NONZERO_PROFILE.csv',rows)
        table('ROOT_LP_FAMILY_PROFILE.csv',column_profile(m,{x['id']:x['v'] for x in units}))
        stats=read(context.folder/'F2_MODEL_COMPLETE.json');stats.update(columns=m.NumVars,max_row_density=maxdensity)
        dump('F2_MODEL_STATS.json',stats)
    else:
        m,units,levels,controls,bindings=build(context,data,kind);stats=read(OUT/(kind+'_MODEL_STATS.json'))
    m.setObjective(levels[0][1]);m.update();stats['P1_model_fingerprint']=hex(m.Fingerprint)
    dump(kind+'_MODEL_STATS.json',stats)
    relax_start=perf_counter();lp=m.relax();copy_seconds=perf_counter()-relax_start
    m.dispose();del m,units,levels,controls,bindings;gc.collect()
    logfile=LOCAL/(kind+'_LP.log');lp.Params.Threads=1;lp.Params.Seed=20260929;lp.Params.TimeLimit=3600;lp.Params.OutputFlag=1;lp.Params.LogFile=str(logfile)
    stop=threading.Event();peak=[psutil.Process().memory_info().rss]
    def sample():
        p=psutil.Process()
        while not stop.wait(.25):peak[0]=max(peak[0],p.memory_info().rss)
    th=threading.Thread(target=sample,daemon=True);th.start();begin=perf_counter();last=[-1.]
    def cb(model,where):
        elapsed=perf_counter()-begin
        if elapsed-last[0]<5:return
        state={}
        if where==gp.GRB.Callback.SIMPLEX:state=dict(phase='LP_SIMPLEX',iteration=model.cbGet(gp.GRB.Callback.SPX_ITRCNT),simplex_objective=model.cbGet(gp.GRB.Callback.SPX_OBJVAL),primal_infeasibility=model.cbGet(gp.GRB.Callback.SPX_PRIMINF),dual_infeasibility=model.cbGet(gp.GRB.Callback.SPX_DUALINF))
        elif where==gp.GRB.Callback.BARRIER:state=dict(phase='LP_BARRIER',iteration=model.cbGet(gp.GRB.Callback.BARRIER_ITRCNT))
        elif where==gp.GRB.Callback.PRESOLVE:state=dict(phase='LP_PRESOLVE',rows_removed=model.cbGet(gp.GRB.Callback.PRE_ROWDEL),columns_removed=model.cbGet(gp.GRB.Callback.PRE_COLDEL))
        if state:atomic(LOCAL/'LP_PROGRESS.json',dict(formulation=kind,elapsed_seconds=elapsed,RSS_bytes=psutil.Process().memory_info().rss,**state));last[0]=elapsed
    try:lp.optimize(cb)
    finally:stop.set();th.join(timeout=1)
    wall=perf_counter()-begin;log=logfile.read_text(encoding='utf8');p=re.search(r'Presolve time: ([\d.]+)s',log);presolved=re.search(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
    receipt=dict(formulation=kind,optimal=lp.Status==gp.GRB.OPTIMAL,status=lp.Status,LP_wall_seconds=wall,native_Runtime_seconds=lp.Runtime,LP_objective=lp.ObjVal if lp.Status==gp.GRB.OPTIMAL else None,iterations=lp.IterCount,barrier_iterations=lp.BarIterCount,LP_algorithm='barrier with crossover' if lp.BarIterCount else 'simplex (Gurobi automatic default)',numerical_warnings=[line.strip() for line in log.splitlines() if 'Warning' in line or 'Numerical' in line],presolve_seconds=float(p[1]) if p else None,presolved=dict(rows=int(presolved[1]),columns=int(presolved[2]),nonzeros=int(presolved[3])) if presolved else None,peak_observed_RSS_bytes=peak[0],relax_copy_seconds=copy_seconds,total_build_and_diagnostic_wall_seconds=perf_counter()-started,build=stats,settings=dict(Threads=1,Seed=20260929,TimeLimit=3600,numerical='inherited defaults'),not_production_A1=True,objective_used_only_for_bound_strength_tie_break=True,time_scope='LP_wall_seconds measures the continuous P1 optimize call including its own LP presolve; PR102 1557.90 s is the separately reported initial MIP root relaxation, so production root timing is reported separately',source_sha256={'v42_root/'+n:sha(ROOT/'v42_root'/n) for n in ('common.py','data.py','factor.py','native.py')})
    dump(kind+'_ROOT_LP.json',receipt);lp.dispose();print('diagnostic complete',kind,receipt['optimal'],wall,receipt['LP_objective'],flush=True);frozen()
def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['F2','F2A','F2B','F2C']);measure(p.parse_args().kind)
if __name__=='__main__':main()
