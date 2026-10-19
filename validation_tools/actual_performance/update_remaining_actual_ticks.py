"""Extend and restart only the read-only monitor; preserve science processes."""
from pathlib import Path
import sys,json,shutil,subprocess,time,urllib.request
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r039 import operations as op
from v44.common import read,record,verify,atomic,now

def run():
    folder=Path('D:/MobileESS_V43/development/monitor_partial')
    target=folder/'monitor_binding.py'
    out=Path('D:/MobileESS_V44/development/MONITOR_REMAINING_ACTUAL_TICKS_20261018');out.mkdir(exist_ok=False)
    workers=[];pins=[]
    for w in op.base.workers():
        args=w['cmdline'];r=read(args[args.index('--worker')+1]);pins+=r['sources']+r.get('R039_sources',[])
        p=psutil.Process(w['pid']);workers.append(dict(pid=p.pid,process_created=p.create_time(),affinity=p.cpu_affinity()))
    verify(pins)
    assert str(target).casefold() not in {r['path'].casefold() for r in pins}
    source=target.read_text(encoding='utf-8');shutil.copy2(target,out/'monitor_binding.before.py')
    edits={
        'from v44_monitor_live import actual_state':'from v44_monitor_live import actual_state\nfrom actual_tick_details import details as remaining_actual_ticks, extend_html as actual_ticks_html',
        'workers=workers,cases=cases,stage_bounds=bound_history,case_line_loading=case_loading_table(campaign,cases),':
        'workers=workers,cases=cases,actual_tick_details=remaining_actual_ticks(campaign),stage_bounds=bound_history,case_line_loading=case_loading_table(campaign,cases),',
        "    return html.encode('utf8')":"    return actual_ticks_html(html).encode('utf8')",
    }
    for old,new in edits.items():
        assert source.count(old)==1,old
        source=source.replace(old,new)
    compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
    sys.path.insert(0,str(folder));import monitor_binding as binding
    value=binding.view(None);ticks=value['actual_tick_details']
    assert len(ticks['rows'])==8 and {(r['day'],r['arm']) for r in ticks['rows']}=={(f'2025-05-{d:02d}',a) for d in range(4,8) for a in ('B1','B3')}
    assert ticks['rows'][0]['completed_control_ticks']>0
    assert all(r['completed_control_ticks']==0 for r in ticks['rows'] if not r['actual_started'])
    html=binding.existing_index().decode('utf-8');assert html.count('id="actual-ticks-card"')==1
    atomic(out/'BEFORE_RESTART.json',dict(workers=workers,ticks=ticks))
    matches=[]
    for p in psutil.process_iter(['pid','cmdline']):
        try:
            if str(target) in (p.info['cmdline'] or []) and p.info['cmdline'][-1]=='8795':matches.append(p)
        except psutil.Error:pass
    assert len(matches)==1
    old=matches[0];command=old.cmdline();cwd=old.cwd();env=old.environ()
    assert old.pid not in [w['pid'] for w in workers]
    atomic(out/'MONITOR_BEFORE.json',dict(pid=old.pid,process_created=old.create_time(),command=command,cwd=cwd))
    old.terminate();old.wait(timeout=10)
    with (out/'stdout.log').open('ab') as stdout,(out/'stderr.log').open('ab') as stderr:
        p=subprocess.Popen(command,cwd=cwd,env=env,stdout=stdout,stderr=stderr,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(40):
        if p.poll() is not None:raise RuntimeError('MONITOR_EXITED')
        try:
            with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=3) as response:value=json.load(response)
            break
        except (OSError,ValueError):time.sleep(.25)
    else:raise RuntimeError('MONITOR_NOT_READY')
    assert len(value['actual_tick_details']['rows'])==8
    verify(pins);op.authority()
    for worker in workers:
        assert abs(psutil.Process(worker['pid']).create_time()-worker['process_created'])<.001
    atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,monitor_pid=p.pid,workers_untouched=workers,
        remaining_Actual=value['actual_tick_details'],sources=[record(target),record(folder/'actual_tick_details.py')],
        URL='http://127.0.0.1:8795/',small_read_only_journals=True))
    print(json.dumps(dict(PASS=True,monitor_pid=p.pid,remaining_Actual=value['actual_tick_details']),ensure_ascii=False))

if __name__=='__main__':run()
