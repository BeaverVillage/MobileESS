"""python -m v42_unified [replay|status|audit|build-only|handoff-check]."""
import argparse
from .storage import setup


def main():
    setup()
    parser = argparse.ArgumentParser(description='Single V42 authority, pipeline and independent replay')
    parser.add_argument('mode', nargs='?', default='status', choices=('run','replay','status','audit','build-only','handoff-check'))
    parser.add_argument('--handoff', help='Completed M result manifest, for read-only admission checking')
    parser.add_argument('--output', help='New run output folder inside D V42')
    args = parser.parse_args()
    if args.mode == 'run':
        from uuid import uuid4
        from .audit import ROOT
        from .backend import CommittedEvidenceBackend
        from .pipeline import run_pipeline
        backend = CommittedEvidenceBackend()
        r = run_pipeline(backend, backend.authority, args.output or ROOT/'runtime'/str(uuid4()))
        print(r['status'], 'stopped_at='+r['stopped_at'], 'native_optimize_calls='+str(r['native_optimize_calls']))
    elif args.mode == 'audit':
        from .audit import audit
        r = audit(); print('AUTHORITY', r['PASS'], r['common_ancestor'])
    elif args.mode == 'replay':
        from .replay import aidc_replay
        from .mess_replay import run
        from .pipeline import saved_pipeline_status
        a, _, _ = aidc_replay(); m = run(); r = saved_pipeline_status()
        print('A1', a['PASS'], 'C3A', m['PASS'], 'pipeline', r['status'], 'Native optimize=0')
    elif args.mode == 'status':
        from .pipeline import saved_pipeline_status
        r = saved_pipeline_status(); print(r['status'], r['stopped_at'], 'M1_ACCEPTED=false', r['historical_M1_global_gap_percent'])
    elif args.mode == 'build-only':
        from .native import build_only
        r = build_only(); print('C3A_BUILD_ONLY', r['PASS'], r['rows'], r['columns'], 'Native optimize=0')
    else:
        if not args.handoff:
            parser.error('--handoff is required for handoff-check')
        from .handoff import inspect_completed_result
        r = inspect_completed_result(args.handoff); print(r)


if __name__ == '__main__':
    main()
