"""Seal intended evidence; interpreter caches are not campaign authority."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from v42_b0_production.authority import DOC, read
from v42_b0_production.report import manifest
from v42_orchestrator.ledger import atomic


root = Path(read(DOC / 'RUN_LOCATION.json')['run_root'])
manifest(root)
payload = read(DOC / 'SHA256_MANIFEST.json')
payload['repository_evidence'] = [r for r in payload['repository_evidence']
                                  if '__pycache__' not in Path(r['path']).parts]
payload['interpreter_caches_excluded'] = True
atomic(DOC / 'SHA256_MANIFEST.json', payload)
