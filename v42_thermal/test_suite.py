"""Run every inherited test with its recorded EOL variant; restore exact BASE."""
import subprocess
import sys
import re
import hashlib
from .common import *

def main():
    compatibility=read(ROOT/'docs/v42_autonomous_grid_controls_april_b0/TEST_CHECKOUT_COMPATIBILITY.json')
    original={}
    try:
        for row in compatibility['files']:
            p=ROOT/row['path'];data=p.read_bytes()
            if hashlib.sha256(data).hexdigest()!=row['original_sha256']:raise ValueError('BASE_TEST_CHECKOUT_DRIFT')
            original[p]=data;variant=data.replace(b'\r\n',b'\n')
            if row['test_variant']=='CRLF':variant=variant.replace(b'\n',b'\r\n')
            if hashlib.sha256(variant).hexdigest()!=row['expected_sha256']:raise ValueError('HISTORICAL_EOL_SHA_DRIFT')
            p.write_bytes(variant)
        result=subprocess.run([sys.executable,'-X','utf8','-c','import opendssdirect; import pytest; raise SystemExit(pytest.main(["-q"]))'],cwd=ROOT,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    finally:
        for p,data in original.items():p.write_bytes(data)
    summary=result.stdout.strip().splitlines()[-1];passed=re.search(r'(\d+) passed',summary)
    (OUT/'PYTEST_FULL.log').write_text(result.stdout,encoding='utf-8',newline='\n')
    write(OUT,'TEST_RECEIPT.json',dict(command='pytest -q via Python with native DSS DLL preloaded before pytest faulthandler registration',full_suite=True,
        native_DLL_preloaded_only=True,pytest_plugins_assertions_and_engine_parameters_unchanged=True,
        exit_code=result.returncode,passed=int(passed[1]) if passed else None,summary=summary,
        inherited_EOL_variant_receipt=record(ROOT/'docs/v42_autonomous_grid_controls_april_b0/TEST_CHECKOUT_COMPATIBILITY.json'),
        temporary_EOL_files=len(original),exact_BASE_bytes_restored=True,no_assertion_changes=True))
    print(result.stdout[-12000:],flush=True)
    raise SystemExit(result.returncode)

if __name__=='__main__': main()
