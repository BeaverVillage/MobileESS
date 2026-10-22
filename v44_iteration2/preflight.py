"""Only light reads/contracts and scoped entry probes. Native and DSS are denied."""
from pathlib import Path
import unittest,time,io,traceback,ast
from . import config as c
from .io import read,record,atomic,now
from .archives import Store

def check():
 from .bootstrap import base
 from v42_may_campaign_native90.preflight import native_zero
 from v44_recovery_r038.cpu import placement
 from v44_recovery_r029.cpu_placement import windows_cpu_sets
 from v44 import svr12
 from unittest.mock import patch
 from .authority import sources
 started=time.monotonic();store=Store();margins=[]
 try:
  catalogue=read(c.DOC/'BASELINE_CATALOG.json');assert {r['day'] for r in catalogue['days']}==set(c.DAYS);assert catalogue['MESS_units']==list(c.FLEET)
  for row in catalogue['days']:
   for receipt in row['evidence']:
    actual=store.record(receipt['path'])
    if any(actual[k]!=receipt[k] for k in ('bytes','sha256')):raise ValueError('BASELINE_RECEIPT_DRIFT:'+receipt['path'])
   margin=Path(row['M1'])/'R030_M1_FULL_VOLTAGE_ROWS.json'
   margins.append(dict(day=row['day'],M1=row['M1'],explicit_original_margin_receipt=store.record(margin) if store.exists(margin) else None,policy='REUSE_EXACT_ORIGINAL_M1_WITHOUT_RETROACTIVE_POLICY_CLAIM'))
  for source in c.CODE.glob('*.py'):ast.parse(source.read_text(encoding='utf-8-sig'),filename=str(source))
  plan=placement(windows_cpu_sets(),7);atomic(c.DOC/'CPU_PLACEMENT.json',plan)
  # Test all core gates and original scoped worker entry. Any optimize or DSS
  # oracle construction in these tests is a failure, including hidden probes.
  suite=unittest.defaultTestLoader.discover(str(c.REPO/'tests_iteration2'),pattern='test_iteration2.py')
  output=io.StringIO()
  with native_zero() as denied,patch.object(svr12,'SVR12CurrentAC',side_effect=AssertionError('PREFLIGHT_DSS_FORBIDDEN')):
   result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
  value=dict(PASS=result.wasSuccessful() and not denied,UTC=now(),tests=result.testsRun,failed=len(result.failures),errors=len(result.errors),output=output.getvalue(),
   denied_Native_attempts=denied,Native_calls=0,Actual_or_Fresh_calls=0,baseline_dates=31,MESS_units=list(c.FLEET),cpu_placement=record(c.DOC/'CPU_PLACEMENT.json'),
   M1_original_policy=margins,sources=sources(),wall_seconds=time.monotonic()-started,
   production_models_built=False,B2_workers_or_ledgers_modified=False)
  atomic(c.DOC/'VALIDATION.json',value);atomic(c.DOC/'M1_REUSE_POLICY_DISCLOSURE.json',dict(days=margins,originals_modified=False))
  print(output.getvalue());print('VALIDATION_PASS',value['PASS'])
  if not value['PASS']:raise RuntimeError('ITERATION2_PREFLIGHT_FAILED')
  return value
 finally:store.close()
