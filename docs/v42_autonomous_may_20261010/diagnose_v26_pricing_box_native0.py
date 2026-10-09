"""Actual saved L2 prices: Infinity repro and exact projected decomposition."""
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from fractions import Fraction
import json
import gc
from time import perf_counter
import psutil

import numpy as np
from scipy import sparse

from v42_autonomous_b2.pricing_box import ProjectionAuthority
from v42_b2_seed_recovery_v18 import certificate_box
from v42_m1_hybrid.blocks import build_blocks,matrix_sha
from v42_m1_hybrid.bound import local_exact_price_bound,assemble_full_dual
from v42_m1_hybrid.pricing import make_prices
from v42_may_campaign_native90.m_model import _domain_sha
from v42_b2_seed_recovery_v19.common import record


ROOT=Path(__file__).resolve().parents[2]
CAMPAIGN=Path(r'D:\v42_may_restart_20261010_02')
PROOF_ROOT=ROOT/'docs/v42_autonomous_may_20261010/V26_PRICING_BOX_PROOF'


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))


def load(path):
    with np.load(path,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}


def day_proof(day):
    output=CAMPAIGN/'dates/B2'/day/'attempts/fresh_b2_v23_01/output'
    source=output/'005_L2_00'
    A=sparse.load_npz(output/'C3A_A.npz').tocsr();d=load(output/'C3A_DATA.npz')
    identity=read(output/'SCIENTIFIC_CASE_IDENTITY.json')
    assert matrix_sha(A)==identity['selected_matrix_sha']
    assert _domain_sha(d)==identity['selected_domain_sha']
    case=SimpleNamespace(A=A,d=d,case_sha=identity['case_sha'])
    decomp=build_blocks(case)
    source_dual=read(source/'SOURCE_FULL_DUAL_EXACT.json')
    prices=make_prices(case,decomp,source_dual)
    assert {str(k):str(v) for k,v in prices.nonunit_exact_objective.items()}==read(source/'NONUNIT_PRICE_EXACT.json')
    block=decomp.nonunit_block
    before=(_domain_sha(case.d),matrix_sha(case.A),block.d['lower'].copy(),block.d['upper'].copy())
    try:local_exact_price_bound(block,prices.nonunit_exact_objective,prices.seed_nonunit_dual)
    except OverflowError as error:assert 'Infinity' in str(error)
    else:raise AssertionError('ACTUAL_INFINITY_FAILURE_NOT_REPRODUCED')
    authority=ProjectionAuthority(case,decomp,PROOF_ROOT/day,local_exact_price_bound)
    nonunit=authority.local_bound(block,prices.nonunit_exact_objective,prices.seed_nonunit_dual)
    unit_duals={u:read(source/(u+'_SELECTED_DUAL_EXACT.json')) for u in decomp.units}
    units={u:authority.local_bound(b,prices.exact_objectives[u],unit_duals[u])
           for u,b in decomp.units.items()}
    full=assemble_full_dual(case,decomp,prices.coupling_dual,unit_duals,prices.seed_nonunit_dual)
    authoritative=certificate_box.original_checker(case.A,case.d,full,
        lower=authority.lower,upper=authority.upper,case_sha=case.case_sha)
    separately_routed=certificate_box.check(case.A,case.d,full,case_sha=case.case_sha)
    exact_sum=Fraction(float(case.d['constant']))+Fraction(prices.coupling_constant_exact)
    exact_sum+=Fraction(nonunit['exact_bound'])+sum((Fraction(c['exact_bound']) for c in units.values()),Fraction(0))
    assert exact_sum==Fraction(authoritative['exact_bound'])==Fraction(separately_routed['exact_bound'])
    assert before[:2]==(_domain_sha(case.d),matrix_sha(case.A))
    assert np.array_equal(before[2],block.d['lower']) and np.array_equal(before[3],block.d['upper'])
    for unit,b in decomp.units.items():
        assert np.isfinite(b.d['lower']).all() and np.isfinite(b.d['upper']).all()
        original=local_exact_price_bound(b,prices.exact_objectives[unit],unit_duals[unit])
        assert original['exact_bound']==units[unit]['exact_bound']
        assert 'certificate_scope' not in units[unit]
    rmp=read(output/'005_L2_00_MASTER/RMP_RESULT.json')
    strict=read(output/'BEST_STRICT_UB_CERTIFICATE.json')
    assert strict['PASS'] is True
    return dict(day=day,PASS=True,Native_optimize_calls=0,Native_model_build_calls=0,
        actual_failure_reproduced='OverflowError: cannot convert Infinity to integer ratio',
        actual_source_matrix=record(output/'C3A_A.npz'),actual_source_domain=record(output/'C3A_DATA.npz'),
        saved_L2_source_dual=record(source/'SOURCE_FULL_DUAL_EXACT.json'),
        saved_L2_unit_duals={u:record(source/(u+'_SELECTED_DUAL_EXACT.json')) for u in decomp.units},
        full_original_equality_implication_proof=authority.receipt,
        original_unit_exact_price_certificates=units,
        globally_extendable_nonunit_projection_certificate=nonunit,
        independent_original_full_signed_dual_certificate=authoritative,
        existing_certificate_box_checker_bound_matches=True,
        exact_decomposition_sum=str(exact_sum),exact_decomposition_sum_equals_independent_Global_LB=True,
        unit_domains_byte_preserved=True,original_nonunit_model_and_block_domains_unmodified=True,
        original_scientific_matrix_domain_SHA_unchanged=True,
        standalone_nonunit_closure_or_domain_bound_claimed=False,
        actual_RMP_Native_status=rmp['native'].get('Native_status'),
        actual_RMP_dual_status=rmp.get('dual_status'),
        existing_actual_strict_FULL_physical_integer_objective_certificate=record(output/'BEST_STRICT_UB_CERTIFICATE.json'),
        actual_existing_Global_UB=strict['exact_Global_UB'],
        new_production_PASS_or_3_percent_Gap_or_qualification_claimed=False,
        process_RSS_bytes=psutil.Process().memory_info().rss)


def main():
    start=perf_counter();originals={}
    adapter_sources={name:record(ROOT/name) for name in
        ('v42_autonomous_b2/pricing_box.py','v42_autonomous_b2/worker.py')}
    for name in ('v42_m1_hybrid/pricing.py','v42_m1_hybrid/bound.py','v42_m1_hybrid/verify.py',
                 'v42_b2_seed_recovery_v18/certificate_box.py','v42_m1_research/check_lb.py',
                 'v42_m1_research/check_ub.py','v42_m1_hybrid/blocks.py'):
        current=record(ROOT/name);old=record(Path(r'D:\v42run23')/name)
        assert current['sha256']==old['sha256']
        originals[name]=dict(current=current,frozen_v23=old,byte_identical=True)
    dates=[]
    for day in ('2025-05-07','2025-05-08','2025-05-09'):
        row=day_proof(day);dates.append(row)
        print(json.dumps(dict(day=day,PASS=True,Native_optimize_calls=0,
            exact_Global_LB=row['exact_decomposition_sum'],RSS=row['process_RSS_bytes'])),flush=True)
        gc.collect()
    if any(record(ROOT/name)!=receipt for name,receipt in adapter_sources.items()):
        raise ValueError('V26_DIAGNOSTIC_SOURCE_CHANGED_DURING_PROOF')
    result=dict(schema='V42_B2_V26_ACTUAL_L2_PRICING_INFINITY_NATIVE0_PROOF',PASS=True,
        UTC=datetime.now(timezone.utc).isoformat(),Native_optimize_calls=0,Native_model_build_calls=0,
        original_scientific_sources=originals,
        adapter_sources=adapter_sources,
        dates=dates,wall_seconds=perf_counter()-start,
        globally_extendable_projection_not_standalone_nonunit_domain=True,
        final_production_PASS_and_gap_still_require_actual_fresh_execution=True)
    path=Path(__file__).with_name('V26_ACTUAL_THREE_DATE_PRICING_BOX_NATIVE0_PROOF.json')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(PASS=True,proof=record(path))),flush=True)


if __name__=='__main__':main()
