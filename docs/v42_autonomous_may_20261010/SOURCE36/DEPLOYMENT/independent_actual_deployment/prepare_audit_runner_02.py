from pathlib import Path
folder=Path(__file__).resolve().parent
src=(folder/'audit_deployment.py').read_text(encoding='utf-8')
assert 'D:/v42_source35_independent_review_20261010_01/SOURCE36_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json' in src
src=src.replace('D:/v42_source35_independent_review_20261010_01/SOURCE36_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json','D:/v42_source36_independent_review_20261010_01/SOURCE36_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json')
src=src.replace("receipt=OUT/'SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT.json'","receipt=OUT/'SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT_02.json'")
src=src.replace("r['finished_UTC']=datetime.now(timezone.utc).isoformat()", "r['preliminary_external_harness_wrong_independent_receipt_folder']=rec(OUT/'SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT.json')\nr['finished_UTC']=datetime.now(timezone.utc).isoformat()")
path=folder/'audit_deployment_02.py';assert not path.exists();path.write_text(src,encoding='utf-8');print(path)
