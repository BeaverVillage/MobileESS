"""Check historical 27-day receipt compatibility without inheriting acceptance."""
from collections import Counter
from .audit import ROOT, REPORTS, write
from .storage import FrozenStore
from .replay import pinned, read


def check():
    prior = pinned(ROOT/'docs/v42_b1_may17_may19_repair_20261007/PASS27_REUSE_COMPATIBILITY.json')
    store = FrozenStore(); rows=[]; stages=Counter()
    for entry in prior['receipts']:
        path = store.copy(entry['receipt'])
        saved = read(path)
        stages[entry['stage']] += 1
        identity = saved.get('identity', {})
        rows.append(dict(day=entry['day'], stage=entry['stage'], original_sha256=entry['receipt']['sha256'],
                         frozen_file_sha_PASS=True, historical_PASS=entry['PASS'],
                         saved_identity=identity,
                         new_P1_only_M1_interface_certified=False,
                         new_A1_M1_A2_M2_pipeline_accepted=False))
    if len(prior['dates']) != 27 or len(rows) != 135 or any(n != 27 for n in stages.values()):
        raise ValueError('HISTORICAL_27_DATE_RECEIPT_COVERAGE_DRIFT')
    # Original pipeline source is immutable and explicitly sets MESS_OFF.
    source = ROOT/'v42_pr134_b1/replay.py'
    text = source.read_text(encoding='utf8')
    if 'MESS_OFF=True' not in text or 'M1=0,M2=0,MESS_PQ=0' not in text:
        raise ValueError('HISTORICAL_B1_PIPELINE_SCOPE_DRIFT')
    r = dict(PASS=True, checked_dates=prior['dates'], historical_receipts=rows,
             old_stage_coverage=dict(stages), old_MESS_OFF=True,
             source_schema='FOUR_OBJECTIVE_A1_B1_FIXED_TRAJECTORY',
             new_schema='A1_P1_ONLY_TO_M1_WITH_MESS',
             acceptance_automatically_inherited=False,
             classification='OLD_27_PASS_PRESERVED_NEW_CONTRACT_NOT_CERTIFIED',
             reason='The 27-date receipts have no M1/A2/M2 or new P1-only handoff; their inputs and decisions must be rebound and independently verified.',
             native_optimize_calls=0, campaign_runs=0, source_copies=store.seal())
    write(REPORTS/'PASS27_P1_ONLY_COMPATIBILITY.json', r)
    return r
