from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
import json

REPO=Path(r'D:\MobileESS_v42_autonomous')
DEST=REPO/'docs/v42_autonomous_may_20261010/SOURCE34/RMP_REVIEW'
OWNER1=Path(r'D:\v42_rmp_current_start34_tests_20261010_01')
OWNER2=Path(r'D:\v42_rmp_current_start34_tests_20261010_02')
INDEPENDENT=Path(r'D:\v42_source34_independent_review_20261010_01')
HISTORY33=Path(r'D:\v42_source33_pdhg_review_20261010_01')

def receipt(path,data=None):
 path=Path(path).resolve();data=path.read_bytes() if data is None else data
 return dict(path=str(path),bytes=len(data),sha256=sha256(data).hexdigest())

assert not DEST.exists(),'PRESERVE_NEW_PACKAGE_ONLY'
copies=[]
for root,folder,names in (
 (OWNER1,'owner_history_01',[
  'INITIAL_UNKNOWN_EXPECTATION_FAILURE.txt','INITIAL_UNKNOWN_EXPECTATION_FAILURE.xml',
  'RMP_TEST_OUTPUT.txt','RMP_TEST_RESULT.xml','run_source34_native_denied_tests.py',
  'OWNER_STDOUT.txt','OWNER_STDERR.txt','SOURCE34_NATIVE_DENIED_TEST_RESULT.xml',
  'SOURCE34_RMP_CURRENT_START_NATIVE_DENIED_TEST_RECEIPT.json']),
 (OWNER2,'owner_final_02',[
  'run_source34_native_denied_tests.py','OWNER_STDOUT.txt','OWNER_STDERR.txt',
  'SOURCE34_NATIVE_DENIED_TEST_RESULT.xml','SOURCE34_RMP_CURRENT_START_NATIVE_DENIED_TEST_RECEIPT.json']),
 (INDEPENDENT,'independent_01',[
  'independent_review.py','SOURCE34_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json',
  'SOURCE34_NATIVE_DENIED_OUTPUT.log','SOURCE34_TWO_FILE_NORMALIZED_DIFF.patch']),
 (HISTORY33,'historical_Source33_selected214',[
  'run_source33_native_denied_tests.py','SOURCE33_F1_NATIVE_DENIED_TEST_RECEIPT_02.json',
  'SOURCE33_F1_NATIVE_DENIED_TEST_RESULT_02.xml','stdout_02.txt','stderr_02.txt']),
 (REPO,'owned_source',[
  'v42_autonomous_b2/rmp_presolve.py','tests/test_v42_autonomous_b2_rmp_presolve.py'])):
 for name in names:
  original=root/name;raw=original.read_bytes();target=DEST/folder/name
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as stream:stream.write(raw)
  assert target.read_bytes()==raw
  copies.append(dict(original=receipt(original,raw),copy=receipt(target),
                     relative_path=target.relative_to(DEST).as_posix(),raw_bytes_preserved=True))

owner=json.loads((OWNER2/'SOURCE34_RMP_CURRENT_START_NATIVE_DENIED_TEST_RECEIPT.json').read_bytes())
independent=json.loads((INDEPENDENT/'SOURCE34_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json').read_bytes())
failed=json.loads((OWNER1/'SOURCE34_RMP_CURRENT_START_NATIVE_DENIED_TEST_RECEIPT.json').read_bytes())
baseline=json.loads((HISTORY33/'SOURCE33_F1_NATIVE_DENIED_TEST_RECEIPT_02.json').read_bytes())
assert owner['PASS'] is True and owner['tests_passed']==244
assert independent['PASS'] is True and independent['tests_passed']==244
assert failed['PASS'] is False and failed['tests_passed']==243
assert baseline['PASS'] is True and baseline['tests_passed']==214
assert owner['execution_SHA']==independent['execution_SHA']=='dd14a820e9b65f35e13827d89143bca22e656abd10365fe5b96dd04b40160016'
assert owner['source_file_count']==independent['source_file_count']==1105
assert receipt(REPO/'v42_autonomous_b2/rmp_presolve.py')['sha256']=='e588518a24348741f26704bc9de9a053858c63a8c494d6cd0e687735c1bc839f'
assert receipt(REPO/'tests/test_v42_autonomous_b2_rmp_presolve.py')['sha256']=='6a9dac43025f1a412fbb1fc8a7ffec429d65b9884f0af2af2cb99ab24a53bd7e'
assert receipt(INDEPENDENT/'SOURCE34_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json')['sha256']=='a7539f596e4bf64f13f2412e4fff6e7d8b80b1dc19a10fc457a348c32323bce7'

readme='''# Source34 RMP review evidence

Owner and independent selected suites each passed 244 cases with protected original preloads followed by denial of `gp.Model`, the retained real model constructor, and retained real optimize. Both report zero real Native/model calls, empty attempts, identical 1105 source-file and 98 execution-source start/end bindings. Original 1007 source files and the other 97 Source33 execution files remain identical. These are small fixture/code/guard tests; fixture Runtime values are synthetic. They do not certify actual solver start use, basis quality, performance, Global LB improvement, or a daily PASS.

The candidate retains the original single RMP30 call, Method1, Presolve0, Threads1, original precision and Crossover, budget/source/model/closure guards, original row/Pi pullback, and original scientific checkers. It installs complete current-attempt PStart (current nonunit values, first actual own seed lambda1 per unit, other lambdas0) and computational zero DStart with LPWarmStart2 only at the admitted entry. Current FULL and original/scaled RMP residual checks are recorded separately; a start is a hint and has no feasibility/UB/LB or measured Native Pi authority. Ineligible hints use the original cold call. Partial installation failure remains a failure with original UNKNOWN accounting when Runtime is unavailable. Native completion is followed by no start setter, update, or start readback; original disposal is retained.

`owner_history_01` preserves raw development and failed harness artifacts. The focused initial UNKNOWN test failed because its expectation named the install exception; the unchanged original budget preserves that error in the ledger and reissues `NATIVE_RUNTIME_UNAVAILABLE_QUARANTINE`. The saved focused XML contains one failed test. The initial 99-case attempt stopped after 93 passes and that failure; a later direct 99-case run passed and its stdout/XML are included. The full first selected suite has exactly 243 passes and one failure: its external basetemp violated an existing protected-source test's explicit checkout-inside fixture requirement. Its raw XML, stdout, empty stderr, runner, and PASS=false receipt are unchanged. The final `_02` harness uses the same Repo/tmp fixture placement as the existing Source33 runner and passed all 244 without a science-file change between the two selected runs. Tool-only development outputs without a saved raw file are not represented here as archived raw artifacts.

`historical_Source33_selected214` is the original Source33 214-case owner baseline. It is historical, not a newly executed Source33 suite or actual Source34 daily run. `owned_source` preserves only the reviewed RMP module and existing RMP test file. Root reported Source34 science commit `cae08b21cb83864887e397805c0a6a8944da7f83`, immutable D:/v42run34 freeze1110 and smoke Native0 PASS; this package independently covers review files only. Root packages deployment evidence separately. No Git staging/commit/push, Native solve, worker/process/queue or immutable-source changes were performed to assemble it.

`PROVENANCE_SHA_INDEX.json` maps every copied file to its original absolute path, byte count and SHA256. Raw JSON, XML, scripts, stdout/stderr and patch bytes were copied without normalization. `SHA_INVENTORY.json` covers all package files except itself.
'''
(DEST/'README.md').write_bytes(readme.encode('utf8'))
index=dict(schema='V42_SOURCE34_RMP_REVIEW_RAW_PROVENANCE_V1',UTC=datetime.now(timezone.utc).isoformat(),
 PASS=True,raw_copy_count=len(copies),copies=copies,
 owner_final=receipt(OWNER2/'SOURCE34_RMP_CURRENT_START_NATIVE_DENIED_TEST_RECEIPT.json'),
 independent=receipt(INDEPENDENT/'SOURCE34_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json'),
 original_failed_harness=receipt(OWNER1/'SOURCE34_RMP_CURRENT_START_NATIVE_DENIED_TEST_RECEIPT.json'),
 Source33_selected214_is_historical=True,actual_Native_or_performance_or_daily_PASS_claimed=False,
 production_or_immutable_or_worker_or_queue_or_process_or_Git_mutations=0)
(DEST/'PROVENANCE_SHA_INDEX.json').write_bytes((json.dumps(index,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
script_raw=Path(__file__).read_bytes()
(DEST/'preserve_source34_rmp_docs.py').write_bytes(script_raw)
inventory=dict(schema='V42_SOURCE34_RMP_REVIEW_SHA_INVENTORY_V1',UTC=datetime.now(timezone.utc).isoformat(),
 files={p.relative_to(DEST).as_posix():receipt(p) for p in sorted(DEST.rglob('*')) if p.is_file()})
(DEST/'SHA_INVENTORY.json').write_bytes((json.dumps(inventory,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
for item in copies:assert receipt(item['original']['path'])==item['original'] and receipt(item['copy']['path'])==item['copy']
print(json.dumps(dict(PASS=True,raw_copies=len(copies),total_files=len(inventory['files'])+1,
 inventory=receipt(DEST/'SHA_INVENTORY.json'),provenance=receipt(DEST/'PROVENANCE_SHA_INDEX.json'),
 copied_bytes=sum(v['copy']['bytes'] for v in copies)),ensure_ascii=False,indent=2))
