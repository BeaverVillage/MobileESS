"""Keep existing worker exclusion; exempt only the inspected read-only monitor."""
import os
import psutil


def no_heavy_peer():
    conflicts=[]
    for p in psutil.process_iter(['pid','name','cmdline']):
        try:
            if p.pid==os.getpid() or (p.info['name'] or '').lower() not in ('python.exe','pythonw.exe','python'):continue
            argv=p.info['cmdline'] or []
            if '-m' in argv and argv[argv.index('-m')+1]=='v43_followup.monitor_binding':continue
            cmd=' '.join(argv).lower()
            if any(x in cmd for x in ('v43.golden','v43_followup','v43.weather_repair','v43.electrical_repair',
                    'audit_v42','native0','.worker','m_stage','solve_v42','v43_corrective.experiment','v43_corrective.compare')):
                conflicts.append(p.info)
        except psutil.Error:pass
    if conflicts:raise PermissionError('HEAVY_WORKER_CONFLICT:'+repr(conflicts))
