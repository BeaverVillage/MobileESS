"""Read-only model attribute diagnosis; never calls optimize."""
from .base import *

def run():
    def probe(m,objectives,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings
        m.setObjective(objectives[0][1]);m.update()
        rows=[dict(phase='unstarted',**stats(m))]
        m.Params.Method=2;m.Params.Threads=1;m.Params.Seed=20260929;m.Params.MIPGap=.005
        rows.append(dict(phase='inherited_params',**stats(m)))
        values=data[2]['values'].copy();map_bindings(bindings,values)
        m.setAttr('Start',[values[n] for n in m.getAttr('VarName')]);m.update()
        rows.append(dict(phase='inherited_MIP_start',**stats(m)))
        dump('BASE_FINGERPRINT_PHASE_DIAGNOSIS.json',dict(optimize_calls=0,phases=rows))
        print(rows,flush=True)
        return None,dict(optimize_calls=0)
    build(probe)

if __name__=='__main__':run()
