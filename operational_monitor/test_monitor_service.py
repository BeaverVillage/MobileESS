import json,tempfile,time
from pathlib import Path
from unittest.mock import patch
import monitor_service as service

def main():
    checks=[]
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);case=root/'2025-05-22/B1/attempt002';case.mkdir(parents=True)
        (case/'ACTUAL_START.json').write_text(json.dumps(dict(pid=77,process_created=123)),encoding='utf8')
        worker=dict(day='2025-05-22',arm='B1',pid=77)
        batch=dict(phase='MAIN_ACTUAL_PARALLEL',jobs=[dict(day='2025-05-22',arm='B1',status='ACTUAL_RUNNING',case_root=str(case)),dict(day='2025-05-31',arm='B3',status='PREPARED')])
        value=dict(workers=[worker],cases=[dict(day='2025-05-22',arm='B1',status='RUNNING')],
            campaign_summary=dict(actual_eligible=2,prepared_waiting=1),
            case_line_loading=dict(rows=[dict(day='2025-05-22',scope='current',cells=[dict(arm='B1',percent=None,tone='live')]),dict(day='2025-05-22',scope='current',cells=[dict(arm='B0',percent=50.,tone='pass',state='Fresh PASS')])]),
            actual_tick_details=dict(rows=[dict(day='2025-05-22',arm='B1',actual_control_complete=False)]))
        disconnected=service.normalize(value,root,batch,dict(pid=88,process_created=456),alive=lambda identity:False)
        assert disconnected['workers']==[] and disconnected['campaign_summary']['actual_running']==0
        assert disconnected['state']=='DISCONNECTED' and disconnected['cases'][0]['status']=='DISCONNECTED'
        assert disconnected['campaign_summary']['stale_workers']==1
        assert disconnected['case_line_loading']['rows'][0]['cells'][0]['state']=='프로세스 종료'
        assert disconnected['case_line_loading']['rows'][1]['cells'][0]['state']=='Fresh PASS'
        assert disconnected['run_id']=='V44 · 5월 22~31일 캠페인'
        assert value['cases'][0]['status']=='RUNNING'  # journal input not mutated
        connected=service.normalize(value,root,batch,dict(pid=88,process_created=456),alive=lambda identity:True)
        assert len(connected['workers'])==1 and connected['campaign_summary']['actual_running']==1
        checks.append('live_and_terminated_workers_separated_without_journal_or_completed_Fresh_mutation')
    store=service.SnapshotStore()
    with patch.object(service,'snapshot',return_value=dict(status='정상')):store.refresh()
    code,cached=store.response();assert code==200 and cached['status']=='정상'
    with patch.object(service,'snapshot',side_effect=ValueError('한글 상태 조회 오류')),patch.object(service.binding,'atomic'):store.refresh()
    code,cached=store.response();assert code==200 and cached['state']=='MONITOR_ERROR'
    assert json.loads(json.dumps(cached,ensure_ascii=False))['reason']=="ValueError('한글 상태 조회 오류')"
    checks.append('failed_snapshot_keeps_last_value_and_returns_UTF8_error_as_JSON_data')
    page=service.index()
    assert isinstance(page,bytes) and '<html' in page.decode('utf8')
    assert '5월 8~14일 캠페인' not in page.decode('utf8')
    checks.append('existing_monitor_HTML_bytes_render_with_current_campaign_heading')
    report=dict(PASS=True,checks=checks,Native_calls=0,scientific_files_written=0)
    service.binding.atomic(service.HOME/'TEST_RESULT.json',report);print(report)

if __name__=='__main__':main()
