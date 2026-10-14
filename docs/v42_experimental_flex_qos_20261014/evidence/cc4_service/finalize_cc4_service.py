from pathlib import Path
import json,hashlib
B=Path(__file__).parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rec(p):return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
p=B/'Q50_Q90_DEMAND_VS_OCCUPANCY_KO.md'
s=p.read_text(encoding='utf-8')
s=s.replace('PR64·74·129의 동일 NPZ SHA', 'PR64·74 NPZ blob과 PR129 외부 prediction 바인딩의 동일 NPZ SHA')
s=s.replace('를 원본 Commit blob으로 확인했다.', '를 원본 Commit blob 및 재검증한 외부 NPZ bytes로 확인했다. PR129 branch는 prediction NPZ 사본 대신 정확한 외부 경로·SHA 바인딩을 보존한다.')
p.write_text(s,encoding='utf-8')
m=read(B/'CC4_SERVICE_AUDIT_MANIFEST.json')
m['artifacts']=[rec(Path(x['path'])) for x in m['artifacts']]
m['finalizer']=rec(Path(__file__))
(B/'CC4_SERVICE_AUDIT_MANIFEST.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(status='FINAL_NATIVE0',manifest=rec(B/'CC4_SERVICE_AUDIT_MANIFEST.json')),ensure_ascii=False))
