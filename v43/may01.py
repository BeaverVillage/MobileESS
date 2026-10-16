"""Official May01 entry: corrected Actual and certified fast AC for all arms."""
from pathlib import Path
import argparse

from .common import DOC,read,verify_records


def actual(arm,output,*,reference_folder=None,mess_result=None,correction_proof=None):
    pointer=DOC/'V43_CURRENT_AC_PRODUCTION_CERTIFICATION_POINTER.json'
    if not pointer.exists():
        raise RuntimeError('RUN_REAL_PREFIX_EQUIVALENCE_AND_B1_PAIRED_CANARY_BEFORE_FULL_ACTUAL')
    bound=read(pointer)['certificate'];verify_records([bound])
    from v43_corrective.compare import run
    return run(arm,output,reference_folder=reference_folder,mess_result=mess_result,
        correction_proof=correction_proof,control_slots=120,ac_mode='FAST',ac_certification=bound['path'])


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    for name in ('actual','canary'):
        a=s.add_parser(name);a.add_argument('arm',choices=['B0','B1','B2','B3']);a.add_argument('output')
        a.add_argument('--reference-folder');a.add_argument('--mess-result');a.add_argument('--correction-proof')
        if name=='canary':a.add_argument('--ac-mode',choices=['FULL_REFERENCE','SHADOW'],default='SHADOW')
    for name in ('verify-ac','diagnose'):
        a=s.add_parser(name);a.add_argument('output')
    a=s.add_parser('mess');a.add_argument('request')
    args=vars(p.parse_args());action=args.pop('action')
    if action=='actual':return actual(**args)
    if action=='canary':
        from v43_corrective.compare import run
        return run(**args,control_slots=25)
    if action=='verify-ac':
        from v43_corrective.verify_ac import run
        return run(**args)
    if action=='diagnose':
        from v43_corrective.diagnose import run
        return run(**args)
    if action=='mess':
        from v43_mess.worker import run
        return run(args['request'])


if __name__=='__main__':main()
