"""Structural Pareto census, then post-rollback immutable performance freeze."""
import argparse
from .config import PRIMARY
from .performance import performance_gate
from v42_root.common import *

def census():
    rows=[]
    for k in PRIMARY:
        d=read(OUT/('BASELINE_STRUCTURAL.json' if k=='F2-BASE' else k+'_STRUCTURAL.json'))
        f=d['family_nonzeros'];rows.append(dict(formulation=k,eligible=True,binaries=d['binaries'],general_integers=d['integers'],continuous=d['continuous'],columns=d['columns'],rows=d['rows'],nonzeros=d['nonzeros'],Runtime_nonzeros=f.get('Runtime_completion_risk',0),Runtime_definition_nonzeros=f.get('Runtime_count_definition',0),tie_nonzeros=f.get('tie',0),GPU_nonzeros=f.get('resource_GPU',0),WAN_nonzeros=f.get('resource_WAN',0),grid_nonzeros=f.get('native_grid',0),CC4_nonzeros=f.get('CC4',0),max_row_density=d['max_row_density'],p99_row_density=d['p99_row_density'],model_build_seconds=d.get('model_build_seconds',d.get('build',{}).get('model_build_seconds')),peak_RSS_bytes=d.get('peak_RSS_bytes',d.get('build',{}).get('peak_observed_RSS_bytes')),timing_is_clean_benchmark=False))
    table('FORMULATION_STRUCTURAL_COMPARISON.csv',rows)
    axes=['columns','rows','nonzeros'];pareto=[];dominated={}
    for d in rows:
        by=[x['formulation'] for x in rows if x is not d and all(x[a]<=d[a] for a in axes) and any(x[a]<d[a] for a in axes)]
        if by:dominated[d['formulation']]=by
        else:pareto.append(d['formulation'])
    dump('PARETO_CANDIDATES.json',dict(axes=axes,Pareto=pareto,dominated=dominated,eligible=PRIMARY,stronger_relaxation_exception='hybrid staying histograms preserve integer physical paths and can strengthen the relaxation; candidates are not discarded merely for different bounds',maximum_primary_target=3,candidate_set_frozen=False))
    return pareto

def main():
    p=argparse.ArgumentParser();p.add_argument('--performance-freeze',action='store_true');args=p.parse_args();pareto=census()
    if not args.performance_freeze:return
    gate=performance_gate()
    if len(pareto)>3:raise ValueError('PARETO_REQUIRES_REVIEW_BEFORE_DIAGNOSTICS:'+str(pareto))
    exact=read(OUT/'FORMULATION_EXACTNESS.json');native=read(OUT/'NATIVE_REAL_EQUIVALENCE.json')
    if not exact['PASS'] or not native['PASS']:raise ValueError('EXACTNESS_NOT_PASS')
    sources=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=sha(p)) for folder in ['v42_root','v42_sparse','tests'] for p in sorted((ROOT/folder).glob('*.py'))]
    dump('SOURCE_MANIFEST.json',dict(sources=sources,preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),scientific_base=BASE,WIP='a88879fdb4e6c51dae35656feee90f68ed19ad8f',canonical='WINDOWS'))
    dump('CANDIDATE_FREEZE.json',dict(PASS=True,LP_candidates=pareto,eligibility='all bounded complete sets, six objectives and independent native certificate PASS',performance_gate=gate,freeze_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),structural_selection_only=True,production_outcome_used=False,source_manifest_sha256=sha(OUT/'SOURCE_MANIFEST.json')))
    d=read(OUT/'PARETO_CANDIDATES.json');d['candidate_set_frozen']=True;dump('PARETO_CANDIDATES.json',d)
if __name__=='__main__':main()
