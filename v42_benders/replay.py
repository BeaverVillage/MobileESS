"""Independent archive replay and stronger physical-source perturbation checks."""
import copy
import numpy as np
import gurobipy as gp
from .common import *
from .fixtures import build,CASES
from .canonical import from_model
from .independent import verify
from .certificates import Uncertifiable

def run():
    payload=read('FIXTURE_CUT_PAYLOADS.json');env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
    audits=[];adversarial=[]
    for case in CASES:
        m=build(env,case);can=from_model(m);rows=[r for r in payload if r['case']==case]
        known=[(np.array(r['source_x']),r['record']['recourse_optimum']) for r in rows if r['record']['type']=='optimality']
        cuts=[dict(record=r['record'],coefficients=np.array(r['coefficients']),multipliers=np.array(r['multipliers']),source_x=np.array(r['source_x'])) for r in rows]
        for cut in cuts:verify(can,cut,known)
        physical=[c for c in cuts if c['record']['type']=='feasibility' and
            np.max(can.B[can.discrete_rows]@c['source_x']-can.b[can.discrete_rows],initial=0)<=1e-7]
        assert physical
        candidate=next((c for c in physical if c['record']['bound_row_contribution']!='0'),physical[0])
        for mutation in ['ray_sign','bound_term','B_coefficient','RHS']:
            bad=copy.deepcopy(candidate);known_excluded=False
            if mutation=='ray_sign':bad['multipliers']=-bad['multipliers']
            elif mutation=='bound_term':bad['record']['bound_row_contribution']='999'
            elif mutation=='B_coefficient':
                if known:
                    point,_=known[0];j=int(np.flatnonzero(point)[0])
                    old=bad['record']['intercept']+bad['coefficients']@point
                    bad['coefficients'][j]-=old+1.;known_excluded=bad['record']['intercept']+bad['coefficients']@point<0
                else:bad['coefficients'][0]-=1.
            else:
                shift=1.+max([bad['record']['intercept']+bad['coefficients']@p for p,_ in known]+[0.])
                bad['record']['intercept']-=shift
                known_excluded=bool(known and bad['record']['intercept']+bad['coefficients']@known[0][0]<0)
            rejected=False;reason=None
            try:verify(can,bad,known)
            except Uncertifiable as e:rejected=True;reason=str(e)
            assert rejected
            adversarial.append(dict(case=case,mutation=mutation,rejected=rejected,reason=reason,
                source_discrete_legal=True,source_cut_type='physical_recourse_infeasibility',
                nonzero_bound_contribution=candidate['record']['bound_row_contribution']!='0',
                perturbed_cut_excludes_known_feasible=known_excluded))
        audits.append(dict(case=case,certificates=len(cuts),feasible_assignments=len(known),
            physical_infeasible_sources=len(physical),all_certificates_PASS=True,independent_implementation=True))
        m.dispose()
    env.dispose()
    table('INDEPENDENT_ADVERSARIAL_CUT_VALIDATION.csv',adversarial,['case','mutation','rejected','reason',
        'source_discrete_legal','source_cut_type','nonzero_bound_contribution','perturbed_cut_excludes_known_feasible'])
    dump('INDEPENDENT_CUT_REPLAY_AUDIT.json',dict(PASS=True,certificates=len(payload),cases=audits,
        independent_implementation=True,COO_rational_products=True,global_affine_domination=True,
        additional_stronger_perturbation_rejections=len(adversarial),optimize_calls=0))
    print('INDEPENDENT REPLAY PASS',len(payload),'certificates',len(adversarial),'physical perturbations',flush=True)

if __name__=='__main__':run()
