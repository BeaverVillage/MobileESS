from .common import *
from .certificate import enclosures,audit_solution,farkas
from .diagnose import run as diagnose
from .resources import gate
from v42_degen.identity import inputs,model,signature,digest
import numpy as np
import time
from datetime import datetime,timezone

FIELDS=['rank','MESS','slot','site','stay_name','column','y','priority_score','classification','solver_status',
        'objective','L_safe','certified_conditional_lower_bound','runtime','simplex_iterations',
        'wall_start_seconds','wall_end_seconds','certificate_PASS','reason','only_selected_bounds_changed','baseline_basis_restored']

def run():
    gate('conditional_before_setup')
    basis_receipt=read(OUT/'DISJ_BASELINE_BASIS_RECEIPT.json')
    assert basis_receipt['PASS'] and basis_receipt['usable_simplex_basis']
    A,d,B,e,identity,_=inputs()
    with np.load(OUT/'BASELINE_BASIS.npz') as z:base={k:z[k].copy() for k in z.files}
    with np.load(ROOT/'docs/v42_m1_exact_formulation_strengthening/BASELINE_ROOT_LP_SOLUTION.npz') as z:point=z['values'].copy()
    candidates=diagnose(B,e,point,base['Pi'])
    lo,hi=enclosures(B,e)
    m,receipt=model(B,e,identity)
    variables=m.getVars(); constraints=m.getConstrs()
    m.setAttr('VType',variables,['C']*len(variables));m.update()
    for key,value in dict(Threads=1,Method=1,LPWarmStart=1,FeasibilityTol=1e-8,OptimalityTol=1e-8,PreDual=0,Seed=20260929,InfUnbdInfo=1).items():setattr(m.Params,key,value)
    m.Params.LogFile='docs/v42_m1_location_grid_disjunctive_cuts/CONDITIONAL_STATE_LP.log'
    policy=read(OUT/'NUMERICAL_POLICY.json')
    write('CONDITIONAL_EXECUTION_POLICY.json',dict(preregistered_before_conditionals=True,InfUnbdInfo=1,
          purpose='Obtain Farkas evidence in the original model if infeasible; no parameter retries.',
          audit_reserve_seconds=60,
          audit_reserve_reason='Reserve fixed wall time for bound restoration, full original row checks and exact rational certificate. No state-count cap.',
          basis_SHA=sha(OUT/'BASELINE_BASIS.npz'),numerical_policy_SHA=sha(OUT/'NUMERICAL_POLICY.json')))
    once('CONDITIONAL_SEPARATION')
    start=time.perf_counter();started_utc=datetime.now(timezone.utc).isoformat()
    results=[];certs=[];infeasible=[];stop='CANDIDATES_EXHAUSTED'
    try:
        for candidate in candidates:
            elapsed=time.perf_counter()-start; remaining=1800-elapsed
            if remaining<=60:
                stop='WALL_BUDGET_AUDIT_RESERVE';break
            j=candidate['column'];v=variables[j]
            result={k:candidate[k] for k in FIELDS if k in candidate}
            result.update(classification='UNRESOLVED',solver_status=None,objective=None,L_safe=None,
                 certified_conditional_lower_bound=None,runtime=None,simplex_iterations=None,wall_start_seconds=elapsed,
                 wall_end_seconds=None,certificate_PASS=False,reason='',only_selected_bounds_changed=False,baseline_basis_restored=False)
            cert=None
            try:
                # Original optimal basis -> exactly ONE selected bound change.
                m.setAttr('VBasis',variables,base['VBasis'].tolist());m.setAttr('CBasis',constraints,base['CBasis'].tolist())
                m.update();v.LB=1.;v.UB=1.;m.update()
                lower=np.array(m.getAttr('LB'));upper=np.array(m.getAttr('UB'))
                changed=np.flatnonzero((lower!=d['lower'])|(upper!=d['upper']))
                assert changed.tolist()==[j] and lower[j]==upper[j]==1.
                result['only_selected_bounds_changed']=True
                # A valid dual-feasible original basis becomes primal-infeasible
                # under this sole bound change; dual simplex repairs it.
                m.Params.TimeLimit=max(.001,1800-(time.perf_counter()-start)-60)
                m.optimize()
                result.update(solver_status=int(m.Status),runtime=float(m.Runtime),simplex_iterations=float(m.IterCount))
                if m.Status==2:
                    result['objective']=float(m.ObjVal)
                    cert=audit_solution(A,d,B,e,np.array(m.getAttr('X')),np.array(m.getAttr('Pi')),np.array(m.getAttr('RC')),
                        np.array(m.getAttr('VBasis')),np.array(m.getAttr('CBasis')),lo,hi,j,float(m.ObjVal),float(m.Kappa),
                        f"DUAL_STATE_{candidate['rank']:05d}.npz")
                    cert.update(rank=candidate['rank'],MESS=candidate['MESS'],slot=candidate['slot'],site=candidate['site'])
                    certs.append(cert)
                    if cert['PASS']:
                        result.update(classification='OPTIMAL',L_safe=cert['L_safe'],
                                      certified_conditional_lower_bound=cert['certified_conditional_lower_bound'],certificate_PASS=True)
                    else:result['reason']='OPTIMAL_STATUS_NUMERICAL_CERTIFICATE_FAILED'
                elif m.Status==3:
                    cert=farkas(B,e,m,lo,hi,j,f"FARKAS_STATE_{candidate['rank']:05d}.npz")
                    cert.update(rank=candidate['rank'],MESS=candidate['MESS'],slot=candidate['slot'],site=candidate['site'],column=j,stay_name=candidate['stay_name'])
                    infeasible.append(cert)
                    if cert['PASS']:result.update(classification='INFEASIBLE',certificate_PASS=True)
                    else:result['reason']='INFEASIBLE_STATUS_WITHOUT_CLOSED_RATIONAL_PROOF'
                else:result['reason']='NON_OPTIMAL_NO_RETRY'
            except Exception as error:
                result['reason']=type(error).__name__+': '+str(error)
            finally:
                v.LB=float(d['lower'][j]);v.UB=float(d['upper'][j]);m.update()
                m.setAttr('VBasis',variables,base['VBasis'].tolist());m.setAttr('CBasis',constraints,base['CBasis'].tolist());m.update()
                assert v.LB==d['lower'][j] and v.UB==d['upper'][j]
                assert np.array_equal(m.getAttr('VBasis'),base['VBasis']) and np.array_equal(m.getAttr('CBasis'),base['CBasis'])
                result['baseline_basis_restored']=True
            result['wall_end_seconds']=time.perf_counter()-start
            results.append(result)
            table('CONDITIONAL_STATE_LP_RESULTS.csv',results,FIELDS)
            write('CONDITIONAL_LB_CERTIFICATE.json',dict(policy_SHA=sha(OUT/'NUMERICAL_POLICY.json'),
                  exact_checker_source_SHA=sha(ROOT/'v42_disjunctive/certificate.py'),
                  safe_coefficients_from_raw_objective=False,certificates=certs))
            write('CONDITIONAL_INFEASIBLE_STATE_PROOF.json',dict(proofs=infeasible,
                  proven_fixings=[c for c in infeasible if c['PASS']],unproven_fixings_added=0))
            print('STATE',result,flush=True)
            if result['wall_end_seconds']>=1800:
                stop='WALL_BUDGET_EXHAUSTED';break
        elapsed=time.perf_counter()-start
        counts={c:sum(r['classification']==c for r in results) for c in ('OPTIMAL','INFEASIBLE','UNRESOLVED')}
        write('CONDITIONAL_STATE_LP_RESOURCE_RECEIPT.json',dict(start_UTC=started_utc,end_UTC=datetime.now(timezone.utc).isoformat(),
              budget_seconds=1800,total_separation_wall_seconds=elapsed,wall_budget_PASS=elapsed<=1800,
              candidate_states=len(candidates),actual_conditional_LP_calls=len(results),classifications=counts,
              unattempted_candidate_states=len(candidates)-len(results),unattempted_is_not_UNRESOLVED=True,stop_reason=stop,
              MAX_HEAVY_WORKERS=1,Threads=1,Method=1,LPWarmStart=1,environment=ENV,
              model_instances=1,baseline_basis_loaded_per_state=True,all_bounds_and_basis_restored=True,
              cold_conditional_barrier_calls=0,retry_calls=0,other_solver_calls=0,pytest_during_heavy=0,
              original_matrix_identity=receipt['reference'],baseline_primal_feasibility_receipt_SHA=sha(OUT/'DISJ_BASELINE_BASIS_RECEIPT.json')))
        # Post-loop identity is outside the separation budget, has no optimize.
        from v42_integrated.matrix import arrays
        C,f=arrays(m);f['types']=d['types']
        assert signature(C,f)==signature(B,e)
        write('CONDITIONAL_POST_LOOP_IDENTITY.json',dict(PASS=True,rows=m.NumConstrs,columns=m.NumVars,nnz=m.NumNZs,
              original_matrix_RHS_objective_names_bounds_unchanged=True,all_integer_types_relaxed_only=True,
              baseline_basis_restored=True,optimize_calls=len(results)))
    finally:m.dispose()

if __name__=='__main__':run()
