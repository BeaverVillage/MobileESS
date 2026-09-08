"""Validate declared retained DA junctions without weakening artifact readback."""
from pathlib import Path
from fast_prepare import read, record
from v41r4_loop_runtime import MAY_RUN, MAY_OUT, BASE_RUN, PREVIOUS_RUN
from v41r4_loop_budget import adapted

def check_path(file, root):
    # Reject lexical traversal even when its resolved destination is local.
    relative = file.relative_to(root)
    assert not relative.is_absolute() and '..' not in relative.parts, 'ARCHIVE_PATH_TRAVERSAL'
    resolved = file.resolve()
    if resolved.is_relative_to(root.resolve()):
        return
    unit = root.relative_to(MAY_RUN)
    assert len(unit.parts) == 2, 'UNDECLARED_EXTERNAL_ARCHIVE'
    day, policy = unit.parts
    assert policy in ('B0', 'B2') and relative.parts[0] == 'dayahead', 'UNDECLARED_EXTERNAL_ARCHIVE'
    retained = read(MAY_OUT/day/f'REUSED_DA_PRODUCER_{policy}.json')
    source = retained['source']
    assert record(source['path']) == source, 'RETAINED_DA_RECEIPT_DRIFT'
    target = Path(source['path']).parent.resolve()
    assert target in {(r/day/policy/'dayahead').resolve() for r in (BASE_RUN, PREVIOUS_RUN)}, 'UNAPPROVED_RETAINED_ROOT'
    assert (root/'dayahead').resolve() == target, 'RETAINED_LINK_CHANGED'
    resolved.relative_to(target)
    assert read(source['path'])['science'] == retained['science'], 'RETAINED_PRODUCER_CHANGED'

def install():
    from dayahead.v41 import scientific_archive as archive
    if getattr(archive.verify_manifest, '_retained_junction_adapter', False):
        return
    fn = adapted(archive.verify_manifest,
        [('file.resolve().relative_to(root.resolve())', 'check_path(file, root)')],
        dict(check_path=check_path))
    fn._retained_junction_adapter = True
    archive.verify_manifest = fn

if __name__ == '__main__':
    import sys
    install()
    from v41r4_loop_worker import main
    main(sys.argv[1], sys.argv[2])
