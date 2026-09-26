"""Read-only post-run preservation audit of the original frozen authorities."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import *


def main():
    require(read('VALIDATION.json')['PASS'], 'POST_RUN_VALIDATION_REQUIRED')
    legacy = read('MOE_BASELINE_REPRODUCTION.json')
    require(sha(LEGACY/'kestrel_preissue_normalized.parquet') == legacy['source_sha256'], 'LEGACY_SOURCE_CHANGED')
    require(sha(LEGACY/'window_predictions/1742652000.parquet') == legacy['reference_sha256'], 'LEGACY_REFERENCE_CHANGED')
    require(sha(RAW) == read('PREPARATION_COMPLETE.json')['archive_sha256'], 'RAW_ARCHIVE_CHANGED')
    count = 0
    for record in read('MODERN_BASELINE_REPRODUCTION.json')['days']:
        day = record['day']
        snapshot = Path('D:/ChatGPT/Mobile ESS 2/CC4_FORENSIC_20260922/evidence/V41R4_May2025_raw/frozen_artifacts/v41r4_may/loop_wall_v4')/day/'B0/dayahead/ml/ML_SNAPSHOT.json'
        authority = json.loads(snapshot.read_text(encoding='utf-8'))
        require(sha(Path(authority['model']['path'])) == record['model_sha256'], 'PRODUCTION_MODEL_CHANGED')
        require(sha(Path(authority['preprocessing']['path'])) == record['preprocessing_sha256'], 'PRODUCTION_PREPROCESSOR_CHANGED')
        require(sha(SNAP/day/'V37_R4A_D1_SNAPSHOT.parquet') == record['snapshot_sha256'], 'FROZEN_FEATURE_SNAPSHOT_CHANGED')
        require(authority['runtime_training_membership_hash'] == record['training_membership_hash'], 'PRODUCTION_MEMBERSHIP_CHANGED')
        count += 1
    inventory = read('HPC_SOURCE_INVENTORY.json')
    require(subprocess.check_output(['git','rev-parse','HEAD'], cwd=HPC).decode().strip() == inventory['git_HEAD'], 'HPC_SOURCE_COMMIT_CHANGED')
    for record in inventory['source_files']:
        require(sha(HPC/record['path']) == record['sha256'], 'HPC_SOURCE_BYTES_CHANGED')
    dump('AUTHORITY_PRESERVATION_VALIDATION.json', dict(time=now(), PASS=True,
         frozen_production_days=count, HPC_source_files=len(inventory['source_files']),
         legacy_source_and_reference_unchanged=True, raw_archive_unchanged=True,
         production_models_preprocessors_snapshots_unchanged=True, read_only=True))
    print('FROZEN AUTHORITY PRESERVATION PASS', count, len(inventory['source_files']), flush=True)


if __name__ == '__main__':
    main()
