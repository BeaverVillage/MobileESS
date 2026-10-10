"""Preserve observed queue during parent-reported interrupted/resumed enqueue."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path('D:/v42_may_restart_20261010_02');OUT=Path(__file__).parent
path=ROOT/'RECOVERY_QUEUE.json';data=path.read_bytes()
raw=OUT/'ENQUEUE_RESUME_QUEUE_RAW.json'
with raw.open('xb') as stream:stream.write(data)
doc=json.loads(data.decode('utf-8-sig'))
SOURCE='9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9'
rows=[row for row in doc['entries'] if row['repair_source_SHA']==SOURCE]
first_four=[dict(date=row['date'],queue_id=row['queue_id'],queued_UTC=row['queued_UTC'],verification_status=row['verification_status']) for row in rows if row['date'][-2:] in ('01','02','03','04')]
assert len(first_four)==4 and len({row['date'] for row in first_four})==4
assert len({row['queue_id'] for row in rows})==len(rows)
report=dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),schema='V42_SOURCE32_ENQUEUE_INTERRUPTION_RESUME_READ_ONLY_OBSERVATION',
    original_parent_report='Initial enqueue stopped after four READY because manual repair lease was released before completion; new manual lease resumed idempotent enqueue.',
    parent_report_is_not_independent_capture_of_exception=True,
    independently_observed_current_Source32_queue_count=len(rows),first_four_existing_queue_ids=first_four,
    current_unique_date_queue_ids=True,completed_deployment_receipt_exists=(ROOT/'autonomous/V32_ZERO_START_RETRY_DEPLOYMENT.json').exists(),
    raw_source=dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),source_read_count=1),raw_snapshot=str(raw),
    full_nine_completion_not_claimed=True,Native_optimize_calls=0,model_constructions=0,queue_process_manifest_mutations=0)
target=OUT/'SOURCE32_ENQUEUE_PARTIAL_RESUME_READ_ONLY_OBSERVATION.json'
with target.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
blob=target.read_bytes();print(json.dumps(dict(PASS=True,path=str(target),bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),current_count=len(rows),first_four=first_four),ensure_ascii=False))
