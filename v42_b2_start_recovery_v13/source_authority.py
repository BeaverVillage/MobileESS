"""Sealed original builder authority; no historical Solver state is admitted."""
from pathlib import Path
import ast
import inspect
from .common import read, record, sha


def original_sources(root):
    base=read(Path(root)/'CAMPAIGN_MANIFEST.json')
    sources=dict(base['sources'])
    for name, value in base['implementation']['sources'].items():
        if name in sources and sources[name] != value:
            raise PermissionError('V13_ORIGINAL_SOURCE_AUTHORITIES_CONFLICT:'+name)
        sources[name]=value
    for name in ('v42_may_campaign_native90/m_model.py','v42_bootstrap/m1.py','v42_native/mess.py'):
        if name not in sources or sha(Path(__file__).resolve().parents[1]/name) != sources[name]:
            raise PermissionError('V13_ORIGINAL_BUILDER_SOURCE_SHA_REQUIRED:'+name)
    return sources


def inherited_baseline(root, previous):
    from v42_b2_start_recovery_v12 import full_validation as old
    from . import full_validation as new
    for name in ('semantic_digest','fingerprint'):
        before=ast.dump(ast.parse(inspect.getsource(getattr(old,name))),include_attributes=False)
        after=ast.dump(ast.parse(inspect.getsource(getattr(new,name))),include_attributes=False)
        if before != after:
            raise PermissionError('V13_BASELINE_FINGERPRINT_FUNCTION_CHANGED')
    root=Path(root)
    gate=read(root/'B2_BUILD_FULL_VALIDATION_V12.json')
    sealed=gate['builds']['2025-05-01/BASELINE']['receipt']
    if record(sealed['path']) != sealed:
        raise PermissionError('V13_BASELINE_RECEIPT_CHANGED')
    receipt=read(sealed['path'])
    if (receipt.get('PASS') is not True or receipt['day'] != '2025-05-01' or receipt['mode'] != 'BASELINE'
            or receipt['Native_calls'] != 0 or receipt['P2_calls'] != 0
            or receipt['implementation_SHA'] != previous['implementation']['source_SHA']
            or receipt['input_SHA'] != sha(Path(previous['input_folders']['B2/2025-05-01'])/'NATIVE_INPUT.json')
            or receipt['original_transport_verification']['PASS'] is not True):
        raise PermissionError('V13_BASELINE_ORIGINAL_SCIENCE_OR_INPUT_DRIFT')
    return dict(receipt=sealed,source_authority=original_sources(root),
        fingerprint_function_AST_identical=True,Native_calls=0,
        purpose='NATIVE_ZERO_ORIGINAL_FULL_REFERENCE_ONLY; NO_POINTS_BOUNDS_OR_CLOCKS_TO_PRODUCTION')
