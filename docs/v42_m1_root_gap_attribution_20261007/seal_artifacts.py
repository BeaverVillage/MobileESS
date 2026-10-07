"""Hash completed evidence only; never performs a model build or optimization."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent


def main():
    verification = json.loads((OUT/'VERIFICATION.json').read_text(encoding='utf-8'))
    assert verification['mode'] == 'FINAL'
    assert verification['workflow_integrity_PASS'] and verification['workflow_checks_complete']
    state = json.loads((OUT/'WORK_STATE.json').read_text(encoding='utf-8'))
    state.update(stage='FINAL_ARTIFACTS_VERIFIED', active_exec_session=None,
                 workflow_integrity_PASS=True, workflow_checks_complete=True,
                 strict_raw_numeric_feasibility_PASS=verification['strict_raw_numeric_feasibility_PASS'],
                 pending=['publish final Git HEAD / Draft PR identity'])
    (OUT/'WORK_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    digests = {}
    sizes = {}
    for path in sorted(OUT.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        rel = path.relative_to(OUT).as_posix()
        if rel == 'SHA256_MANIFEST.json':
            continue
        h = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024), b''):
                h.update(block)
        digests[rel] = h.hexdigest()
        sizes[rel] = path.stat().st_size
    report = dict(PASS=True, meaning='Evidence file hash census; not a solver feasibility PASS.',
        SHA256=digests, bytes=sizes, file_count=len(digests), total_bytes=sum(sizes.values()),
        excluded=['SHA256_MANIFEST.json (self-reference)', '__pycache__', '*.pyc'],
        original_selected_authority=verification['original_selected_hashes'],
        workflow_integrity_PASS=verification['workflow_integrity_PASS'],
        strict_raw_numeric_feasibility_PASS=verification['strict_raw_numeric_feasibility_PASS'],
        no_optimize_calls=True)
    (OUT/'SHA256_MANIFEST.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(files=len(digests), bytes=report['total_bytes'],
        workflow_integrity_PASS=True, strict_raw_numeric_feasibility_PASS=report['strict_raw_numeric_feasibility_PASS']), ensure_ascii=False))


if __name__ == '__main__':
    main()
