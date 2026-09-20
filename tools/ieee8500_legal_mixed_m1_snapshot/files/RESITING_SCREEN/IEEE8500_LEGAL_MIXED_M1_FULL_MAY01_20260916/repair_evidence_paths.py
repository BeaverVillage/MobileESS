"""Prepare exact-content aliases and preserve failure evidence before resume."""
import json,hashlib,shutil,time
from pathlib import Path
H=Path(__file__).absolute().parent;W=H.parent.parent
ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2),encoding='utf-8')
def main():
 folder=H/('repair_missing_gate_evidence_'+str(time.time_ns()));folder.mkdir(exist_ok=False)
 for name in ('B1_FAILURE.json','SUPERVISOR_STATUS.json','STATUS.json'):
  if (H/name).exists():shutil.copyfile(H/name,folder/name)
 aliases=read(H/'SOURCE_PATH_ALIASES.json');gate=read(ROOT/'dayahead/artifacts/v41r1_pending_running_migration/F_AND_O_EQUIVALENCE_GATE.json');checks=[]
 for ref in gate['sources']+[gate['test_results']]:
  p=Path(ref['path']);local=p
  if not p.exists():
   rel=p.relative_to(ROOT);candidates=[W/'v41r4_final_results_pr'/rel,W/'B3_2ROUND_EXTENSION/original_source'/rel,W/'v41r4_alpha_screen_pr'/rel,W/'v41r4_final_results_pr/dayahead/artifacts/v41r1_first_improvement/source'/rel]
   matches=[q for q in candidates if q.is_file() and sha(q)==ref['sha256'] and q.stat().st_size==ref['bytes']]
   assert matches,('NO_IDENTICAL_HISTORICAL_EVIDENCE',ref)
   local=H/'authority_sources'/rel;local.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(matches[0],local)
   aliases[str(p)]=dict(local_copy=str(local),sha256=ref['sha256'],bytes=ref['bytes'],same_content_source=str(matches[0]))
  assert sha(local)==ref['sha256'] and local.stat().st_size==ref['bytes']
  checks.append(dict(logical_path=str(p),physical_read_path=str(local),sha256=sha(local),bytes=local.stat().st_size))
 save(H/'SOURCE_PATH_ALIASES.json',aliases)
 save(folder/'EVIDENCE_ALIAS_AUDIT.json',dict(status='PASS',gate_file=str(ROOT/'dayahead/artifacts/v41r1_pending_running_migration/F_AND_O_EQUIVALENCE_GATE.json'),checks=checks,original_gate_not_modified=True,all_record_comparisons_retained=True))
 # Pin completed preparation before the worker restart. These are outputs
 # of this full run, never screening/proxy artifacts.
 files=[p for p in (H/'B1_electrical_rows').iterdir() if p.is_file()]
 assert read(H/'B1_electrical_rows/CERTIFICATE.json')['status']=='PASS'
 assert len(list((H/'B1_electrical_rows').glob('active_data_*.npz')))==96
 signature=[dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for p in files]
 inputs=[H/'LAYOUT.json',H/'PCC_OVERLAY_INVENTORY.json',H/'COEFFICIENT_GENERATION.json',H/'MAY01_B0_AIDC_POWER.npz',H/'HEADROOM_AUTHORITY.json']
 signature.extend(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for p in inputs)
 # Preserve presearch ranking outputs before they are recomputed in memory.
 for name in ('IEEE8500_RANKING_PHYSICS.npz','RANKING_INPUT_PORT_AUDIT.json'):
  shutil.copyfile(H/'B1'/name,folder/name)
 save(H/'B1_PREPARATION_RESUME.json',dict(status='PASS',files=signature,full_96_slot_current_run_only=True,search_started=False,repair_unix=time.time()))
 print('VERIFIED_EVIDENCE_RECORDS',len(checks),'PREPARATION_FILES',len(signature),flush=True)
if __name__=='__main__':main()
