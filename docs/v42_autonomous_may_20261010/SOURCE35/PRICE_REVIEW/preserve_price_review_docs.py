from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET

REPO=Path(r'D:\MobileESS_v42_autonomous')
DEST=REPO/'docs/v42_autonomous_may_20261010/SOURCE35/PRICE_REVIEW'
OWNER=Path(r'D:\v42_source35_owner_review_20261010_01')
INDEP=Path(r'D:\v42_source35_independent_review_20261010_01')
DRAFT=Path(r'D:\v42_f1_price_seed35_candidate_20261010_01')
PREVIOUS=REPO/'docs/v42_autonomous_may_20261010/SOURCE34/RMP_REVIEW/SHA_INVENTORY.json'
DIAGNOSIS=REPO/'docs/v42_autonomous_may_20261010/SOURCE35/DIAGNOSIS/SHA_INVENTORY.json'

def record(path,raw=None):
 path=Path(path).resolve();raw=path.read_bytes() if raw is None else raw
 return dict(path=str(path),bytes=len(raw),sha256=sha256(raw).hexdigest())

assert not DEST.exists(),'NEW_PRICE_REVIEW_PACKAGE_ONLY'
previous_before=record(PREVIOUS);diagnosis_before=record(DIAGNOSIS)
owner_path=OWNER/'SOURCE35_OWNER_SELECTED_NATIVE_DENIED_RECEIPT.json'
independent_path=INDEP/'SOURCE35_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json'
assert record(owner_path)['sha256']=='27b5a0fed3ea491e78d6f2c8bca315546e88e950a26cfff627af04f71c43229d'
assert record(independent_path)['sha256']=='cb5b009e1f1b0fefdbe064f3c45dd3bc56a30b5e1c683dd9cb915374f4c1547c'
owner=json.loads(owner_path.read_bytes());independent=json.loads(independent_path.read_bytes())
assert owner['PASS'] is True and owner['tests']==335 and independent['PASS'] is True and independent['tests_passed']==335
assert owner['execution_SHA']==independent['execution_SHA']=='a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'
assert owner['source_file_count']==independent['source_file_count']==1106
assert owner['execution_source_count']==independent['execution_source_count']==99
assert owner['Native_optimize_calls']==owner['real_Native_model_constructions']==0
assert independent['Native_optimize_calls']==independent['real_Native_model_constructions']==0
copies=[]
for source,folder,names in (
 (OWNER,'owner335', ['run_owner_review.py','SOURCE35_OWNER_SELECTED_NATIVE_DENIED_RECEIPT.json',
  'SOURCE35_OWNER_SELECTED_NATIVE_DENIED.xml']),
 (INDEP,'independent335', ['independent_review.py','SOURCE35_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json',
  'SOURCE35_NATIVE_DENIED_TEST_OUTPUT_01.log','SOURCE35_NATIVE_DENIED_TESTS_01.xml',
  'SOURCE35_PRODUCTION_STATIC_CONTRACT_REVIEW.json','SOURCE35_OPS_HELPERS_STATIC_READONLY_REVIEW.json']),
 (DRAFT,'retained_draft_history', ['candidate02.xml','candidate03.xml','candidate04.xml','candidate05.xml',
  'candidate06.xml','candidate07.xml','production_port01.xml','production_port02.xml','production_port03.xml',
  'price_seed.py','test_price_seed.py']),
 (DRAFT,'root_hook_preview', ['ROOT_HOOK35_STATIC_REVIEW.json','ROOT_HOOK35_TEST_ADDITIONS.py',
  'ROOT_WORKER35_HOOK_PREVIEW.py']),
 (REPO,'reviewed_source_bytes', ['v42_autonomous_b2/f1_price_seed.py','v42_autonomous_b2/worker.py',
  'tests/test_v42_autonomous_b2_f1_price_seed.py','tests/test_v42_autonomous_b2.py'])):
 for name in names:
  original=source/name;raw=original.read_bytes()
  if source==REPO:
   expected=owner['source_file_records'].get(name) or owner['test_file_records'][name]
   assert record(original,raw)==expected
  target=DEST/folder/name;target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as stream:stream.write(raw)
  assert target.read_bytes()==raw
  copies.append(dict(relative_path=target.relative_to(DEST).as_posix(),
   original=record(original,raw),copy=record(target),raw_bytes_preserved=True))

history=[]
for path in sorted((DEST/'retained_draft_history').glob('*.xml')):
 root=ET.parse(path).getroot();suites=list(root.iter('testsuite'))
 history.append(dict(raw_xml=record(path),tests=sum(int(v.attrib.get('tests',0)) for v in suites),
  failures=sum(int(v.attrib.get('failures',0)) for v in suites),
  errors=sum(int(v.attrib.get('errors',0)) for v in suites),
  source_state_is_historical_not_final335=True))
assert history[0]['tests']==42 and history[0]['failures']==2 and history[0]['errors']==0
readme='''# Source35 current F1 pricing-seed review

Owner and independent selected suites each passed 335 cases. The owner receipt SHA is `27b5a0fe...43229d`; independent is `cb5b009e...c1547c`. Both bind execution99 SHA `a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14`, all 1106 original+execution files, and identical source/execution/test start/end records. Actual backend `gp.Model`, retained constructor-init and optimize were denied after protected original preloads. Native and real model counts are zero and attempted real calls are empty. These test/qualification facts do not demonstrate actual pricing performance, Global LB improvement, a solver-native optimum, or a daily PASS.

The complete selected five-file suite includes retained F1 state/basis, RMP34, canonical worker CLI and current price-seed tests plus the four lazy Root hook cases. The unchanged pricing_cache120 review is carried as same-byte historical evidence and was not rerun by these commands. Original 1007 scientific files remain equal to immutable Source34; the old 97 other execution files, original physics/dual checker/Frontier/final bracket, precision, Threads1 and 120/300/5400 caps remain unchanged. The current same-attempt F1 price seed is a computational input; it does not replace the authoritative selected dual/bound. Actual improving bound adoption still needs the original independent full certificate and exact Frontier/packet gates.

Raw `retained_draft_history/candidate02.xml` has 42 cases with two failures and zero errors. Later draft XMLs record 44, 54, 61, 61 and 64 passing cases; the production-port milestones record 64, 81 and 87 passes. These reflect evolving historical source/test states, not the final 335 current-source review. Their XML bytes were copied unchanged; no failures, counts, paths or labels were normalized. Current draft code/test copies identify only the retained final draft bytes, not a reconstructed exact version for each earlier XML.

Root hook preview and its proposed-test source/static review are historical pre-integration artifacts. Its static receipt explicitly reports tests_executed0/proposed4; the integrated four lazy-hook cases are covered by the later 335 suite. Production/static ops helper reviews are separate read-only records, not actual deployment or Native performance. The owner runner returned stdout through its tool invocation and did not save a separate stdout/stderr file; its raw XML and JSON receipt are preserved. Independent raw output log and XML are preserved. No invented stdout or rerun history was added.

Root reports Source35 science commit `810f98a5`, sparse freeze1111 and smoke Native0 PASS. The raw owner/independent receipts retain their original commit-pending fields because qualification preceded commit. This package preserves review evidence only; Root packages actual deployment separately. Existing Source35 DIAGNOSIS and Source34 RMP_REVIEW files remain untouched. The established previous review path was found with rg; no duplicate guessed campaigns package was created.

`reviewed_source_bytes` contains raw copies of the final current price module/test and Root worker/base-test hooks matching the owner records. `PROVENANCE_SHA_INDEX.json` maps every copied artifact to the original absolute path, bytes and SHA256. `HISTORICAL_XML_OBSERVATION.json` records independently read historical counts without editing XML. `SHA_INVENTORY.json` covers all package files except itself. No scientific source/immutable/process/queue or Git staging/commit/push changes were performed to assemble this package.
'''
(DEST/'README.md').write_bytes(readme.encode('utf8'))
observation=dict(schema='SOURCE35_PRICE_REVIEW_RAW_HISTORICAL_XML_OBSERVATION_V1',UTC=datetime.now(timezone.utc).isoformat(),
 PASS=True,history=history,raw_xml_not_modified=True,
 candidate_code_or_actual_performance_or_daily_PASS_claimed_by_packager=False,
 owner_stdout_stderr_raw_file_not_saved=True,independent_raw_output_log_preserved=True,
 previous_Source34_review_inventory=previous_before,existing_DIAGNOSIS_inventory=diagnosis_before)
(DEST/'HISTORICAL_XML_OBSERVATION.json').write_bytes((json.dumps(observation,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
provenance=dict(schema='SOURCE35_PRICE_REVIEW_RAW_PROVENANCE_V1',UTC=datetime.now(timezone.utc).isoformat(),PASS=True,
 copies=copies,raw_copy_count=len(copies),owner=record(owner_path),independent=record(independent_path),
 no_raw_xml_JSON_or_script_normalization=True,no_invented_stdout_or_rerun_history=True)
(DEST/'PROVENANCE_SHA_INDEX.json').write_bytes((json.dumps(provenance,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
(DEST/'preserve_price_review_docs.py').write_bytes(Path(__file__).read_bytes())
inventory=dict(schema='SOURCE35_PRICE_REVIEW_SHA_INVENTORY_V1',UTC=datetime.now(timezone.utc).isoformat(),
 files={p.relative_to(DEST).as_posix():record(p) for p in sorted(DEST.rglob('*')) if p.is_file()})
(DEST/'SHA_INVENTORY.json').write_bytes((json.dumps(inventory,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
for item in copies:assert record(item['original']['path'])==item['original'] and record(item['copy']['path'])==item['copy']
assert record(PREVIOUS)==previous_before and record(DIAGNOSIS)==diagnosis_before
print(json.dumps(dict(PASS=True,raw_copies=len(copies),total_files=len(inventory['files'])+1,
 total_bytes=sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file()),
 inventory=record(DEST/'SHA_INVENTORY.json'),provenance=record(DEST/'PROVENANCE_SHA_INDEX.json')),indent=2))
