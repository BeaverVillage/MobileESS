"""Seal diagnostic artifacts and verify every preserved production byte."""
import shutil
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record,ROOT
from .flex_diagnostic import OUT,WORK

def run():
    preservation=read(OUT/'PRESERVATION.json');checks=[]
    for e in preservation['entries']:
        for key in ('original','preserved'):
            r=e[key];actual=record(r['path']);assert actual['sha256']==r['sha256'] and actual['bytes']==r['bytes'],r['path']
        checks.append(dict(original=e['original'],preserved=e['preserved'],status='PASS'))
    write_json(OUT/'PRESERVATION_FINAL_READBACK.json',dict(status='PASS',file_count=len(checks),checks=checks,
        prior_production_results_unchanged=True,Actual_archived_only=True))
    source=OUT/'source';source.mkdir(exist_ok=True)
    for path in (ROOT/'dayahead/v41r1').glob('flex_*.py'):
        target=source/path.name
        if not target.exists():shutil.copyfile(path,target)
        assert record(path)['sha256']==record(target)['sha256']
    refs=[]
    for root in (OUT,WORK):
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.name!='DIAGNOSTIC_FREEZE.json':refs.append(record(p))
    path=OUT/'DIAGNOSTIC_FREEZE.json'
    if path.exists():raise ValueError('PRESERVE_DIAGNOSTIC_FREEZE')
    write_json(path,dict(status='FROZEN',scope='MAY04_B1_FLEXIBILITY_DIAGNOSTIC',files=refs,
        root_cause='COMPUTATIONAL_LOCAL_BASIN',global_optimality_claim=False,full_May_started=False,
        subsequent_first_improvement_revision_separately_authorized=True))
    assert all(record(r['path'])==r for r in refs)
    print('DIAGNOSTIC_FREEZE_PASS',len(checks),len(refs),record(path)['sha256'],flush=True)

if __name__=='__main__':run()
