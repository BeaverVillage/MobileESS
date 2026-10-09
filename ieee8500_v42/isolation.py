"""Read-only campaign evidence; running ledgers are observed, never modified."""
from pathlib import Path
import argparse
import json
import subprocess
from .common import REPORT, read, write, receipt

CAMPAIGN = Path('D:/MobileESS_V42/runtime/v42_may_campaign/native90_build_reuse_20261009_01')
SOURCE = Path('D:/MobileESS_V42')


def scheduler_registration_diff(before, after):
    """Audit existing registrations separately from new concurrent tasks."""
    def records(rows):
        if not isinstance(rows,list):rows=[rows]
        return {r['TaskPath']+r['TaskName']:{k:v for k,v in r.items() if k!='State'}
                for r in rows}
    b,a=records(before),records(after)
    return dict(added=sorted(set(a)-set(b)),removed=sorted(set(b)-set(a)),
                modified=sorted(k for k in set(b)&set(a) if b[k]!=a[k]))


def capture(label):
    immutable = {}
    for pattern in ('*MANIFEST.json', '*PERMIT.json'):
        for path in sorted(CAMPAIGN.glob(pattern)):
            immutable[str(path)] = receipt(path)
    for folder in ('v42_may25_recovery_v9', 'v42_may_mess_build_v7', 'v42_may_build_v6',
                   'v42_native', 'v42_regcontrol', 'v42_thermal'):
        for path in sorted((SOURCE / folder).glob('*.py')):
            immutable[str(path)] = receipt(path)
    base = read(CAMPAIGN / 'CAMPAIGN_MANIFEST.json')
    for folder in base.get('input_folders', {}).values():
        if str(folder).endswith('2025-05-01'):
            for path in sorted(Path(folder).iterdir()):
                if path.is_file():
                    immutable[str(path)] = receipt(path)
    command = "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|gurobi' } | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Depth 3"
    processes = subprocess.check_output(['powershell', '-NoProfile', '-Command', command], text=True, encoding='utf8')
    schedule_command = "Get-ScheduledTask | Where-Object { $_.TaskName -match 'MobileESS_V42|v42' } | Select-Object TaskName,TaskPath,State,@{n='Actions';e={$_.Actions|Select-Object Execute,Arguments}},@{n='Triggers';e={$_.Triggers|Select-Object StartBoundary,Enabled}} | ConvertTo-Json -Depth 5"
    scheduler = subprocess.check_output(['powershell', '-NoProfile', '-Command', schedule_command], text=True, encoding='utf8')
    observed = {}
    for name in ('ACTIVE.json', 'ACTIVE_V9.json', 'CHECKPOINT_V9.json', 'CAMPAIGN_STATUS.json'):
        p = CAMPAIGN / name
        if p.exists():
            observed[name] = receipt(p)
    doc = dict(label=label, immutable_files=immutable,
               processes=json.loads(processes or '[]'), scheduler=json.loads(scheduler or '[]'),
               mutable_live_state_observed_only=observed,
               source_version_worker_scheduler_input_ledger_budget_writes=0,
               worker_kills=0, scheduler_mutations=0,
               ledger_hash_changes_can_be_normal_live_progress=True)
    write(REPORT / ('CAMPAIGN_ISOLATION_' + label + '.json'), doc)
    before_path = REPORT / 'CAMPAIGN_ISOLATION_before.json'
    if label == 'after' and before_path.exists():
        before = read(before_path)
        drift = [name for name, r in before['immutable_files'].items()
                 if immutable.get(name) != r]
        # Preserve each originally observed authority while recording newly
        # registered concurrent tasks. New tasks are NOT silently discarded.
        scheduler_diff = scheduler_registration_diff(before['scheduler'],doc['scheduler'])
        scheduler_drift = bool(scheduler_diff['removed'] or scheduler_diff['modified'])
        write(REPORT / 'CAMPAIGN_PRESERVATION_CHECK.json', dict(
            PASS=not drift and not scheduler_drift, immutable_files_checked=len(before['immutable_files']),
            scope='PRESERVATION_OF_ORIGINALLY_OBSERVED_AUTHORITIES_NOT_IDENTICAL_LIVE_GLOBAL_STATE',
            immutable_file_changes=drift, existing_scheduler_registration_change=scheduler_drift,
            scheduler_snapshot_identical=not any(scheduler_diff.values()),scheduler_registration_diff=scheduler_diff,
            newly_observed_files=sorted(set(immutable)-set(before['immutable_files'])),
            own_external_mutations=0, mutable_checkpoint_equality_required=False,
            limitation='Read-only snapshots compare original authorities. New RecoveryV10 tasks were observed during this work; their registering actor is not established here. This work invoked no scheduler mutation or campaign write.'))
    print(label, len(immutable), 'immutable authority files captured; no campaign mutations.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('label', choices=('before', 'after'))
    capture(parser.parse_args().label)

