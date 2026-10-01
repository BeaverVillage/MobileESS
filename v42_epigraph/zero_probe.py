from .common import *
from v42_bootstrap.grid import coefficients
from .oracle import add_slot_lines
import gurobipy as gp
def run():
    b,a,*_=inputs();_,cc=coefficients(b)
    for t in read(OUT/'CRITICAL_SLOT_FREEZE.json')['slots']:
        m=gp.Model();m.Params.OutputFlag=0;r=m.addVar(lb=0,ub=1)
        x=[float(a['controls'][t][i]) if n.startswith('aidc_load_kw') else 0. for i,n in enumerate(cc[t].control_names)]
        add_slot_lines(m,cc[t],x,r);m.setObjective(r);m.optimize();print(t,m.Status,m.ObjVal,flush=True);m.dispose()
if __name__=='__main__':run()
