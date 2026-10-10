"""Read-only production admission and saved-byte checks; no DSS/native calls."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--freeze', required=True, type=Path)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.source.resolve()))
    from v42_voltage_control import authority
    from v42_b3_joint.contracts import digest
    from v42_pr134_b1.common import read, record
    from v42_may_campaign_native90.preflight import native_zero
    sources = authority.source_files()
    source_sha = digest(sources)
    freeze_receipt = record(args.freeze)
    with native_zero() as attempts:
        freeze, scenario = authority.verify_frozen_infrastructure(freeze_receipt, source_sha)
        archive = read(authority.checked(freeze['source_archive_receipt']))
        for row in archive['files'] + archive['external_files']:
            assert record(row['archived']['path']) == row['archived']
            assert record(authority.checked(row['original'])) == dict(row['original'], path=str(authority.checked(row['original'])))
        assert not attempts
    assert authority.source_files() == sources
    result = dict(schema='V42_SVR_FROZEN_INFRASTRUCTURE_READ_ONLY_ADMISSION_AUDIT_V2',
        PASS=True, source_SHA=source_sha, scenario_SHA=scenario['scenario_SHA'],
        infrastructure_variant=freeze.get('infrastructure_variant','SVR4'),
        hardware_freeze_receipt=freeze_receipt,
        source_initial_state_SHA=freeze['source_initial_state_SHA'],
        saved_archive_original_and_copy_rows_checked=len(archive['files'])+len(archive['external_files']),
        native_literal_initial_state_verifier='v42_voltage_control.authority.verify_frozen_infrastructure',
        Native_optimizer_calls=0, OpenDSS_solve_calls=0, Source_and_tests_edits=0,
        verified_scope='hardware-only frozen existing-plan replay admission; no model/E2E/all31 qualification',
        source_manifest_before_after_equal=True, verification_script=record(__file__))
    if args.receipt:
        with args.receipt.open('x', encoding='utf8') as stream:
            json.dump(result,stream,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write('\n')
    print(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False))


if __name__ == '__main__':
    main()
