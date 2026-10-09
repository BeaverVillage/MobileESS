"""Only this isolated IEEE8500 test namespace; no production dispatch."""
import sys
from pathlib import Path
import importlib.metadata
import platform
import subprocess
import re
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from ieee8500_v42.common import REPORT,write,receipt


def ids(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from ids(item)
        else:yield item.id()


def run():
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_ieee8500_v42_*.py')
    test_ids=list(ids(suite));log=REPORT/'FINAL_LIGHTWEIGHT_TEST_LOG.txt';started=time.perf_counter()
    with log.open('w',encoding='utf8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    # These five artifact-corruption checks use pytest fixtures and therefore
    # are imported but not collected by unittest.discover.
    saved_auto=ROOT/'tests/test_ieee8500_v42_saved_auto_port_audit.py'
    extra=subprocess.run([sys.executable,'-B','-X','utf8','-m','pytest','-q',str(saved_auto)],
                         cwd=ROOT,capture_output=True,text=True,encoding='utf8')
    extra_log=REPORT/'FINAL_SAVED_AUTO_TEST_LOG.txt'
    extra_log.write_text(extra.stdout+extra.stderr,encoding='utf8')
    matches=re.findall(r'\b(\d+) passed\b',extra.stdout)
    extra_passed=int(matches[-1]) if matches else 0
    passed=result.wasSuccessful() and extra.returncode==0 and extra_passed==5
    versions={}
    for package in ('numpy','scipy','pandas','matplotlib','opendssdirect.py','dss-python','dss-python-backend','pytest','gurobipy'):
        try:versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:versions[package]='UNAVAILABLE'
    doc=dict(PASS=passed,test_count=result.testsRun+extra_passed,
        unittest_count=result.testsRun,additional_pytest_count=extra_passed,additional_pytest_exit_code=extra.returncode,
        additional_pytest_log=receipt(extra_log),failures=len(result.failures),errors=len(result.errors),
        skipped=len(result.skipped),test_ids=test_ids,elapsed_seconds=time.perf_counter()-started,
        interpreter=platform.python_version(),packages=versions,log=receipt(log),
        scope='real original OpenDSS regression and portable geometry/data/contract tests; fixture contracts are not Native/Production certification',
        production_native_calls=0,full_model_builds=0)
    write(REPORT/'FINAL_LIGHTWEIGHT_TEST_RECEIPT.json',doc)
    print(f"IEEE8500 isolated tests: {result.testsRun}+{extra_passed} unique tests; PASS={passed}",flush=True)
    if not passed:
        print(log.read_text(encoding='utf8'))
        print(extra_log.read_text(encoding='utf8'))
        raise SystemExit(1)


if __name__=='__main__':run()
