"""Replay an already priced A1 certificate through the PR191 verifier boundary.

The current FULL model and full domains are prepared afresh. Recorded Native
Pi/X values supply the original source pricing routine; optimize is unavailable.
"""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path

import numpy as np

from .m_engine import _write,file_record


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def replay_same_problem_dw(context,case,built,previous,output):
    """Return a reverified same-problem DW receipt, or None without a solve."""
    from .table_v_dw import prepare_current_dw
    from v42_b3_joint.a_source import _stage_lock
    from v42_may_campaign_native90.a_routing import rebound
    from v42_a_stage_canary import pricing
    from v42_a_stage_phase1.core import (elastic_master,verify_zero,primal_replay,verify_sign_convention)
    from v42_a_stage_phase1.backend import artificial_point
    from v42_a_stage_compact_rowgen.assembly import partition
    from v42_a_stage_compact_rowgen.lift import expanded_point
    output=Path(output)
    if (not previous or previous.get('LB_certified') is not True
            or previous.get('full_domain_pricing_complete') is not True
            or previous.get('phase_I_status')!='PHI_ZERO_CERTIFIED'
            or previous.get('case_sha')!=case.case_sha
            or previous.get('native_binding')!=built[6]['native_binding']):
        return None
    if output.exists(): raise FileExistsError('TABLE_V_DW_REPLAY_FRESH_OUTPUT_REQUIRED')
    output.mkdir(parents=True)
    def checked(receipt):
        if file_record(receipt['path'])!=receipt: raise ValueError('TABLE_V_DW_REPLAY_SAVED_RECEIPT_DRIFT')
        return Path(receipt['path']).resolve()
    try:
        certificates=previous['certificate']
        for record in certificates.values(): checked(record)
        p1=_read(checked(certificates['P1']))
        old_price=checked(p1['full_pricing']).parent
        old_root=Path(certificates['P1']['path']).resolve().parent
        if not old_price.is_relative_to(old_root): raise ValueError('TABLE_V_DW_REPLAY_SOURCE_OUTPUT_ESCAPE')
        state=prepare_current_dw(context,case,built,output)
        master=old_price.parent
        native_result=_read(master/'NATIVE_RESULT.json')
        if native_result['snapshot_sha']!=state['compact'].fingerprint():
            raise ValueError('TABLE_V_DW_REPLAY_CURRENT_COMPACT_MATRIX_DRIFT')
        with np.load(master/'RAW_ATTRIBUTES.npz',allow_pickle=False) as archive:
            raw={key:archive[key].copy() for key in archive.files}
        sign=verify_sign_convention(state['compact'],raw['Pi'],raw['RC'])
        compact=primal_replay(state['compact'],raw['X'])
        expanded=primal_replay(state['reference'],expanded_point(state,raw['X']))
        elastic=elastic_master(state['compact'],state['grows'])
        point,point_proof=artificial_point(elastic,raw['X'])
        zero=verify_zero(elastic,point)
        if not all(proof.get('PASS') is True for proof in (sign,compact,expanded,point_proof,zero)):
            raise ValueError('TABLE_V_DW_REPLAY_CURRENT_PHASE_I_PRIMAL_DUAL_FAILED')

        class RecordedNative:
            def remaining(self): return 1.
            def solve(self,snapshot,folder,component):
                folder=Path(folder).resolve()
                if component!='LOCAL_PRICING' or not folder.is_relative_to(old_root):
                    raise PermissionError('TABLE_V_DW_REPLAY_NATIVE_EXECUTION_FORBIDDEN')
                record=_read(folder/'NATIVE_RESULT.json')
                if record['snapshot_sha']!=snapshot.fingerprint():
                    raise ValueError('TABLE_V_DW_REPLAY_FULL_PRICED_MODEL_DRIFT')
                with np.load(folder/'RAW_ATTRIBUTES.npz',allow_pickle=False) as archive:
                    arrays={key:archive[key].copy() for key in archive.files}
                return record,arrays

        local,owned=partition(state['compact'],state['metas'],state['grows'])
        with _stage_lock:
            full=rebound(pricing.full_pricing,dict(pricing.full_pricing.__globals__,HISTORY=output,
                atomic=lambda *args,**kwargs:None,print=lambda *args,**kwargs:None))
            priced,negative=full(RecordedNative(),state['compact'],None,raw,None,state['data'],state['domains'],
                state['ledger'],state['axes'],state['n'],state['grows'],local,owned,old_price)
        if (not priced.get('PASS') or negative or not priced.get('no_negative_omitted_block_certified')
                or not priced.get('complete_STAY_and_migration_coverage')
                or Fraction(priced['full_domain_phase1_lower_bound'])!=Fraction(previous['exact_Global_LB'])):
            raise ValueError('TABLE_V_DW_REPLAY_EXACT_COMPLETE_BOUND_DRIFT')
        _write(output/'PHASE_I_ZERO_CERTIFICATE.json',dict(PASS=True,Phi=0.,zero=zero,full_original_replay=expanded,
            original_P1_point_independently_replayed=True,native_reoptimization_calls=0))
        _write(output/'P1_REPLAY.json',dict(PASS=True,current_compact_sha=state['compact'].fingerprint(),
            exact_Global_LB=previous['exact_Global_LB'],primal=compact,dual_sign=sign,
            previous_P1=file_record(Path(certificates['P1']['path'])),full_pricing=file_record(old_price/'FULL_PRICING_RESULT.json')))
        result=deepcopy(previous)
        result.update(native_calls=0,Native_Runtime=0.,reused_pricing_certificate=True,
            current_math_identity=state['_table_v'],reused_certificate=deepcopy(certificates),
            current_replay=file_record(output/'P1_REPLAY.json'),
            certificate=dict(phase_I=file_record(output/'PHASE_I_ZERO_CERTIFICATE.json'),
                P1=deepcopy(certificates['P1']),math_equivalence=file_record(output/'ORIGINAL_FULL_DW_MATH_EQUIVALENCE.json'),
                source_domain=file_record(output/'SOURCE_DOMAIN_NATIVE0_AUDIT.json'),
                complete_pricing_roster=file_record(output/'BLOCK_PRICING_ORACLE_VERIFICATION.json')))
        _write(output/'DW_RESULT.json',result)
        return result
    except (ValueError,KeyError,OSError,PermissionError,IndexError) as error:
        _write(output/'DW_REUSE_REJECTED.json',dict(status='NOT_CERTIFIED',Native_calls=0,
            error=type(error).__name__+': '+str(error)))
        return None
