from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
import json

REPO=Path(r'D:\MobileESS_v42_autonomous')
OUT=REPO/'docs/v42_autonomous_may_20261010/SOURCE35/DIAGNOSIS'
OWNER=Path(r'D:\v42_f1_price_seed35_candidate_20261010_01')
REVIEW=Path(r'D:\v42_price_seed35_evidence_independent_review_20261010_01')
EVIDENCE='SOURCE32_CURRENT_F1_PRICE_SEED_EVIDENCE_94dd89f0a9d5d36e.json'
INDEPENDENT='SOURCE35_DIAGNOSIS_INDEPENDENT_NATIVE_ZERO_REVIEW.json'

def record(path,raw=None):
 path=Path(path).resolve();raw=path.read_bytes() if raw is None else raw
 return dict(path=str(path),bytes=len(raw),sha256=sha256(raw).hexdigest())

assert not OUT.exists(),'NEW_DIAGNOSIS_PACKAGE_ONLY'
assert record(OWNER/EVIDENCE)['sha256']=='94dd89f0a9d5d36ebb8fde0d321e3a4e6533f49b9fdbdf4159c77a41040bc1a6'
assert record(REVIEW/INDEPENDENT)['sha256']=='fa6319097aa59b8a7f4eae89dfc7ec307d510900f4ceaba209a9a0c5bac2ec7b'
copies=[]
for source,folder,names in (
 (OWNER,'producer', [EVIDENCE,'seal_actual_seed_evidence.py']),
 (REVIEW,'independent',[INDEPENDENT,'review_saved_source32_evidence.py','INITIAL_RUN_ENCODING_FAILURE.txt',
  '2025-05-01_LIVE_LEDGER_SNAPSHOT.json','2025-05-02_LIVE_LEDGER_SNAPSHOT.json','2025-05-03_LIVE_LEDGER_SNAPSHOT.json'])):
 for name in names:
  original=source/name;raw=original.read_bytes();target=OUT/folder/name
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as stream:stream.write(raw)
  assert target.read_bytes()==raw
  copies.append(dict(relative_path=target.relative_to(OUT).as_posix(),
   original=record(original,raw),copy=record(target),raw_bytes_preserved=True))

review=json.loads((REVIEW/INDEPENDENT).read_bytes());producer=json.loads((OWNER/EVIDENCE).read_bytes())
assert review['PASS'] is True and producer['PASS'] is True
assert review['Native_optimize_calls']==review['real_Native_model_constructions']==0
assert review['modelattempts']==review['nativeattempts']==[]
order=[]
for row,old in zip(review['rows'],producer['rows']):
 day=row['day'];snapshot=REVIEW/(day+'_LIVE_LEDGER_SNAPSHOT.json')
 assert record(snapshot)==review['live_ledger_raw_snapshots'][day]
 ledger=json.loads(snapshot.read_bytes())
 native=[old['f1_completed_native_receipt'],*[x['native'] for x in old['rmp_no_pi']]]
 indices=[ledger['calls'].index(call) for call in native]
 assert indices==sorted(indices) and len(set(indices))==3
 order.append(dict(day=day,completed_F1_RMP_record_indices=indices,
  completed_F1_RMP_records_exact_and_in_original_order=True,
  whole_live_ledger_matches_producer_snapshot=row['live_ledger_bytes_equal_producer_snapshot'],
  producer_historical_ledger_record=row['producer_live_ledger_snapshot'],
  independently_saved_live_snapshot=record(snapshot),
  prior_whole_ledger_bytes_available_for_complete_prefix_comparison=False))

readme='''# Source35 saved Source32 diagnosis

This package contains diagnosis evidence only. It does not validate the Source35 candidate module, invoke Native, load a model/case factory, or claim pricing performance or a daily PASS. No candidate/science files, Source34 sealed files, processes, queue, or Git staging/commit were changed to assemble it. Large NPZ packets, CSR matrices and large RMP producer JSON files are referenced by their existing byte/SHA records rather than copied here.

The producer evidence (`94dd89f0...40bc1a6`) matched a freshly replayed complete repaired F1-vector SHA to the already saved full-domain certificate. Its own limitations correctly state that it did not reevaluate the full certificate. The independent review (`fa631909...ac2ec7b`) separately reread saved same-attempt/source request, admission and all state arrays, checked complete C3A CSR/domain fingerprints and independently derived original coupling axes, replayed the unchanged original equality repair, verified the saved equality-envelope implications with the original verifier, and freshly reevaluated the complete original rational checker. All three days matched the stored dual SHA and exact bound. All 1105 immutable Source32 original+execution source files matched the declared map at start/end; loaded original module roots and bytes were verified. Native model construction and optimize were denied, with zero attempts.

May01/02/03 raw F1 coupling has 44/44/45 nonzero rows; the exact repaired vector has 48 each. Recomputed F1 bounds are approximately -492.54522661241856, -406.1207858228788 and -591.3602997475448. The authoritative selected dual/bound remains empty/0 because none improves the independently certified zero. Actual L1/L4 pricing coupling is zero, and the six Source32 RMP results have status11/SolCount0 with no finite Pi; that absence is not measured zero Pi.

A separate current-attempt computational pricing seed is mathematically permissible if it leaves the authoritative best dual, exact Frontier and final bracket unchanged. Each round must still run the original independent complete signed certificate, producer/full-sum agreement, packet-SHA and Frontier.publish gates. Only an actually certified improving adopted result may update the authoritative dual; the original final checker/Frontier equality remains. Forty-eight coupling rows establish a nonzero candidate input, not performance, improved Global LB or a date PASS. Candidate code and actual results require separate review.

The producer's full live-ledger SHA naturally differs from the later independently saved snapshots for all three dates. Exact completed F1 and both RMP records remain present, with their original order independently checked in `PACKAGING_OBSERVATION.json`. Only a historical ledger SHA was embedded in the producer evidence, so this package does not invent a comparison of every byte or every unrelated call in the earlier whole ledger. Each independently captured ledger snapshot was read once and copied without normalization.

`INITIAL_RUN_ENCODING_FAILURE.txt` is the saved raw reproduction of the initial audit runner's encoding-name typo (`utf8-sig`) before correction. The first invocation was tool-observed; the same failure was captured before editing the helper to `utf-8-sig`. No saved-case repair/checker computation was reached by those failed parsing invocations. The successful runner stdout was returned by the tool but was not saved as a raw stdout file; the exact final JSON receipt is preserved. No reconstructed stdout, extra scientific rerun, or invented history is included.

`PROVENANCE_SHA_INDEX.json` maps all eight raw copies to their original absolute path, bytes and SHA256. `SHA_INVENTORY.json` covers package files except itself. Producer and independent runner copies retain their original bytes; candidate code is omitted.
'''
(OUT/'README.md').write_bytes(readme.encode('utf8'))
facts=dict(schema='SOURCE35_DIAGNOSIS_ADDITIVE_PACKAGING_OBSERVATION_V1',UTC=datetime.now(timezone.utc).isoformat(),
 PASS=True,records=order,source_records=review['source_records'],
 producer_methods='Original exact repair replay and match to existing signed certificate; no new full certificate reevaluation',
 independent_methods='Original exact repair, original saved-envelope implication verifier, fresh complete original rational checker',
 saved_success_stdout_available=False,no_reconstructed_stdout_or_invented_rerun_history=True,
 Native_or_model_or_actual_performance_or_daily_PASS_claimed=False,
 candidate_or_production_or_process_queue_Git_mutations=0)
(OUT/'PACKAGING_OBSERVATION.json').write_bytes((json.dumps(facts,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
provenance=dict(schema='SOURCE35_DIAGNOSIS_RAW_PROVENANCE_V1',UTC=datetime.now(timezone.utc).isoformat(),PASS=True,
 copies=copies,raw_copy_count=len(copies),large_scientific_data_copied=False,
 successful_raw_stdout_not_saved=True,initial_raw_typo_failure_preserved=True)
(OUT/'PROVENANCE_SHA_INDEX.json').write_bytes((json.dumps(provenance,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
(OUT/'preserve_diagnosis_docs.py').write_bytes(Path(__file__).read_bytes())
inventory=dict(schema='SOURCE35_DIAGNOSIS_SHA_INVENTORY_V1',UTC=datetime.now(timezone.utc).isoformat(),
 files={p.relative_to(OUT).as_posix():record(p) for p in sorted(OUT.rglob('*')) if p.is_file()})
(OUT/'SHA_INVENTORY.json').write_bytes((json.dumps(inventory,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
for item in copies:assert record(item['original']['path'])==item['original'] and record(item['copy']['path'])==item['copy']
print(json.dumps(dict(PASS=True,raw_copies=len(copies),total_files=len(inventory['files'])+1,
 total_bytes=sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),
 inventory=record(OUT/'SHA_INVENTORY.json'),provenance=record(OUT/'PROVENANCE_SHA_INDEX.json')),indent=2))
