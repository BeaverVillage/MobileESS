"""Post-Native original signed thermal-row changes; no solver and no FULL CSR.

Only FULL-PASS best points are read. This is operating-plan interpretation,
never a new LB engine or a repair of rejected points.
"""
from __future__ import annotations
import argparse
from fractions import Fraction as F
import json
from pathlib import Path
from time import perf_counter
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
DOCS=ROOT/'docs/v42_b2_u4_primal_alns_600x3'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--final',action='store_true')
    args=parser.parse_args()
    if not args.final:raise ValueError('POST_NATIVE_COMPLETE_ONLY')
    from tools.u4_primal_alns import verify as v
    from tools.u4_primal_alns.current_grid import refresh
    started=perf_counter();comp=v.read(DOCS/'COMPARISON.json')
    v.require(comp['total_wall_seconds'] is not None and set(comp['methods'])=={'N1','N2','N3'}
        and all(a['stopped_reason'] is not None for a in comp['methods'].values()),'ALL_NATIVE_ALGORITHMS_COMPLETE')
    plans=v.read(DOCS/'ORIGINAL_SOURCE_OPERATING_PLAN_COMPARISON.json')
    v.require(plans['PASS'],'VERIFIED_OPERATING_PLANS_REQUIRED')
    case=v.load_case(native=False)
    initial=v.read(DOCS/'SIGNED_SELECTION_CONTEXT.json')
    original_points={};candidates={}
    for label,plan in plans['candidates'].items():
        v.require(plan['PASS'] and v.file_sha(plan['point_path'])==plan['point_file_sha256'], 'BEST_POINT_SHA')
        x=v.load_point(plan['point_path']);v.require(v.vector_sha(x)==plan['point_vector_sha256'],'BEST_VECTOR_SHA')
        original_points[label]=case.lift(x)
        context,receipt=refresh(case,x)
        thermal=context['current_U4_grid_scan']['line_thermal_face']['highest_normalized_values'][0]
        candidates[label]=dict(point_vector_sha256=v.vector_sha(x),verified_UB=plan['verified_UB'],
            current_all_grid_receipt=receipt,maximum_thermal_facet_loading_numerical=thermal['rho_scaled_loading'],
            critical_row=thermal['original_row'],critical_name=thermal['name'],critical_metadata=thermal['metadata'],
            all_original_security_rows_scanned=814560,Native_optimize_calls=0)
    rows=[]
    for packet in initial['critical_exact_rows']:
        if packet['family']!='line_thermal_face':continue
        weights={int(j):F(w) for j,w in packet['coeff'].items()}
        rho=int(initial['original_rho_column']);a=-weights.get(rho,F(0))
        v.require(a>0,'DIRECT_RHO_THERMAL_REQUIREMENT')
        fixed=-F(packet['rhs'])/a
        evaluations={}
        for label,point in original_points.items():
            per_unit={u:{f:F(0) for f in ('Pch','Pdis','Q')} for u in case.graph[1]}
            value=fixed
            for j,w in weights.items():
                if j==rho:continue
                name=str(case.original_d['names'][j]);family,body=name.split('[',1);unit=body.split(',',1)[0]
                v.require(family in ('Pch','Pdis','Q') and unit in per_unit,'THERMAL_NONPHYSICAL_LEAF')
                term=w*F(float(point[j]))/a;value+=term;per_unit[unit][family]+=term
            evaluations[label]=dict(facet_loading_exact=str(value),facet_loading=float(value),
                per_unit_exact={u:{f:str(z) for f,z in terms.items()} for u,terms in per_unit.items()},
                per_unit={u:{f:float(z) for f,z in terms.items()} for u,terms in per_unit.items()})
        rows.append(dict(original_row=packet['original_row'],name=packet['name'],slot=packet['slot'],
            metadata=packet['metadata'],fixed_forecast_correction_term_exact=str(fixed),
            source_row_sha256=packet['source_row_sha256'],evaluations=evaluations,
            Global_LB=False,Actual='ACTUAL_NOT_RUN'))
    output=dict(PASS=True,source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,candidates=candidates,
        identical_original_U4_thermal_rows=rows,comparison_file_sha256=v.file_sha(DOCS/'COMPARISON.json'),
        operating_plan_comparison_sha256=v.file_sha(DOCS/'ORIGINAL_SOURCE_OPERATING_PLAN_COMPARISON.json'),
        frozen_original_context_sha256=v.file_sha(DOCS/'SIGNED_SELECTION_CONTEXT.json'),
        Native_optimize_calls=0,FULL_CSR_constructed=False,source_model_constructed=False,
        exact_projected_row_values_from_stored_binary64=True,
        all_grid_maximum_is_numerical_scan_not_new_UB_or_LB_certificate=True,
        rejected_points_not_read_or_repaired=True,Actual='ACTUAL_NOT_RUN',wall_seconds=perf_counter()-started)
    v.write(DOCS/'ORIGINAL_CRITICAL_GRID_POINT_COMPARISON.json',output)
    print(json.dumps(dict(PASS=True,wall_seconds=output['wall_seconds'],candidates=list(candidates),
        Native_optimize_calls=0,FULL_CSR_constructed=False)))


if __name__=='__main__':main()
