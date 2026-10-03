"""Read-only reaggregation of saved vectors; never an optimization retry."""
from .common import OUT,write,read,sha
from .analysis import graph_inputs,census
import numpy as np
import re

def main():
    sites,initial,arcs,_,_=graph_inputs()
    with np.load(OUT/'BASELINE_ROOT_LP_SOLUTION.npz') as z:
        d=dict(names=z['names'],types=z['integer_types']);point=z['values']
    census(d,point,sites,initial,arcs)
    for label in ('CUT_A_ROOT','STRENGTHENING_B_ROOT','SOC_FLOW_FULL_ROOT'):
        result=read(OUT/(label+'_RESULT.json'))
        path=OUT/(label+'_SOLUTION.npz')
        if path.exists():
            with np.load(path) as z:point=z['values'][:len(d['names'])]
            result['fractional_census'],_=census(d,point,sites,initial,arcs,label)
        else:
            result['fractional_census']=None
            result['reason']='TIME_LIMIT_NO_OPTIMAL_LP_OR_RETURNED_PRIMAL_POINT'
            result['root_LB_certificate']=None
            result['material_improvement_established']=False
            log=(OUT/(label+'.log')).read_text(encoding='utf8')
            iterations=[]
            for line in log.splitlines():
                match=re.match(r'^\s*(\d+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+(\d+)s$',line)
                if match:
                    iterations.append(dict(iteration=int(match[1]),primal_objective=float(match[2]),dual_objective=float(match[3]),
                                           primal_residual=float(match[4]),dual_residual=float(match[5]),complementarity=float(match[6]),seconds=int(match[7])))
            result['last_barrier_iteration_diagnostic']=iterations[-1] if iterations else None
            result['barrier_diagnostic_is_not_root_LB_certificate']=True
        write(label+'_RESULT.json',result)
    write('READ_ONLY_POSTPROCESS_RECEIPT.json',dict(optimization_calls=0,
          input_solution_SHAs={p.name:sha(p) for p in OUT.glob('*SOLUTION.npz')},
          mass_reaggregation='Exact requested sum min(x,1-x) over all integer variables, alongside the thresholded diagnostic mass.',
          unavailable_LP_vectors_not_inferred=True))

if __name__=='__main__':main()
