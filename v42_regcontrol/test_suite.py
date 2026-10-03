"""All pytest, preserving exact BASE after historical Windows EOL compatibility."""
import subprocess
import sys
import hashlib
import re
from .common import *


def main():
    compatibility=read(AUDIT/'TEST_CHECKOUT_COMPATIBILITY.json')
    originals={}
    try:
        for row in compatibility['files']:
            p=ROOT/row['path']; data=p.read_bytes()
            if hashlib.sha256(data).hexdigest()!=row['original_sha256']:
                raise ValueError('BASE_TEST_CHECKOUT_DRIFT')
            originals[p]=data; variant=data.replace(b'\r\n',b'\n')
            if row['test_variant']=='CRLF': variant=variant.replace(b'\n',b'\r\n')
            if hashlib.sha256(variant).hexdigest()!=row['expected_sha256']:
                raise ValueError('HISTORICAL_EOL_SHA_MISMATCH')
            p.write_bytes(variant)
        result=subprocess.run([sys.executable,'-X','utf8','-m','pytest','-q'],cwd=ROOT,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    finally:
        for p,data in originals.items(): p.write_bytes(data)
    summary=result.stdout.strip().splitlines()[-1]; passed=re.search(r'(\d+) passed',summary)
    (OUT/'PYTEST_FULL.log').write_text(result.stdout,encoding='utf-8')
    write(OUT,'TEST_RECEIPT.json',dict(command='python -X utf8 -m pytest -q',
        full_suite_including_contract_tests=True,exit_code=result.returncode,
        passed=int(passed[1]) if passed else None,summary=summary,
        inherited_windows_EOL_compatibility=record(AUDIT/'TEST_CHECKOUT_COMPATIBILITY.json'),
        temporary_EOL_files=len(originals),original_BASE_bytes_restored=True,
        native_real_source_fixtures_in_standalone_subprocess=True,
        no_pytest_assertion_or_historical_manifest_changes=True,
        regressions_A_to_W='source, implementation, real source fixtures, 3/30-day measured receipts, identity/axes/firewalls'))
    print(result.stdout[-16000:],flush=True)
    raise SystemExit(result.returncode)


if __name__=='__main__': main()
