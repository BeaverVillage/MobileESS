"""Resume orchestration with the Git executable available to detached children."""
from pathlib import Path
import os
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parent
GIT = Path(r'C:\Users\kjw39\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe')
assert GIT.is_file(), 'GIT_EXECUTABLE_MISSING'
os.environ['PATH'] = str(GIT.parent) + os.pathsep + os.environ.get('PATH', '')
os.environ['PYTHONPATH'] = str(ROOT)
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.chdir(ROOT)
git_version = subprocess.check_output(['git', '--version'], text=True).strip()

import restoration_revision_background as bg


def main():
    from dayahead.v41.campaign import campaign_lock
    with campaign_lock(bg.OUT / 'lock'):
        assert bg.r.read(bg.r.OUT / bg.DAY / bg.POLICY / 'ACCEPTANCE.json')['status'] == 'PASS'
        assert not (bg.r.NEWAC / 'replays' / bg.DAY / bg.POLICY / 'CANDIDATE_RECEIPT.json').exists()
        archive = bg.OUT / 'history' / ('git_path_failure_' + time.strftime('%Y%m%d_%H%M%S'))
        archive.mkdir(parents=True, exist_ok=False)
        for name in ('FAILURE.json', 'DISPATCHER_STATE.json', 'HEARTBEAT.json', 'HANDOFF_RECEIPT.json', 'B3_new_actual_v2.log'):
            path = bg.OUT / name
            if path.exists():
                shutil.copy2(path, archive / name)
        started = time.time()
        bg.atomic(bg.OUT / 'ENV_RESUME_RECEIPT.json', dict(
            status='RESUMED', pid=os.getpid(), git=str(GIT), git_version=git_version,
            source=bg.r.record(__file__), previous_failure_archive=str(archive),
            DA_reoptimization=False, scientific_code_changed=False, started_at=started))
        stage = 'ACTUAL'
        child, log = bg.launch(['selective_actual_revision_v1.py', bg.DAY, bg.POLICY], 'B3_new_actual_v2_env_r1')
        try:
            while True:
                bg.publish(stage, child.pid, log, [], started)
                if child.poll() is None:
                    time.sleep(5)
                    continue
                if child.returncode != 0:
                    raise RuntimeError((stage, 'WORKER_FAILED', child.returncode, log))
                if stage == 'ACTUAL':
                    done = bg.r.read(bg.r.NEWAC / 'replays' / bg.DAY / bg.POLICY / 'COMPLETE.json')
                    assert done['status'] == 'PASS' and not done['ETA95_QSAFE_ACTUAL']['physical_violation']
                    child, log = bg.launch(['restoration_revision_final_audit.py', '--final'], 'final_124_audit_env_r1')
                    stage = 'AUDIT'
                else:
                    result = bg.r.read(bg.r.OUT / 'FINAL_AUDIT.json')
                    assert result['status'] == 'COMPLETE' and result['counts']['total_accepted'] == 124
                    bg.atomic(bg.OUT / 'CAMPAIGN_FINISHED.json', dict(status='COMPLETE', finished_at=time.time(), final_audit=bg.r.record(bg.r.OUT / 'FINAL_AUDIT.json'), counts=result['counts']))
                    bg.publish('COMPLETE', None, log, [], started)
                    return
        except Exception as exc:
            error = dict(day=bg.DAY, phase='B3_' + stage, error=repr(exc), traceback=bg.traceback.format_exc(), log=log)
            bg.atomic(bg.OUT / 'FAILURE.json', error)
            bg.publish(stage, None, log, [error], started)
            raise


if __name__ == '__main__':
    main()
