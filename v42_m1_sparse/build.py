"""Native unchanged route/SOC/PCS model with injectable exact grid builder."""
import argparse,threading
from time import perf_counter
import psutil
from v42_root.common import *
from v42_root.data import prepare
from v42_bootstrap.m1 import native_inputs,OptimizeOnlyBudget
from v42_bootstrap.grid import frozen_grid,grid_report
from v42_bootstrap.attribution import supplemental_physical
from v42_native.mess import validate
from .census import inspect
def inputs():
    frozen();bundle=prepare()[0];anchor=read(OUT/'A1_AIDC_GRID_CONTROL_ANCHOR.json');prior=read(LOCAL/'PR106_M1_PLAN.json')
    sites,initial,routes,battery,source=native_inputs(bundle)
    physical=validate(prior,sites,routes,battery,96);extra=supplemental_physical(prior,sites,battery)
    grid=grid_report(bundle,read(LOCAL/'PR106_M1_CONTROLS.json'),prior['values']['rho_max'])
    assert physical['PASS'] and extra['charge_mode_and_connection_PASS'] and grid['PASS']
    assert all(abs(prior['values'][f'SOC[{u},0]']-battery.initial)<=1e-5 for u in initial)
    dump('PR106_M1_INCUMBENT_RECEIPT.json',dict(PASS=True,source_sha256=sha(LOCAL/'PR106_M1_PLAN.json'),physical=physical,supplement=extra,grid=grid,domain_sha256=prior['domain_sha256'],MIP_start_only=True,variables_fixed=False))
    return bundle,anchor,prior,sites,initial,routes,battery
def run(label):
    bundle,anchor,prior,sites,initial,routes,battery=inputs();values=prior['values'].copy();budget=OptimizeOnlyBudget();handles=[];bindings=[];cost=[]
    process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event()
    def sampler():
        while not stop.wait(.25):peak[0]=max(peak[0],process.memory_info().rss)
    thread=threading.Thread(target=sampler,daemon=True);thread.start()
    def builder(m,p,q):
        if label=='M1-F0':levels,controls=frozen_grid(m,bundle,anchor,p,q)
        else:
            from .grid import compressed_grid
            levels,controls=compressed_grid(m,bundle,anchor,p,q,label,bindings,cost)
        handles.extend(controls);return levels
    result={}
    def capture(m,objectives,deadline,*args,**kwargs):
        m.update()
        from .grid import map_bindings
        map_bindings(bindings,values)
        m.setObjective(objectives[0][1]);s,mapped,numerical=inspect(m,label,values,label=='M1-F0');result.update(stats=s,start=mapped,numerical=numerical)
        return None,dict(structural_only=True,optimize_calls=0)
    import v42_native.mess as native
    old=native.optimize;native.optimize=capture;start=perf_counter()
    try:_,receipt=native.solve('M1',budget,sites,initial,routes,battery,96,builder)
    finally:native.optimize=old;stop.set();thread.join(1)
    result['stats'].update(build_seconds=receipt['model_build_seconds'],census_total_seconds=perf_counter()-start,peak_RSS_bytes=peak[0])
    full=read(OUT/'census'/(label+'.json'));full.update(result);full['factor_cost_audit']=cost
    atomic(OUT/'census'/(label+'.json'),full)
    print('CENSUS FINISHED',label,result['stats'],flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('candidate');run(parser.parse_args().candidate)
