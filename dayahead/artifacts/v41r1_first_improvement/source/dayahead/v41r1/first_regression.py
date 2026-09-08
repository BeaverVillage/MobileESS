"""Full original May-04 model regression of first-improvement discovery."""
import numpy as np
import gurobipy as gp
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from dayahead.v40g.domain import audit
from dayahead.v40a.grid import controls_from_trajectory,evaluate_grid
from .flex_model import Data,ProbeModel
from .flex_diagnostic import OUT as DIAG
from .first_replay import OUT
from .bounded_solver import BoundedLex,PolicyBudget
from .feasible_seed import job_audit

def run(attempt='r3'):
    d=Data();results={}
    try:
        oracle=read(OUT/'KNOWN_B1_P2_IMPROVING_COUNTEREXAMPLE.json')
        pair=read(DIAG/'PAIR_ORIGINAL_MODEL_WITNESS.json')
        write_json(OUT/'KNOWN_B1_P1_COUPLED_COUNTEREXAMPLE.json',dict(status='PASS',
            witness=pair,evidence=record(DIAG/'PAIR_ORIGINAL_MODEL_WITNESS.json'),
            warning='Original UID-serial WAN permits 23-hour checkpoint waiting and post-horizon service shift.'))
        for label,groups,priority,seconds in [('KNOWN_P2',[oracle['group']],1,75),
            ('KNOWN_P1_PAIR',sorted(d.uidgroup[u] for u in pair['choices']),0,90)]:
            p=ProbeModel(d)
            try:
                p.reset(groups)
                if priority==1:p.m.addConstr(1000*p.rho<=1000*d.base[0],name='PRIMARY_EXACT_VALUE_LOCK')
                exprs=[p.rho,gp.quicksum(p.xi)/81];p.m.setObjective(exprs[priority]);p.m.update()
                folder=OUT/(label+'_'+attempt)
                if folder.exists():raise RuntimeError('PRESERVE_FULL_MODEL_REGRESSION_ATTEMPT')
                def validate():
                    chosen=p.decode(engine.values);q,why=d.quick(chosen)
                    if q is None:return dict(status='FAIL',reason=why)
                    rows=d.rows(chosen);state=audit(d.refs,rows,d.ctx.capacity,d.ctx.wan)
                    physical,power=job_audit(rows,d.ctx)
                    grid=evaluate_grid(d.ctx.coefficients,controls_from_trajectory(d.ctx.coefficients,power['pcc'],()),d.ctx.nodes)
                    return dict(status='PASS' if state['status']==physical['status']==grid['status']=='PASS' else 'FAIL',
                        service=state,physical=physical,grid=grid,materialized_jobs=rows,materialized_power=power,
                        independent_objective_vector=[grid['rho_max'],q['vector'][1]],
                        canonical_auxiliary_values={'rho_max':grid['rho_max'],**{f'V41_H4_shortfall_GPUh[{k}]':v for k,v in enumerate(q['reserve']['xi_GPUh'])}})
                engine=BoundedLex(p.m,p.seed,folder,PolicyBudget(seconds),allocation=[1],
                    objective_expressions=exprs,validator=validate,
                    metadata={g:dict(members=d.cohorts[g]['members'],candidate_count=len(d.opts[d.cohorts[g]['members'][0]])) for g in groups})
                # Exact requested neighborhood; everything outside was bound
                # to the preserved B0 incumbent before engine construction.
                engine.decision_groups={g:p.groups[g] for g in groups};engine.visits={g:0 for g in groups};engine.stage_counts=dict(engine.visits)
                # Full-size fixture startup must not inherit subsecond slices
                # from the deliberately shortened regression-day budget.
                engine.minimum_solve_seconds=20.
                p.m.Params.LogFile=str(folder/'SOLVER.log')
                report=engine.optimize('P'+str(priority+1));chosen=p.decode(engine.values)
                cert,_=p.certify(chosen,label+'_FIRST_IMPROVEMENT_WITNESS_'+attempt)
                assert cert['status']=='PASS' and cert['vector'][priority]<d.base[priority]-1e-9
                if priority==1:assert cert['vector'][0]<=d.base[0]+1e-10
                assert engine.accepted_improvements
                results[label]=dict(status='PASS',opened_groups=groups,oracle_warmstart_used=False,baseline=d.base,
                    result=cert['vector'],witness=record(DIAG/(label+'_FIRST_IMPROVEMENT_WITNESS_'+attempt+'.json')),
                    production_engine_report=record(folder/'BOUNDED_SOLVER_REPORT.json'),accepted=engine.accepted_improvements,
                    original_full_model_verified=True,complete_destinations=True)
                write_json(OUT/(label+'_REGRESSION_'+attempt+'.json'),results[label])
                write_json(OUT/(label+'_REGRESSION.json'),results[label])
                print('FIRST_IMPROVEMENT_REGRESSION_PASS',label,cert['vector'],flush=True)
            finally:p.close()
        write_json(OUT/'FULL_MODEL_REGRESSIONS.json',dict(status='PASS',results=results))
    finally:d.close()

if __name__=='__main__':run()
