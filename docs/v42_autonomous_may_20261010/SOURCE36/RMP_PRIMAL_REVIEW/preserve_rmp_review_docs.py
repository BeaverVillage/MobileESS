from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
import json,xml.etree.ElementTree as ET
REPO=Path(r'D:\MobileESS_v42_autonomous')
DEST=REPO/'docs/v42_autonomous_may_20261010/SOURCE36/RMP_PRIMAL_REVIEW'
OWNER=Path(r'D:\v42_source36_owner_review_20261010_01')
INDEP=Path(r'D:\v42_source36_independent_review_20261010_01')
DRAFT=Path(r'D:\v42_rmp_method36_candidate_20261010_01')
ROOT=Path(r'D:\v42_may_restart_20261010_02')
DIAG=Path(r'D:\v42_source36_actual_source35_rmp_diagnosis_20261010_01')
PREVIOUS=REPO/'docs/v42_autonomous_may_20261010/SOURCE35/SHA_INVENTORY.json'
def record(path,raw=None):
    p=Path(path).resolve();raw=p.read_bytes() if raw is None else raw
    return dict(path=str(p),bytes=len(raw),sha256=sha256(raw).hexdigest())
assert not DEST.exists()
previous=record(PREVIOUS)
owner_path=OWNER/'SOURCE36_OWNER_SELECTED_NATIVE_DENIED_RECEIPT.json'
ind_path=INDEP/'SOURCE36_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json'
owner=json.loads(owner_path.read_bytes());ind=json.loads(ind_path.read_bytes())
assert record(owner_path)['sha256']=='3ff0607e176918b08d63aeeced4667e687609dc72e33180321a82ba8924557ac'
assert record(ind_path)['sha256']=='c74bc9a9c721106e3bba4ee8094a2cad3a7ad46b61702aaf0af07f61f4187605'
assert owner['PASS'] is True and owner['tests']==369 and ind['PASS'] is True and ind['tests_passed']==369
assert owner['execution_SHA']==ind['execution_SHA']=='4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39'
assert owner['source_file_count']==ind['source_file_count']==1106
assert owner['Native_optimize_calls']==owner['real_Native_model_constructions']==ind['Native_optimize_calls']==ind['real_Native_model_constructions']==0
assert record(DIAG/'SOURCE36_ACTUAL_SOURCE35_RMP_READONLY_DIAGNOSIS.json')['sha256']=='27de93b4931e42284e8fc8ce2e5b416ccc2bae4701c0bf5264fa525f1848b6c9'
copies=[]
for source,folder,names in (
    (OWNER,'owner369',['run_owner_review.py','SOURCE36_OWNER_SELECTED_NATIVE_DENIED_RECEIPT.json','SOURCE36_OWNER_SELECTED_NATIVE_DENIED.xml','SOURCE36_OPS_OWNER_STATIC_READONLY_REVIEW.json']),
    (INDEP,'independent369',['independent_review.py','SOURCE36_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json','SOURCE36_NATIVE_DENIED_TEST_OUTPUT_01.log','SOURCE36_NATIVE_DENIED_TESTS_01.xml','SOURCE36_FINAL_STATIC_CONTRACT_REVIEW.json']),
    (DRAFT,'focused_history',['rmp_presolve.py','test_rmp_presolve.py','SOURCE36_FOCUSED_INITIAL_TEST_HISTORY.json','SOURCE36_FOCUSED_TESTS_02.xml']),
    (DIAG,'actual_Source35_RMP_diagnosis',['SOURCE36_ACTUAL_SOURCE35_RMP_READONLY_DIAGNOSIS.json']),
    (REPO,'reviewed_source_bytes',['v42_autonomous_b2/rmp_presolve.py','tests/test_v42_autonomous_b2_rmp_presolve.py']),
    (ROOT/'autonomous','historical_metadata_candidate',['build_v36_validation_template_02_historical_candidate.py'])):
    for name in names:
        original=source/name;raw=original.read_bytes()
        if source==REPO:
            expected=owner['source_file_records'].get(name) or owner['test_file_records'][name]
            assert record(original,raw)==expected
        target=DEST/folder/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
        assert target.read_bytes()==raw
        copies.append(dict(relative_path=target.relative_to(DEST).as_posix(),original=record(original,raw),copy=record(target),raw_bytes_preserved=True))
xml=ET.parse(DEST/'focused_history/SOURCE36_FOCUSED_TESTS_02.xml').getroot()
suites=list(xml.iter('testsuite'))
assert sum(int(v.attrib.get('tests',0)) for v in suites)==136
assert sum(int(v.attrib.get('failures',0)) for v in suites)==0
readme='''# Source36 current-start RMP primal computational review

Owner and independent selected suites each passed 369 cases: base 22, F1 state 51, F1 basis 73, RMP 136 and price 87. Both bind execution99 SHA `4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39`, complete 1106 source records and identical source/execution/five-test-file start/end records. Real gp.Model, retained constructor-init and optimize were denied after protected-module preloads; attempted real calls are empty and Native/model counts are zero. The original1007 and other98 execution files are byte-identical to immutable Source35. Unchanged pricing_cache120 is carried historical evidence, not a rerun.

Only rmp_presolve.py changes scientific execution bytes. The original budget must still enter with Method1. After exact complete same-current PStart/DStart installation, sealed original AND Native-scaled row and bound violations must be within literal original1e-9 to select Method0 at the single original RMP boundary. Other cold/ineligible or finite nonfeasible starts retain Method1. Presolve0, installed LPWarmStart2, Crossover, Threads1, FeasibilityTol/OptimalityTol1e-9, NumericFocus3, ScaleFlag2, matrix/domain/objective and dyadic row/Pi transport are preserved. The original single30-second call, remaining total5400 cap and independent full checker remain unchanged. There are no added Native calls, no post-Native start setters/updates/parameter repair and no Native-objective lower-bound authority. F1 price, full-LP/PDHG and worker bytes remain Source35.

The current-method choice is recomputed from the sealed hint with literal1e-9. Own helpers and Entry descriptors/code/instance delegates are checked at original progress and after the receipt writer. Exact starts and current source/math/parameters are checked immediately before the raw delegate, with one exact expected Method. The original early-progress guard-failure inflight is preserved as unfinished/unknown. Computational starts and zero DStart do not prove a Native basis, usable Pi or scientific feasibility. No actual Source36 speedup, GlobalLB improvement, final3% Gap or Actual/Fresh PASS is claimed by these tests.

The separate actual Source35 diagnosis records all three current requests/OS identities and first two RMPs per day: actual Method1/warm2/Presolve0, unchanged30 caps, status11/Sol0 and no usable Pi. These are historical runtime observations, not a fresh Case/full-checker replay or Source36 performance proof. The original independent positive L1 bounds from Source35 remain separate scientific evidence.

The first focused run had122PASS and one old assertion-regex failure: the new exact Method guard correctly denied early, and the prior test expected a later error label. That observation JSON and original port-input draft bytes are retained. That run did not request/save a raw XML or stdout file; none is invented here. The final focused XML has136PASS. Later369 owner/independent commands qualify the final current source. The owner saved JSON/XML and returned stdout through its tool invocation, not a separate raw log; the independent raw log/XML are retained.

The initial generated Source36 validation inherited a direct RMP_Method1 metadata label. Root preserves that original template/validation/preparation and all four executed helper bytes. Additive metadata02 validation/preparation and enqueue-only02 clarify original admission1, eligible Native0 and fallback1. The preserved96d9 historical candidate was not executed. Actual deployment metadata and queues are packaged separately by Root. This package never edits Source35 seals, immutable checkouts, runtime ledgers, processes, queues or Git state. PROVENANCE_SHA_INDEX.json maps byte-for-byte copies; SHA_INVENTORY.json covers all package files except itself.

Official computational context: [Gurobi LPWarmStart](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameterlpwarmstart) and [Method](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parametermethod) describe primal simplex/PStart refinement. They provide no application-specific performance guarantee.
'''
(DEST/'README.md').write_bytes(readme.encode('utf-8'))
provenance=dict(schema='SOURCE36_RMP_PRIMAL_REVIEW_PROVENANCE_V1',UTC=datetime.now(timezone.utc).isoformat(),PASS=True,copies=copies,
    owner=record(owner_path),independent=record(ind_path),raw_copy_count=len(copies),no_invented_raw_output_or_rerun_history=True,
    unchanged_previous_Source35_inventory=previous,source_commit_reported_by_Root='68b8903c',
    actual_Source36_Native_or_performance_or_final_scientific_PASS_claimed=False)
(DEST/'PROVENANCE_SHA_INDEX.json').write_bytes((json.dumps(provenance,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
(DEST/'preserve_rmp_review_docs.py').write_bytes(Path(__file__).read_bytes())
inventory=dict(schema='SOURCE36_RMP_PRIMAL_REVIEW_SHA_INVENTORY_V1',UTC=datetime.now(timezone.utc).isoformat(),files={p.relative_to(DEST).as_posix():record(p) for p in sorted(DEST.rglob('*')) if p.is_file()})
(DEST/'SHA_INVENTORY.json').write_bytes((json.dumps(inventory,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
assert record(PREVIOUS)==previous
for item in copies:
    assert record(item['original']['path'])==item['original'] and record(item['copy']['path'])==item['copy']
print(json.dumps(dict(PASS=True,raw_copies=len(copies),file_count=len(inventory['files'])+1,inventory=record(DEST/'SHA_INVENTORY.json'),provenance=record(DEST/'PROVENANCE_SHA_INDEX.json'))))
