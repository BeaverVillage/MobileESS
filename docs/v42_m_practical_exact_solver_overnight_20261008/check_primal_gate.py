"""Read-only M4 progress/stagnation gate; never solves and never changes bounds."""
from practical_support import *
from fractions import Fraction as F

def run():
    state=read(OUT/'external_production/OPEN_CHECKPOINT.json')['state'];nodes=state['nodes'];rows=state['ledger']
    floor=F.from_float(.5687116104049206);ub=F(state['UB']);open_nodes=[n for n in nodes.values() if n['state']=='OPEN'];lb=min((F(n['LB']) for n in open_nodes),default=ub)
    new=[r for r in rows if r['node_id']>0 and r['LP_status']=='OPTIMAL']
    uplift=[r['node_id'] for r in new if F(r['effective_LB'])>F(nodes[str(r['node_id'])]['inherited_LB'])]
    fathomed=[r['node_id'] for r in rows if r['state']=='FATHOMED']
    native=[read(p) for p in (OUT/'runs').glob('*/RESULT.json')];primals=[r for r in native if r['kind']=='primal']
    last=datetime.fromisoformat(read(OUT/'IMMUTABLE_DEADLINE.json')['task_start_UTC'])
    for p in (OUT/'runs').glob('*/RESULT.json'):
        r=read(p)
        if r['UB_improvement']>0:last=max(last,datetime.fromisoformat(r['UTC']))
    prior=F.from_float(INITIAL_UB)
    for row in rows:
        value=F(row['UB_after'])
        if value<prior:
            # Missing old acceptance time fails conservatively for stagnation.
            accepted=datetime.fromisoformat(row['accepted_UTC']) if row.get('accepted_UTC') else datetime.now(timezone.utc)
            last=max(last,accepted);prior=value
    stagnation=(datetime.now(timezone.utc)-last).total_seconds();gap=float((ub-lb)/abs(ub))
    progress=len(new)>=2 and bool(uplift or fathomed)
    eligible=gap>.005 and progress and stagnation>=3600 and len(primals)<2 and remaining(900)>=1200
    if len(primals)==1:eligible=eligible and primals[0]['UB_improvement']>=.001
    r=dict(UTC=stamp(),PASS=eligible,optimize_calls=0,gap=gap,LB=float(lb),UB=float(ub),fresh_OPTIMAL_child_certificates=len(new),effective_LB_uplift_nodes=uplift,exact_fathomed_nodes=fathomed,exact_LB_search_progress=progress,UB_stagnation_seconds=stagnation,completed_primal_interventions=len(primals),maximum_primal_interventions=2,first_radius=64,second_radius=96,second_requires_first_valid_UB_gain_at_least=.001,each_TimeLimit_at_most=600,local_bound_never_global=True,reason='Eligible only with actual stronger node bounds or exact fathoming, in addition to new certified LP nodes; tree width alone is insufficient.',remaining_before_publication_reserve=remaining(900))
    atomic(OUT/'PRIMAL_GATE.json',r);print(json.dumps(r))
if __name__=='__main__':run()
