"""Preregistered formulation choice from completed clean LPs only."""
from v42_root.common import *
from .performance import source_freeze
from .config import PRIMARY

def main():
    source_freeze();freeze=read(OUT/'CANDIDATE_FREEZE.json');results=[read(OUT/(k+'_ROOT_LP.json')) for k in freeze['LP_candidates']]
    table('ROOT_LP_COMPARISON.csv',[dict(formulation=r['formulation'],optimal=r['optimal'],status=r['status'],presolve_seconds=r['presolve_seconds'],presolved_rows=(r['presolved'] or {}).get('rows'),presolved_columns=(r['presolved'] or {}).get('columns'),presolved_nonzeros=(r['presolved'] or {}).get('nonzeros'),LP_algorithm=r['LP_algorithm'],iterations=r['iterations'],barrier_iterations=r['barrier_iterations'],LP_wall_seconds=r['LP_wall_seconds'],P1_objective=r['LP_objective'],numerical_warnings='; '.join(r['numerical_warnings']),peak_RSS_bytes=r['peak_observed_RSS_bytes']) for r in results])
    eligible=[r for r in results if r['optimal']]
    if eligible:
        fastest=min(r['LP_wall_seconds'] for r in eligible);near=[r for r in eligible if r['LP_wall_seconds']<=fastest*1.05]
        bound=max(r['LP_objective'] for r in near);near=[r for r in near if r['LP_objective']>=bound-1e-7]
        def rank(r):
            p=r['presolved'] or {};numerical=read(OUT/(r['formulation']+'_NUMERICAL.json'))['matrix']
            ratio=numerical['maximum_abs']/numerical['minimum_abs']
            return (p.get('nonzeros',float('inf')),p.get('rows',float('inf'))+p.get('columns',float('inf')),len(r['numerical_warnings']),ratio,PRIMARY.index(r['formulation']))
        chosen=min(near,key=rank)['formulation'];reason='lowest completed LP wall; within 5% stronger bound, within 1e-7 fewer presolved nonzeros/rows+columns, numerical risk, simplicity'
    else:chosen='F2-BASE';reason='preregistered unchanged baseline fallback because no eligible LP completed; no compressed-speed claim'
    dump('FORMULATION_SELECTION.json',dict(selected=chosen,reason=reason,completed_clean_LP_candidates=[r['formulation'] for r in eligible],scientific_production_objective_used=False,frozen_before_production=True,selection_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),CANDIDATE_FREEZE_sha256=sha(OUT/'CANDIDATE_FREEZE.json')))
    table('ROOT_NODE_CANARY.csv',[dict(run=False,NodeLimit=1,reason='optional canary omitted under preregistration; no parameter tuning')])
    print('frozen production formulation',chosen,flush=True)
if __name__=='__main__':main()
