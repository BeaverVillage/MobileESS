"""Single explicit native issue-axis conversion shared by live and replay."""
from copy import deepcopy
from .frozen_unknown import _migration_capability


def compile_known_commands(selected_jobs, *, slot_zero_seconds, migration_authority=None, gpu_by_uid=None):
    commands={}
    for uid,option in selected_jobs.items():
        if 'start_seconds' in option:
            commands[uid]=deepcopy(option);continue
        command=dict(start_seconds=slot_zero_seconds+option['start']*900,
            site=option['initial_site'],original_option=deepcopy(option))
        if gpu_by_uid and uid in gpu_by_uid:
            command['protected_segments']=[dict(resource='gpu:'+s,begin=slot_zero_seconds+a*900,
                end=slot_zero_seconds+b*900,quantity=gpu_by_uid[uid]) for s,a,b in option['segments'] if b>a]
        if option.get('checkpoint',-1)>=0:
            command.update(migration_destination=option['destination'],
                checkpoint_control_seconds=slot_zero_seconds+option['checkpoint']*900,
                physical_checkpoint_seconds=slot_zero_seconds+option['physical_checkpoint_seconds'],
                planned_migration_times={k:slot_zero_seconds+option[k]*900
                    for k in ('transfer_start','transfer_end','restart_end')},planned_wan=deepcopy(option['wan']))
            if migration_authority and gpu_by_uid and uid in gpu_by_uid:
                command['migration_capability']=_migration_capability(migration_authority,
                    option['initial_site'],option['destination'],gpu_by_uid[uid])
                cap=command['migration_capability']
                if cap:
                    times=dict(checkpoint=command['checkpoint_control_seconds'],**command['planned_migration_times'],
                        restart_start=command['planned_migration_times']['transfer_end'])
                    a,b=times['transfer_start'],times['transfer_end']
                    command['protected_segments'].extend([
                        dict(resource='wan:'+cap['wan_path'],begin=a,end=b,quantity=cap['bandwidth_bytes_per_second']),
                        dict(resource='active:WAN',begin=a,end=b,quantity=1),
                        *[dict(resource='wan:LINK::'+link,begin=a,end=b,quantity=cap['bandwidth_bytes_per_second']) for link in cap['route_links']]])
                    for site,left,right in ((option['initial_site'],command['physical_checkpoint_seconds'],times[cap['source_hold_until']]),
                        (option['destination'],times[cap['destination_hold_from']],times['restart_end'])):
                        if right>left:command['protected_segments'].append(dict(resource='gpu:'+site,begin=left,end=right,quantity=gpu_by_uid[uid]))
        commands[uid]=command
    return commands
