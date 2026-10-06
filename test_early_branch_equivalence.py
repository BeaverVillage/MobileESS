"""New small exact equivalence with root branching before pricing closure."""
import json
import numpy as np
import gurobipy as gp
from v42_bap.fixtures import FixtureProblem,seed,complete_integer_master
from v42_bap.solver import ToyGuard,NodeCG,BoundedMaster
from v42_bap.state import Tree,NodeResult
from run_restricted_1841 import OUT,write

def run():
    results=[];guard=ToyGuard()
    cases=[dict(name='early_one'),dict(name='early_two_coupled',units=2,branch_benefit=True),dict(name='early_SOC',terminal=.875),dict(name='early_location',branch_benefit=True),dict(name='early_movement',branch_benefit=True,preferred_family='movement')]
    for case in cases:
        p=FixtureProblem(**case);registry,keys=seed(p,True);tree=Tree(registry,keys,tolerance=1e-8,allow_early_branching=True)
        direct,A,d=p.direct();integer=complete_integer_master(p,registry,keys);root=BoundedMaster(p,False)
        for key in keys:
            c=registry.columns[key];root.add(c.mess,np.array(c.x),np.array(c.a),c.c,key)
        cg=NodeCG(p,guard);root_prices=[None];first=[True]
        def solve(n,r):
            if first[0]:
                first[0]=False;guard.optimize(root.model,p.name+'/root_unpriced_RMP')
                assert root.model.Status==2 and root.checked();points,z=root.projection(len(p.blocks));root_prices[0]=len(cg.pricing_audits)
                # rho>=0 and all local objective=0 is an exact inherited LB.
                return NodeResult('ROOT_PRICING_NOT_RUN',keys,root.model.ObjVal,0.,False,points,z,certificate=dict(PASS=True,node_id=0,exact_original_rho_nonnegative=True))
            return cg(n,r)
        try:
            guard.optimize(direct,p.name+'/direct');guard.optimize(integer.model,p.name+'/complete_integer_master')
            # An integral unpriced root remains open; only the next independently
            # certified pricing pass may close it. Do not discard that subtree.
            for _ in range(30):
                if not tree.open_ids or tree.accepted(.005):break
                tree.step(solve,p.projections,p.validate_projection)
            assert tree.accepted(.005) and tree.incumbent is not None,(p.name,tree.global_lb,tree.incumbent)
            ub=tree.incumbent['objective'];assert abs(ub-direct.ObjVal)<=1e-8 and abs(ub-integer.model.ObjVal)<=1e-8
            branches=sum(any(c.parent_id==n.node_id for c in tree.nodes.values()) for n in tree.nodes.values())
            assert root_prices[0]==0 and p.validate_projection(tree.incumbent['points'],tree.incumbent['global_point'])['PASS']
            results.append(dict(name=p.name,PASS=True,direct_MILP=direct.ObjVal,complete_integer_master=integer.model.ObjVal,early_BAP=ub,
                root_pricing_calls_before_first_decision=root_prices[0],branches=branches,gap=tree.gap,original_feasible=True))
        finally:direct.dispose();integer.model.dispose();root.model.dispose();p.close()
    assert results[1]['branches']>0 and results[3]['branches']>0 and results[4]['branches']>0
    write('EARLY_BRANCH_EXACT_EQUIVALENCE.json',dict(PASS=True,cases=results,receipts=guard.receipts,fullscale_native_calls=0))
if __name__=='__main__':run()
