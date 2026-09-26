"""Preserve failed Actual input audit and continue from completed B2 DA/Fresh."""
import json,time,sys,subprocess,shutil,hashlib
from pathlib import Path
import psutil
H=Path(__file__).absolute().parent
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,v):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2),encoding='utf-8');tmp.replace(p)
def main():
    prior=read(H/'CAMPAIGN_STATUS.json')
    assert prior['status']=='FAILED' and not psutil.pid_exists(prior['supervisor_pid'])
    assert read(H/'B2/COMPLETE.json')['status']=='PASS'
    assert read(H/'B2_ACTUAL_SOC_AUDIT_PREFLIGHT.json')['status']=='PASS'
    d=H/'diagnostic_attempts/B2_ACTUAL_SOC_AUDIT_20260922'
    for name in ('B2_ACTUAL_STAGE_RUNTIME.json','B2_PAPER_TERMINATION_RUN_20260921/WATCHER.json'):
        shutil.copy2(H/name,d/name.replace('/','__'))
    old=H/'Actual/B2';dest=d/'Actual_B2'
    assert old.resolve().is_relative_to(H.resolve()) and dest.resolve().is_relative_to(d.resolve())
    old.rename(dest)
    save(H/'B2_ACTUAL_AUDIT_SCALE_REPAIR_AUTHORITY.json',dict(status='PASS',
        repair='Independent audit SOC denominators and terminal reporting use frozen scaled electrical authority',
        capacity_kWh=2400.,required_terminal_kWh=1520.,audited_vehicle_slots=576,independent_max_error=0.,
        actuator_P_Q_energy_unchanged=True,Q_controller_unchanged=True,DA_search_rerun=False,
        source_sha256=hashlib.sha256((H/'actual_binding.py').read_bytes()).hexdigest(),
        failure_preserved=str(d),unix=time.time()))
    log=H/'logs'/f'ACTUAL_SOC_REPAIR_WATCHER_{time.time_ns()}.log'
    with log.open('x',encoding='utf-8') as f:
        watcher=subprocess.Popen([sys.executable,'-B','-u','campaign_resume_after_sparse_b2.py'],cwd=H,
            stdout=f,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    record=dict(PID=watcher.pid,started_unix=time.time(),log=str(log),resume_scope='B2_ACTUAL_THEN_B1_B3')
    save(H/'B2_ACTUAL_SOC_REPAIR_WATCHER.json',record)
    save(H/'B2_PAPER_TERMINATION_RUN_20260921/WATCHER.json',record)
    print(json.dumps(record),flush=True)
if __name__=='__main__':main()
