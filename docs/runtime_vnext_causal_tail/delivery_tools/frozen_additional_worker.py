"""Resource-only fourth worker using the unchanged frozen fit implementation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parallel_pipeline import worker
from common import *


def main():
    freeze = read('FINAL_SELECTION_FREEZE.json')
    for name, digest in freeze['code_hashes'].items():
        require(sha(ROOT/name) == digest, 'FROZEN_IMPLEMENTATION_CHANGED')
    require(read('STAGE_A_FREEZE.json') == freeze['temporal'], 'TEMPORAL_POLICY_CHANGED')
    require(sha(ROOT/'PROTOCOL.json') == freeze['protocol_sha256'], 'PROTOCOL_CHANGED')
    issues = pd.read_csv(ROOT/'ISSUES.csv')
    issues.issue_time = pd.to_datetime(issues.issue_time, utc=True)
    may = issues.loc[issues.role.eq('MAY_HISTORICAL'), 'issue_time'].tolist()
    exposed = issues.loc[issues.role.eq('EXPOSED_EVALUATION'), 'issue_time'].tolist()
    order = list(reversed(may[:16])) + may[16:] + list(reversed(exposed))
    for issue in order:
        worker((issue, True))
        print('FOURTH_WORKER_READY', issue, flush=True)


if __name__ == '__main__':
    main()
