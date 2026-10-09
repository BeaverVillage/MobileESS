"""A status-only CLI. It never dispatches a worker or resolves a solver."""
import json
import sys
from .hold import receipt, require_execution_approval


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ['status']):
        require_execution_approval('CLI:' + ' '.join(args))
    print(json.dumps(receipt(), indent=2))


if __name__ == '__main__':
    main()
