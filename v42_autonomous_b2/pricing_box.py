"""Certificate-only NONUNIT envelopes proved by original full-case equalities.

These projected bounds contain every globally extendable NONUNIT point.
They need not contain every standalone NONUNIT point and confer no local
pricing closure. Original builders, blocks, unit boxes and physics stay intact;
the original pricing sum must still equal the independent full-original proof.
"""
from pathlib import Path
from types import SimpleNamespace
import numpy as np

from v42_b2_seed_recovery_v18 import certificate_box
from v42_m1_hybrid.blocks import verify_decomposition,matrix_sha
from v42_may_campaign_native90.m_model import _domain_sha
from v42_may_campaign_native90.a_routing import rebound
from . import canonical_stream


class ProjectionAuthority:
    def __init__(self,case,decomp,output,original_local_bound):
        self.case,self.decomp,self.original_local_bound=case,decomp,original_local_bound
        self.case_sha=case.case_sha
        inclusion=verify_decomposition(case,decomp)
        self.matrix_sha=matrix_sha(case.A);self.domain_sha=_domain_sha(case.d)
        self.lower,self.upper,proof=certificate_box.derive(case.A,case.d)
        checked=certificate_box.verify(case.A,case.d,self.lower,self.upper,proof)
        for block in decomp.units.values():
            axis=np.asarray(block.original_columns)
            if (not np.array_equal(self.lower[axis],block.d['lower'])
                    or not np.array_equal(self.upper[axis],block.d['upper'])):
                raise ValueError('PRICING_BOX_UNIT_ORIGINAL_STANDALONE_BOX_CHANGED')
        proof.update(schema='V42_B2_PRICING_FULL_CASE_PROJECTION_BOX_V26',
            case_sha=case.case_sha,source_matrix_sha256=self.matrix_sha,
            source_domain_sha256=self.domain_sha,independent_replay=checked,
            decomposition=inclusion,Native_optimize_calls=0,
            original_model_and_block_bounds_mutated=False,
            unit_boxes_are_original=True,
            nonunit_scope='PROJECTION_OF_GLOBALLY_EXTENDABLE_ORIGINAL_FEASIBLE_POINTS',
            standalone_nonunit_domain_bound_or_closure_claimed=False,
            authoritative_Global_LB_requires_full_original_signed_dual_check=True)
        output=Path(output)
        output.mkdir(parents=True,exist_ok=True)
        path=output/'FULL_CASE_PRICING_BOX_PROOF.json'
        canonical_stream.atomic(path,proof)
        from v42_b2_seed_recovery_v19.common import record
        self.receipt=record(path)

    def local_bound(self,block,exact_objective,dual):
        if self.case.case_sha!=self.case_sha or self.decomp.case_sha!=self.case_sha:
            raise ValueError('PRICING_BOX_ORIGINAL_CASE_IDENTITY_DRIFT')
        if block is not self.decomp.nonunit_block:
            if not any(block is b for b in self.decomp.units.values()):
                raise ValueError('PRICING_BOX_UNBOUND_ORIGINAL_BLOCK')
            # Every unit retains its original standalone full-96-slot box.
            return self.original_local_bound(block,exact_objective,dual)
        if (matrix_sha(self.case.A)!=self.matrix_sha
                or _domain_sha(self.case.d)!=self.domain_sha):
            raise ValueError('PRICING_BOX_FULL_ORIGINAL_CASE_SHA_DRIFT')
        axis=np.asarray(block.original_columns)
        for key in ('lower','upper','types','names','objective'):
            if not np.array_equal(np.asarray(block.d[key]),np.asarray(self.case.d[key])[axis]):
                raise ValueError('PRICING_BOX_ORIGINAL_NONUNIT_DOMAIN_DRIFT:'+key)
        expected=self.case.A[block.original_rows][:,axis].tocsr()
        if matrix_sha(expected)!=matrix_sha(block.A):
            raise ValueError('PRICING_BOX_ORIGINAL_NONUNIT_MATRIX_DRIFT')
        for key in ('rhs','sense','row_names'):
            if not np.array_equal(block.d[key],np.asarray(self.case.d[key])[block.original_rows]):
                raise ValueError('PRICING_BOX_ORIGINAL_NONUNIT_ROW_DRIFT:'+key)
        if np.isfinite(block.d['lower']).all() and np.isfinite(block.d['upper']).all():
            return self.original_local_bound(block,exact_objective,dual)
        # The full-case equality proof was independently replayed. These are
        # only checker inputs; neither block.d nor any Native model is changed.
        domain=dict(block.d,lower=self.lower[axis],upper=self.upper[axis])
        proxy=SimpleNamespace(A=block.A,d=domain)
        result=self.original_local_bound(proxy,exact_objective,dual)
        result.update(certificate_scope='GLOBAL_ORIGINAL_FEASIBLE_NONUNIT_PROJECTION_ONLY',
            finite_box_full_original_equality_proof=self.receipt,
            standalone_nonunit_domain_lower_bound_claimed=False,
            standalone_nonunit_pricing_closure_claimed=False,
            original_model_and_block_bounds_mutated=False,
            rounded_or_artificial_bounds_used=False,
            authoritative_Global_LB_requires_full_original_signed_dual_check=True)
        return result


def scoped_pricing(original,original_local_bound,output_directory):
    """Retain original pricing, Native calls and exact decomposition equality."""
    def run(case,decomp,prices,ledger,output,**kwargs):
        authority=ProjectionAuthority(case,decomp,output_directory(output),original_local_bound)
        namespace=dict(original.__globals__,local_exact_price_bound=authority.local_bound,
                       output_directory=output_directory)
        checked=rebound(original,namespace)
        return checked(case,decomp,prices,ledger,output,**kwargs)
    run.original_pricing=original
    run.original_local_bound=original_local_bound
    return run
