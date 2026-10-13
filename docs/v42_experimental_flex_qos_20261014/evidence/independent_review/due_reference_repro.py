"""Named Source-row unit reproduction; no Actual/Native/AC execution."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import sys
import numpy as np

ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from test_v42_integration_sensitivity_policy import fixture
from v42_integration.experimental_policy import ExperimentalControlPolicy
from v42_integration.q90_recourse import load_nominal_service
from v42_integration.policy import ReservationLedger


def record(p):
    b=Path(p).read_bytes();return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))


def main():
    source=fixture(voltage_slope=.3);packet=source[0]
    # Declared fixture: only future slot3 has a voltage response to siteB.
    # SourceA IEEE123 coefficients are never loaded or changed in this repro.
    for t,c in enumerate(packet.coefficients):
        if t!=3:c.voltage_matrix[:]=0.;c.voltage_constant[:]=1.
    plan=dict(packet.aidc_plan,resource_sites=list(packet.sites),
        nominal_site_GPU={s:[1.]*96 for s in packet.sites},known_site_GPU={s:[0.]*96 for s in packet.sites},
        CC4_service={str((h,t)):.5 for h in range(24) for t in range(4*h,4*h+4)},
        CC4_carryout={str(h):0. for h in range(24)})
    q=np.full(24,2.);lo=np.zeros(100);hi=np.ones(100)
    authority=dict(model_id='LGBM_weighted_c1_s20260924',prediction_sha=source[6]['cc4_sha'],
        kernel_sha='NAMED_FIXTURE_KERNEL_REFERENCE',timing_envelope_sha='NAMED_FIXTURE_CDF')
    nominal=load_nominal_service(plan,q,lo,hi,source_authority=authority)
    provider=SimpleNamespace(scenario='E1',participation='FLEX30',stats=SimpleNamespace(sha='NAMED_FIXTURE_QOS'))
    selector=ExperimentalControlPolicy(packet,source[6],qos_provider=provider,q50_hourly=q,q90_hourly=q,
        kernel=[1.],queue_authority=authority,frozen_anonymous_gpu=np.ones((96,2)),
        nominal_service=nominal,train_cdf_lower=lo,train_cdf_upper=hi,recourse_source_authority=authority)
    selector.set_observed_context(now=1800,observed_gpu={'A':1,'B':1},pending_nominal_work={'DUE':.5},
        remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={'scope':'NAMED_OBSERVED_FIXTURE'})
    ledger=ReservationLedger({'A':8,'B':8})
    for site in packet.sites:ledger.retain_running('BG_'+site,site,0,86400,1)
    due=[dict(resource='gpu:B',begin=1800.,end=3600.,quantity=1)]
    ledger.reserve('DUE',due)
    metadata=dict(uid='DUE',state='PENDING',gpu=1,t50_seconds=1800,current_site=None)
    old,old_reason=selector._score(metadata,due,1800,ledger,replace=True)
    original=[dict(resource='gpu:A',begin=0.,end=1800.,quantity=1)]
    corrected,corrected_reason=selector._score(metadata,due,1800,ledger,replace=True,reference_segments=original)
    result=dict(schema='C_DUE_REFERENCE_FUTURE_REBOUND_UNIT_REPRODUCTION_V1',
        reproduced=bool(old and old['q50_hard_feasible'] and corrected and not corrected['q50_hard_feasible']),
        scope='DECLARED_SYNTHETIC_SIGNED_96_SLOT_GEOMETRY;NOT_REAL_MAY_OR_ACTUAL_EXECUTION',
        scheduled_action='DELAYED_PREPLACE_B_AT1800',original_causal_reference='A_AT0_SERVICE1800',
        current_slot=2,future_voltage_rebound_slot=3,
        missing_explicit_reference=dict(reason=old_reason,q50_hard_pass=old['q50_hard_feasible'] if old else None,
            candidate_delta_sha=old.get('candidate_gpu_delta_sha') if old else None),
        explicit_frozen_reference=dict(reason=corrected_reason,q50_hard_pass=corrected['q50_hard_feasible'] if corrected else None,
            violations=corrected['q50_violations'] if corrected else None,
            candidate_delta_sha=corrected.get('candidate_gpu_delta_sha') if corrected else None),
        source_files=[record(ROOT/'v42_integration/experimental_policy.py'),
            record(ROOT/'v42_integration/experimental_actual.py'),record(__file__)],
        Native_Optimize_calls=0,Actual_runs=0,Fresh_AC_calls=0,production_source_edits=0)
    Path(__file__).with_name('DUE_REFERENCE_FUTURE_REBOUND_REPRO.json').write_text(
        json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
