import json,pathlib,pickle,sys,hashlib,statistics
sys.dont_write_bytecode=True
sys.path.insert(0,'C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
D=pathlib.Path(__file__).absolute().parent;H=D.parent.parent;W=H.parent.parent
OLD=W/'independent_screening/IEEE8500_MAY01_MESS6_B2B3_20260913'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
result={}
for label,root in [('previous',OLD),('current',H)]:
 files=sorted((root/'B2/candidate_cache').rglob('*.pkl'),key=lambda p:p.stat().st_mtime)
 rows=[]
 for p in files[:30]:
  x=pickle.loads(p.read_bytes());r=x['result'];ident=x['identity']
  rows.append({'path':str(p),'bytes':p.stat().st_size,'mtime':p.stat().st_mtime,'sha256':sha(p),'identity':ident,'row':r[0],'repair':r[3],'cut_counts':{k:len(v) for k,v in r[4].items()}})
 result[label]={'root':str(root),'cache_count':len(files),'first_30':rows,'runtime_median':statistics.median(r['row']['runtime_seconds'] for r in rows) if rows else None}
 shared={}
 for rel in ['MESS_24_SERVICE_PCC_COLUMN_BINDING.json','MESS_TRAFFIC_AUTHORITY.json','AXES.json','COEFFICIENT_GENERATION.json','MESS_INTEGRATED_SOURCE_ADAPTER.json','traffic/shared/traffic/2025-05-01/TRAFFIC_FORECAST.npz','traffic/shared/traffic/2025-05-01/ROUTE_TABLE.json.gz']:
  p=root/rel;shared[rel]={'exists':p.exists(),'path':str(p)}
  if p.is_file():shared[rel].update(bytes=p.stat().st_size,sha256=sha(p))
 result[label]['artifacts']=shared
(D/'cache_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:{'cache_count':v['cache_count'],'runtime_median':v['runtime_median'],'rows':[(r['row']['candidate_id'],round(r['row']['runtime_seconds'],3),r['cut_counts']) for r in v['first_30'][:4]]} for k,v in result.items()}))
