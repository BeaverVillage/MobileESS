from datetime import datetime, timezone
from pathlib import Path
from v42_april_port.audit import write, record

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_april_modelable_population_b0'
BASE = '9f6abde13c8d4a8b36162aae3ddab2e7cd540b13'
PHYSICAL = '''# Frozen current V42 physical modelability rule

Freeze before population statistics, reference feasibility, power or voltage results.
Stable exact source UID and submission; submit <= causal inference event;
current frozen Runtime available at that event and finite nonnegative Q50/service;
source requested GPU a finite positive integer; source H100 resource partition;
whole gang fits at least one current compatible rack/site; current IT map exists.
No node-count or allocated-resource inference. No imputation. Missing GPU:
UNMODELABLE_MISSING_GPU_REQUEST. Other absent/invalid required physical field:
UNMODELABLE_SOURCE_RECORD with exact field/reason. Retain every excluded event.
No source site and no flexibility capability are NOT exclusion criteria.
Aggregate capacity contention is NOT a modelability filter. The common scheduler
must separately certify capacity feasibility and retain blocked physical rows.
Requested walltime is a Runtime feature only. GPUh coverage is not identifiable
when excluded GPU request is missing. No coverage percentage acceptance gate.
Same J_PHYSICAL, immutable GPU, Runtime, service and power map for all four arms.
Kestrel submission-version history remains UNVERIFIED_SOURCE_PROXY: do not claim
historical deployment causality. This is a retrospective request-descriptor proxy
with exact UID/submission and model availability checks; no fabricated versions.
'''
FLEX = '''# Frozen current V42 flexibility eligibility rule

J_FLEX is a subset of J_PHYSICAL, never a separate service population.
Evaluate current TRAIN-only hierarchical WaitAuthority for pending TS capability.
Prestart placement requires pending state, multiple compatible/residency-authorized
sites and current service boundary. Checkpoint migration requires current checkpoint,
elapsed, WAN and service-boundary authority. Missing capability authority means fixed.
Record potential capability separately from an executable certified domain; do not
promote a capability mask or prototype into native executable authority.
Reference generation does not depend on eligibility or grid results. B0/B2 use the
common reference for every physical job. B1/B3 retain every non-flex job fixed.
No outcome-dependent classification, May outcomes or policy optimization.
'''

def main():
    if (OUT/'PREREGISTRATION.json').exists():
        raise ValueError('ALREADY_FROZEN')
    (OUT/'POPULATION').mkdir(parents=True)
    (OUT/'.gitattributes').write_text('* -text whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol\n', encoding='utf8')
    for name, text in [('V42_PHYSICAL_MODELABILITY_RULE.md', PHYSICAL), ('V42_FLEXIBILITY_ELIGIBILITY_RULE.md', FLEX)]:
        (OUT/'POPULATION'/name).write_text(text, encoding='utf8', newline='\n')
    for stem in ['V42_PHYSICAL_MODELABILITY', 'V42_FLEXIBILITY_ELIGIBILITY']:
        write(OUT, 'POPULATION/'+stem+'_AUTHORITY.json', dict(frozen=True,
            rule=record(OUT/'POPULATION'/(stem+'_RULE.md')), result_independent=True,
            all_arms_service_J_PHYSICAL=True, May_outcomes_used=False,
            population_statistics_observed_before_freeze=False))
    write(OUT, 'PREREGISTRATION.json', dict(exact_base=BASE, frozen_at=datetime.now(timezone.utc).isoformat(),
        days=['2025-04-%02d'%d for d in range(1,31)], rules_frozen_before_statistics=True,
        primary_voltage_band=[.95,1.05], B0_ML_ON=True, B0_flex_OFF=True, B0_MESS_OFF=True,
        raw_records_retained=True, historical_requested_walltime_fallback=False,
        May_outcomes_used=False, FINAL_MARGIN_ACCEPTED=False))
    write(OUT, 'PR122_BASE_RECEIPT.json', dict(exact_base=BASE, inherited_PR=122,
        original_evidence_namespace='docs/v42_april_port_from_may_pipeline', modified=False))

if __name__ == '__main__': main()
