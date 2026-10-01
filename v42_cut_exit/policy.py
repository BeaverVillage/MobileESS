"""Preregistered selection and authorization, with no optimizer calls."""
BASE_LB=.5718494710510547
BASE_GAP=.1460022544050313
def rank(r):
    p=r['passes'][0];t=p['telemetry'];first=t.get('first_non_root_node_seconds')
    return (not p['quality_PASS'],-(p['bound'] if p['bound'] is not None else -float('inf')),p['relative_gap'] if p['relative_gap'] is not None else float('inf'),first if first is not None else float('inf'),-p['nodes'],p.get('work',float('inf')),p['solve_wall_seconds'])
def meaningful(r):
    p=r['passes'][0];t=p['telemetry'];first=t.get('first_non_root_node_seconds');s=t['checkpoints']['600']
    a=first is not None and first<=450
    # The final receipt of the bounded 600s solve is authoritative for the
    # canary outcome; checkpoint observations retain their separate age.
    capped=p['status']==9 and 600<=p['solve_wall_seconds']<=605
    bound=p['bound'] if capped else s.get('bound')
    relative=p['relative_gap'] if capped else s.get('relative_gap')
    b=bound is not None and bound-BASE_LB>=1e-4
    c=relative is not None and BASE_GAP-relative>=.001
    # Early completed optimum is a stronger certificate than a 600s run.
    if p['quality_PASS']:b=b or (p['bound'] is not None and p['bound']-BASE_LB>=1e-4);c=True
    return dict(PASS=a or b or c,A_first_non_root_by_450=a,B_bound_gain_at_600=b,C_material_gap_reduction=c,material_gap_threshold=.001,final_600s_capped_receipt_used=capped)
def isolation_allowed(a,b):
    def stuck(r):
        p=r['passes'][0];f=p['telemetry'].get('first_non_root_node_seconds')
        return not p['quality_PASS'] and (f is None or f>450) and (f is None or f>=.8*p['solve_wall_seconds'])
    return stuck(a) and stuck(b)
def select(a,b):
    ranked=sorted([a,b],key=rank);best=ranked[0]
    gates={r['label']:meaningful(r) for r in [a,b]}
    return dict(selected=best['label'],CutPasses=best['settings']['CutPasses'],production_authorized=any(g['PASS'] for g in gates.values()),gates=gates,ranking=[r['label'] for r in ranked],frozen=True,H0_production_eligible=False)
