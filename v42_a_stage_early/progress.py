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
