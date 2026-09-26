"""One extra independent fit worker; no outcome scoring or selection."""
from parallel_pipeline import worker
from common import *


def main():
    issues = pd.read_csv(ROOT/'ISSUES.csv')
    issues.issue_time = pd.to_datetime(issues.issue_time, utc=True)
    selected = issues[issues.role.isin(['TRAIN', 'DEVELOPMENT', 'CALIBRATION'])]
    for t in reversed(selected.issue_time.tolist()):
        worker((t, False))
        print('AUX_SELECTION_READY', t, flush=True)
    while not (ROOT/'FINAL_SELECTION_FREEZE.json').exists():
        time.sleep(5)
    freeze = read('FINAL_SELECTION_FREEZE.json')
    for name, digest in freeze['code_hashes'].items():
        require(sha(ROOT/name) == digest, 'POST_FREEZE_CODE_DRIFT')
    for t in reversed(issues.issue_time.tolist()):
        worker((t, True))
        print('AUX_FROZEN_READY', t, flush=True)


if __name__ == '__main__':
    main()
