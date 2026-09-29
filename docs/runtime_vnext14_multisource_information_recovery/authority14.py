"""Bounded read-only local authority search for negative-result documentation."""
from common14 import *
import re

def main():
    inv=pd.read_csv(ROOT/'RAW_SOURCE_INVENTORY.csv',keep_default_na=False)
    patterns={
        'identity_crosswalk':r'crosswalk|job.?id.{0,30}(mapping|anonym|reset|encrypt)|reset_index|enumerate\(',
        'embedding_export':r'encrypt|chunk_|job_strings|row_id',
        'original_submit_revision':r'original.?submit|revision|submit.?revision',
        'requeue':r'requeue', 'restart_attempt':r'restart|attempt', 'preemption':r'preempt',
        'job_step':r'job.?step|step.?duration|sacct', 'dependency_DAG':r'dependency|\bDAG\b',
        'scheduler_event_log':r'slurmctld|scheduler.?event|state.?history',
    }
    inspected=[];hits={k:[] for k in patterns};errors=[];sourcecells=0
    candidates=inv[inv.relative_path.str.contains('RADDiT|Kestrel|scheduler_authority',case=False)&inv.extension.isin(['.py','.md','.sql','.html','.txt','.ipynb'])]
    for _,row in candidates.iterrows():
        if '/.git/' in row.relative_path or '.git/' in row.relative_path or '/dataset_v2/' in row.relative_path:continue
        p=RAW_A/row.relative_path
        if row.size_bytes>5_000_000 and p.suffix!='.ipynb':continue
        try:
            if p.suffix=='.ipynb':
                nb=json.loads(p.read_text(encoding='utf-8'))
                code=[''.join(c.get('source',[])) for c in nb.get('cells',[]) if c.get('cell_type')=='code']
                text='\n'.join(code);sourcecells+=len(code)
            else:text=p.read_text(encoding='utf-8',errors='replace')
        except Exception as e:errors.append(dict(path=str(p),error=str(e)));continue
        inspected.append(record(p))
        for key,pat in patterns.items():
            matches=[dict(line=i+1,text=line[:240]) for i,line in enumerate(text.splitlines()) if re.search(pat,line,re.I)]
            if matches:hits[key].append(dict(path=str(p),matches=matches[:12],total_matching_lines=len(matches)))
    write('LOCAL_AUTHORITY_SEARCH.json',dict(time=now(),scope='Local source/documentation only; notebooks code cells only, never stored outputs. Keyword hits are leads, not historical authority.',
        inventory_source=record(ROOT/'RAW_SOURCE_INVENTORY.csv'),inspected_files=inspected,inspected_file_count=len(inspected),
        notebook_code_cells=sourcecells,errors=errors,hits=hits,
        historical_Slurm_to_RADDiT_crosswalk_found=False,distributed_embedding_export_receipt_found=False,
        search_limit='Unreadable links recorded; generic Slurm docs and example code do not establish actual historical event availability. No approximate or timestamp-only substitute join attempted.'))
    lines=['# Missing event authority — local search scope','',
        'Source-authority failure 이후 최종 보고의 근거를 보존하기 위한 문서 검색만 수행했습니다. 새로운 모델·연결 실험은 수행하지 않았습니다.',
        f'원본 inventory 전체 경로와 로컬 문서/코드 {len(inspected)}개를 검사했습니다. Notebook은 code cell만 검사했습니다. '
        '키워드 출현과 실제 과거 사건 로그의 존재는 구분합니다. 일부 링크의 접근 오류는 LOCAL_AUTHORITY_SEARCH.json에 보존합니다.','',
        '| 항목 | 판정 | 범위 |','|---|---|---|']
    for item in ['original submit revision','requeue events','restart attempts','preemption','job-step/step duration',
                 'dependency DAG','scheduler event logs','revision history','sacct state history']:
        lines.append(f'| {item} | NOT_FOUND_IN_SEARCHED_LOCAL_AUTHORITY | 일반 Slurm 설명/예시와 최종 accounting snapshot은 존재하지만, V13 작업에 연결되는 역사적 event/revision ledger는 입증하지 못함 |')
    lines+=['','RADDiT 공개 job_id는 0-based row position입니다. Slurm ID 대응표와 배포 embedding chunk 생성·변환 receipt를 찾지 못했습니다. '
            '이는 검색 범위의 결과이며 자료가 어디에도 존재하지 않는다는 주장이 아닙니다.']
    (ROOT/'KERNEL_MISSING_EVENT_AUTHORITY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('LOCAL_AUTHORITY_DOCUMENTS',len(inspected),'errors',len(errors),flush=True)

if __name__=='__main__':main()
