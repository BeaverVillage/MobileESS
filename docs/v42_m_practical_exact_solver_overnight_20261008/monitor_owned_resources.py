"""Observe one registered M-stage PID; no solver calls or process mutations."""
import csv,json,os,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
import psutil
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
def atomic(p,r):
    t=p.with_name(p.name+'.tmp')
    with t.open('w',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(t,p)
def run():
    owned=[];expected=(OUT/'selected_external_controller.py').resolve()
    for q in psutil.process_iter(['pid']):
        try:
            cmd=q.cmdline();cwd=Path(q.cwd()).resolve()
            if len(cmd)<2 or cwd!=ROOT.resolve():continue
            s=Path(cmd[1]);s=(cwd/s).resolve() if not s.is_absolute() else s.resolve()
            if s==expected:owned.append(q)
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    assert len(owned)==1,'EXPECTED_EXACTLY_ONE_REGISTERED_SELECTED_PROCESS'
    q=owned[0];created=q.create_time();start=datetime.now(timezone.utc)
    deadline=datetime.fromisoformat(json.loads((OUT/'IMMUTABLE_DEADLINE.json').read_text())['deadline_UTC'])
    provenance=dict(PID=q.pid,create_time=created,script=str(expected),cmdline=q.cmdline(),cwd=str(ROOT),observer_start_UTC=start.isoformat(),optimize_calls=0,process_mutations=0)
    atomic(OUT/'OWNED_RESOURCE_MONITOR_REGISTRATION.json',provenance)
    peak=0;windows_peak=0;last=None;count=0
    with (OUT/'OWNED_RESOURCE_TELEMETRY.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['UTC','PID','seconds_since_process_creation','RSS','Windows_lifetime_peak_wset','CPU_user','CPU_system']);w.writeheader()
        while datetime.now(timezone.utc)<deadline:
            try:
                assert q.create_time()==created and Path(q.cwd()).resolve()==ROOT.resolve()
                mem=q.memory_info();cpu=q.cpu_times();now=datetime.now(timezone.utc)
                last=dict(UTC=now.isoformat(),PID=q.pid,seconds_since_process_creation=now.timestamp()-created,RSS=mem.rss,Windows_lifetime_peak_wset=getattr(mem,'peak_wset',None),CPU_user=cpu.user,CPU_system=cpu.system)
                w.writerow(last);f.flush();peak=max(peak,mem.rss);windows_peak=max(windows_peak,getattr(mem,'peak_wset',0));count+=1
                atomic(OUT/'OWNED_RESOURCE_LIVE.json',dict(provenance=provenance,samples=count,last=last,observed_peak_RSS=peak,Windows_lifetime_peak_wset=windows_peak))
            except (psutil.NoSuchProcess,psutil.ZombieProcess):break
            time.sleep(min(15,max(0,(deadline-datetime.now(timezone.utc)).total_seconds())))
    atomic(OUT/'OWNED_RESOURCE_MONITOR_RESULT.json',dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),provenance=provenance,samples=count,last=last,observed_peak_RSS=peak,Windows_lifetime_peak_wset=windows_peak,optimize_calls=0,process_mutations=0,scope='Windows OS peak working set since this selected solver process creation includes build, LP, replay and audit; observer itself began later',older_closed_process_outside_solve_peak_not_reconstructable=True))
if __name__=='__main__':run()
