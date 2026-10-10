"""External prototype tests only; deny all actual Gurobi model/Native entries."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
PROPOSAL = Path(r'D:\v42_source36_pdhg_diagnostics_draft_20261010_01')
sys.path.insert(0, str(PROPOSAL))


def record(path):
    raw = Path(path).read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def main():
    import pytest
    import gurobipy as gp
    import pdhg_observer
    freeze = json.loads(Path(r'D:\v42_may_restart_20261010_02\autonomous\V35_SPARSE_IMMUTABLE_FREEZE.json').read_bytes())
    expected = {item['path']:item['sha256'] for item in freeze['source_files']}
    paths = [PROPOSAL/'pdhg_observer.py', OUT/'test_pdhg_observer_proposal.py',Path(__file__)]
    source_before = {str(path):record(path) for path in paths}
    frozen_before = {path:record(path)['sha256'] for path in expected}
    attempted = []
    def deny_model(*args, **kwargs):
        attempted.append('gurobipy.Model')
        raise AssertionError('EXTERNAL_PROPOSAL_REAL_MODEL_DENIED')
    def deny_init(*args, **kwargs):
        attempted.append('retained_Model.__init__')
        raise AssertionError('EXTERNAL_PROPOSAL_RETAINED_MODEL_DENIED')
    def deny_native(*args, **kwargs):
        attempted.append('retained_Model.optimize')
        raise AssertionError('EXTERNAL_PROPOSAL_REAL_NATIVE_DENIED')
    original = gp.Model
    xml = OUT/'external_proposal_native_denied.xml'
    callback_constants = {name:getattr(gp.GRB.Callback,name) for name in
        ['PDHG','RUNTIME',*pdhg_observer.FIELDS['PDHG']]}
    with patch.object(original,'__init__',deny_init),patch.object(original,'optimize',deny_native),patch.object(gp,'Model',deny_model):
        exit_code = pytest.main([str(OUT/'test_pdhg_observer_proposal.py'),'-q','--junitxml='+str(xml),
            '--basetemp='+str(Path(r'D:\MobileESS_v42_autonomous\tmp\external_pdhg_observer_proposal_tests'))])
    source_after = {str(path):record(path) for path in paths}
    frozen_after = {path:record(path)['sha256'] for path in expected}
    suites = ET.parse(xml).getroot()
    stats = {name:sum(int(s.get(name,'0')) for s in suites.iter('testsuite')) for name in
        ('tests','failures','errors','skipped')}
    checks = dict(external_simulated_observer_tests_PASS=exit_code==0 and stats['tests']>0
                  and stats['failures']==stats['errors']==0,
                  actual_model_native_attempts_zero=attempted==[],
                  external_source_test_producer_bytes_unchanged=source_before==source_after,
                  frozen_1111_before_end_matches_declared=frozen_before==frozen_after==expected,
                  official_callback_constants_present=True)
    value = dict(PASS=all(checks.values()), UTC=datetime.now(timezone.utc).isoformat(),
        schema='V42_EXTERNAL_PDHG_OBSERVER_PROPOSAL_NATIVE_DENIED_TEST_RECEIPT', checks=checks,
        test_statistics=stats, test_XML=record(xml), source_before=source_before, source_after=source_after,
        frozen_before=frozen_before,frozen_after=frozen_after, backend_version=list(gp.gurobi.version()),
        callback_constants=callback_constants, attempted_model_native_entries=attempted,
        Native_optimize_calls=0, real_model_constructions=0, production_mutations=0,
        prototype_NOT_production_admission_qualified=True,
        required_future_port_steps=[
            'Bind exact active F1 Scope/request/current case/model, declared immutable source and single original call before delegation.',
            'Retain incoming original callbackNone guard; attach observer only to the exact existing original Native delegation, preserving Runtime cap/accounting and UNKNOWN first.',
            'Seal and check observer/factory/caller callable identity/code and all retained callback/model bindings; public prototype fields are mutable.',
            'Use bounded diagnostic error aggregation per field with counts/latest receipt, avoiding repeated unbounded error-list growth.',
            'Keep original300/5400 Native caps, Threads and all math/precision/verification unchanged; callback overhead counts as actual Native Runtime.',
            'Publish owned supplemental diagnostics separately; scalar PDHG dual objective is not Native Pi or an independent Global LB.'
        ], limitations=[
            'Tests use simulated callback scalars and original accounting records; they are not actual solver callbacks or performance measurements.',
            'Prototype lacks production source/admission/factory guards and must not be directly integrated based on this PASS.',
            'No fresh scientific matrix replay, algorithm improvement, final3%gap or datePASS is claimed.'
        ])
    path = OUT/'EXTERNAL_PDHG_OBSERVER_PROPOSAL_NATIVE_DENIED_TEST_RECEIPT.json'
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(PASS=value['PASS'],stats=stats,receipt=record(path),prototype_only=True,
        attempted_entries=attempted,Native_optimize_calls=0)))
    return 0 if value['PASS'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
