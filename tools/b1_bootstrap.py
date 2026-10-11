"""Scheduled B1-only Native0 qualification gate; no scientific calls."""
from pathlib import Path
import sys,traceback,subprocess
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import b1_only_v3 as b

def tick():
    root=b.DEFAULT_ROOT
    with b.singleton(root/'BOOTSTRAP.lock'):
        contract=b.read(root/'BOOTSTRAP_CONTRACT.json')
        assert b.record(__file__)==contract['bootstrap_source']
        assert b.record(ROOT/'tools/verify_b1_only_release_v3.py')==contract['independent_verifier']
        m=b.verify_only(root)
        if (root/'BOOTSTRAP_READY.json').exists():return
        if (root/'BOOTSTRAP_ERROR.json').exists():return
        old=Path(r'D:\v42_b1_only_may_20261012');proof=old/'NATIVE0_PREFLIGHT.json'
        try:
            if not proof.exists():
                receipt=b.read(old/'PREFLIGHT_PROCESS.json')
                if not b.live(receipt):raise RuntimeError('NATIVE0_PROCESS_EXITED_WITHOUT_VERIFIED_RECEIPT')
                b.atomic(root/'BOOTSTRAP_HEARTBEAT.json',dict(status='WAIT_NATIVE0',original_preflight=receipt,UTC=b.now()))
                return
            if not b.read(proof)['PASS']:raise RuntimeError('NATIVE0_FAILED')
            receipt=b.read(old/'PREFLIGHT_PROCESS.json')
            if b.live(receipt):
                b.atomic(root/'BOOTSTRAP_HEARTBEAT.json',dict(status='WAIT_PREFLIGHT_NATURAL_EXIT',UTC=b.now()));return
            from tools.verify_b1_only_release_v3 import audit
            if not (root/'RELEASE_INDEPENDENT_AUDIT.json').exists():audit(root)
            if not b.read(root/'RELEASE_INDEPENDENT_AUDIT.json')['PASS']:raise RuntimeError('INDEPENDENT_RELEASE_AUDIT_FAILED')
            ok,obs=b.admitted(root,m)
            if not ok:
                b.atomic(root/'BOOTSTRAP_HEARTBEAT.json',dict(status='WAIT_RESOURCE',observation=obs,UTC=b.now()));return
            # Only this new B1 watchdog is registered. Old Tasks remain unchanged.
            command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
                     str(ROOT/'tools/register_b1_only_v3.ps1'),'-CampaignRoot',str(root),'-SourceRoot',str(ROOT)]
            run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
            if run.returncode:raise RuntimeError('B1_TASK_REGISTRATION_FAILED:'+run.stdout+run.stderr)
            b.atomic(root/'BOOTSTRAP_READY.json',dict(PASS=True,Native0=b.record(root/'NATIVE0_PREFLIGHT.json'),
                independent_audit=b.record(root/'RELEASE_INDEPENDENT_AUDIT.json'),admission=obs,
                task='MobileESS_V42_B1_Only_May2025_20261012_V3_Watchdog',UTC=b.now()))
        except Exception as error:
            b.atomic(root/'BOOTSTRAP_ERROR.json',dict(PASS=False,error=repr(error),traceback=traceback.format_exc(),UTC=b.now()))
            raise

if __name__=='__main__':tick()
