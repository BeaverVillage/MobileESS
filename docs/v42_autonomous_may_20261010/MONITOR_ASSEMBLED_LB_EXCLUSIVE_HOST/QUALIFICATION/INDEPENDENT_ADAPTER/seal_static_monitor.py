from pathlib import Path
import hashlib, json
from datetime import datetime, timezone

folder=Path('D:/v42_monitor_assembled_lb_independent_review_20261010_01')
repo=Path('D:/MobileESS_v42_autonomous')
helper=Path('D:/v42_may_restart_20261010_02/autonomous/reload_owned_monitor_assembled_lb.py')
def record(path):
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
receipt=folder/'MONITOR_ASSEMBLED_LB_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json'
assert record(receipt)['sha256']=='36ca9a1e0736426a11bd9d418a741cf45346e23d866ef8eb4d9f4a81d4e63a66'
expected={
 'v42_autonomous_monitor/current_certificates.py':'678aa1378bf72aa4830d7a782366f7d1fc81fe310a04086c971247a8eb18dcf7',
 'v42_autonomous_monitor/monitor.py':'ab5f9d2f2a5f9a8451c71653df2eaf4c27d04bc9c73b8b3f7206de24d3457885',
 'tests/test_v42_autonomous_monitor_assembled_lb.py':'545af951a2636af7b35f4b7ec1bb381a09335ef1dfb77dfed7f34dc33cf56fe1'}
sources={name:record(repo/name) for name in expected}
assert all(sources[name]['sha256']==sha for name,sha in expected.items())
assert record(helper)['sha256']=='aebfd58534243990fd35dc99c743cec0616d1934586b768822ad93dcac58fb4a'
value=dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),independent_test_receipt=record(receipt),
 tests=97,Native_optimize_calls=0,real_Native_model_constructions=0,modelattempts=[],nativeattempts=[],
 source_records=sources,original_certificate_reader=record(repo/'v42_b2_monitor_v16/certificates.py'),helper=record(helper),
 monitor_contract=[
 'current_certificates.py:47-81 binds current request/case/manifest/execution and original source hashes to one exact source root and owned transport receipt.',
 'current_certificates.py:84-149 requires complete original-row/column decomposition, original integer containment, exact rational nested certificate, owned raw full dual SHA and canonical rational sparse SHA, original unchanged-checker/full-box proof, exact frontier LB.',
 'current_certificates.py:152-181 retains original flat reader, binds nested current source/attempt and exact UB/LB/gap without clamping.',
 'monitor.py:174,352,417 provides current request/source/attempt metadata and returns UNKNOWN on failure; no science/Native change.',
 'Adapter sealed reads parse the exact same raw bytes whose SHA was checked; cache keys include path/SHA/stat; mutation/partial/wrong-source/current-case/path/gap fixtures passed.'
 ],helper_contract=[
 'reload helper:30 + recovery.py:248 requires ACTIVE matching token, live guardian identity and held actual OS repair lock.',
 'reload helper:31-38 requires exact display PID102084/create/command/cwd, pythonw module and owned localhost8794 listener.',
 'reload helper:39-56 snapshots exactly three current D35 worker process/request identities and Native ledgers with source a8cb6983..., ceiling5400/P2zero, plus supervisor107788 identity.',
 'reload helper:63-67 has one termination target, the exact owned display host; replacement uses same command/cwd hidden.',
 'reload helper:68-94 requires replacement identity, three current-source CERTIFIED rows, positive first-two LB; rechecks each worker/request/completed Native prefix/runtime monotonicity, supervisor identity and control source bytes.'
 ],findings=[],limits=[
 'Static helper review only; no helper/reload/HTTP/production process actions executed by this reviewer.',
 'Independent test receipt establishes current frozen1111, Repo science1106 and original certificate reader unchanged before/end under model/Native denial.',
 'Actual saved certificate display reads are verified wrapper/hash/exact-bound evidence; no fresh matrix/checker replay, final gap<=3%, Actual/Fresh scientific PASS or performance claim.'
 ])
out=folder/'MONITOR_ASSEMBLED_LB_STATIC_AND_RELOAD_HELPER_READONLY_REVIEW.json'
assert not out.exists()
out.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record(out)))
