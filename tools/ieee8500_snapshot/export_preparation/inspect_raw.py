import json,sys
from pathlib import Path
W=Path(r'D:\ChatGPT\Mobile ESS 2')
def compact(x,d=0):
 if isinstance(x,dict): return {k:compact(v,d+1) for k,v in x.items()} if d<2 else {'keys':list(x)[:35]}
 if isinstance(x,list): return {'length':len(x),'first':compact(x[0],d+1) if x else None,'last':compact(x[-1],d+1) if x else None}
 return x[:200]+'...[long string]' if isinstance(x,str) and len(x)>500 else x
for rel in sys.argv[1:]:
 p=W/rel
 print(rel)
 try: print(json.dumps(compact(json.loads(p.read_text(encoding='utf-8-sig'))),ensure_ascii=False))
 except Exception as e: print(str(e))
