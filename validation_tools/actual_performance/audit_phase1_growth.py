"""Audit real May02 selected batches, inclusion witnesses, and gain history."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import v44_recovery_r024b
from v44.common import read, record, atomic, now
from v44_recovery_r024b.adaptive_pricing import AdaptivePricing
from copy import deepcopy


def audit(output):
    base = Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3')
    files = sorted((base / 'attempt007/A2/OUTPUT/PHASE_I').glob('S*/PRICE/PRICING_RESULT.json'),
                   key=lambda p: int(p.parents[1].name[1:]))
    files += sorted((base / 'attempt010/A2/OUTPUT/PHASE_I').glob('S*/PRICE/PRICING_RESULT.json'),
                    key=lambda p: int(p.parents[1].name[1:]))
    seen = set()
    rows = []
    for path in files:
        data = read(path)
        identities = [json.dumps([c['class_id'], c['option']], sort_keys=True, separators=(',', ':'))
                      for c in data['selected_candidates']]
        previous = sum(x in seen for x in identities)
        seen.update(identities)
        folder = path.parents[1]
        witnesses = {}
        for name in ('PRIOR_INCLUSION.json', 'PHYSICAL_ACTIVATION.json'):
            f = folder / name
            if f.exists():
                value = read(f)
                assert value['PASS']
                witnesses[name] = record(f)
        rows.append(dict(pricing=record(path), classes=data['classes_priced'], selected=len(identities),
                         selected_options_already_selected_in_previous_batches=previous,
                         full_class_sweep=data['full_eligible_class_exploration'],
                         full_option_closure=data['full_native_fractional_LP_pricing_closure'],
                         inclusion_and_activation_witnesses=witnesses))
    history = read(base / 'attempt010/A2/OUTPUT/R024B_ADAPTIVE_PROGRESS.json')['feedback']
    latest_folder = base / 'attempt010/A2/OUTPUT/PHASE_I/S2'
    original_plan = read(latest_folder / 'PRICE/R024B_CLASS_EXPLORATION.json')
    attribution = read(latest_folder / 'ATTRIBUTION/RESIDUAL_ATTRIBUTION.json')
    parent = read(Path('D:/MobileESS_V44/development/r024b/current_continuation/ADAPTIVE_PARENT.json'))
    visited = dict(parent['visited'])
    first_plan = read(base / 'attempt010/A2/OUTPUT/PHASE_I/S0/PRICE/R024B_CLASS_EXPLORATION.json')
    visited.update({key:first_plan['round'] for key in first_plan['target_class_ids']})
    duplicate_restart = [i for i, r in enumerate(history) if i and r.get('previous_selected_columns') is None
                         and r['exact_full_Phi'] == history[i-1]['exact_full_Phi']]
    assert duplicate_restart == [7]
    comparisons = {}
    for label, feedback in [('recorded', history), ('without_duplicate_restart_observation',
                              [r for i,r in enumerate(history) if i not in duplicate_restart])]:
        controller = AdaptivePricing(output.parent)
        controller.feedback = deepcopy(feedback)
        controller.visited = dict(visited)
        controller.round = original_plan['round']
        controller.last_full = parent['last_full']
        plan = controller.plan_classes(attribution)
        comparisons[label] = dict(mode=plan['mode'], slow_rounds=plan['slow_rounds'],
                                   target_classes=len(plan['target_class_ids']))
    assert comparisons['recorded']['mode'] == original_plan['mode']
    receipt = dict(UTC=now(), scope='REAL_MAY02_R024A_R024B_HISTORY_READ_ONLY',
        batches=rows, unique_selected_options=len(seen),
        cross_batch_duplicates=sum(r['selected_options_already_selected_in_previous_batches'] for r in rows),
        all_existing_inclusion_and_activation_witnesses_PASS=True,
        last_batch_may_be_selected_without_completed_activation_due_to_user_stop=True,
        Phi_history=[dict(Phi=r['full_Phi'], relative_decrease=r['relative_decrease']) for r in history],
        equal_Phi_restart_observation_is_not_new_candidate_batch=True,
        restart_feedback_issue=dict(duplicate_observation_indices=duplicate_restart,
            policy_only_real_history_replay=comparisons,
            issue='Same-support restart at identical Phi is counted as another slow candidate-expansion round',
            proven_effect='Premature widening of class search; no feasibility or Native speedup conclusion',
            correction_deployed=False),
        slow_gain_policy='Two consecutive <15% gains widen focus/rotation; >=3 permit full sweep with cooldown; periodic full sweep independent of gains',
        no_claim_of_full_domain_feasibility_or_infeasibility=True)
    atomic(output, receipt)
    print(dict(batches=len(rows), unique_options=len(seen), cross_batch_duplicates=receipt['cross_batch_duplicates'],
               inclusion_proofs=sum(bool(r['inclusion_and_activation_witnesses']) for r in rows)))


if __name__ == '__main__':
    audit(Path(sys.argv[1]))
