"""Run the actual integrated source with a denied real model constructor."""
from pathlib import Path
from datetime import datetime,timezone
import contextlib,io,json,re,sys,time
sys.path.insert(0,'D:/MobileESS_v42_autonomous')
import gurobipy as gp
# Capture the real protected Native descriptor before denying constructors.
from v42_autonomous_b2 import rmp_presolve,pricing_cache
from v42_autonomous_b2.worker import sources
from v42_b2_seed_recovery_v19.common import record,digest
from unittest.mock import patch
import pytest
ROOT=Path('D:/v42_may_restart_20261010_02')
REPO=Path('D:/MobileESS_v42_autonomous')
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
folder=ROOT/'autonomous'/('source30_regression_'+stamp);folder.mkdir()
execution=sources();assert len(execution)==98
before={p:record(REPO/p) for p in execution}
attempts=[]
def denied(*args,**kwargs):
    attempts.append(dict(args=repr(args),kwargs=repr(kwargs)))
    raise AssertionError('SOURCE30_REAL_NATIVE_MODEL_CONSTRUCTION_FORBIDDEN')
test_files=['tests/test_v42_autonomous_b2.py',
    'tests/test_v42_autonomous_b2_f1_basis.py',
    'tests/test_v42_autonomous_b2_f1_state.py',
    'tests/test_v42_autonomous_b2_projection_cache.py',
    'tests/test_v42_autonomous_b2_rmp_presolve.py']
args=test_files+['-q','--basetemp',str(REPO/('.pytest_tmp_v31_integrated_'+stamp))]
stdout=io.StringIO();stderr=io.StringIO();start=time.perf_counter()
with patch.object(gp,'Model',denied),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
    exit_code=int(pytest.main(args))
elapsed=time.perf_counter()-start
out=stdout.getvalue();err=stderr.getvalue()
(folder/'stdout.txt').write_text(out,encoding='utf-8')
(folder/'stderr.txt').write_text(err,encoding='utf-8')
after={p:record(REPO/p) for p in execution}
matched=re.search(r'(\d+) passed',out)
doc=dict(schema='V42_SOURCE30_INTEGRATED_NATIVE_DENIED_PRODUCTION_REGRESSION',
    UTC=datetime.now(timezone.utc).isoformat(),PASS=exit_code==0 and not attempts and before==after,
    exit_code=exit_code,tests_passed=int(matched.group(1)) if matched else None,
    wall_seconds=elapsed,pytest_arguments=args,repair_source_SHA=digest(execution),
    source_files=list(before.values()),test_files=[record(REPO/p) for p in test_files],
    source_files_unchanged=before==after,real_Native_model_constructor_attempts=attempts,
    real_Native_model_constructions=0,Native_optimize_calls=0,
    synthetic_budget_receipts_are_not_Native_measurements=True,
    stdout=record(folder/'stdout.txt'),stderr=record(folder/'stderr.txt'),
    runner=record(__file__),actual_full_case_performance_or_final_PASS_claimed=False)
target=folder/'V31_INTEGRATED_NATIVE_DENIED_REGRESSION.json'
target.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=doc['PASS'],tests=doc['tests_passed'],wall_seconds=elapsed,
    receipt=record(target)),ensure_ascii=False))
if not doc['PASS']:
    print(out);print(err);raise SystemExit(1)
