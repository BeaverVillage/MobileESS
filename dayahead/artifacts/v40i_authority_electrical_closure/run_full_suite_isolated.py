from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import subprocess,sys,time,json,xml.etree.ElementTree as ET
root=Path('dayahead/artifacts/v40i_authority_electrical_closure'); out=root/'full_suite_isolated';out.mkdir(exist_ok=True)
files=sorted(p for p in Path('tests').rglob('test_*.py') if '__pycache__' not in p.parts)
started=time.time();results=[]
def run(p):
 name=str(p).replace('\\','__').replace('/','__').replace('.py',''); log=out/(name+'.log'); xml=out/(name+'.xml');begin=time.time()
 with log.open('wb') as stream:
  try:r=subprocess.run([sys.executable,'-m','pytest',str(p),'-q','--tb=short','--junitxml='+str(xml)],stdout=stream,stderr=subprocess.STDOUT,timeout=360); code=r.returncode
  except subprocess.TimeoutExpired:code='TIMEOUT_360_SECONDS'
 row={'file':str(p),'exit_code':code,'elapsed':time.time()-begin,'log':str(log),'xml':str(xml) if xml.exists() else None}
 if xml.exists():
  doc=ET.parse(xml).getroot(); suites=list(doc.iter('testsuite'));row.update({k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')})
 return row
with ThreadPoolExecutor(max_workers=4) as pool:
 futures={pool.submit(run,p):p for p in files}
 for f in as_completed(futures):
  r=f.result();results.append(r)
  (root/'V40I_FULL_SUITE_ISOLATED_PROGRESS.json').write_text(json.dumps({'completed_files':len(results),'total_files':len(files),'last':r},ensure_ascii=False),encoding='utf-8')
  print(len(results),'/',len(files),r['file'],r['exit_code'],flush=True)
report={'status':'PASS' if all(r['exit_code']==0 for r in results) else 'FAIL','scope':'All tests/test_*.py and tests/dayahead/test_*.py in separate processes to isolate legacy native runtime state','files':results,'elapsed':time.time()-started,'per_file_timeout_seconds':360,'tests':sum(r.get('tests',0) for r in results),'failures':sum(r.get('failures',0) for r in results),'errors':sum(r.get('errors',0) for r in results),'skipped':sum(r.get('skipped',0) for r in results),'incomplete_files':[r for r in results if not r['xml']]}
(root/'V40I_FULL_REPOSITORY_TEST_REPORT.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
print('RESULT',report['status'],report['tests'],report['failures'],report['errors'],flush=True)
