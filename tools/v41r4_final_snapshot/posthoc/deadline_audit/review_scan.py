from audit_deadlines import *

def main():
    scan=json.loads((HERE/'field_scan.json').read_text(encoding='utf-8'))
    assert set(scan['JSON_deadline_key_findings'])=={'contention_caused_RW_deadline_miss','contention_caused_RW_deadline_misses','deadline_overrun_noninterruptible_work_seconds'}
    for item in scan['parquet_schemas'].values():assert set(item['deadline_fields']) <= {'contention_caused_RW_deadline_miss'}
    assert not scan['text_findings']
    body=subprocess.check_output(['git','show',f'{COMMIT}:v41r4_loop_budget.py'],cwd=REPO)
    lines=body.decode('utf-8-sig').splitlines()
    assert 'deadline_overrun_noninterruptible_work_seconds=max(0.,self.elapsed-self.total)' in body.decode()
    sources=json.loads((HERE/'method_sources.json').read_text(encoding='utf-8'))
    sources=[s for s in sources if s['path']!='v41r4_loop_budget.py']
    sources.append(dict(path='v41r4_loop_budget.py',commit=COMMIT,sha256=digest(body),bytes=len(body),excerpts=[dict(begin=1,end=60,lines=lines[:60])]))
    save('method_sources.json',sources)
    save('scan_review.json',dict(status='REVIEWED_NO_JOB_DEADLINE_AUTHORITY',
        JSON_fields={
            'contention_caused_RW_deadline_miss':'Per-job Actual diagnostic boolean: contention changes completion from <= frozen RW reference to > RW. Not an input completion deadline.',
            'contention_caused_RW_deadline_misses':'Aggregate count of the preceding Actual diagnostic. Not deadline authority.',
            'deadline_overrun_noninterruptible_work_seconds':'DA optimization search-loop wall-clock budget overrun (max(0,elapsed-total)); not a job due time. v41r4_loop_budget.py:54.'},
        Parquet_fields={'contention_caused_RW_deadline_miss':'Same Actual contention diagnostic in DELAYED_JOBS, JOB_DECISIONS and PHYSICAL_EXECUTION_DISPATCH.'},
        raw_requests_all_124_no_deadline_fields=True,canonical_selected_all_184368_no_deadline_fields=True,
        discarded_proxies=['D-day end','B0 reference completion','optimized completion','requested walltime','safe_duration','RSP start','RW completion'],
        conclusion='No authoritative job-specific latest completion/window can be assigned to any of the 619 flagged or 677 migrated records.'))
    print('Authority scan review: C; all discovered deadline-like fields explained.')

if __name__=='__main__':main()
