from pathlib import Path
import sys
from v42_pr134_b1.common import atomic, process, now, sha, read
from v42_may_campaign_native90.common import environment


def main():
    mode,raw=sys.argv[1:]
    root=Path(raw).resolve()
    if mode!='monitor' or root.drive.upper()!='D:':raise PermissionError('READ_ONLY_B2_MONITOR_ONLY')
    authority=read(root/'B2_MONITOR_V18_AUTHORITY.json')
    for name,expected in authority['sources'].items():
        if sha(Path(__file__).resolve().parents[1]/name)!=expected:raise PermissionError('MONITOR_SOURCE_SHA_DRIFT')
    environment(root)
    sys.stdout=(root/'monitor_v18.stdout.log').open('a',encoding='utf-8',buffering=1)
    sys.stderr=(root/'monitor_v18.stderr.log').open('a',encoding='utf-8',buffering=1)
    atomic(root/'MONITOR_V18_HOST.json',dict(process=process(),UTC=now(),read_only=True))
    from .monitor import run
    run(root)


if __name__=='__main__':main()
