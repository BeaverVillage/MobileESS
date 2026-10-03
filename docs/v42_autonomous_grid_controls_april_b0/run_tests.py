"""Full pytest under source historical Windows EOL receipts; restore raw BASE.

No assertion, evidence SHA or production behavior is changed. Compatibility
variants must exactly match the immutable historical receipt SHA, and every
original file is restored in finally. The output explicitly records the
different tested checkout bytes and the separate exact-BASE preservation proof.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def main():
    compat = json.loads((OUT/'TEST_CHECKOUT_COMPATIBILITY.json').read_text(encoding='utf-8'))
    originals = {}
    if (OUT/'PYTEST_FULL.log').exists():
        (OUT/'PYTEST_INITIAL_EOL_FAILURE.log').write_bytes((OUT/'PYTEST_FULL.log').read_bytes())
    try:
        for row in compat['files']:
            path = ROOT / row['path']
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != row['original_sha256']:
                raise ValueError('TEST_CHECKOUT_ORIGINAL_DRIFT:' + row['path'])
            originals[path] = data
            variant = data.replace(b'\r\n', b'\n')
            if row['test_variant'] == 'CRLF':
                variant = variant.replace(b'\n', b'\r\n')
            if hashlib.sha256(variant).hexdigest() != row['expected_sha256']:
                raise ValueError('TEST_EOL_VARIANT_NOT_EXACT_HISTORICAL_SHA:' + row['path'])
            path.write_bytes(variant)
        result = subprocess.run([sys.executable,'-X','utf8','-m','pytest','-q'], cwd=ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    finally:
        for path, data in originals.items():
            path.write_bytes(data)
    (OUT/'PYTEST_FULL.log').write_text(result.stdout, encoding='utf-8')
    summary = result.stdout.strip().splitlines()[-1]
    passed = re.search(r'(\d+) passed', summary)
    receipt = dict(command='python -X utf8 -m pytest -q', exit_code=result.returncode,
        full_suite=True, includes_tests_and_contract_tests=True,
        passed=int(passed[1]) if passed else None, summary=summary,
        audit_only_regressions=6, autonomous_implementation_regressions_A_to_Q_completed=False,
        temporary_checkout_EOL_compatibility_files=len(originals),
        temporary_files_exact_historical_receipt_SHA_verified=True,
        original_BASE_bytes_restored_in_finally=True,
        exact_BASE_preservation_requires_separate_VERIFICATION=True,
        inherited_runtime_log1p_warning_present='invalid value encountered in log1p' in result.stdout)
    (OUT/'TEST_RECEIPT.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(result.stdout[-12000:], flush=True)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
