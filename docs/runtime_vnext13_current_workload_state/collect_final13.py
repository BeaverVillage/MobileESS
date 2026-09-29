"""Collect existing diagnostics after user-ordered early termination. NEVER fits a model."""
from common13 import *
from train13 import collect
import shutil

EARLY = 'NOT_RUN_EARLY_TERMINATION_AFTER_PRIMARY_GATE_FAILURE'


def main():
    selection = read(ROOT/'TOTAL_MODEL_SELECTION_FREEZE.json')
    assert not selection['TOTAL_RUNTIME_MODEL_VALIDATED']
    anchor = selection['diagnostic_ablation_anchor']
    baseline = pd.read_csv(ROOT/'TOTAL_MODEL_COMPARISON.csv').set_index('arm').loc[anchor]
    rows, actual, inventory = [], [], []
    for group in 'ABCDE':
        name = anchor+'_ABL_'+group
        complete = []
        for fold in range(1, 6):
            folder = LOCAL/f'fold{fold}'
            required = [folder/(name+'.json'), folder/(name+'.parquet'), folder/(name+'_quantiles.npz'),
                        ROOT/'FOLD_MODELS'/f'fold{fold}'/name/'model.json',
                        ROOT/'FOLD_MODELS'/f'fold{fold}'/name/'hazard.txt']
            present = [p.is_file() for p in required]
            assert all(present) or not any(present), ('partial write requires manual accounting', group, fold, present)
            if all(present):
                complete.append(fold)
                actual.append(read(required[0]))
            inventory.append(dict(group=group, arm=name, fold=fold, status='COMPLETED_DIAGNOSTIC' if all(present) else EARLY,
                                  metrics_available=all(present), files=[record(p) for p in required] if all(present) else []))
        missing = sorted(set(range(1, 6))-set(complete))
        if len(complete) == 5:
            summary, _, _ = collect(anchor, group)
            summary.update(group=group, status='DIAGNOSTIC_ONLY', metrics_available=True, anchor=anchor,
                           delta_min_fold=summary['min_fold_coverage']-baseline.min_fold_coverage,
                           delta_pinball=summary['Q90_pinball']-baseline.Q90_pinball)
        else:
            # Do not pool a partial arm or fill absent scientific measurements with zero.
            summary = dict(group=group, arm=name, anchor=anchor, status=EARLY, metrics_available=False)
        summary.update(completed_fold_count=len(complete), completed_folds=';'.join(map(str, complete)),
                       unrun_folds=';'.join(map(str, missing)), full_five_fold_metrics_available=len(complete)==5)
        rows.append(summary)
    assert [r['completed_fold_count'] for r in rows] == [5, 5, 5, 5, 2]
    pd.DataFrame(rows).to_csv(ROOT/'CURRENT_STATE_FEATURE_ABLATION.csv', index=False)
    pd.DataFrame(actual).to_csv(ROOT/'ABLATION_FOLD_METRICS.csv', index=False)
    pd.DataFrame([{k:v for k,v in r.items() if k != 'files'} for r in inventory]).to_csv(ROOT/'ABLATION_EXECUTION_STATUS.csv', index=False)
    archive = ROOT/'EXECUTION_LOGS'
    archive.mkdir(exist_ok=True)
    logs = []
    for p in sorted(LOCAL.glob('*.log')):
        dest = archive/p.name
        if dest.exists():
            assert sha(dest) == sha(p), ('previously archived log changed', p)
        else:
            shutil.copyfile(p, dest)
        logs.append(dict(original=record(p), archived=record(dest)))
    write('EARLY_TERMINATION_RECEIPT.json', dict(time=now(),
        status='PRIMARY_COMPLETE_DIAGNOSTICS_EARLY_TERMINATED',
        EARLY_TERMINATION_AFTER_PRIMARY_GATE_FAILURE=True,
        governing_instruction=record(ROOT/'EARLY_TERMINATION_INSTRUCTION.md'),
        scientific_decision_time=selection['time'], primary_selection_freeze=record(ROOT/'TOTAL_MODEL_SELECTION_FREEZE.json'),
        reason='User-ordered cost-saving decision after frozen primary gate failure; only remaining diagnostic ablations omitted.',
        stop_mechanism='Exclusive read lock on HAZARD_BIN_CONTRACT.json allowed in-memory E folds 1/2 to finish. Next fits failed at contract read before learner construction. Lock released only after both workers exited. No frozen source or contract content changed.',
        current_jobs_completed=[dict(group='E', fold=1, done='2026-09-29T06:03:18.959981+00:00'),
                                dict(group='E', fold=2, done='2026-09-29T06:04:23.386234+00:00')],
        administrative_errors='PermissionError and parent CalledProcessError are intentional launch blocking, not scientific failures. FIT log line is emitted before model13.fit reads its contract and does not establish training began.',
        completed_ablation_folds=len(actual), unrun_ablation_folds=3, completed_groups=['A','B','C','D'], partial_group='E',
        fold_inventory=inventory, preserved_logs=logs, additional_training_authorized=False,
        Stage_C_executed=False, provider_created=False, April_evaluated=False, May_opened=False))
    write('TRAINING_COMPLETED.json', dict(time=now(), status='PRIMARY_COMPLETE_DIAGNOSTICS_EARLY_TERMINATED',
        primary_complete=True, all_diagnostics_complete=False, completed_diagnostic_folds=len(actual), unrun_diagnostic_folds=3,
        selected=None, ablation_anchor=anchor, April_opened=False, May_opened=False,
        EARLY_TERMINATION_AFTER_PRIMARY_GATE_FAILURE=True))
    # Inventory all existing local evidence; large data stay local and are never deleted.
    write('LOCAL_EVIDENCE_MANIFEST.json', dict(time=now(), retained=True, git_included=False,
        files=[record(p) for p in sorted(LOCAL.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]))
    print('FINALIZATION_ONLY_COLLECTED', len(actual), 'completed folds; 3 NOT_RUN', flush=True)


if __name__ == '__main__':
    main()
