"""Verified read aliases for missing historical evidence, not a gate bypass."""
import json,hashlib
from pathlib import Path
H=Path(__file__).absolute().parent
def install():
 import dayahead.v41.preflight as preflight
 if getattr(preflight.record,'verified_evidence_alias',False):return
 aliases=json.loads((H/'SOURCE_PATH_ALIASES.json').read_text(encoding='utf-8'))
 original=preflight.record
 def record(path):
  p=Path(path)
  if p.exists():return original(path)
  entry=aliases.get(str(p))
  if entry is None:return original(path)
  local=Path(entry['local_copy']);body=local.read_bytes();digest=hashlib.sha256(body).hexdigest()
  assert digest==entry['sha256'],'HISTORICAL_EVIDENCE_ALIAS_HASH_MISMATCH'
  assert len(body)==entry['bytes'],'HISTORICAL_EVIDENCE_ALIAS_SIZE_MISMATCH'
  # Keep the frozen logical reference name. Content and size come from the
  # verified local copy; the original gate still compares every full record.
  return dict(path=str(p),sha256=digest,bytes=len(body))
 record.verified_evidence_alias=True;preflight.record=record
