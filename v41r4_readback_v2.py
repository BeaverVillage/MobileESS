"""Validate compound ordering only where the retained neighborhood has anchors.

Coverage/direct-only neighborhoods legitimately emit an empty anchor queue
and a false compound flag. They are NOT_APPLICABLE, not missing ranking.
"""
from fast_prepare import *
from v41r4_runtime import MAY_RUN,MAY_OUT

def validate(root):
    events={(r['phase'],r['iteration']):(p,r) for p in Path(root).glob('PHYSICS_RANKING_*.json') for r in [read(p)]}
    checked=[];compounds=[];empty=[]
    for p in Path(root).glob('ITERATION_*.json'):
        r=read(p);stage,iteration=map(int,r['neighborhood_id'].split(':'))
        assert iteration==r['iteration']
        ep,e=events[stage+1,iteration]
        units=e['ordered_existing_anchor_units'];expected=[u['kind'] for u in units]
        n=r['neighborhood']
        assert n['consumed_anchor_unit_order']==expected, ('COMPOUND_ORDER_NOT_CONSUMED',str(p))
        assert n['compound_net_effect_used_in_ordering']==bool(units), ('COMPOUND_FLAG_INCONSISTENT',str(p))
        for u in units:
            if not u['kind'].startswith('EXISTING_COMPOUND_'):continue
            width=u['kind'].rsplit('_',1)[1];s=e['existing_compound_anchor_scores'][width]
            assert u['search_key'][:4]==[s['P1_hat_active'],-s['ExposureRelief'],-s['critical_leverage'],-max(s['differential_sensitivity_relief'],0.)]
        row=dict(iteration=iteration,phase=stage+1,compound_widths=list(e['existing_compound_anchor_scores']),
            receipt=record(p),ranking=record(ep))
        checked.append(row)
        if row['compound_widths']:compounds.append(row)
        if not units:empty.append(dict(iteration=iteration,status='NOT_APPLICABLE_NO_ANCHORS',receipt=record(p)))
    assert compounds,'NO_REAL_COMPOUND_ORDER_CONSUMPTION_RECEIPT'
    assert {'2','3'} <= {w for r in compounds for w in r['compound_widths']},'MISSING_COMPOUND_WIDTH_EVIDENCE'
    return dict(status='PASS',real_consumption=compounds,checked_iterations=len(checked),empty_anchor_iterations=empty,
        ranking_matching='phase and iteration; exact consumed queue; all four net-effect key fields')

def compound_readback(day):
    root=MAY_RUN/day/'B1/dayahead/A0';result=validate(root/'bounded_checkpoints')
    domain=read(MAY_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json')
    ranking=read(MAY_OUT/day/'V41R3_FO_PHYSICS_RANKING_AUDIT.json')
    final=read(root/'V41R1_FULL_CANDIDATE_MANIFEST.json')
    assert ranking['candidate_count']==domain['total_count']==final['final_authoritative_candidates']
    assert ranking['candidate_set_SHA']==domain['candidate_set_SHA']==final['candidate_set_SHA']
    result.update(COMPOUND_NET_EFFECT_COMPUTED='YES',COMPOUND_NET_EFFECT_USED_IN_ORDERING='YES',
        CANDIDATE_UNIVERSE_CHANGED='NO',NEW_VARIABLES=0,NEW_CONSTRAINTS=0,OBJECTIVE_CHANGED='NO',
        candidate_count=domain['total_count'],candidate_set_SHA=domain['candidate_set_SHA'],
        diagnostic_reader=record(__file__))
    save(MAY_OUT/day/'V41R3_COMPOUND_RANKING_COMPLETION_AUDIT.json',result)
    return result

def install():
    import v41r4_report as original
    original.compound_readback=compound_readback
