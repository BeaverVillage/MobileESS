"""Supervisor admission for the requested SAME-pool original 4x24 comparison.

All costs append to PR230's existing canonical ledger. Historical S1/A1 scope
guards remain unchanged; this separate admission is tied to the resumed user's
specific comparison and an independently verified row deletion certificate.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import numpy as np

from .budget import IntegrationBudget
from .followup_contract import require_sha
from .unified_contract import file_sha
from .unified_resource import UnifiedResearchBudget
from .m_engine import matrix_sha, domain_sha, vector_sha, APPROVED_JOINT_PARAMETERS


class FollowupComparisonBudget(UnifiedResearchBudget):
    def __init__(self, *, certificate_path, expected_certificate_sha, identity, expected_packets):
        super().__init__()
        self.certificate_path = Path(certificate_path).resolve()
        self.certificate_sha = require_sha(expected_certificate_sha, 'certificate_sha')
        self.comparison_identity = deepcopy(identity)
        for key in ('source_sha', 'case_sha', 'physical_sha', 'pool_sha'):
            require_sha(identity.get(key), key)
        if (identity.get('MESS_count'), identity.get('nodes'), identity.get('slots')) != (4, 24, 96):
            raise ValueError('FOLLOWUP_ORIGINAL_4X24_FULL96_REQUIRED')
        self.expected_packets = expected_packets
        if set(expected_packets) != {'ORIGINAL', 'COMPRESSED'}:
            raise ValueError('FOLLOWUP_BOTH_MATCHED_PACKETS_REQUIRED')
        self._certificate()
        if self.remaining(reserve=30.) < 40.:
            raise RuntimeError('FOLLOWUP_MATCHED_PAIR_BUDGET_REQUIRED')
        self.completed_variants = []
        self.pair_cap = None

    def _certificate(self):
        if file_sha(self.certificate_path) != self.certificate_sha:
            raise ValueError('FOLLOWUP_COMPRESSION_CERTIFICATE_BYTE_DRIFT')
        c = json.loads(self.certificate_path.read_text(encoding='utf8'))
        required = ('PASS', 'same_pool_integer_domain_equivalent', 'same_pool_LP_domain_equivalent',
                    'raw_lift_bit_identical', 'MIP_Start_bit_identical', 'objective_types_bounds_bit_identical')
        if (c.get('status') != 'PASS' or any(c.get(k) is not True for k in required) or
                c.get('non_grid_rows_removed') != 0 or c.get('restricted_ObjBound_is_Global_LB') is not False):
            raise ValueError('FOLLOWUP_EXACT_JOINT_COMPRESSION_PROOF_REQUIRED')
        for key in ('source_sha', 'case_sha', 'physical_sha', 'pool_sha'):
            if c.get('identity', {}).get(key) != self.comparison_identity[key]:
                raise ValueError('FOLLOWUP_COMPRESSION_CASE_POOL_DRIFT:' + key)
        if c.get('independently_verified', {}).get('PASS') is not True:
            raise ValueError('FOLLOWUP_DELETION_PROOF_INDEPENDENT_RECHECK_REQUIRED')
        for variant, packet in self.expected_packets.items():
            a, d, lift, start, _ = packet
            expected_matrix = c['identity']['matrix_sha'] if variant == 'ORIGINAL' else c['compressed_matrix_sha']
            expected_domain = c['identity']['domain_sha'] if variant == 'ORIGINAL' else c['compressed_domain_sha']
            if (matrix_sha(a) != expected_matrix or domain_sha(d) != expected_domain or
                    matrix_sha(lift) != c['identity']['lift_sha'] or vector_sha(start) != c['identity']['start_sha']):
                raise ValueError('FOLLOWUP_CERTIFIED_PACKET_BYTE_DRIFT:' + variant)
        return c

    def _model_binding(self, model, variant):
        a, d, _, start, _ = self.expected_packets[variant]
        model.update()
        if matrix_sha(model.getA().tocsr()) != matrix_sha(a):
            raise ValueError('FOLLOWUP_ACTUAL_NATIVE_MATRIX_DRIFT')
        for attr, key in (('LB', 'lower'), ('UB', 'upper'), ('Obj', 'objective'),
                          ('VType', 'types'), ('VarName', 'names'), ('RHS', 'rhs'),
                          ('Sense', 'sense'), ('ConstrName', 'row_names')):
            if not np.array_equal(np.asarray(model.getAttr(attr)), d[key]):
                raise ValueError('FOLLOWUP_ACTUAL_NATIVE_DOMAIN_DRIFT:' + attr)
        if (model.ObjCon != float(d['constant']) or model.ModelSense != 1 or
                not np.array_equal(np.asarray(model.getAttr('Start')), start)):
            raise ValueError('FOLLOWUP_ACTUAL_NATIVE_OBJECTIVE_START_DRIFT')
        if any(getattr(model.Params, key) != value for key, value in APPROVED_JOINT_PARAMETERS.items()):
            raise ValueError('FOLLOWUP_MATCHED_NATIVE_PARAMETER_DRIFT')
        return dict(PASS=True, actual_matrix_sha=matrix_sha(a), actual_domain_sha=domain_sha(d),
                    Start_sha=vector_sha(start), source_case_pool_certificate_sha=self.certificate_sha)

    def solve(self, model, *, label, cap, callback=None):
        context = deepcopy(getattr(self, 'stage_context', {}))
        variant = context.get('comparison_variant')
        if variant not in ('ORIGINAL', 'COMPRESSED') or not label.startswith('M_PR222_JOINT:'):
            raise ValueError('FOLLOWUP_MATCHED_COMPRESSION_COMPARISON_ONLY')
        if not math.isfinite(float(cap)) or not 0. < float(cap) <= 20.:
            raise ValueError('FOLLOWUP_MATCHED_NATIVE_CAP_AT_MOST_20_SECONDS')
        if self.completed_variants != ([] if variant == 'ORIGINAL' else ['ORIGINAL']):
            raise ValueError('FOLLOWUP_MATCHED_PAIR_SINGLE_SEQUENTIAL_EXECUTION_REQUIRED')
        if variant == 'ORIGINAL':
            self.pair_cap = float(cap)
        elif float(cap) != self.pair_cap:
            raise ValueError('FOLLOWUP_MATCHED_NATIVE_TIME_LIMIT_DRIFT')
        self._certificate()
        context['actual_native_binding'] = self._model_binding(model, variant)
        # Keep return/accounting headroom; solver overshoot is still charged.
        if self.remaining(reserve=30.) < float(cap):
            raise RuntimeError('FOLLOWUP_NATIVE_RETURN_RESERVE_REQUIRED')
        with self.exclusive_worker():
            before = len(self.document['calls'])
            with self._transaction():
                self.document['active_stage_context'] = context
                self.document['research_execution'] = 'USER_RESUMED_LIMITED_SAME_POOL_COMPARISON'
            try:
                return IntegrationBudget.solve(self, model, label=label, cap=cap, callback=callback)
            finally:
                with self._transaction():
                    if len(self.document['calls']) > before:
                        self.document['calls'][-1].update(
                            session_identity=deepcopy(self.document['identity']), stage_context=context,
                            original_4x24_comparison_identity=deepcopy(self.comparison_identity),
                            compression_certificate_sha=self.certificate_sha,
                            bound_scope='SAME_RESTRICTED_BEAM_POOL_NOT_GLOBAL', usage_reset=False)
                        self.completed_variants.append(variant)
                    self.document['active_stage_context'] = None
