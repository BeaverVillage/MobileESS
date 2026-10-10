"""Stage-local saved-array admission; no campaign or scientific model rebuild."""
from pathlib import Path
from types import SimpleNamespace
from hashlib import sha256
import json
from fractions import Fraction as F
import subprocess
import numpy as np
from scipy import sparse
from v42_m1_hybrid.blocks import matrix_sha, build_blocks
from v42_may_campaign.m_model import _domain_sha
from v42_b2_seed_recovery_v18.certificate_box import verify
from v42_m1_research.check_lb import check_rational_dual_certificate
from v42_m1_research.check_ub import matrix_replay


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def file_sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def load(spec):
    """Require a separate fixed-decision identity for every B2/B3 stage."""
    if spec['stage'] not in ('B2_M', 'B3_M1', 'B3_M2'):
        raise ValueError('UNKNOWN_STAGE')
    root = Path(spec['arrays']).resolve()
    development = Path(__file__).resolve().parents[1]
    subprocess.run(['git','merge-base','--is-ancestor',spec['source_head'],'HEAD'],
                   cwd=development, check=True, capture_output=True)
    identity = read(root/'SCIENTIFIC_CASE_IDENTITY.json')
    for key in ('case_sha', 'selected_matrix_sha', 'selected_domain_sha'):
        if identity[key] != spec[key]:
            raise ValueError('STAGE_IDENTITY_DRIFT:'+key)
    if identity['day'] != spec['day'] or identity['arm'] != spec['stage'].split('_')[0]:
        raise ValueError('FIXED_STAGE_DAY_DRIFT')
    if not identity['input_identity']['PASS'] or not identity['transport']['integer_and_full_LP_domains_identical']:
        raise ValueError('SOURCE_OR_ORIGINAL_DOMAIN_NOT_PROVEN')
    # Source and complete fixed-input identity are required, never inherited from B2.
    if spec['fixed_input_sha'] != identity['input_identity']['input_SHA']:
        raise ValueError('FIXED_INPUT_IDENTITY_DRIFT')
    if spec['fixed_decision_sha'] != identity['anchor_sha']:
        raise ValueError('COMPLETE_FIXED_DECISION_IDENTITY_DRIFT')
    A = sparse.load_npz(root/'C3A_A.npz').tocsr()
    d = dict(np.load(root/'C3A_DATA.npz', allow_pickle=False))
    if matrix_sha(A) != spec['selected_matrix_sha'] or _domain_sha(d) != spec['selected_domain_sha']:
        raise ValueError('ORIGINAL_ARRAY_BYTE_DRIFT')
    if identity['slots'] != 96 or not np.isfinite(d['objective']).all() or not np.isfinite(d['constant']).all():
        raise ValueError('FULL96_OR_ORIGINAL_OBJECTIVE_DRIFT')
    # M2 may have a different linear objective: retain its entire original vector
    # and ObjCon, rather than silently replacing it by B2/M1's rho objective.
    for label in ('point', 'point_replay', 'seed_dual', 'seed_certificate', 'envelope'):
        if file_sha(spec[label]['path']) != spec[label]['sha256']:
            raise ValueError('FROZEN_FILE_DRIFT:'+label)
    replay = read(spec['point_replay']['path'])
    if not replay['PASS'] or replay['case_sha'] != spec['case_sha']:
        raise ValueError('ORIGINAL_BEST_UB_REPLAY_FAILURE')
    point = np.load(spec['point']['path'], allow_pickle=False)['point']
    if not matrix_replay(A, d, point)['PASS']:
        raise ValueError('CURRENT_FULL_ORIGINAL_UB_REPLAY_FAILURE')
    objective = F(float(d['constant']))+sum((F(float(d['objective'][j]))*F(float(point[j]))
                  for j in np.flatnonzero(d['objective'])),F(0))
    if objective != F(spec['ub_exact']):
        raise ValueError('ORIGINAL_OBJECTIVE_AND_UB_IDENTITY_DRIFT')
    envelope = read(spec['envelope']['path'])
    lo, hi = d['lower'].copy(), d['upper'].copy()
    for step in envelope['steps']:
        lo[step['column']], hi[step['column']] = step['lower'], step['upper']
    envelope_receipt = verify(A, d, lo, hi, envelope)
    source = read(spec['seed_dual']['path'])
    baseline = check_rational_dual_certificate(A, d, source, lower=lo, upper=hi,
                                              case_sha=spec['case_sha'])
    stored = read(spec['seed_certificate']['path'])
    if baseline['exact_bound'] != stored['exact_Global_LB']:
        raise ValueError('EXISTING_L1_NOT_REPRODUCED')
    case = SimpleNamespace(A=A, d=d, point=point, case_sha=spec['case_sha'],
                           identity=identity, lower=lo, upper=hi)
    decomp = build_blocks(case)
    if any(np.any(b.d['types'] != 'C') for b in [decomp.nonunit_block]):
        raise ValueError('NONUNIT_INTEGRAL_DOMAIN_REQUIRES_SEPARATE_HULL')
    for b in decomp.units.values():
        if not np.isfinite(b.d['lower']).all() or not np.isfinite(b.d['upper']).all():
            raise ValueError('UNBOUNDED_UNIT_TRAJECTORY_DOMAIN')
    for data in (d,):
        for value in data.values():
            value.flags.writeable = False
    for value in (A.data, A.indices, A.indptr, point, lo, hi):
        value.flags.writeable = False
    return case, decomp, source, dict(PASS=True, spec=spec, identity=identity,
                                     baseline=baseline, envelope=envelope_receipt,
                                     decomposition=decomp.inclusion)
