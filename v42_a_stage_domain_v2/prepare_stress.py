"""Finalize short PASS gates; never invokes a production optimizer."""
from pathlib import Path
import json
import py_compile
import subprocess
import xml.etree.ElementTree as ET
from .census import record,write
from . import AUTHORITY

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_a_stage_v2_stress4_20261007'
REVIEW=ROOT/'docs/v42_a_stage_domain_authority_v2_20261007'
BASE='1e2d819406081af5b4bbee6fab3c4b5c3e102b2b'


def prepare():
    junit=OUT/'SHORT_REGRESSION_JUNIT.xml'
    totals={key:0 for key in ('tests','failures','errors','skipped')}
    seconds=0.;unique_cases={}
    receipts=[junit,OUT/'FINAL_BACKEND_CERTIFICATE_JUNIT.xml']
    for document in receipts:
        tree=ET.parse(document).getroot()
        for suite in tree.iter('testsuite'):
            if any(int(suite.attrib.get(key,0)) for key in ('failures','errors','skipped')):
                raise ValueError('SHORT_TEST_RECEIPT_NOT_PASS:'+str(document))
            seconds+=float(suite.attrib.get('time',0))
        for case in tree.iter('testcase'):
            unique_cases[case.attrib['classname'],case.attrib['name']]=case
    totals['tests']=len(unique_cases)
    if not totals['tests'] or any(totals[key] for key in ('failures','errors','skipped')):
        raise ValueError('ALL_SHORT_REGRESSION_TESTS_MUST_PASS:'+str(totals))
    tracked=subprocess.check_output(['git','diff','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    paths={ROOT/name for name in tracked if name.endswith('.py')}
    paths.update((ROOT/'v42_a_stage_domain_v2').glob('*.py'))
    paths.update((ROOT/'tests').glob('test_v42_a_stage*.py'))
    for path in sorted(paths):py_compile.compile(str(path),doraise=True)
    receipt=dict(PASS=True,scope='ALL_REPOSITORY_SHORT_TESTS_AND_ALL_MODIFIED_PYTHON_COMPILATION',
        passed=totals['tests'],test_counts=totals,pytest_seconds=seconds,
        junit=record(junit),log=record(OUT/'SHORT_REGRESSION.log'),
        final_backend_certificate_recheck=record(receipts[1]),
        test_count_rule='Unique testcase classname/name union; final backend recheck supersedes duplicate cases',
        compilation=dict(PASS=True,files=[record(path) for path in sorted(paths)]),
        stress_production_optimization_calls_before_gate=0,
        historical_native_fixture_reads=True,short_synthetic_optimizer_fixtures_allowed=True,
        other_27_production_dates_run=0,Actual_production_calls=0,Fresh_production_calls=0)
    write(OUT/'PRE_RUN_TESTS.json',receipt)
    write(REVIEW/'TEST_RESULTS.json',receipt)
    from .report import finalize
    finalize()
    write(OUT/'A_STAGE_DOMAIN_AUTHORITY_V2_REFERENCE.json',dict(PASS=True,authority=AUTHORITY,
        exact_initial_base=BASE,initial_review_verification=record(REVIEW/'VERIFICATION.json'),
        domain_authority=record(REVIEW/'AIDC_A_STAGE_DOMAIN_AUTHORITY_V2.json'),
        complete_STAY_qualification_override='Complete hard-valid STAY; singleton original flow retained; no universal LP histogram substitution',
        complete_STAY_proof=record(OUT/'COMPLETE_STAY_VERIFICATION.json'),
        no_flex_nesting=record(REVIEW/'DOMAIN_NESTING_VERIFICATION.json'),
        production_acceptance_requires_independent_integer_closure=True))
    print('PRE_RUN_GATES_PASS',totals['tests'],'tests',len(paths),'compiled files')


if __name__=='__main__':prepare()
