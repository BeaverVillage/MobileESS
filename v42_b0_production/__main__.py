import argparse
from pathlib import Path
from .authority import DOC, prepare, read


def main():
    parser = argparse.ArgumentParser(description='Explicit B0-only May 2025 production campaign')
    parser.add_argument('command', choices=['prepare', 'run', 'report'])
    parser.add_argument('--run-root', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare()
        return
    root = args.run_root or Path(read(DOC / 'RUN_LOCATION.json')['run_root'])
    if args.command == 'run':
        from .execution import run
        run(root)
    else:
        from .report import report
        report(root)


if __name__ == '__main__':
    main()
