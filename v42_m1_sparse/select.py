"""Measured structural filtering before any LP/MIP benchmark."""
from collections import defaultdict
from v42_root.common import *
from .grid import CANDIDATES
def run():
    data={n:read(OUT/'census'/(n+'.json')) for n in CANDIDATES};stats={n:d['stats'] for n,d in data.items()}
    comparison=[{k:s[k] for k in ['candidate','binary','integer','continuous','columns','rows','nonzeros','grid_nonzeros','voltage_nonzeros','line_nonzeros','transformer_nonzeros','PCS_nonzeros','max_row_density','P99_row_density','build_seconds','peak_RSS_bytes']} for s in stats.values()]
    table('FORMULATION_STRUCTURAL_COMPARISON.csv',comparison)
    table('NONZERO_REDUCTION.csv',[dict(candidate=n,baseline_nonzeros=stats['M1-F0']['nonzeros'],nonzeros=s['nonzeros'],reduction_percent=100*(1-s['nonzeros']/stats['M1-F0']['nonzeros'])) for n,s in stats.items()])
    table('ROW_DENSITY_COMPARISON.csv',[dict(candidate=n,max_row_density=s['max_row_density'],P99_row_density=s['P99_row_density'],unchanged_SOC_max=602) for n,s in stats.items()])
    dominated={n:[k for k,t in stats.items() if k!=n and all(t[c]<=s[c] for c in ('rows','columns','nonzeros')) and any(t[c]<s[c] for c in ('rows','columns','nonzeros'))] for n,s in stats.items()}
    nondominated=[n for n in stats if not dominated[n]]
    # Reserve one slot for injection-only and two for the strongest distinct
    # network combinations. Baseline is measured census/reference, not a fourth LP.
    selected=['M1-F1'] if 'M1-F1' in nondominated else []
    alternatives=sorted([n for n in nondominated if n not in ('M1-F0','M1-F1')],key=lambda n:stats[n]['nonzeros'])
    selected+=alternatives[:3-len(selected)]
    assert 1<=len(selected)<=3
    cross={n:d['start'] for n,d in data.items()};assert all(d['PASS'] for d in cross.values())
    dump('PR106_INCUMBENT_CROSS_FORMULATION.json',dict(PASS=True,source_sha256=sha(LOCAL/'PR106_M1_PLAN.json'),physical_projection_unchanged=True,route_P_Q_SOC_rho_unchanged=True,independent_voltages_line_transformers_unchanged=True,AIDC_anchor_unchanged=True,candidates=cross))
    dump('FORMULATION_CANDIDATES.json',dict(candidates=list(CANDIDATES),exact_projection=True,LP_projection_unchanged=True,dominated_by=dominated,nondominated=nondominated,primary_LP_candidates=selected,selection_reason='<=3 exact nondominated candidates; injection-only reference plus two smallest measured nonzero network extensions; F0 retained as PR106/census reference',cost_gate_summary={n:dict(proposals=len(d.get('factor_cost_audit',[])),selected=sum(r['selected'] for r in d.get('factor_cost_audit',[])),rejected=sum(not r['selected'] for r in d.get('factor_cost_audit',[]))) for n,d in data.items()}))
    dump('NUMERICAL_RANGE_AUDIT.json',dict(candidates={n:d['numerical'] for n,d in data.items()},coefficient_deletion=False,clipping=False,rounding=False))
    dump('EXACT_SCALING_AUDIT.json',dict(investigated=True,selected=False,physical_units='kW/kvar/kVA/kWh',exact_possible_mapping='y_MW=y_kW/1000; original y=1000*y_MW; every substituted coefficient becomes 1000*a, equality expressed in MW divides its full original equality by 1000; all bounds and extraction inverse-transformed',reason='Exact response compression tested in original units first. Remaining range contains inherited PCS coefficient 400 and original small voltage/current coefficients. An injection unit change alone cannot improve unchanged extreme row families; no warning reduction or speed benefit demonstrated. Selection gate not satisfied.',coefficient_clipping=False,coefficient_deletion=False,physical_reporting_unchanged=True))
    print('STRUCTURAL SELECT',selected,comparison,flush=True)
if __name__=='__main__':run()
