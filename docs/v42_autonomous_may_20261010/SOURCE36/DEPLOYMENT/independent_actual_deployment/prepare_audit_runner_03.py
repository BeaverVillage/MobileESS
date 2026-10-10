from pathlib import Path
folder=Path(__file__).resolve().parent
src=(folder/'audit_deployment_02.py').read_text(encoding='utf-8')
assert "v['verification_status']=='WORKER_ENTERED'" in src
src=src.replace("v['verification_status']=='WORKER_ENTERED'", "v['verification_status'] in ('WORKER_ENTERED','NATIVE_PROGRESS_VERIFIED')")
src=src.replace("receipt=OUT/'SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT_02.json'", "receipt=OUT/'SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT_03.json'")
src=src.replace("r['finished_UTC']=datetime.now(timezone.utc).isoformat()", "r['preliminary_external_harness_active_worker_queue_state_assumption']=rec(OUT/'SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT_02.json')\nr['finished_UTC']=datetime.now(timezone.utc).isoformat()")
path=folder/'audit_deployment_03.py';assert not path.exists();path.write_text(src,encoding='utf-8');print(path)
