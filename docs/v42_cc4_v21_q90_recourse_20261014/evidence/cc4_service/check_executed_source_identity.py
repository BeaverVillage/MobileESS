from pathlib import Path
import hashlib,json
B=Path(__file__).parent;root=B.parents[1]
freeze=json.loads(Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/SOURCE_FREEZE_DDAY_GRID_V5.json').read_text(encoding='utf-8-sig'))
relative=['v42_temporal/service.py','v42_temporal/native.py','v42_final/workload.py','v42_final/reserve.py','v42_integration/a_engine.py','v42_integration/cc4_policy_inputs.py']
proof=[]
for name in relative:
    original=next(r for r in freeze['files'] if r['path'].replace('\\','/').endswith('/'+name))
    current=hashlib.sha256((root/name).read_bytes()).hexdigest()
    proof.append(dict(module=name,executed_V5_sha256=original['sha256'],current_sha256=current,exact=current==original['sha256']))
assert all(p['exact'] for p in proof)
for name in ['A_STAGE_SERVICE_TIMING_REUSE_AUDIT.json','CC4_24H_96SLOT_BINDING_AUDIT.json']:
    p=B/name;v=json.loads(p.read_text(encoding='utf-8'));v['current_original_service_source_matches_executed_V5']=dict(PASS=True,files=proof)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
mfile=B/'CC4_SERVICE_AUDIT_MANIFEST.json';m=json.loads(mfile.read_text(encoding='utf-8'))
for r in m['artifacts']:
    p=Path(r['path']);r.update(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
m['executed_A2_service_source_identity']='PASS_EXACT_EXECUTED_V5_BYTES'
m['source_identity_checker_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
mfile.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(PASS=True,files=proof),ensure_ascii=False))
