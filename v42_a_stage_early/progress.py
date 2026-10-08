"""Separate prior-point inclusion witness for numerical Phi increases.

This post-canary correction never changes a solver point or a tolerance.
Three low-progress re-solves still trigger the fixed stagnation rule.
"""
from fractions import Fraction
import numpy as np
from v42_a_stage_phase1.backend import evaluate
from v42_a_stage_phase1.core import primal_replay,phase_objective

def capture(original,descriptor,master,raw):
    return dict(original_columns=original.matrix.shape[1],descriptor=descriptor,
        raw_X=raw['X'],Phi=phase_objective(master,raw['X']),
        weights=master.weights,signs=master.artificial_signs,
        source_original_snapshot_sha256=original.fingerprint())

def inclusion_witness(previous,original,descriptor,master,global_variables):
    if tuple(previous['weights'])!=tuple(master.weights) or tuple(previous['signs'])!=tuple(master.artificial_signs):
        raise ValueError('PRIOR_WITNESS_FROZEN_ARTIFICIAL_WEIGHT_OR_SIGN_DRIFT')
    lookup={}
    for unit in previous['descriptor']['units']:
        for family,items in unit['v'].items():
            for key,e in items.items():lookup[unit['id'],family,key]=evaluate(e,previous['raw_X'])
    point=np.zeros(original.matrix.shape[1]);point[:global_variables]=previous['raw_X'][:global_variables]
    assigned=set(range(global_variables))
    for unit in descriptor['units']:
        for family,items in unit['v'].items():
            for key,e in items.items():
                if e[0]=='v':point[e[1]]=lookup.get((unit['id'],family,key),0.);assigned.add(int(e[1]))
    for unit in descriptor['units']:
        for family,items in unit['v'].items():
            for key,e in items.items():
                if e[0]=='e' and len(e[2])==1 and int(e[2][0]) not in assigned:
                    point[e[2][0]]=(lookup.get((unit['id'],family,key),0.)-e[1])/e[3][0];assigned.add(int(e[2][0]))
    mapped=np.r_[point,previous['raw_X'][previous['original_columns']:]]
    replay=primal_replay(master.snapshot,mapped)
    phi=phase_objective(master,mapped)
    return dict(PASS=replay['PASS'] and phi==previous['Phi'],replay=replay,
        previous_Phi=str(previous['Phi']),mapped_Phi=str(phi),
        raw_solver_points_unchanged=True,separate_projection=True,
        inference='An increase in the new raw objective is not certified worsening when the previous raw point remains feasible at identical Phi.'),mapped


def artificial_free_inclusion(previous,previous_descriptor,previous_point,original,descriptor,global_variables):
    """P1 inclusion uses original rows; it never compares artificial objectives.

    The positive-Phi inclusion witness above retains its frozen-weight check.
    This path rejects an infeasible prior original point and replays the new
    original matrix, instead of creating an elastic model for an original P1.
    """
    if not primal_replay(previous,previous_point)['PASS']:
        raise ValueError('P1_PRIOR_ARTIFICIAL_FREE_POINT_INVALID')
    lookup={}
    for unit in previous_descriptor['units']:
        for family,items in unit['v'].items():
            for key,e in items.items():lookup[unit['id'],family,key]=evaluate(e,previous_point)
    target_keys={(unit['id'],family,key) for unit in descriptor['units'] for family,items in unit['v'].items() for key in items}
    if not set(lookup)<=target_keys:raise ValueError('P1_OLD_COLUMN_IDENTITIES_DELETED')
    point=np.zeros(original.matrix.shape[1]);point[:global_variables]=previous_point[:global_variables]
    assigned=set(range(global_variables))
    for unit in descriptor['units']:
        for family,items in unit['v'].items():
            for key,e in items.items():
                if e[0]=='v':point[e[1]]=lookup.get((unit['id'],family,key),0.);assigned.add(int(e[1]))
    for unit in descriptor['units']:
        for family,items in unit['v'].items():
            for key,e in items.items():
                if e[0]=='e' and len(e[2])==1 and int(e[2][0]) not in assigned:
                    point[e[2][0]]=(lookup.get((unit['id'],family,key),0.)-e[1])/e[3][0];assigned.add(int(e[2][0]))
    replay=primal_replay(original,point)
    def value(snapshot,x):
        o=snapshot.objective('rho')
        return Fraction(o.constant)+sum((v*Fraction(float(x[j])) for j,v in o.coefficients().items()),Fraction(0))
    unchanged=value(previous,previous_point)==value(original,point)
    return dict(PASS=replay['PASS'] and unchanged,original_replay=replay,
        original_P1_objective_exactly_preserved=unchanged,previous_P1_value=str(value(previous,previous_point)),
        mapped_P1_value=str(value(original,point)),raw_solver_point_unchanged=True,separate_projection=True,
        artificial_variables=0,artificial_weight_comparison_not_part_of_original_P1=True,
        all_old_descriptor_coordinates_preserved=True),point
