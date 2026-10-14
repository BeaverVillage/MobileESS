"""Verify repair package identity without optimization or Actual replay."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.frozen_unknown import FrozenUnknownPolicy
from v42_integration.policy import digest

REQUIRED=(
    'KNOWN_UNKNOWN_ARCHITECTURE_CORRECTION_KO.md',
    'KNOWN_PLANNING_SCHEDULE_EXECUTION_AUDIT.json',
    'UNKNOWN_POLICY_COMPILER_SPEC.json','UNKNOWN_FROZEN_POLICY_TABLE.json',
    'UNKNOWN_POLICY_COVERAGE_AUDIT.json','UNKNOWN_ACTION_ALTERNATIVE_RANKING.csv',
    'UNKNOWN_RESOURCE_STATE_LOOKUP_TEST.json','UNKNOWN_COMMAND_REVALIDATION_BEFORE_AFTER.csv',
    'KNOWN_UNKNOWN_UID_ACTION_FUSION_AUDIT.json','UNKNOWN_GPUH_ALLOCATION_EFFECT.csv',
    'UNKNOWN_POLICY_Q50_Q90_GRID_RISK.json','V42_POLICY_INTEGRATION_SOURCE_MANIFEST.json',
    'V42_UNKNOWN_CONTROL_FINAL_KO.md')


def main(output):
    documents={p.name:json.loads(p.read_text(encoding='utf8')) for p in output.glob('*.json')}
    manifest=documents['V42_POLICY_INTEGRATION_SOURCE_MANIFEST.json']
    for relative,record in manifest['source_files'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==record['sha256'],relative
    spec=documents['UNKNOWN_POLICY_COMPILER_SPEC.json']
    science=digest(dict(parent=manifest['parent_PR226_HEAD'],
        source_files={k:v['sha256'] for k,v in manifest['source_files'].items()},compiler_spec=spec))
    assert science==manifest['correction_science_sha']
    policy=FrozenUnknownPolicy.load(output/'UNKNOWN_FROZEN_POLICY_TABLE.json')
    assert policy.sha==manifest['fixture_policy_sha']
    assert policy.sha==FrozenUnknownPolicy.load(output/'FIXTURE_FROZEN_UNKNOWN_POLICY.json').sha
    assert policy.document['evidence_kind']=='NAMED_SYNTHETIC_TWO_AIDC_TEMPLATE_NOT_MAY01'
    assert policy.document['compiler_source_sha']==manifest['source_files']['v42_integration/frozen_unknown.py']['sha256']
    cases=list(ET.parse(output/'REGRESSION_TESTS.xml').iter('testcase'))
    assert len(cases)==manifest['tests_passed'] and all(not len(c) for c in cases)
    assert len(documents['REQUIRED_CONTRACT_TEST_RESULTS.json']['contracts'])==27
    assert documents['NATIVE0_AUDIT_RECEIPT.json']['Solver_ledger_preserved_seconds']==621.2855198158068
    assert manifest['campaign_HOLD'] and manifest['Native_Optimize_calls']==manifest['Fresh_AC_calls']==0
    subprocess.run(['git','merge-base','--is-ancestor',manifest['parent_PR226_HEAD'],'HEAD'],cwd=ROOT,check=True)
    assert not subprocess.check_output(['git','diff',manifest['parent_PR226_HEAD'],'--',
        'docs/v42_flex30_adjustment_diagnosis_20261014',
        'docs/v42_experimental_flex_qos_20261014'],cwd=ROOT)
    required_receipts=[]
    for name in REQUIRED:
        path=output/name
        assert path.is_file() and path.stat().st_size>0,name
        if path.suffix=='.csv':
            with path.open(encoding='utf-8-sig',newline='') as stream:
                rows=list(csv.DictReader(stream));assert rows and all(None not in r for r in rows),name
        required_receipts.append(dict(file=name,bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    receipt=dict(PASS=True,required_artifacts=required_receipts,required_artifacts_count=len(REQUIRED),
        regression_tests=len(cases),named_contracts=27,correction_science_sha=science,
        Source_code_and_policy_SHA_verified=True,original_PR226_evidence_unchanged=True,
        campaign_HOLD=True,Native_Optimize_calls=0,Fresh_AC_calls=0,
        real_May01_policy_full96_compilation='NOT_RUN',real_grid_improvement='NOT_CERTIFIED')
    (output/'ARTIFACT_PACKAGE_AUDIT.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='required_artifacts'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args().output)
