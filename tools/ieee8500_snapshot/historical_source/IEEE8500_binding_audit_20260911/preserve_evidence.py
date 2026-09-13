import hashlib,json,time
from pathlib import Path
H=Path(__file__).parent
P=H.parent/'IEEE8500_production_20260911'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
rows=[]
for p in sorted(P.rglob('*')):
    if p.is_file():rows.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
v={'status':'NONAUTHORITATIVE_PRE_AIDC_BINDING_AUDIT','scientific_result_use_allowed':False,'restart_allowed':False,'file_count':len(rows),'files':rows,'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
out=H/'PRESERVED_PRODUCTION_SHA256.json'
out.write_text(json.dumps(v,indent=2),encoding='utf-8')
(H/'PRESERVED_PRODUCTION_SHA256.sha256').write_text(sha(out)+'  '+out.name+'\n',encoding='ascii')
print(json.dumps({'files':len(rows),'bytes':sum(r['bytes'] for r in rows),'manifest_sha256':sha(out)}))
