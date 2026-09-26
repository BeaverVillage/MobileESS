"""Read-only check of the original per-fit prediction and checkpoint digests."""
from common import *


def main():
    require((ROOT/'EVALUATION_COMPLETE.json').exists(), 'EVALUATION_NOT_COMPLETE')
    count = 0
    models = 0
    for receipt in (ROOT/'fits').glob('*/*/PREDICTION_RECEIPT.json'):
        evidence = json.loads(receipt.read_text(encoding='utf-8'))
        folder = receipt.parent
        prediction = ROOT/'predictions'/folder.parent.name/(folder.name+'.parquet')
        require(sha(prediction) == evidence['prediction_sha256'], 'PREDICTION_RECEIPT_DRIFT')
        require(not evidence['target_columns_passed_to_predictor'], 'TARGET_PASSED_TO_MODEL')
        for relative, digest in evidence['model_files'].items():
            require(sha(folder/relative) == digest, 'CHECKPOINT_RECEIPT_DRIFT')
            models += 1
        count += 1
    require(count > 0 and models > 0, 'EMPTY_FIT_AUDIT')
    dump('FIT_RECEIPT_VALIDATION.json', dict(time=now(), PASS=True, prediction_receipts=count,
         checkpoints=models, prediction_bytes_unchanged=True, checkpoint_bytes_unchanged=True,
         refitting_performed=False))
    print('FIT RECEIPTS PASS', count, models, flush=True)


if __name__ == '__main__':
    main()
