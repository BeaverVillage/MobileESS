"""Read-only preparation/runtime view. No process launches or solver imports."""
from html import escape
from pathlib import Path
import argparse
import json
from .common import DOC,RUNTIME,read

FIELDS=('day','arm','stage','status','worker','pid','Native_used','Native_remaining','K48_LB','FULL_UB',
    'Global_Gap','gap_certified','FULL_feasible','timeout','Build_wall','Native_wall','Actual_wall',
    'Current_AC_wall','Fresh_wall','next_stage','next_day','error','resume')


def rows(manifest,root=RUNTIME):
    from .stages import CHAINS
    from .config import DAYS
    result=[]
    for case in manifest['cases']:
        chain=CHAINS[case['arm']]
        attempts=sorted((Path(root)/case['day']/case['arm']).glob('attempt*'))
        for index,stage in enumerate(chain):
            row=dict.fromkeys(FIELDS,None);row.update(day=case['day'],arm=case['arm'],stage=stage,
                status=case['status'],error='; '.join(case['blockers']),resume='NOT_STARTED',
                next_stage=chain[index+1] if index+1<len(chain) else None,
                next_day=DAYS[DAYS.index(case['day'])+1] if case['day']!=DAYS[-1] else None)
            if attempts:
                case_root=attempts[-1]
                physical_stage=stage[4:] if stage.startswith('K48_') else 'ACTUAL' if stage=='FRESH' else stage
                attempt=case_root/physical_stage
                if (case_root/'START.json').is_file():
                    start=read(case_root/'START.json');row.update(pid=start.get('pid'),worker=start.get('worker_slot'))
                if (case_root/'progress.json').is_file():
                    progress=read(case_root/'progress.json')
                    if progress.get('stage')==physical_stage or progress.get('stage')=='ACTUAL_FRESH' and stage in ('ACTUAL','FRESH'):
                        row.update(status='RUNNING',resume='ACTIVE_ATTEMPT')
                path=case_root/'A1_REUSE.json' if stage=='A1_REUSE' else Path(root)/'references'/case['day']/'AIDC_REFERENCE.json' if stage=='REFERENCE' else attempt/'RESULT.json'
                if path.is_file():
                    doc=read(path);row.update({k:doc[k] for k in FIELDS if k in doc})
                    row.update(status=doc.get('status','COMPLETE' if doc.get('PASS',stage=='REFERENCE') else 'FAILED'),
                        error=doc.get('error',''),resume='RESULT_PRESERVED')
                    for target,key in [('FULL_UB','Global_UB'),('K48_LB','Global_LB'),('gap_certified','global_gap_certified'),
                            ('Build_wall','build_wall_seconds'),('Native_wall','Native_seconds')]:
                        if key in doc:row[target]=doc[key]
                    if stage in ('ACTUAL','FRESH'):
                        metric=doc.get('variants',{}).get('C1',doc)
                        row['Actual_wall']=metric.get('actual_event_wall_seconds',metric.get('Actual_wall_seconds'))
                        row['Fresh_wall']=metric.get('Fresh_wall_seconds')
                        key=('Actual96_execution_PASS' if 'Actual96_execution_PASS' in metric else 'Actual96_PASS') if stage=='ACTUAL' else ('Fresh96_physical_PASS' if 'Fresh96_physical_PASS' in metric else 'Fresh96_PASS')
                        if key in metric:row['status']='COMPLETE' if metric[key] else 'COMPLETE_PHYSICAL_FAIL' if stage=='FRESH' else 'FAILED'
                ledger=attempt/('K48_NATIVE_LEDGER.json' if stage.startswith('K48_') else 'JOINT_NATIVE_LEDGER.json' if stage in ('M1','M2') else 'NATIVE_RUNTIME_LEDGER.json')
                if ledger.is_file():
                    doc=read(ledger);used=doc['measured_Native_Runtime']
                    row.update(Native_used=used,Native_remaining=max(0.,doc['Native_ceiling_seconds']-used))
                policies=attempt/'CORRECTIVE_POLICY_RECEIPTS.json'
                if stage in ('ACTUAL','FRESH') and policies.is_file():
                    entry=next((p for p in read(policies)['policies'] if p['variant']=='C1'),None)
                    if entry is not None:row['Current_AC_wall']=entry['timings'].get('current_AC_seconds')
                if (case_root/'RESUME_BLOCKED.json').is_file():
                    row.update(resume='RECONCILIATION_REQUIRED',error=read(case_root/'RESUME_BLOCKED.json')['reason'])
                row['attempt']=str(attempt)
            result.append(row)
    return result


def render(manifest,root=RUNTIME):
    data=rows(manifest,root)
    headers=''.join('<th>'+escape(k)+'</th>' for k in FIELDS)
    body=''.join('<tr>'+''.join('<td>'+escape('—' if r[k] is None else str(r[k]))+'</td>' for k in FIELDS)+'</tr>' for r in data)
    return ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta http-equiv="refresh" content="10">'
        '<title>V44 준비 현황</title><style>body{font:14px system-ui;margin:20px;background:#111827;color:#e5e7eb}'
        'table{border-collapse:collapse;white-space:nowrap}td,th{padding:8px;border:1px solid #374151}'
        'th{position:sticky;top:0;background:#1f2937}p{max-width:1100px}</style>'
        '<h1>V44 PREPARE ONLY</h1><p>실행 0회 · 입력 미인증은 INPUT_NOT_READY · 빈 수치는 미실행이며 0 또는 PASS를 뜻하지 않습니다. '
        'K48 300초 / Joint 900초 (서로 독립) · Main 1 / B2 2 · Forecast NOT_CERTIFIED</p>'
        '<p>V43 기존 모니터: <a href="http://127.0.0.1:8795/">현재 V43 상태</a></p>'
        '<div style="overflow:auto"><table><thead><tr>'+headers+'</tr></thead><tbody>'+body+'</tbody></table></div></html>')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--serve',action='store_true');parser.add_argument('--port',type=int,default=8796)
    args=parser.parse_args()
    if not args.serve:
        path=DOC/'MONITOR.html';path.write_text(render(read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')),encoding='utf8');print(path);return
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            page=render(read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')).encode()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(page)
        def log_message(self,*args):pass
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__=='__main__':main()
