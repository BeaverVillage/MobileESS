"""Exact-copy, additive docs package; no solver imports or production writes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(r'D:\MobileESS_v42_autonomous')
BASE = ROOT / 'docs/v42_autonomous_may_20261010'
DEST = BASE / 'SOURCE35_FULL_LP_DIAGNOSIS'
OUT = Path(__file__).resolve().parent
DIAG = Path(r'D:\v42_source35_full_lp_independent_diagnosis_20261010_02')
INITIAL = Path(r'D:\v42_source35_full_lp_independent_diagnosis_20261010_01')
PROPOSAL = Path(r'D:\v42_source36_pdhg_diagnostics_draft_20261010_01')


def rec(path):
    raw = Path(path).read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def write_json(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8'))


README = '''# Source35 original full-LP diagnosis and external observer proposal

This additive evidence package preserves a read-only comparison of the May01,
May02 and May03 Source35 original full-LP calls, the first comparison-harness
failure, and the subsequent external observer prototype tests. The diagnosis
receipt PASS validates its listed evidence comparisons. The test receipt PASS
validates 35 simulated observer tests with actual Gurobi model and Native entry
points denied. Neither receipt certifies a campaign date, an improved scientific
bound, a final 3% Global Gap, or a production observer implementation.

## Actual saved Source35 evidence

The original calls used Method6, LPWarmStart2, Crossover-1, Threads1 and the
original 300-second Native cap. The current same-day F1 complete primal point,
dual vector and basis were admitted; the saved original full-domain replay
receipts report PASS. All three calls ended with status11, SolCount0 and no
recorded exception, after the original Runtime callback cap:

| Date | Saved Native Runtime (s) | Full-LP/F1 independently certified LB | Nonzero dual rows |
| --- | ---: | ---: | ---: |
| May01 | 300.88899993896484 | -492.54522661241856 | 9463 |
| May02 | 300.8159999847412 | -406.1207858228788 | 9518 |
| May03 | 301.01900005340576 | -591.3602997475448 | 9518 |

The full-LP and current F1 certificate mathematical fields agree per date;
diagnostic `check_wall_seconds` is excluded from that equality. All three have
nonzero dual certificates and no saved `LP_DUAL_UNAVAILABLE.json`. SolCount0
therefore does not establish that Pi was unavailable. The exact initial bound
selection remains the original zero signed dual; the full-LP calls did not
improve that selected bound.

The frozen original diagnostic code has no PDHG callback branch and does not
read PDHGIterCount at completion. Saved SIMPLEX iteration0 and header-only
Native logs cannot establish actual PDHG iteration counts, residuals, or which
phase consumed the cap. The cap interruption and this observability gap are
established. A numerical failure or the precise solver phase is not established.
The possibility that the returned Pi remained the starting basis Pi while an
unfinished PDHG/crossover iterate progressed is an inference only.

## Official warm-start semantics and the future decision

Gurobi documents PDHG primal/dual starts, including vectors derived from a
basis. LPWarmStart2 transforms starts for the presolved model. Method2 with
complete warm vectors or a basis uses crossover without barrier iterations;
that is a possible future computational candidate, with no measured benefit
or 300-second guarantee here. [Official LPWarmStart documentation](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter-LPWarmStart).

Gurobi13.0.2 includes a PDHG dual-start sign correction. The saved calls already
used13.0.2. [Official fixed bugs](https://docs.gurobi.com/projects/optimizer/en/current/reference/releasenotes/fixedbugs.html).

Keep the separately qualified Source36 RMP policy and evaluate its actual
behavior. No observer integration or new repair source is authorized by this
package. A later guarded observer could collect PDHG iterations and residuals
at the single existing original full-LP call, retaining original Runtime and
UNKNOWN failure guards before delegation. Official fields are listed in
[callback codes](https://docs.gurobi.com/projects/optimizer/en/current/reference/numericcodes/callbacks.html)
and [PDHGIterCount](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#attr-PDHGIterCount).
Such scalar diagnostics must remain separate from Native accounting,
independent dual certificates, LB/UB and Global Gap.

## Preserved failure and test qualification limits

`INITIAL_HARNESS_01` is the initial producer and its partial raw May01 snapshot.
Its actual exit1 occurred because a whole-dictionary comparison included the
diagnostic checker wall time. The recorded mathematical fields match. The
corrected diagnosis02 excludes only `check_wall_seconds`; it does not weaken
any mathematical-field comparison. The initial failure receipt is retained
exactly; it is not represented as an independently redirected full stderr log.

`DIAGNOSIS_QUALIFIED_02` includes the final receipt, all three raw requests,
Native ledgers, call/warm-start/admission/selection and replay/certificate
receipts, original frozen source copies and historical draft. State archives
and matrices remain referenced by saved hashes; this package performs no fresh
scientific matrix or rational-checker replay. The historical draft's statement
that tests had not run describes that draft's earlier creation time.

`EXTERNAL_OBSERVER_PROPOSAL_TESTS` preserves the exact runner, test source,
JUnit XML and receipt for 35 passing simulated tests. Actual Gurobi Model,
retained Model.__init__ and optimize were denied; attempted entries were empty.
The JUnit XML is the existing raw test artifact. Original runner stdout was not
separately redirected; this package does not invent a raw terminal log.
`EXTERNAL_OBSERVER_SOURCE` is the exact tested prototype source. Tests cover
PDHG fields, phase separation, unknown/nonfinite values, model/closed/authority
guards, original callback-first behavior, accounting preservation and bounded
publication timing. They prove no actual solver callback or performance gain.

The external prototype is explicitly not production-admission qualified.
Future production work requires sealed current request/case/source/model and
single-call bindings, retained callable-code checks, original admission and
Runtime/UNKNOWN guards, and bounded per-field error aggregation. Public
prototype bindings are mutable and its diagnostic fault list is unbounded.
No model construction, Native call, physical constraint or precision change,
extra budget, production integration, process mutation or Git action occurred
while assembling this package.

## Inventory and byte preservation

`COPY_PROVENANCE.json` records exact origin/destination bytes and SHA256;
`SHA_INVENTORY.json` seals every payload file except itself. Package-local
`.gitattributes` disables text conversion for these immutable evidence copies.
It affects only this new documentation folder. The earlier sealed Source35,
Source36 and monitor documentation inventories are unchanged.
'''


def main():
    assert not DEST.exists(), 'NEW_DOC_PACKAGE_ALREADY_EXISTS'
    critical = {
        DIAG / 'SOURCE35_FULL_LP_INDEPENDENT_READONLY_DIAGNOSIS.json':
            'b93e8392db161abf03e086f26fd8295b2d9016149abea81c88c10bc724589686',
        OUT / 'EXTERNAL_PDHG_OBSERVER_PROPOSAL_NATIVE_DENIED_TEST_RECEIPT.json':
            '3cb945653bb69fd87e700e089eff03e5b7ff9d2083bd3fbd31776fb3c1b2bedc',
        PROPOSAL / 'pdhg_observer.py':
            '883f29c747575c1e31ba70b09bd1ebcbfe4088a9e415a9bb9f2233043468fe5a',
    }
    for path, expected in critical.items():
        assert rec(path)['sha256'] == expected, ('SEALED_INPUT_CHANGED', str(path))
    diagnosis = json.loads(next(iter(critical)).read_bytes())
    assert diagnosis['PASS'] is True
    expected_frozen = diagnosis['immutable_frozen_1111_before']
    frozen_before = {path: rec(path)['sha256'] for path in expected_frozen}
    assert frozen_before == expected_frozen
    prior_paths = [BASE / rel for rel in [
        'SOURCE35/SHA_INVENTORY.json',
        'SOURCE35/PRICE_REVIEW/SHA_INVENTORY.json',
        'SOURCE35/DIAGNOSIS/SHA_INVENTORY.json',
        'SOURCE35/DEPLOYMENT/SHA_INVENTORY.json',
        'SOURCE36/RMP_PRIMAL_REVIEW/SHA_INVENTORY.json',
        'SOURCE36/ACTUAL_SOURCE35_RMP_DIAGNOSIS/SHA_INVENTORY.json',
        'MONITOR_ASSEMBLED_LB_EXCLUSIVE_HOST/SHA_INVENTORY.json',
    ]]
    prior_before = {str(path): rec(path) for path in prior_paths}
    copies = []
    for srcdir, prefix in [(DIAG, 'DIAGNOSIS_QUALIFIED_02'),
                           (INITIAL, 'INITIAL_HARNESS_01')]:
        for origin in sorted(srcdir.rglob('*')):
            if origin.is_file():
                assert '__pycache__' not in origin.parts and origin.suffix != '.pyc'
                copies.append((origin, Path(prefix) / origin.relative_to(srcdir)))
    for name in ['EXTERNAL_PDHG_OBSERVER_PROPOSAL_NATIVE_DENIED_TEST_RECEIPT.json',
                 'external_proposal_native_denied.xml', 'run_native_denied_tests.py',
                 'test_pdhg_observer_proposal.py']:
        copies.append((OUT / name, Path('EXTERNAL_OBSERVER_PROPOSAL_TESTS') / name))
    copies.append((PROPOSAL / 'pdhg_observer.py', Path('EXTERNAL_OBSERVER_SOURCE/pdhg_observer.py')))
    copies.append((Path(__file__).resolve(), Path('package_full_lp_diagnosis.py')))
    origins_before = {str(origin): rec(origin) for origin, _ in copies}
    DEST.mkdir(parents=True)
    provenance = {}
    for origin, relative in copies:
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(origin.read_bytes())
        origin_record, target_record = rec(origin), rec(target)
        assert {k: origin_record[k] for k in ('sha256', 'bytes')} == {
            k: target_record[k] for k in ('sha256', 'bytes')}
        provenance[relative.as_posix()] = dict(origin=origin_record, copied=target_record)
    (DEST / 'README.md').write_bytes(README.encode('utf8'))
    (DEST / '.gitattributes').write_bytes(b'* -text\n** -text\n')
    write_json(DEST / 'COPY_PROVENANCE.json', dict(
        schema='V42_SOURCE35_FULL_LP_DIAGNOSIS_DOC_EXACT_COPY_PROVENANCE',
        UTC=datetime.now(timezone.utc).isoformat(), copies=provenance,
        documentation_only=True, existing_sealed_source35_source36_docs_modified=False,
        Native_optimize_calls=0, real_model_constructions=0,
        scientific_module_imports=0, production_mutations=0,
        scientific_date_or_Global_Gap_PASS_claimed=False,
        external_observer_NOT_production_admission_qualified=True))
    payload = {path.relative_to(DEST).as_posix():
               {k: rec(path)[k] for k in ('bytes', 'sha256')}
               for path in sorted(DEST.rglob('*')) if path.is_file()}
    inventory = DEST / 'SHA_INVENTORY.json'
    write_json(inventory, dict(schema='V42_SOURCE35_FULL_LP_DIAGNOSIS_DOC_INVENTORY',
        UTC=datetime.now(timezone.utc).isoformat(), files=payload,
        payload_file_count=len(payload), payload_bytes=sum(v['bytes'] for v in payload.values()),
        exact_origin_copy_count=len(copies), inventory_excludes_only_itself=True,
        mathematical_campaign_PASS_claimed=False,
        external_observer_NOT_production_admission_qualified=True))
    current = {path.relative_to(DEST).as_posix():
               {k: rec(path)[k] for k in ('bytes', 'sha256')}
               for path in sorted(DEST.rglob('*')) if path.is_file() and path != inventory}
    assert current == payload
    assert {str(origin): rec(origin) for origin, _ in copies} == origins_before
    assert {str(path): rec(path) for path in prior_paths} == prior_before
    frozen_after = {path: rec(path)['sha256'] for path in expected_frozen}
    assert frozen_before == frozen_after == expected_frozen
    verification = dict(PASS=True, schema='V42_SOURCE35_FULL_LP_DOC_PACKAGE_SEAL_VERIFICATION',
        UTC=datetime.now(timezone.utc).isoformat(), package=str(DEST),
        inventory=rec(inventory), payload_file_count=len(payload),
        total_file_count=len(payload)+1, payload_bytes=sum(v['bytes'] for v in payload.values()),
        origin_copy_count=len(copies), payload_exact_set_bytes_SHA_verified=True,
        all_origins_start_end_byte_exact=True, immutable_frozen_1111_declared_start_end=True,
        prior_sealed_inventory_start_end=prior_before,
        prior_sealed_inventory_unchanged=True,
        Native_optimize_calls=0, real_model_constructions=0,
        scientific_module_imports=0, production_mutations=0, Git_actions=0,
        only_NEW_docs_package_and_external_packaging_receipt_created=True,
        mathematical_campaign_PASS_claimed=False,
        external_observer_NOT_production_admission_qualified=True)
    path = OUT / 'SOURCE35_FULL_LP_DOC_PACKAGE_SEAL_VERIFICATION.json'
    write_json(path, verification)
    print(json.dumps(dict(PASS=True, package=str(DEST), inventory=rec(inventory),
        files=len(payload)+1, payload_bytes=verification['payload_bytes'],
        copies=len(copies), verification=rec(path), Native_optimize_calls=0)))


if __name__ == '__main__':
    main()
