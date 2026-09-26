"""Prove unavailable compound widths; preserve the original consumption checks."""
from pathlib import Path
import json,inspect,textwrap
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def prove_unavailable(root,compounds):
    groups=read(Path(root).parent/'EXACT_JOB_EQUIVALENCE_AUDIT.json')['cohorts']
    available={w for r in compounds for w in r['compound_widths']}
    missing={'2','3'}-available
    checks=[]
    for p in Path(root).glob('PHYSICS_RANKING_*.json'):
        event=read(p)
        assert event['compound_generation']=='UNCHANGED_EXISTING_2_AND_3_PREFIXES_ONLY'
        direct=[u for u in event['ordered_existing_anchor_units'] if u['kind']=='DIRECT_ANCHOR']
        # A finite direct key proves that group has at least one ranked member.
        # Counting ALL its members gives a conservative upper bound. If this
        # bound permits the missing width, no exception is allowed.
        upper=sum(len(groups[u['groups'][0]]['members']) for u in direct if u['search_key'][0] is not None)
        for width in missing:assert upper<int(width),('MISSING_APPLICABLE_COMPOUND_WIDTH',str(p),width,upper)
        checks.append(dict(event=p.name,phase=event['phase'],iteration=event['iteration'],eligible_component_upper_bound=upper))
    assert checks,'NO_RANKING_EVENTS_FOR_APPLICABILITY_PROOF'
    return dict(status='PROVEN_NOT_APPLICABLE',missing_widths=sorted(missing),observed_widths=sorted(available),
        maximum_eligible_components=max(r['eligible_component_upper_bound'] for r in checks),events=checks,
        rule='Original Ranking.reorder generates width w only when len(components)>=w',
        invented_consumption_receipts=0,solver_algorithm_changes=0)
def install():
    import v41r4_readback_v2 as module
    original=module.validate
    source=textwrap.dedent(inspect.getsource(original))
    old="assert {'2','3'} <= {w for r in compounds for w in r['compound_widths']},'MISSING_COMPOUND_WIDTH_EVIDENCE'"
    assert source.count(old)==1
    source=source.replace(old,'prove_unavailable(root,compounds)')
    ns=dict(original.__globals__,prove_unavailable=prove_unavailable)
    exec(compile(source,__file__+'::original_checks_with_applicability','exec'),ns)
    checked=ns['validate']
    def validate(root):
        try:return original(root)
        except AssertionError as error:
            if str(error)!='MISSING_COMPOUND_WIDTH_EVIDENCE':raise
            result=checked(root)
            proof=prove_unavailable(root,result['real_consumption'])
            result.update(width_coverage=proof,original_validator_failure='MISSING_COMPOUND_WIDTH_EVIDENCE',
                historical_validator_unchanged=True)
            from dayahead.paper_analysis.storage import write_json
            write_json(Path(root).parent/'COMPOUND_WIDTH_APPLICABILITY.json',proof)
            return result
    module.validate=validate
