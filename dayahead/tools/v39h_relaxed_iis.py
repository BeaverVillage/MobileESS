"""Fast IIS refinement of an already-proven full Shadow A infeasibility.

All standby options and every grid row remain represented. Integrality and
C1 graph are relaxed to their continuous convex hull, never strengthened.
An infeasible hull proves the original exact MILP infeasible; a feasible
hull proves NOTHING. This is not the forbidden fixed-load voltage screen.
"""
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from dayahead.tools import run_v39h_shadow as h
from threadpoolctl import threadpool_limits

def run(day):
    parent=h.ROOT/"days"/day;out=parent/"full_option_LP_IIS";out.mkdir(exist_ok=True)
    a,_,_=h.inputs(day)
    # Builder reads the already prepared day authority; logs/proofs are copied
    # to the separate refinement directory after construction.
    bundle=h.build_model(a,parent,"V39H_IIS_CONVEX_HULL_REFINEMENT");m=bundle["model"]
    m.Params.LogFile=str(out/"V39H_LP_IIS.log")
    for gc in m.getGenConstrs():
        assert gc.GenConstrType==h.GRB.GENCONSTR_PWL
        x,y,xp,yp=m.getGenConstrPWL(gc)
        lam=m.addVars(len(xp),lb=0,ub=1,name="C1_hull_lambda")
        m.addConstr(lam.sum()==1)
        m.addConstr(x==h.gp.quicksum(xp[k]*lam[k] for k in lam))
        m.addConstr(y==h.gp.quicksum(yp[k]*lam[k] for k in lam))
        m.remove(gc)
    m.update()
    for v in m.getVars():v.VType=h.GRB.CONTINUOUS
    m.setObjective(0);m.update();m.optimize()
    result={"day":day,"status":m.Status,"all_eligible_temporal_options_retained":True,"fixed_only_voltage_screen":False,
        "proof":"Continuous allocation and full C1 graph convex-hull relaxation is a superset of the full exact standby shadow. INFEASIBLE proves original infeasible; OPTIMAL does not resolve the original.","Threads":4,"original_MILP_not_reoptimized":True}
    if m.Status==h.GRB.INFEASIBLE:
        m.computeIIS();m.write(str(out/"V39H_SHADOW_A_IIS.ilp"))
        result.update(full_shadow_infeasibility_proven=True,IIS_minimal=bool(m.IISMinimal),constraints=[c.ConstrName for c in m.getConstrs() if c.IISConstr])
    h.atomic(out/"V39H_SHADOW_A_IIS_SUMMARY.json",result);m.dispose();print(result["status"])

if __name__=="__main__":
    with threadpool_limits(limits=4):run(sys.argv[1])
