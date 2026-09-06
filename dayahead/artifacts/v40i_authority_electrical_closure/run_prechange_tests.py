from pathlib import Path
import json,sys,subprocess,time
from concurrent.futures import ThreadPoolExecutor,as_completed
repo=Path.cwd(); root=repo/'dayahead/artifacts/v40i_authority_electrical_closure'; base=Path('C:/codex_mobileess_workspace/v40i_prechange_tests'); out=root/'prechange_tests';out.mkdir(exist_ok=True)
fail=json.loads((root/'V40I_FULL_REPOSITORY_FAILURES.json').read_text(encoding='utf-8'));groups={}
for r in fail:
 p=Path(r['file']); suffix=r['test']['classname'].split(p.stem,1)[1].lstrip('.')
 node=str(p)+('::'+suffix.replace('.','::') if suffix else '')+'::'+r['test']['name']
 groups.setdefault(str(p),[]).append(node)
def run(item):
 p,nodes=item;n=p.replace('\\','__').replace('/','__').replace('.py','');log=out/(n+'.log');xml=out/(n+'.xml')
 with log.open('wb') as f:
  result=subprocess.run([sys.executable,'-X','utf8','-m','pytest',*nodes,'-q','--tb=short','--junitxml='+str(xml)],cwd=base,stdout=f,stderr=subprocess.STDOUT,timeout=180)
 return {'file':p,'exit_code':result.returncode,'nodes':nodes,'log':str(log),'xml':str(xml)}
results=[]
with ThreadPoolExecutor(max_workers=4) as pool:
 for f in as_completed([pool.submit(run,x) for x in groups.items()]):
  row=f.result();results.append(row);print(len(results),row['file'],row['exit_code'],flush=True)
(root/'V40I_PRECHANGE_TEST_EXECUTION.json').write_text(json.dumps({'baseline_HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=base,text=True).strip(),'baseline_path':str(base),'current_repository_HEAD_unchanged':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'selected_count':len(fail),'files':results},indent=2),encoding='utf-8')

