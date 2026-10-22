"""Separate read-only local monitor. It cannot dispatch a scientific worker."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from datetime import datetime,timezone
import json
from . import config as c
from .io import optional,now
from .safety import alive,b2_state

HTML='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>V44_iteration2</title>
<style>body{margin:28px;background:#0d1724;color:#dde7f3;font:15px system-ui}h1{margin-bottom:8px}small{color:#a3b7ce}#summary{display:flex;gap:16px;margin:24px 0}.card{padding:18px;background:#19283b;border-radius:12px;flex:1}table{width:100%;border-collapse:collapse;background:#122034}td,th{padding:10px;text-align:left;border-bottom:1px solid #2c3f55}.PASS,.PLANNING_PASS{color:#56d9a2}.FAILED,.PLANNING_FAILED,.BLOCKED{color:#ff9898}.RUNNING,.PLANNING_RUNNING{color:#66beff}pre{white-space:pre-wrap;color:#b4c8de}a{color:#74c0ff}</style>
<h1>V44_iteration2 · 2025년 5월 B3</h1><small>MESS 4대 · 공통 변압기 825 kVA · M2/M3 0.955–1.045 · M4/Actual/Fresh 0.95–1.05</small>
<div id="summary"></div><p id="phase"></p><p id="b2"></p><pre id="resources"></pre>
<table><thead><tr><th>날짜</th><th>Planning</th><th>M2</th><th>A3</th><th>M3</th><th>A4</th><th>M4</th><th>Actual/Fresh</th></tr></thead><tbody id="days"></tbody></table>
<h3>현재 Worker · 최대 Actual 7개</h3><pre id="workers"></pre><pre id="error"></pre><small>원본 캠페인은 보존됩니다. 완료·Fresh PASS는 검증된 결과에서만 표시합니다. Native 시간은 측정 원장값이며 벽시계로 추정하지 않습니다.</small>
<script>
function el(tag,text,cls){let e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e}
async function refresh(){try{let s=await(await fetch('/api/status',{cache:'no-store'})).json();let summary=document.getElementById('summary');summary.replaceChildren();for(let [a,b] of [['Planning M4',s.planning_pass+'/31'],['Actual/Fresh PASS',s.actual_pass+'/31'],['실행 Worker',s.workers.length+'/7'],['연결',s.supervisor_alive?'정상':'감독기 확인 필요']])summary.append(el('div',a+' · '+b,'card'));
document.getElementById('phase').textContent=s.phase+' · '+s.UTC+' · 상태 수신 지연 '+s.age_seconds.toFixed(1)+'초';document.getElementById('b2').textContent='기존 B2: '+s.B2_phase+' · '+s.B2_terminal+'/10 종료 · 원장 '+s.B2_state_path;
let days=document.getElementById('days');days.replaceChildren();for(let j of s.jobs){let tr=el('tr','');tr.append(el('td',j.day));tr.append(el('td',j.status,j.status));for(let stage of ['M2','A3','M3','A4','M4']){let x=(j.stages||{})[stage]||{};let td=el('td',x.status||'대기',x.status);td.title=x.error||x.root||'';tr.append(td)}let a=j.actual||{};tr.append(el('td',a.status||'31일 M4 검증 대기',a.status));days.append(tr)}
document.getElementById('resources').textContent=s.resources?JSON.stringify(s.resources,null,2):'B2 완료 대기 · 신규 Planning/Actual 미실행';document.getElementById('workers').textContent=JSON.stringify(s.workers,null,2);document.getElementById('error').textContent=s.error||'';
}catch(e){document.getElementById('phase').textContent='모니터 수신 오류: '+e}}refresh();setInterval(refresh,2000);
</script></html>'''

def snapshot():
 state=optional(c.ROOT/'STATE.json');b2,pointer=b2_state();workers=[]
 for w in state.get('workers',[]):
  item=dict(w,alive=alive(w));root=Path(w['root']);stage=w.get('stage');core=root/c.CORE_STAGE.get(stage,'ACTUAL')
  item['progress']=optional(core/'progress.json') or optional(root/'progress.json')
  item['Native_completed_seconds']={n:optional(core/n).get('measured_Native_Runtime') for n in ('K48_NATIVE_LEDGER.json','JOINT_NATIVE_LEDGER.json','NATIVE_RUNTIME_LEDGER.json') if (core/n).exists()}
  workers.append(item)
 stamp=state.get('UTC',now())
 return dict(state,UTC=stamp,phase=state.get('phase','PREPARING'),age_seconds=max(0,datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(stamp).timestamp()),
  jobs=state.get('jobs',[]),workers=workers,supervisor_alive=alive(state.get('supervisor',{})),
  planning_pass=sum(bool(j.get('M4_freeze')) and j.get('status')=='PLANNING_PASS' for j in state.get('jobs',[])),
  actual_pass=sum(j.get('actual',{}).get('status')=='PASS' for j in state.get('jobs',[])),
  B2_phase=b2.get('phase'),B2_state_path=str(pointer),B2_terminal=sum(j.get('status') in ('PASS','FAILED','ACTUAL_FAILED','EXCLUDED') for j in b2.get('jobs',[])))

def serve(port=8796):
 class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
   try:
    if self.path.split('?',1)[0]=='/api/status':raw=json.dumps(snapshot(),ensure_ascii=False,allow_nan=False).encode();kind='application/json'
    elif self.path=='/':raw=HTML.encode();kind='text/html'
    else:self.send_error(404);return
    self.send_response(200);self.send_header('Content-Type',kind+'; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
   except Exception as error:self.send_error(503,str(error))
  def log_message(self,*args):pass
 ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
