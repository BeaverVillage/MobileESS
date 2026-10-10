"""Small read-only automatically refreshed official campaign dashboard."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import argparse,json,time,statistics
from v42_pr134_b1.common import read,atomic,now
from .processes import identity,live
from . import ORDER

PAGE='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V42 SVR11 · May 2025</title><style>
body{font:16px system-ui;background:#f5f6f8;color:#172339;margin:0}main{max-width:1050px;margin:40px auto;padding:0 24px}h1{font-size:28px;margin:0}small{color:#607087}header{display:flex;justify-content:space-between;align-items:center}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.card,section{background:white;border:1px solid #dfe4eb;border-radius:12px;padding:20px}.value{font-size:28px;font-weight:650;margin-top:8px}section{margin:16px 0}table{width:100%;border-collapse:collapse}td,th{padding:12px 8px;text-align:left;border-bottom:1px solid #edf0f5}button{background:#eef2fa;border:0;padding:8px 12px;border-radius:7px;cursor:pointer}.PASS{color:#08765c}.FAIL{color:#b72d39}.RUNNING{color:#2457b3}.bar{height:6px;background:#d9e5f8;border-radius:3px;margin-top:18px}.bar div{height:100%;background:#2457b3}#days{display:flex;gap:7px;flex-wrap:wrap}.err{color:#b72d39}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}dialog{max-width:800px;border:1px solid #dfe4eb;border-radius:12px}a{color:#2457b3}@media(max-width:650px){.cards{grid-template-columns:1fr 1fr}main{margin:24px auto;padding:0 14px}}</style><main><header><div><h1>V42 · SVR11</h1><small>2025년 5월 공식 캠페인 · B0 → B2 → B1 → B3</small></div><small id="updated">연결 중</small></header><div id="cards" class="cards"></div><section><h3>정책 진행률</h3><table><thead><tr><th>정책</th><th>PASS</th><th>FAIL</th><th>RUNNING</th><th>남은 날짜</th></tr></thead><tbody id="policies"></tbody></table></section><section><h3>현재 작업</h3><div id="current"></div></section><section><h3>날짜별 결과</h3><p><select id="policy" onchange="days()"><option>B0</option><option>B2</option><option>B1</option><option>B3</option></select> 날짜를 선택하면 전압·부하율·위반 건수를 확인합니다.</p><div id="days"></div></section><section><h3>최근 주요 오류</h3><div id="errors"></div></section><small id="source"></small><p><a href="/report">캠페인 보고서</a> · <a href="/evidence">실행·무결성 근거</a></p><dialog id="detail"><button onclick="detail.close()">닫기</button><div id="detailbody"></div></dialog></main><script>
let state;const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const num=v=>v==null?'—':Number(v).toLocaleString(undefined,{maximumFractionDigits:3});
async function update(){try{state=await(await fetch('/api/state',{cache:'no-store'})).json();let c=state.counts;cards.innerHTML=[['완료 / 전체',c.completed+' / 124'],['현재 정책',state.policy||state.status],['PASS / FAIL',c.PASS+' / '+c.FAIL],['활성 Worker / ETA',state.workers.length+' / '+state.ETA]].map(([k,v])=>'<div class="card"><small>'+esc(k)+'</small><div class="value">'+esc(v)+'</div></div>').join('');policies.innerHTML=state.policies.map(p=>'<tr><td>'+p.policy+'</td><td class="PASS">'+p.PASS+'</td><td class="FAIL">'+p.FAIL+'</td><td class="RUNNING">'+p.RUNNING+'</td><td>'+p.remaining+'</td></tr>').join('');current.innerHTML=state.workers.length?state.workers.map(w=>'<p><b>'+esc(w.arm+' '+w.day)+'</b> · '+esc(w.phase)+'<br>Native '+num(w.Native_Runtime)+' s · Best feasible UB '+num(w.UB)+'<br><small>인증 LB '+num(w.certified_LB)+' · 인증 Gap '+num(w.certified_Gap)+' · Fresh '+esc(w.Fresh)+' · PID '+w.PID+'</small></p>').join(''):'<p>'+esc(state.status)+'</p>';errors.innerHTML=state.errors.length?state.errors.map(e=>'<p class="err">'+esc(e)+'</p>').join(''):'기록된 오류 없음';updated.textContent='자동 갱신 · '+new Date().toLocaleTimeString();source.textContent='Source '+state.source_SHA+' · '+state.root;days()}catch(e){updated.textContent='HTTP 연결 오류: '+e.message}}function days(){if(!state)return;let a=policy.value;document.getElementById('days').innerHTML=state.dates.filter(r=>r.arm===a).map(r=>'<button class="'+r.status+'" onclick="show(\''+r.arm+'/'+r.day+'\')">'+r.day.slice(-2)+' · '+r.status+'</button>').join('')}async function show(key){let r=await(await fetch('/api/date?key='+encodeURIComponent(key))).json();detailbody.innerHTML='<h3>'+esc(r.arm+' '+r.day+' · '+r.status)+'</h3><p>'+esc(r.reason||'')+'</p><pre>'+esc(JSON.stringify(r.metrics||{},null,2))+'</pre><details><summary>상세 실행 근거</summary><pre>'+esc(JSON.stringify(r,null,2))+'</pre></details>';detail.showModal()}update();setInterval(update,5000);
</script></html>'''

def snapshot(root):
    root=Path(root);m=read(root/'CAMPAIGN_MANIFEST.json');ledger=read(root/'CAMPAIGN_LEDGER.json') if (root/'CAMPAIGN_LEDGER.json').exists() else {'dates':{},'status':'NOT_STARTED'}
    rows=list(ledger['dates'].values());counts={s:sum(r['status']==s for r in rows) for s in ('PASS','FAIL','RUNNING','NOT_EXECUTED')};counts['completed']=counts['PASS']+counts['FAIL']
    peers=[]
    for r in rows:
        if r['status']!='RUNNING' or not live(r.get('worker',{})):continue
        request=read(r['request']);p=Path(request['progress']);v=read(p) if p.exists() else {}
        certified=v.get('global_gap_certified') is True
        fresh=[]
        for f in Path(request['output']).rglob('*_PROGRESS.json'):
            if f.name.startswith('VOLTAGE_CONTROL_'):
                a=read(f);fresh.append(a['namespace']+' '+str(a['logical_Fresh_slots_completed'])+'/96')
        peers.append(dict(arm=r['arm'],day=r['day'],PID=r['worker']['PID'],phase=v.get('stage',v.get('phase','STARTING')),
            Native_Runtime=v.get('Native_Runtime',v.get('native_runtime_seconds',v.get('measured_native_runtime',0))),
            UB=v.get('Best_Feasible_UB',v.get('verified_UB',v.get('UB'))),certified_LB=v.get('Certified_Global_LB'),
            certified_Gap=v.get('Certified_Gap') if certified else None,Fresh=', '.join(fresh) or '대기'))
    policies=[];estimate=0.;known=True
    for arm in ORDER:
        axis=[r for r in rows if r['arm']==arm];p=dict(policy=arm,**{s:sum(r['status']==s for r in axis) for s in ('PASS','FAIL','RUNNING')})
        p['remaining']=31-p['PASS']-p['FAIL']-p['RUNNING'];policies.append(p)
        durations=[r['wall_seconds'] for r in axis if r.get('wall_seconds') is not None and r['status'] in ('PASS','FAIL')]
        if p['remaining']+p['RUNNING']:
            if not durations:known=False
            else:estimate+=(p['remaining']+p['RUNNING'])*statistics.median(durations)/m['worker_counts'][arm]
    return dict(status=ledger['status'],policy=ledger.get('policy'),counts=counts,workers=peers,policies=policies,dates=rows,
        ETA=f'{estimate/3600:.1f} h' if known else '측정 중',errors=[r['arm']+' '+r['day']+': '+str(r.get('reason')) for r in rows if r['status']=='FAIL'][-3:]+([ledger['error']] if ledger.get('error') else []),
        source_SHA=m['execution_SHA'],root=str(root),UTC=now())

def serve(root,port):
    root=Path(root).resolve()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            from urllib.parse import urlsplit,parse_qs
            url=urlsplit(self.path)
            try:
                if url.path=='/':body=PAGE;mime='text/html; charset=utf-8'
                elif url.path=='/api/state':body=json.dumps(snapshot(root),ensure_ascii=False);mime='application/json; charset=utf-8'
                elif url.path=='/api/date':
                    key=parse_qs(url.query)['key'][0];body=json.dumps(read(root/'CAMPAIGN_LEDGER.json')['dates'][key],ensure_ascii=False);mime='application/json; charset=utf-8'
                elif url.path=='/report':body=(root/'REPORT.md').read_text(encoding='utf8');mime='text/plain; charset=utf-8'
                elif url.path=='/evidence':body=json.dumps({name:read(root/name) for name in ('SUPERVISOR_PROCESS.json','WATCHDOG_LAST_RUN.json') if (root/name).exists()},ensure_ascii=False,indent=2);mime='application/json; charset=utf-8'
                else:self.send_error(404);return
                data=body.encode('utf8');self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            except Exception as error:self.send_error(503,str(error))
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    atomic(root/'MONITOR_PROCESS.json',dict(identity(),root=str(root),port=port,source_SHA=read(root/'CAMPAIGN_MANIFEST.json')['execution_SHA']))
    server.serve_forever()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--port',type=int,default=8796);args=p.parse_args();serve(args.root,args.port)
