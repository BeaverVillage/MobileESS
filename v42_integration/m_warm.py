"""Lossless semantic Raw transport from B3 M1 to a newly built M2.

Bounds and objectives are not inherited: only a fresh M2 FULL replay can
produce an M2 incumbent. Legal routes remain heuristic seeds on rejection.
"""
import json
from pathlib import Path
import numpy as np

from .m_engine import (_write, file_record, binding, vector_sha, strict_full,
                       PathGraph, _validate)


def save_m1(case, point, result, acceptance):
    from .table_v_mess import require_m_acceptance
    require_m_acceptance(acceptance,result=result,arm='B3',stage='M1')
    raw = acceptance['raw_point']
    strict_full(case,raw['path'])
    original = case.lift(point)
    folder = case.output/'M1_M2_HANDOFF'
    folder.mkdir(exist_ok=False)
    path = folder/'ORIGINAL_NAMED_POINT.npz'
    np.savez_compressed(path,names=case.original_d['names'],point=original)
    packet = dict(schema='TABLE_V_M1_M2_NAMED_RAW_V1',stage='M1',arm='B3',
        day=result['day'],source_sha=case.identity['D0_source_sha'],
        source_identity=result['D0_source_identity'],source_case_sha=case.case_sha,
        original_named_raw=file_record(path),selected_raw=raw,
        original_vector_sha=vector_sha(original),source_binding=binding(case),
        result_sha=acceptance['result_sha'],acceptance=acceptance,
        routes=result['mess']['routes'],M1_bounds_transferred=False)
    target=folder/'HANDOFF.json';_write(target,packet)
    return file_record(target)


def admit_m1(case, descriptor, *, validator=None):
    folder=case.output/'M1_M2_ADMISSION';folder.mkdir(exist_ok=False)
    receipt=dict(admitted=False,route_seed_admitted=False,old_bound_imported=False,
        target_case_sha=case.case_sha,target_binding=binding(case))
    point=None
    try:
        if file_record(descriptor['path'])!=descriptor:
            raise ValueError('M1_HANDOFF_BYTES_DRIFT')
        packet=json.loads(Path(descriptor['path']).read_text(encoding='utf8'))
        if (packet['schema']!='TABLE_V_M1_M2_NAMED_RAW_V1' or packet['arm']!='B3'
                or packet['stage']!='M1' or case.identity['arm']!='B3' or case.identity['stage']!='M2'
                or packet['day']!=case.identity['day']
                or packet['source_sha']!=case.identity['D0_source_sha']
                or packet['source_identity']['case_sha']!=case.identity['D0_parent_case_sha']):
            raise ValueError('M1_M2_SOURCE_DAY_ARM_PARENT_DRIFT')
        from .table_v_mess import require_m_acceptance
        require_m_acceptance(packet['acceptance'],arm='B3',stage='M1',identity=packet['source_identity'])
        if packet['acceptance']['stage_case_sha']!=packet['source_case_sha']:
            raise ValueError('M1_SOURCE_CERTIFICATE_CASE_DRIFT')
        for key in ('original_named_raw','selected_raw'):
            if file_record(packet[key]['path'])!=packet[key]:raise ValueError('M1_RAW_BYTES_DRIFT')
        # Routes carry no UB authority and are independently legal in M2.
        graph=PathGraph(case)
        if set(packet['routes'])==set(graph.origins):
            for u,p in packet['routes'].items():graph.validate(u,p)
            case.warm_route_seed=packet['routes'];receipt['route_seed_admitted']=True
        with np.load(packet['original_named_raw']['path'],allow_pickle=False) as z:
            names=list(map(str,z['names']));values=z['point'].copy()
        if vector_sha(values)!=packet['original_vector_sha'] or len(names)!=len(set(names)):
            raise ValueError('M1_NAMED_VECTOR_DRIFT')
        target=list(map(str,case.original_d['names']))
        if len(target)!=len(set(target)) or set(target)!=set(names):
            raise ValueError('M2_ORIGINAL_SEMANTIC_AXIS_MISMATCH')
        index={n:i for i,n in enumerate(names)}
        mapped=values[[index[n] for n in target]]
        candidate=case.forward(mapped)
        if not np.array_equal(case.lift(candidate),mapped):
            raise ValueError('M2_ORIGINAL_POINT_TRANSPORT_NOT_LITERAL')
        cert=_validate(case,candidate,folder/'M2_REVALIDATED_RAW.npz',validator or strict_full)
        if cert is None:raise ValueError('M2_CURRENT_ORIGINAL_FULL_REPLAY_REJECTED')
        point=candidate
        receipt.update(admitted=True,M2_FULL_certificate=cert,point_sha=vector_sha(point),
            M2_original_mapping_exact=True)
    except (ValueError,KeyError,OSError,TypeError) as exc:
        receipt['reason']=str(exc)
    receipt['cold_fallback_required']=point is None
    _write(folder/'ADMISSION.json',receipt)
    return point,receipt
