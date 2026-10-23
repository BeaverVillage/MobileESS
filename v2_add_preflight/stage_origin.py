"""Production parents must come from this leased campaign's real M core."""
import math
from pathlib import Path
from .stage_common import read,record
from .stage_authority import current
from v44.stages import m_outcome
from v42_native.contracts import digest
from v42_pr134_b1.common import clean


def require_m(result):
    if not isinstance(result,dict) or result.get('producer')!='v2_add_preflight.stage_handlers.m':
        raise ValueError('FINITE_M_FIXTURE_IS_NOT_A_PRODUCTION_M_PARENT')
    root=Path(current()['lease']['root']).resolve()
    for key in ('accepted_point','Joint_ledger','original_upper'):
        item=result.get(key)
        if not item or not Path(item['path']).resolve().is_relative_to(root) or record(item['path'])!=item:
            raise ValueError('OWN_CAMPAIGN_M_PARENT_ARTIFACT_REQUIRED:'+key)
    if not m_outcome(result)['allow_downstream']:raise ValueError('HEALTHY_ORIGINAL_FULL_M_PARENT_REQUIRED')
    ledger=read(result['Joint_ledger']['path']);calls=ledger['calls']
    if ledger.get('inflight') is not None or not calls or any(
        r.get('fixture_synthetic_Runtime') or r.get('runtime_unavailable') or r.get('status')!='FINISHED'
        or not isinstance(r.get('Native_Runtime'),(int,float)) or not math.isfinite(r['Native_Runtime']) or r['Native_Runtime']<0 for r in calls):
        raise ValueError('REAL_RECONCILED_SOURCE_NATIVE_M_LEDGER_REQUIRED')
    context=ledger['stage_context']
    if any(context[k]!=result[v] for k,v in [('arm','arm'),('stage','stage'),('stage_case_sha','case_sha'),('source_sha','source_sha')]):
        raise ValueError('M_PARENT_NATIVE_CASE_OR_SOURCE_DRIFT')
    if abs(sum(r['Native_Runtime'] for r in calls)-ledger['measured_Native_Runtime'])>1e-7:
        raise ValueError('M_PARENT_MEASURED_NATIVE_TOTAL_DRIFT')
    if digest(clean(read(result['original_upper']['path'])))!=digest(clean(result['upper'])):
        raise ValueError('SOURCE_M_OUTPUT_ARTIFACT_DRIFT')
    return result
