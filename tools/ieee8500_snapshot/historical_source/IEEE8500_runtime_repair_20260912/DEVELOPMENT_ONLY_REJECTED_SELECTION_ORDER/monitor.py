from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import json
import ctypes,msvcrt,os
from ctypes import wintypes
K=ctypes.WinDLL('kernel32',use_last_error=True)
K.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
K.CreateFileW.restype=wintypes.HANDLE
def shared_bytes(path):
    handle=K.CreateFileW(str(path),0x80000000,7,None,3,0x80,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
    with os.fdopen(fd,'rb') as f:return f.read()
P=Path(__file__).absolute().parent
HTML='''<!doctype html><meta charset="utf-8"><title>IEEE8500 · V41R4 production</title><style>body{background:#101720;color:#e3edf8;font:16px system-ui;margin:36px;max-width:1150px}h1{font-size:28px}.card{background:#1c2938;padding:22px;border-radius:12px;margin:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}b{color:#68d9bd}.muted{color:#a1b4c9}progress{width:100%;height:20px}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #34485f}</style><h1>IEEE8500 · V41R4 production</h1><p class="muted">2025-05-21 · source 1.0400 · Vreg 123.5 V · α 0.50 · CAPBank3 OFF</p><div class="card"><b id="stage">Loading…</b><p id="status"></p><progress id="bar" max="14400" value="0"></progress><p id="clock"></p><p id="pid"></p></div><div class="card"><table><thead><tr><th>Policy</th><th>State</th><th>P1 / max line</th></tr></thead><tbody id="policies"></tbody></table></div><div class="card"><b>Checkpoints · 30 min / 1 h / 2 h / 4 h</b><pre id="checkpoints"></pre></div><div class="card"><b>Live metrics / failure detail</b><pre id="detail"></pre></div><p class="muted">Model preparation is separate from the continuous 4-hour search clock. Only independently validated feasible incumbents are retained.</p><script>async function tick(){try{let s=await(await fetch('/api/status',{cache:'no-store'})).json();stage.textContent=s.stage||'Preparing';status.textContent=s.status;let e=s.search_started?Math.min(14400,s.search_elapsed_seconds||0):0;if(s.search_started&&s.search_started_unix&&!s.search_stopped)e=Math.min(14400,Date.now()/1000-s.search_started_unix);bar.value=e;clock.textContent=s.search_started?'Search '+(e/3600).toFixed(3)+' / 4.000 hours':'Search has not started — preparing the verified model';pid.textContent='Worker PID '+s.pid+' · updated '+new Date(s.updated_unix*1000).toLocaleTimeString();policies.innerHTML=['B0','B1','B2','B3'].map(p=>'<tr><td>'+p+'</td><td>'+(s.policy_results?.[p]?.status||(p==='B0'&&s.B0?'PASS':'Pending'))+'</td><td>'+(s.policy_results?.[p]?.P1??(p==='B0'?s.B0?.max_phase_line_loading_pu:'')??'')+'</td></tr>').join('');checkpoints.textContent=JSON.stringify(s.checkpoints||{},null,2);detail.textContent=JSON.stringify(s,null,2)}catch(e){status.textContent='Waiting for status file: '+e}}tick();setInterval(tick,2000)</script>'''
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body=shared_bytes(P/'STATUS.json') if self.path=='/api/status' else HTML.replace('status.textContent','document.getElementById("status").textContent').replace("(p==='B0'&&s.B0?'PASS':'Pending')","(p==='B0'&&s.B0?'PASS':s.stage?.startsWith(p+':')&&s.status==='RUNNING'?'RUNNING':'Pending')").encode()
            self.send_response(200);self.send_header('Content-Type','application/json' if self.path=='/api/status' else 'text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
        except Exception:self.send_error(503)
    def log_message(self,*args):pass
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',8510),Handler).serve_forever()
