"""Post-delivery zero-Native replay into a fresh D runtime directory.

Preserved historical mathematical sources/proofs are byte-identical. README
and attributes are explicitly documented administration additions, so their
old digests are retained as authority rather than imposed on later docs.
"""
from datetime import datetime, timezone
import hashlib
from time import perf_counter
from unittest.mock import patch
import gurobipy as gp

from v42_unified.audit import ROOT, git, write
from v42_unified.storage import sha
from .case import BASE_HEAD, RUNTIME, historical_manifest, load_case
from .blocks import build_blocks
from .verify import phase0, verify_decomposition


def run():
    started = perf_counter()
    run_id = 'replay_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = RUNTIME / run_id
    destination.mkdir(parents=True, exist_ok=False)
    old = historical_manifest()
    checked = {}
    additions = {}
    for name, expected in old['files'].items():
        actual = sha(ROOT / name)
        if name in {'README.md', '.gitattributes'}:
            baseline = git('show', BASE_HEAD + ':' + name)
            current = (ROOT / name).read_bytes()
            if hashlib.sha256(baseline).hexdigest() != expected:
                raise ValueError('HISTORICAL_DOCUMENT_BLOB_DRIFT:' + name)
            if not current.replace(b'\r\n', b'\n').startswith(baseline.replace(b'\r\n', b'\n')):
                raise ValueError('HISTORICAL_DOCUMENT_CONTENT_MUST_BE_PRESERVED:' + name)
            additions[name] = dict(historical_sha256=expected, current_sha256=actual,
                                   historical_document_text_prefix_preserved=True,
                                   documented_research_administration_only=True)
        elif actual != expected:
            raise ValueError('HISTORICAL_SCIENTIFIC_SOURCE_OR_PROOF_DRIFT:' + name)
        else:
            checked[name] = actual
    manifest_name = 'docs/v42_m1_joint_gap_research/SHA256_MANIFEST.json'
    if sha(ROOT / manifest_name) != hashlib.sha256(git('show', BASE_HEAD + ':' + manifest_name)).hexdigest():
        raise ValueError('HISTORICAL_MANIFEST_DRIFT')
    def forbidden(*args, **kwargs):
        raise RuntimeError('ZERO_NATIVE_REPLAY_FORBIDS_OPTIMIZATION_OR_PRESOLVE')
    with patch.object(gp.Model, 'optimize', forbidden), patch.object(gp.Model, 'presolve', forbidden):
        case = load_case(output=destination)
        initial = phase0(case)
        partition = verify_decomposition(case, build_blocks(case))
    receipt = dict(PASS=True, case_sha=case.case_sha,
        baseline_completed_HEAD=BASE_HEAD, current_HEAD=git('rev-parse', 'HEAD').decode().strip(),
        phase0=initial, independent_partition=partition,
        historical_scientific_files_verified=len(checked),
        current_documentation_administration=additions,
        Native_optimize_calls=0, historical_reports_overwritten=False,
        committed_new_research_reports_overwritten=False,
        wall_seconds=perf_counter()-started, output=str(destination))
    write(destination / 'ZERO_NATIVE_REPLAY.json', receipt)
    return receipt


if __name__ == '__main__':
    receipt = run()
    print('HYBRID_ZERO_NATIVE_REPLAY_PASS', receipt['case_sha'], receipt['output'])
