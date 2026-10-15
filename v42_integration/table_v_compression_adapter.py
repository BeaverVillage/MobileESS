"""Prepare an exact complete-class DW LP; keep the original integer UB model.

Phase I, P1, row separation, local pricing, exact dual corrections and the
native accountant remain the existing source implementations. Only their
verified sparse input representation and immutable class-block cache change.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import gzip
import json
from pathlib import Path
import pickle
from time import perf_counter

import numpy as np

from .a_engine import digest
from .m_engine import _write,file_record
from .table_v_compression import semantic_classes,compress_lp,redundant_rows,size,exact_scale
from .table_v_compression_verify import verify_sum,verify_redundancy

VERSION='TABLE_V_VERIFIED_SEMANTIC_CLASS_DW_V1'


def stage_binding(context,case,captured):
    """No class/cache/bound is authorized by a date or header alone."""
    from .table_v_dates import context_day
    day=context_day(context)
    if (case.arm not in ('B1','B3') or case.stage not in ('A1','A2')
            or case.arm=='B1' and case.stage!='A1'):
        raise ValueError('COMPRESSION_EXACT_FLEX_ARM_STAGE_REQUIRED')
    fixed=case.grid.fixed_mess
    if fixed.get('plan_sha')!=digest({k:v for k,v in fixed.items() if k!='plan_sha'}):
        raise ValueError('COMPRESSION_FIXED_MESS_SEAL_DRIFT')
    binding=dict(day=day,arm=case.arm,stage=case.stage,case_sha=case.case_sha,
        source_identity=context['manifest']['identity'],input_sha=context['input_audit']['a_input_sha'],
        fixed_MESS_sha=fixed['plan_sha'],objective_sha=captured['objective_sha'],
        native_binding=captured['native_binding'])
    if captured.get('stage_binding',binding)!=binding:
        raise ValueError('COMPRESSION_DATE_STAGE_FIXED_MESS_OBJECTIVE_BINDING_DRIFT')
    if captured['input_sha']!=binding['input_sha']:
        raise ValueError('COMPRESSION_CURRENT_DATE_INPUT_DRIFT')
    return binding


def _expression(e,fold,N):
    if e[0]=='v':return ('v',int(fold[int(e[1])]))
    constant=float(exact_scale([e[1]],N)[0])
    if e[0]=='c':return ('c',constant)
    return ('e',constant,np.asarray([fold[int(j)] for j in e[2]],dtype=np.int64),np.asarray(e[3]).copy())


def compressed_descriptor(source,records,fold):
    by_uid=defaultdict(list)
    for unit in source['units']:by_uid[unit['uid']].append(unit)
    units=[]
    for record in records:
        N=record['cardinality'];uid=record['members'][0]
        for number,unit in enumerate(by_uid[uid]):
            if unit['optional'] or unit['stay_count']:
                raise ValueError('CLASS_SUM_EXPECTS_UNCHANGED_SINGLETON_FULL_SOURCE')
            units.append(dict(unit,uid=uid,id='MATH_'+record['class_id']+'_'+str(number),
                class_key=record['class_id'],members=record['members'],
                summed_identical_continuous_lanes=N,
                v={family:{key:_expression(e,fold,N) for key,e in items.items()} for family,items in unit['v'].items()}))
    return dict(source,units=units,
        known={key:_expression(e,fold,1) for key,e in source['known'].items()},
        risk={key:_expression(e,fold,1) for key,e in source['risk'].items()})


def prepare_exact_dw(context,case,built,output,*,captured=None,independent_domain_receipt=None,reference_receipt=None):
    from .table_v_dw import (_prepare_progress,audit_source_domain,capture_current_full,_checked_cache)
    from v42_a_stage_phase1.backend import constructed_point
    from v42_a_stage_phase1.core import primal_replay
    from v42_a_stage_compact_rowgen.prepare import shift
    from v42_a_stage_domain_v2.active import _ledger
    from v42_a_stage_domain_v2.lexstage import Objective
    output=Path(output);output.mkdir(parents=True,exist_ok=True);start=perf_counter()
    _prepare_progress(output,'SEMANTIC_CLASS_SOURCE_AUDIT')
    audit=audit_source_domain(context);_write(output/'SOURCE_DOMAIN_NATIVE0_AUDIT.json',audit)
    if captured is None:captured=capture_current_full(context,case,built,output/'FULL_CAPTURE')
    if captured['case_sha']!=case.case_sha or captured['source_identity']!=context['manifest']['identity']:
        raise ValueError('CLASS_COMPRESSION_CURRENT_SOURCE_CASE_REQUIRED')
    binding=stage_binding(context,case,captured)
    if built[6]['native_binding']!=captured['native_binding']:
        raise ValueError('COMPRESSION_CURRENT_ORIGINAL_FULL_BINDING_DRIFT')
    data=captured['data'];base=captured['projected'];descriptor=captured['descriptor']
    if 'preserve_singleton_mixed_flow' not in data[7]:
        data=(*data[:7],dict(data[7],preserve_singleton_mixed_flow=[]))
    model=built[0]
    domains=getattr(model,'__dict__',{}).get('_table_v_authorized_domains') if model is not None else None
    if independent_domain_receipt is not None:
        cached=_checked_cache(independent_domain_receipt)
        if cached['source_identity']!=context['manifest']['identity']:raise ValueError('CLASS_DOMAIN_CACHE_SOURCE_CASE_DRIFT')
        domains=cached['domains']
    if domains is None:raise ValueError('CURRENT_UID_AUTHORITATIVE_DOMAINS_REQUIRED')
    if (set(domains)!=set(data[1]) or digest({u:d.sha for u,d in sorted(domains.items())})!=data[7]['physical_domain_hash']):
        raise ValueError('CLASS_CURRENT_COMPLETE_PHYSICAL_DOMAIN_SHA_DRIFT')
    _prepare_progress(output,'EXACT_SEMANTIC_CLASS_EQUIVALENCE')
    semantic=semantic_classes(data,domains,context['tablev_flex']['known_issued_receipts'])
    _write(output/'UID_AUTHORITY_TO_MATHEMATICAL_CLASS.json',dict(UIDs=semantic['uid_ledger'],
        original_receipts_preserved=True,source_identity=context['manifest']['identity'],case_sha=case.case_sha))
    projection=captured['runtime_projection'];_write(output/'ORIGINAL_RUNTIME_AUXILIARY_PROJECTION.json',projection)
    old_to_projected={int(row):i for i,row in enumerate(projection['retained_original_rows'])}
    axes={(family.upper(),*key) if isinstance(key,tuple) else (family.upper(),'',key):old_to_projected[row]
          for (family,key),row in captured['coupling_rows'].items()}
    result=compress_lp(base,descriptor,data,semantic,forced_global=axes.values(),
        progress=lambda value:_prepare_progress(output,**value))
    exact=verify_sum(base,result)
    old_global_position={int(row):i for i,row in enumerate(result['global_rows'])}
    coupling={key:old_global_position[row] for key,row in axes.items()}
    _prepare_progress(output,'EXACT_REDUNDANT_ROW_PROOF',classes=len(result['records']))
    compact,redundancy=redundant_rows(result['snapshot'],protected_rows=coupling.values())
    independent=verify_redundancy(result['snapshot'],compact,redundancy)
    rowmap={int(row):i for i,row in enumerate(redundancy['retained_rows'])}
    ng=sum(int(row)<len(result['global_rows']) for row in redundancy['retained_rows'])
    newaxes={key:rowmap[row] for key,row in coupling.items()}
    G=tuple(range(ng));n=result['prefix']
    translated=compressed_descriptor(descriptor,result['records'],result['fold'])
    groups={r['class_id']:r['members'] for r in result['records']}
    newdata=(*data[:7],dict(data[7],classes=groups,mathematical_class_aggregation=VERSION,
        original_integer_classes=deepcopy(data[7]['classes'])))
    # The unchanged producer's local witness is constructed in original UID
    # coordinates, then summed; it is never rounded into an integer solution.
    local_original=np.concatenate(list(result['original_local_rows'].values()))
    prior,_=constructed_point(base,descriptor,data,n,local_original)
    initial=np.zeros(compact.matrix.shape[1]);initial[:n]=prior[:n]
    np.add.at(initial,result['fold'][n:],prior[n:])
    local_new=replace(compact,matrix=compact.matrix[ng:].tocsr(),senses=compact.senses[ng:],rhs=compact.rhs[ng:])
    witness=primal_replay(local_new,initial)
    if not witness['PASS']:raise ValueError('COMPRESSED_ORIGINAL_LOCAL_WITNESS_REPLAY_FAILED')
    _prepare_progress(output,'SEMANTIC_CLASS_PRICING_CACHE',classes=0,required_classes=len(groups))
    pricing_started=perf_counter()
    blockroot=output/'FULL_BLOCKS';blockroot.mkdir(exist_ok=False)
    coupling_csc=compact.matrix[list(newaxes.values())].tocsc()
    by_class=defaultdict(list)
    for unit in translated['units']:by_class[unit['class_key']].append(unit)
    roster=[];metas={};global_old_count=len(result['global_rows']);local_start=global_old_count
    for i,record in enumerate(result['records']):
        key=record['class_id'];us=record['members'];uid=us[0];N=len(us)
        cols=np.arange(record['offset'],record['offset']+record['width'])
        source_rows=range(local_start,local_start+record['local_rows'])
        rows=np.asarray([rowmap[r] for r in source_rows if r in rowmap],dtype=np.int64)
        local_start+=record['local_rows']
        units=[shift(u,-record['offset']) for u in by_class[key]]
        snap=replace(compact,matrix=compact.matrix[rows][:,cols].tocsr(),lower=compact.lower[cols],upper=compact.upper[cols],
            senses=compact.senses[rows],rhs=compact.rhs[rows],vtypes=np.full(len(cols),'C'),
            objectives=(Objective('local_price',(),Fraction(0)),)).require()
        B=coupling_csc[:,cols].tocsr();graph=data[5][uid]
        path=blockroot/(key[:12]+'.pkl.gz')
        with gzip.open(path,'xb',compresslevel=1) as stream:
            pickle.dump(dict(snapshot=snap,B=B,constant=np.zeros(len(newaxes)),units=units,graph=graph,
                             constants_already_in_original_global_RHS=True),stream,protocol=5)
        roster.append(dict(PASS=True,class_id=key,cardinality=N,external_full_block_cache=file_record(path),
            full_physical_STAY=len(domains[uid].stays),full_physical_migration=sum(len(b[-1]) for b in domains[uid].blocks),
            full_compact_blocks=len(domains[uid].blocks),complete_graph_sha256=graph.sha,
            complete_local_snapshot_sha256=snap.fingerprint(),original_UIDs=list(us)))
        metas[key]=dict(class_id=key,N=N,offset=record['offset'],width=record['width'],kernel_columns=record['width'],
            points=[],candidates=[],units=units,reference_units=units,reference_columns=list(map(int,cols)))
        if i%10==0 or i+1==len(groups):
            _prepare_progress(output,'SEMANTIC_CLASS_PRICING_CACHE',classes=i+1,required_classes=len(groups))
    if len({r['class_id'][:12] for r in roster})!=len(roster):raise ValueError('SEMANTIC_CLASS_PREFIX_COLLISION')
    _write(output/'BLOCK_PRICING_ORACLE_VERIFICATION.json',dict(PASS=True,records=roster,
        producer='UNCHANGED_FULL_LOCAL_ROWS_AND_EXACT_N_TIMES_CONTINUOUS_LP_SUM',
        all_original_UIDs=sorted(data[1]),complete_class_roster_SHA=digest(groups),case_sha=case.case_sha,
        original_integer_lanes_unchanged=True))
    proof=dict(PASS=True,version=VERSION,case_sha=case.case_sha,source_identity=context['manifest']['identity'],stage_binding=binding,
        original_unprojected_FULL_integer_sha=captured['original'].fingerprint(),
        original_FULL_integer_sha=captured['original'].fingerprint(),original_projected_LP_sha=base.fingerprint(),
        source_reference_LP_sha=compact.fingerprint(),
        original_rows=base.matrix.shape[0],original_columns=base.matrix.shape[1],compressed_size=size(compact),
        original_integer_size=size(captured['original']),objective_unchanged=True,
        all_rows_boxes_coefficients_exact=True,only_continuous_LP_compressed=True,integer_compression_applied=False,
        exact_class_projection=exact,redundancy=independent,Runtime_auxiliaries_removed=projection['eliminated_auxiliaries'],
        UID_authority_ledger=file_record(output/'UID_AUTHORITY_TO_MATHEMATICAL_CLASS.json'))
    _write(output/'ORIGINAL_FULL_DW_MATH_EQUIVALENCE.json',proof)
    _write(output/'AIDC_SEMANTIC_CLASS_EQUIVALENCE.json',dict(PASS=True,classes=len(groups),UIDs=len(data[1]),
        groups=groups,identities=semantic['identities'],source_identity=context['manifest']['identity'],case_sha=case.case_sha))
    _write(output/'AIDC_FULL_DW_COMPRESSION_CERTIFICATE.json',proof)
    np.savez_compressed(output/'EXACT_PROJECTION_COORDINATES.npz',fold=result['fold'],scale=result['scale'])
    resource_variables=[]
    for kind,site,t in newaxes:
        e=translated['known'].get((site,t)) if kind=='GPU' else translated['risk'].get((site,t)) if kind=='RUNTIME' else None
        resource_variables.append(int(e[1]) if e is not None and e[0]=='v' else -1)
    state=dict(compact=compact,reference=compact,reference_descriptor=translated,scientific_descriptor=translated,
        data=newdata,domains=domains,ledger=_ledger(newdata,domains,{}),metas=metas,n=n,grows=G,axes=newaxes,
        prior_original=initial,prior_compact=initial,global_types=base.vtypes[:n].copy(),projection_proofs=[exact],
        atlas=dict(rf=np.zeros(len(G),dtype=int),rf_names=np.asarray(['ORIGINAL_FULL_ROW']),node_names=np.asarray([]),
            voltage_lower_rows=np.asarray([],dtype=int),voltage_upper_rows=np.asarray([],dtype=int),
            resource_variables=np.asarray(resource_variables),domains=domains),
        _class_sum=dict(result=result,original_LP=base),
        _table_v=dict(case_sha=case.case_sha,native_binding=deepcopy(built[6]['native_binding']),stage_binding=binding,
            source_domain_audit_sha=digest(audit),equivalent=proof,full_physical_domain_sha=data[7]['physical_domain_hash'],classes=len(groups)))
    from .table_v_memory import memory_sample
    import psutil
    process_memory=psutil.Process().memory_info()
    _write(output/'CLASS_COMPRESSION_BUILD_PROFILE.json',dict(PASS=True,wall_seconds=perf_counter()-start,
        pricing_preparation_seconds=perf_counter()-pricing_started,
        memory=memory_sample(),peak_RSS_bytes=getattr(process_memory,'peak_wset',process_memory.rss),
        peak_private_commit_bytes=getattr(process_memory,'peak_pagefile',getattr(process_memory,'private',None)),
        native_calls=0,classes=len(groups),pricing_blocks=len(roster),compressed_size=size(compact),
        full_integer_size=size(captured['original']),geometry_cache=data[7].get('authorized_domain_generation'),
        original_local_witness=witness))
    _prepare_progress(output,'VERIFIED_CLASS_DW_NATIVE0_PASS',classes=len(groups))
    return state


def source_lp_replay(state,point,output):
    """Replay the actual new P1 raw point in original UID LP coordinates."""
    from v42_a_stage_phase1.core import primal_replay
    info=state.get('_class_sum')
    if not info:return None
    result=info['result'];lift=np.asarray(point)[result['fold']]/result['scale']
    replay=primal_replay(info['original_LP'],lift)
    if not replay['PASS']:raise ValueError('COMPRESSED_P1_ORIGINAL_UID_LP_REPLAY_FAILED')
    np.savez_compressed(Path(output)/'ORIGINAL_UID_LP_POINT.npz',point=lift)
    _write(Path(output)/'ORIGINAL_UID_LP_REPLAY.json',dict(replay,scope='ORIGINAL_UID_LP_NOT_INTEGER_POINT',
        point=file_record(Path(output)/'ORIGINAL_UID_LP_POINT.npz'),integer_feasibility_claimed=False))
    return replay


def complete_kernel_rebuilder(state):
    """Keep complete kernels when the original source requests an inclusion rebuild."""
    def rebuild(base,grows,n,axes,data,domains,ledger,candidates):
        if (base.fingerprint()!=state['reference'].fingerprint() or tuple(grows)!=tuple(state['grows'])
                or n!=state['n'] or axes!=state['axes'] or data[7]['classes']!=state['data'][7]['classes']
                or any(data[5][uid].sha!=state['data'][5][uid].sha for uid in data[1])):
            raise ValueError('COMPLETE_CLASS_KERNEL_REBUILD_DOMAIN_OR_MATRIX_DRIFT')
        # The complete original graph already contains the candidate. Retaining
        # it preserves every source row and the previous inclusion witness.
        return dict(state,data=data,domains=domains,ledger=ledger)
    return rebuild
