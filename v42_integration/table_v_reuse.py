"""Find completed B1 A1 evidence, including append-only attempt directories.

Discovery does not certify mathematical equivalence. The recipient must compare
its literal matrix/domain/objective and replay the saved integer point in FULL.
"""
import json
from pathlib import Path

from .a_engine import digest
from .release_p1_acceptance import require_acceptance
from .m_engine import vector_sha


def discover_a1_attempts(output, context):
    import numpy as np
    root = Path(output).resolve()
    arm = root / 'B1'
    ledger = json.loads((root/'PLANNING_NATIVE_LEDGER.json').read_text(encoding='utf8'))
    candidates = [arm/'A1'] + [p/'A1' for p in arm.glob('ATTEMPT*') if p.is_dir()]
    admitted = []
    for folder in candidates:
        try:
            if not folder.resolve().is_relative_to(arm) or folder.is_symlink():
                continue
            result_path, acceptance_path = folder/'P1_ONLY_RESULT.json', folder/'P1_ONLY_ACCEPTANCE.json'
            result = json.loads(result_path.read_text(encoding='utf8'))
            acceptance = json.loads(acceptance_path.read_text(encoding='utf8'))
            require_acceptance(acceptance, stage='A1', source_identity=context['manifest']['identity'], result=result)
            if (result.get('arm') != 'B1' or acceptance.get('arm') != 'B1'
                    or acceptance.get('evidence_scope') != 'REAL_PRODUCTION'
                    or result.get('FULL_feasible') is not True
                    or result.get('FULL_point_replay', {}).get('PASS') is not True
                    or result.get('D0_input_sha') != context['input_audit']['a_input_sha']
                    or acceptance.get('source_sha') != context['manifest']['source_sha']
                    or acceptance.get('native_binding') != result.get('native_binding')
                    or result.get('domain_scope') != 'ORIGINAL_SOURCE_AUTHORIZED_E1_FLEX30_FULL_DOMAIN'):
                continue
            with np.load(folder/'P1_ONLY_POINT.npz', allow_pickle=False) as packet:
                point_sha = vector_sha(packet['point'])
            if point_sha != acceptance.get('point_sha256') or point_sha != result['FULL_point_replay'].get('point_sha256'):
                continue
            call = result.get('Native_call') or result.get('reused_native_call')
            if not call:
                continue
            rows = ledger.get('calls', [])
            if not any(digest({k:v for k,v in row.items() if k != 'carried_forward_from'}) == digest(call) for row in rows):
                continue
            ctx = call.get('stage_context') or {}
            if (ctx.get('arm') != 'B1' or ctx.get('stage') != 'A1'
                    or ctx.get('stage_case_sha') != result.get('case_sha')
                    or ctx.get('source_sha') != acceptance.get('source_sha')
                    or call.get('native_binding') != result.get('native_binding')):
                continue
            admitted.append((acceptance_path.stat().st_mtime_ns, folder.resolve()))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return tuple(folder for _, folder in sorted(admitted, reverse=True))
