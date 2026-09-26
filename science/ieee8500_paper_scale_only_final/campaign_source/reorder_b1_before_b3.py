"""Change only pending orchestration order; keep the live B2 worker running."""
import ast,json,time,sys,subprocess,hashlib
from pathlib import Path
import psutil
H=Path(__file__).absolute().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):
    temp=p.with_suffix(p.suffix+'.tmp')
    temp.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8');temp.replace(p)
def main():
    assert not psutil.pid_exists(105748)
    worker=psutil.Process(103248)
    assert 'mess_worker.py B2' in ' '.join(worker.cmdline())
    assert not (H/'B2/COMPLETE.json').exists()
    changed=[]
    for name in ['campaign_resume_after_sparse_b2.py','campaign_final.py']:
        p=H/name;s=p.read_text(encoding='utf-8')
        if name.startswith('campaign_resume'):
            start=s.index("    stage('B1_AIDC'")
            end=s.index("    stage('FINAL_REPORT'",start)
            block=s[start:end]
            s=s[:start]+s[end:]
            marker="    stage('B3_A1_AIDC'"
            s=s.replace(marker,block+"    assert read(H/'B1/COMPLETE.json')['status']=='PASS'\n    assert read(H/'Actual/B1/COMPLETE.json')['AC_feasible']\n"+marker,1)
        else:
            start=s.index('    run("B1_AIDC"')
            end=s.index('    run("FINAL_REPORT"',start)
            block=s[start:end];s=s[:start]+s[end:]
            s=s.replace('    run("B3_A1_AIDC"',block+'    run("B3_A1_AIDC"',1)
        s=s.replace('B0→B2→B3→B1','B0→B2→B1→B3').replace('B0, B2, B3, B1','B0, B2, B1, B3')
        s=s.replace("['B0','B2','B3','B1']","['B0','B2','B1','B3']")
        s=s.replace('["B0","B2","B3","B1"]','["B0","B2","B1","B3"]')
        tree=ast.parse(s);compile(tree,str(p),'exec')
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        calls=[n.value.args[0].value for n in fn.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
               and isinstance(n.value.func,ast.Name) and n.value.func.id in ('stage','run')]
        expected=['B2_ACTUAL','B1_AIDC','B1_ACTUAL','B3_A1_AIDC','B3_M1_ROUTE_PQ','B3_A2_AIDC','B3_M2_PQ','B3_ACTUAL','FINAL_REPORT']
        assert calls[-len(expected):]==expected,(name,calls)
        p.write_text(s,encoding='utf-8');changed.append(dict(file=name,stage_order=calls))
    substitutions={
        'report_final_campaign.py':[("ORDER=('B0','B2','B3','B1')","ORDER=('B0','B2','B1','B3')")],
        'monitor/server.py': [('ORDER = ("B0", "B2", "B3", "B1")','ORDER = ("B0", "B2", "B1", "B3")')],
        'monitor/index.html': [('function render(d){','function render(d){\n  d.order=d.campaign?.order||[\'B0\',\'B2\',\'B1\',\'B3\'];\n  d.results=[...(d.results||[])].sort((a,b)=>d.order.indexOf(a.policy)-d.order.indexOf(b.policy));')],
    }
    for name,pairs in substitutions.items():
        p=H/name;s=p.read_text(encoding='utf-8')
        for old,new in pairs:assert s.count(old)==1;s=s.replace(old,new)
        if p.suffix=='.py':compile(s,str(p),'exec')
        p.write_text(s,encoding='utf-8')
    logs=H/'B2_PAPER_TERMINATION_RUN_20260921';stamp=time.time_ns()
    with (logs/f'watcher_reordered_{stamp}.log').open('x',encoding='utf-8') as out:
        supervisor=subprocess.Popen([sys.executable,'-B','-u','campaign_resume_after_sparse_b2.py'],cwd=H,
            stdout=out,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    save(logs/'WATCHER.json',dict(PID=supervisor.pid,worker_pid=worker.pid,started_unix=time.time(),
        previous_watcher_pid=105748,order=['B0','B2','B1','B3']))
    status=read(H/'CAMPAIGN_STATUS.json');status.update(order=['B0','B2','B1','B3'],
        supervisor_pid=supervisor.pid,order_updated_unix=time.time())
    save(H/'CAMPAIGN_STATUS.json',status)
    save(H/'POLICY_ORDER_AUTHORITY.json',dict(status='PASS',order=['B0','B2','B1','B3'],
        Actual_after_each_policy=True,B2_worker_preserved=worker.pid,
        B3_requires_B1_and_Actual_PASS=True,B3_A1_independent_search_unchanged=True,
        stage_order_checks=changed,new_watcher_pid=supervisor.pid,unix=time.time()))
    print('REORDERED_B0_B2_B1_B3','worker',worker.pid,'watcher',supervisor.pid,flush=True)
if __name__=='__main__':main()
