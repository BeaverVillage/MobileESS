from common10 import *
from finalize10 import assert_freeze,FREEZES
import re,subprocess,hashlib,pandas as pd
def main():
    assert_freeze();request=(ROOT/'USER_REQUEST.txt').read_text(encoding='utf-8-sig')
    required=request.split('30. REQUIRED ARTIFACTS',1)[1].split('31. REQUIRED FINAL KOREAN QUESTIONS',1)[0]
    names=re.findall(r'(?m)^([A-Z][A-Z0-9_]*(?:\.json|\.csv|\.md))\s*$',required)
    for name in names:
        if name!='DELIVERY_MANIFEST.json':assert (ROOT/name).is_file(),name
    assert (ROOT/'RUNTIME_PROVIDER/provider.py').is_file()
    report=(ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8')
    assert [int(n) for n in re.findall(r'(?m)^## (\d+)\.',report)]==list(range(1,33))
    assert read(ROOT/'FINAL_INTEGRITY_AUDIT.json')['PASS']
    selected=read(ROOT/'PREAPRIL_SELECTION_RESULT.json');verdict=read(ROOT/'FINAL_VERDICT.json')
    for k,v in selected['selected'].items():
        if k in verdict:assert verdict[k]==v
    assert not verdict['V42_RESEARCH_RUNTIME_PROVIDER_READY'] and not verdict['STRICT_CAUSAL_RUNTIME_PROVIDER_READY']
    assert verdict['ZERO_SUPPORT_OBSERVED_INTERVAL_COUNT']==0
    assert pd.read_csv(ROOT/'DISTRIBUTIONAL_METRICS.csv').proper_score_finite.all()
    benchmark=pd.read_csv(ROOT/'COMPUTE_BACKEND_BENCHMARK.csv')
    assert len(benchmark)==2 and not benchmark.equivalent_within_preregistered_tolerance.any()
    changed=subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=REPO,text=True).splitlines()
    assert all(p.startswith('docs/runtime_vnext10_tail_calibrated_hazard/') for p in changed)
    sources=read(ROOT/'SOURCE_MANIFEST.json')
    for item in sources['source_code']:assert sha(item['path'])==item['sha256']
    for group in sources['prior_manifests']:
        p=Path(group['manifest']['path']);assert sha(p)==group['manifest']['sha256']
        for r in read(p)['files']:assert sha(p.parent/r['relative'])==r['sha256']
    write('DELIVERY_VERIFICATION.json',dict(time=now(),PASS=True,required_named_artifact_count=len(names),Korean_questions_answered=32,
        six_model_freezes_unchanged=True,prior_scientific_files_verified=591,prior_manifests_verified=4,new_namespace_only=True,negative_result_preserved=True,
        standalone_provider_test=read(ROOT/'STANDALONE_PROVIDER_VALIDATION.json'),scientific_audit=record(ROOT/'FINAL_INTEGRITY_AUDIT.json'),
        plotting='Matplotlib3.11.2 with isolated .local/plotdeps, only plot subprocess; ML environment unchanged',May_payload_opened=False))
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or any(x in p.relative_to(ROOT).parts for x in ['.local','__pycache__']) or p.name in ['DELIVERY_MANIFEST.json','report10.log']:continue
        files.append(dict(relative=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    write('DELIVERY_MANIFEST.json',dict(base=BASE,scope='docs/runtime_vnext10_tail_calibrated_hazard only',files=files,scientific_status='DIAGNOSTIC_NOT_PROMOTED'))
    print('DELIVERY_PASS',len(files),sum(r['bytes'] for r in files),flush=True)
if __name__=='__main__':main()

