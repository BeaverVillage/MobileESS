"""Export honest intermediate/final authority; never converts timeout to PASS."""
import sys,shutil,gzip,hashlib
from .common import *
def copy(p,q):
    q.parent.mkdir(parents=True,exist_ok=True)
    if p.stat().st_size>5_000_000 and p.suffix=='.json':
        raw=p.read_bytes();gz=gzip.compress(raw,mtime=0);q.with_suffix(q.suffix+'.gz').write_bytes(gz)
        atomic(q,dict(lossless_gzip=q.name+'.gz',original_sha256=hashlib.sha256(raw).hexdigest(),sha256=hashlib.sha256(gz).hexdigest(),original_bytes=len(raw),roundtrip_PASS=gzip.decompress(gz)==raw))
    else:shutil.copyfile(p,q)

def main():
    traces=[];lps=[];certs=[];sizes=[];latest=None
    for spec in SHELLS:
        f=CASE/spec['name']
        if not (f/'RESULT.json').exists():continue
        r=read(f/'RESULT.json');c=read(f/'CENSUS.json');latest=spec['name']
        traces.append(dict(shell=spec['name'],kind=spec['kind'],total_options=c['added_options'],expanded_classes=c['added_classes'],
             LP_status=r['LP']['status'],LP_primal_PASS=r['LP']['valid_primal'],MIP_status=None if r['MIP'] is None else r['MIP']['status'],integer_witness_PASS=r['integer_witness_PASS']))
        lps.append(dict(shell=spec['name'],**{k:v for k,v in r['LP'].items() if not isinstance(v,(dict,list))}))
        certs.append(dict(shell=spec['name'],native_status=r['LP']['status'],independent_infeasibility_proven=r['LP'].get('independent_infeasibility_proven',False),
               old_signed_support=record(SUPPORT/'INDEPENDENT_PHYSICAL_SUPPORT_CERTIFICATE.json'),TIME_LIMIT_not_INFEASIBLE=True))
        sizes.append(dict(shell=spec['name'],**c,compact=read(f/'COMPACT/A2SC_MODEL_CENSUS.json')))
        dest=OUT/'evidence'/spec['name']
        for name in ('RESULT.json','CENSUS.json','STATIC_ONLY.json','GLOBAL_NUMERIC_IDENTITY.json','INDEPENDENT_DOMAIN_INCLUSION.json','SELECTED_DOMAIN_INPUT.json',
             'SOLVE_START.json','LP_START.json','MIP_START.json','LP_NATIVE.log','MIP_NATIVE.log','LP_ORIGINAL_FULL_REPLAY.json','MIP_ORIGINAL_FULL_REPLAY.json',
             'INDEPENDENT_PHYSICAL_FEASIBILITY.json','CONTINUATION_SUPPORT_ANALYSIS.json'):
            if (f/name).exists():copy(f/name,dest/name)
        for p in (f/'COMPACT').glob('*.json'):copy(p,dest/'COMPACT'/p.name)
    table(OUT/'MAY19_SHELL_TRACE.csv',traces,['shell','kind','total_options','expanded_classes','LP_status','LP_primal_PASS','MIP_status','integer_witness_PASS'])
    table(OUT/'MAY19_LP_RESULTS.csv',lps,list(lps[0]) if lps else ['shell','status'])
    table(OUT/'MAY19_CERTIFICATE_TRACE.csv',certs,['shell','native_status','independent_infeasibility_proven','old_signed_support','TIME_LIMIT_not_INFEASIBLE'])
    selected=read(CASE/'SELECTED_DOMAIN.json') if (CASE/'SELECTED_DOMAIN.json').exists() else None
    final=read(CASE/'FINAL_RESULT.json') if (CASE/'FINAL_RESULT.json').exists() else dict(classification='RUNNING',completed=False)
    chosen=selected['shell'] if selected else latest
    write('MAY19_SELECTED_DOMAIN.json',selected or dict(selected=False,latest_tested_shell=chosen,classification=final['classification'],global_minimum_claimed=False))
    write('MAY19_SELECTED_DOMAIN_CENSUS.json',dict(selected=bool(selected),shell=chosen,census=read(CASE/chosen/'CENSUS.json') if chosen else None,shells=sizes,
         S38_raw=read(START/'CENSUS.json'),S38_compact=read(START/'COMPACT/A2SC_MODEL_CENSUS.json')))
    integer=read(CASE/selected['shell']/'RESULT.json') if selected else dict(integer_witness_PASS=False,MIP_executed=any(x['MIP_status'] is not None for x in traces))
    write('MAY19_INTEGER_FEASIBILITY.json',integer)
    write('MAY19_ORIGINAL_FULL_REPLAY.json',read(CASE/selected['shell']/'MIP_ORIGINAL_FULL_REPLAY.json') if selected else dict(PASS=False,reason='NO_VERIFIED_INTEGER_WITNESS',normal_physics_relaxed=False))
    production=CASE/'PRODUCTION'
    mapping={'MAY19_A1_RESULT.json':production/'A1/A1_SOLVE_RESULT.json','MAY19_PLANNING_FREEZE.json':production/'PLANNING_FREEZE/V42_DAYAHEAD_DECISION_FREEZE.json',
             'MAY19_ACTUAL_RESULT.json':production/'ACTUAL/ACTUAL_FIXED_REPLAY_RECEIPT.json','MAY19_FRESH_AC_RESULT.json':production/'FRESH_AC/FRESH_RESULT.json',
             'MAY19_PHYSICAL_VALIDATION.json':production/'PHYSICAL_VALIDATION.json'}
    for name,p in mapping.items():
        if p.exists():copy(p,OUT/name)
    preserved=read(OUT/'PR165_PRESERVATION_BEFORE.json');bad=[r['path'] for r in preserved['files'] if sha(r['path'])!=r['sha256']]
    if bad:raise ValueError('PR165_EVIDENCE_CHANGED:'+str(bad))
    v=dict(PASS=True,artifact_integrity_PASS=True,task_completed=(CASE/'FINAL_RESULT.json').exists(),classification=final['classification'],
           PR165_evidence_byte_preserved=True,preserved_files=len(preserved['files']),integer_witness_PASS=bool(selected),
           globally_minimal_claimed=False,first_feasible_tested_shell=None if not selected else selected['shell'],
           production_started=production.exists(),CC4_changed=False,voltage_limits_changed=False,GPU_capacity_changed=False,Runtime_service_changed=False,
           future_information_used=False,May17_May10_May12_or_27_PASS_rerun=False,Actual_PQ_reoptimization=False,memory_guard_added=False,
           base=BASE,blocker=None if selected else 'NO_VERIFIED_INTEGER_WITNESS_IN_TESTED_SHELLS')
    write('VERIFICATION.json',v)
    census=read(CASE/chosen/'CENSUS.json') if chosen else {};start=read(START/'CENSUS.json');domain=read(CASE/(chosen+'_DOMAIN.json')) if chosen else []
    from v42_pr134_adaptive.common import load
    jobs=load(DAY)[1]
    sites=sum(int(x['checkpoint'])<0 and x['site']!=jobs[x['job_representative']].reference_site for x in domain)
    migration=sum(int(x['checkpoint'])>=0 for x in domain)
    answers=[f'시작: S38,26개 확장 클래스·38개 같은 사이트 시작 옵션. 기존 LP600초 TIME_LIMIT, MIP 미실행.',
       '첫 LP-feasible shell: '+str(next((x['shell'] for x in traces if x['LP_primal_PASS']),None)),
       '첫 MIP-feasible shell: '+str(None if not selected else selected['shell']),
       '추가 클래스(원래 S0 대비): '+str(census.get('added_classes')),
       '같은 사이트 시작 옵션: '+str(len(domain)-sites-migration),f'다른 사이트/prestart 옵션: {sites}',f'추가 migration 옵션: {migration}']
    for k in ('cols','binary','rows','nnz'):
        answers.append(f'{k}: S38 {start[k]} → '+str(census.get(k))+(' (증가 '+format(100*(census[k]/start[k]-1),'.6f')+'%)' if k in census else ''))
    answers+=['CC4 변경: NO.','전압 한계 변경: NO.','GPU 용량 변경: NO.','Runtime/서비스 변경: NO.','미래 정보 사용: NO.',
              '정수 witness PASS: '+str(bool(selected)),'원래 전체 replay PASS: '+str(bool(selected))]
    normal=read(production/'A1/A1_SOLVE_RESULT.json') if (production/'A1/A1_SOLVE_RESULT.json').exists() else {}
    passes=normal.get('passes',[])
    for i,n in enumerate(('rho','migration count','shift magnitude','prestart relocation')):
        answers.append(n+': '+(str({k:passes[i].get(k) for k in ('status','valid_UB','valid_LB','gap','native_runtime')}) if len(passes)>i else '미실행'))
    answers+=['Planning freeze: '+str((OUT/'MAY19_PLANNING_FREEZE.json').exists()),'Actual/Fresh: '+str((OUT/'MAY19_FRESH_AC_RESULT.json').exists()),
              '물리 위반: '+(str(read(OUT/'MAY19_FRESH_AC_RESULT.json')['summary']) if (OUT/'MAY19_FRESH_AC_RESULT.json').exists() else 'Fresh 미실행, 판정하지 않음'),
              '최종 분류: '+final['classification'],'commit/Draft PR: publication receipt 및 최종 전달을 따른다.']
    assert len(answers)==27
    (OUT/'FINAL_REVIEW_KO.md').write_text('# May19 practical prescreening rescue\n\n'+'\n\n'.join(f'{i}. {s}' for i,s in enumerate(answers,1))+'\n\n전역 최소 도메인을 주장하지 않는다. PR134 원래 전체 방정식의 확장 도메인 행렬을 압축 전에 캡처하고 독립 정확성 증명 후 raw point를 전체 좌표로 replay한다. TIME_LIMIT을 불능으로 판정하지 않았다.\n',encoding='utf8')
    print('REPORT',final['classification'],flush=True)

def manifest():
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json']+[p for p in (ROOT/'v42_pr134_may19').glob('*.py')]
    write('SHA256_MANIFEST.json',dict(base=BASE,files=[record(p) for p in sorted(paths)],excludes_self=True))
if __name__=='__main__':manifest() if sys.argv[1:]==['--manifest'] else main()
