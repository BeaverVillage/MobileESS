import argparse
import json
import sys

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare'); prep.add_argument('--audited-input-root')
    run=sub.add_parser('run'); run.add_argument('--root',required=True)
    args=p.parse_args()
    if args.command=='prepare':
        from .prepare import prepare
        print(json.dumps(prepare(args.audited_input_root),ensure_ascii=False)); return 0
    from .coordinator import run as execute
    return execute(args.root)

if __name__=='__main__': sys.exit(main())
