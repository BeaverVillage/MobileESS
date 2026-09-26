"""Delivery-only byte audit of original forecast receipts; does not score outcomes."""
from experiment import *


def main():
    require((ROOT/'EVALUATION_COMPLETE.json').exists(), 'EVALUATION_NOT_COMPLETE')
    count = 0
    neural = 0
    for folder in (ROOT/'fits').iterdir():
        if not folder.is_dir() or '.reuse-staging' in folder.name:
            continue
        prediction_path = ROOT/'predictions'/(folder.name+'.npz')
        if not prediction_path.exists():
            continue
        cached = np.load(prediction_path)['q']
        for receipt in folder.glob('*/PREDICTION_*.json'):
            evidence = json.loads(receipt.read_text(encoding='utf-8'))
            indexes = np.array([np.flatnonzero(DAYS == day).item() for day in evidence['issued_days']])
            require(hashlib.sha256(cached[indexes].tobytes()).hexdigest() == evidence['forecast_sha256'],
                    'FORECAST_RECEIPT_DRIFT '+str(receipt.relative_to(ROOT)))
            require(evidence['evaluation_labels_in_fit'] == 0, 'FUTURE_LABEL_IN_FIT')
            count += 1
        for receipt in folder.glob('*/receipt.json'):
            evidence = json.loads(receipt.read_text(encoding='utf-8'))
            require(sha(receipt.parent/'model.pt') == evidence['model_sha256'], 'NEURAL_CHECKPOINT_DRIFT')
            neural += 1
    require(count > 0 and neural > 0, 'EMPTY_FIT_AUDIT')
    dump('FIT_RECEIPT_VALIDATION.json', dict(time=now(), PASS=True, prediction_receipts=count,
         neural_checkpoints=neural, original_receipts_unchanged=True, scoring_performed=False))
    print('FIT RECEIPTS PASS', count, neural, flush=True)


if __name__ == '__main__':
    main()
