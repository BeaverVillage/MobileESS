"""Rebuild only unchanged F3, validating the start without optimizing."""
from .context import *
from v42_m1_sparse.grid import compressed_grid,map_bindings
from v42_m1_sparse.census import inspect
def run():
    bundle,anchor,prior,sites,initial,routes,battery=inputs();bindings=[];cost=[];values=prior['values'].copy();receipt={}
    def builder(m,p,q):
        levels,_=compressed_grid(m,bundle,anchor,p,q,'M1-F3',bindings,cost)
        return levels
    def capture(m,objectives,deadline,*args,**kwargs):
        m.update();map_bindings(bindings,values);m.setObjective(objectives[0][1]);m.update()
        stats,mapped,numeric=inspect(m,'M1-F3',values,False)
        expected=read(PRIOR/'census/M1-F3.json')['stats']
        assert all(stats[k]==expected[k] for k in ['binary','continuous','rows','columns','nonzeros'])
        assert mapped['PASS']
        receipt.update(PASS=True,stats=stats,MIP_start=mapped,numeric=numeric,fingerprint=m.Fingerprint,optimize_calls=0,formulation='M1-F3',formulation_changed=False)
        return None,dict(optimize_calls=0)
    import v42_native.mess as native
    old=native.optimize;native.optimize=capture
    try:native.solve('M1',OptimizeOnlyBudget(),sites,initial,routes,battery,96,builder,incumbent=prior)
    finally:native.optimize=old
    dump('M1_F3_REBUILD_RECEIPT.json',receipt);check_sources();print('F3 REBUILD PASS',receipt['fingerprint'],flush=True)
if __name__=='__main__':run()
