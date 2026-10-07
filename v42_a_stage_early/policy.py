from pathlib import Path
from v42_a_stage_phase1.setup import POLICY as PREVIOUS
from . import BASE

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/v42_a_stage_phase1_corrected_rerun_20261008'
STATIC = ROOT.parent/'v42-a-stage-corrected-static'
HISTORY = ROOT/'docs/v42_a_stage_phase1_pricing_20261007'
DAY = '2025-05-19'
POLICY = dict(PREVIOUS, schema='PHASE1_EARLY_ACTIVATION_V2',
    cumulative_budget_seconds=900, budget_accounting='max(elapsed wall since RUN_STARTED, sum of every native Runtime); no resets',
    max_phase1_rounds=12, max_P1_rounds=0, negative_trigger=16, fully_priced_class_trigger=24,
    batch_initial=16, batch_minimum=16, batch_maximum=16, max_pricing_workers=4,
    concrete_candidates_per_class=1, candidate_recovery='best exact physical STAY or deterministic native-positive migration support; validate one best negative per class',
    candidate_order='exact rational class-column reduced cost, class/site/start/full-path identity',
    batching_adaptation='none', stagnation_resolves=3, stagnation_relative_decrease=.01,
    material_phi_decrease=.01, parallel_order='sorted class IDs; waves <=4; consume canonical prefix; charge all lookahead native calls',
    final_closure='not authorized; artificial-free replay then STOP at certified zero',
    scientific_domain_cap=False, permanently_deleted_candidates=0)
for obsolete in ('cumulative_native_seconds','native_plus_pricing_wall_seconds'):
    POLICY.pop(obsolete)

def trigger(negative_count, fully_priced):
    return negative_count >= POLICY['negative_trigger'] or fully_priced >= POLICY['fully_priced_class_trigger']

def stagnated(relative_decreases, valid_negative_count):
    return valid_negative_count > 0 and len(relative_decreases) >= 3 and all(v < .01 for v in relative_decreases[-3:])
