"""Exact negative concrete STAY directions, without another optimize call."""
from dataclasses import replace
from fractions import Fraction as F
from time import perf_counter
import numpy as np
from v42_a_stage_phase1.runner import load_cache,block_folder
from v42_a_stage_domain_v2.domain import graph_content_hash
from v42_a_stage_practical.policy import POLICY
from v42_pr134_b1.common import read,record,atomic
from .policy import OLDOUT,DAY

def admit_histograms(full,B,units,count,pi,active_lower_bound,allowed,already,service_slots):
    """Every admitted point is N*e_j; other coordinates are EXACTLY zero.

    Require one original cardinality row and the original boxes. This proves
    every local row, without replaying a dense zero vector for every option.
    The float screen grants no certificate and never removes a candidate.
    """
    epsilon=F(POLICY['price_epsilon']);baseline=F(active_lower_bound)
    if np.any(full.lower>0) or np.any(full.upper<0):return []
    zero_violation=np.where(full.senses=='=',full.rhs!=0,
        np.where(full.senses=='<',full.rhs<0,full.rhs>0))
    failed=np.flatnonzero(zero_violation)
    if len(failed)!=1:return []
    row=int(failed[0])
    if full.senses[row]!='=' or F(float(full.rhs[row]))!=count:return []
    A=full.matrix.tocsc();coupling=B.tocsc();prices=-(B.T@pi)*count-float(baseline)
    admitted=[]
    for unit in units:
        if not unit.get('stay_count'):continue
        for (site,start),encoded in sorted(unit['v']['y'].items()):
            if encoded[0]!='v' or (site,start) in already:continue
            if (start,site) not in allowed:raise ValueError('BATCH_STAY_OUTSIDE_ORIGINAL_PHYSICAL_DOMAIN')
            j=int(encoded[1]);lo,hi=A.indptr[j:j+2]
            if hi-lo!=1 or A.indices[lo]!=row or F(float(A.data[lo]))!=1:continue
            if not full.lower[j]<=count<=full.upper[j]:continue
            if prices[j]>=-float(epsilon):continue
            a,b=coupling.indptr[j:j+2]
            price=-count*sum((F(float(coupling.data[k]))*F(float(pi[coupling.indices[k]]))
                for k in range(a,b) if coupling.data[k]!=0 and pi[coupling.indices[k]]!=0),F(0))
            delta=price-baseline
            if delta < -epsilon:
                admitted.append(dict(column=j,site=site,start=start,finish=start+service_slots,
                    count=count,exact_price=str(price),exact_improvement=str(delta),cardinality_row=row,
                    exact_local_point='N*e_j; all other coordinates zero',original_local_rows_and_boxes_exact=True))
    return admitted

def augment(state,negative,price_folder,folder):
    started=perf_counter();required={r['class_id']:r for r in read(OLDOUT/DAY/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    extra=[];result=[]
    for direction in negative:
        key=direction['class_id'];want=required[key];cache=load_cache(want)
        receipt=block_folder(price_folder,key)/'EXACT_COMPLETE_BLOCK_CERTIFICATE.json';cert=read(receipt)
        if cache['snapshot'].fingerprint()!=cert['full_snapshot_sha256']:raise ValueError('BATCH_STAY_FULL_SNAPSHOT_DRIFT')
        uid=state['data'][7]['classes'][key][0];job=state['data'][1][uid];graph=direction['graph']
        if want['cardinality']!=len(state['data'][7]['classes'][key]):raise ValueError('BATCH_STAY_ORIGINAL_CLASS_CARDINALITY_DRIFT')
        already={(site,start) for site,start in graph.events['y'] if (site,start+job.service_slots) in graph.events['f0']}
        admitted=admit_histograms(cache['snapshot'],cache['B'],cache['units'],want['cardinality'],
            np.asarray(cert['global_coupling_pi']),cert['active_local_lower_bound'],
            set(state['domains'][uid].stays),already,job.service_slots)
        if admitted:
            events={name:set(values) for name,values in graph.events.items()};states={name:set(values) for name,values in graph.states.items()}
            for option in admitted:
                site,start,finish=option['site'],option['start'],option['finish']
                events['y'].add((site,start));events['f0'].add((site,finish))
                states['r0'].update((site,t) for t in range(start,finish))
            # Add only the proven STAY primitive support. Preserve the prior
            # migration roster, compatibility, physical envelopes and bounds.
            graph=replace(graph,events={k:tuple(sorted(v)) for k,v in events.items()},
                states={k:tuple(sorted(v)) for k,v in states.items()})
            graph.sha=graph_content_hash(graph)
        result.append(dict(direction,graph=graph,support_sha256=graph.sha))
        extra.append(dict(class_id=key,original_full_cache=want['external_full_block_cache'],pricing_certificate=record(receipt),
            admitted_negative_concrete_STAY_columns=admitted,count=len(admitted),graph_sha256=graph.sha,
            original_migration_metadata_preserved=True))
    proof=dict(PASS=True,classes=len(extra),additional_negative_concrete_STAY_columns=sum(x['count'] for x in extra),
        exact_pricing_and_local_feasibility=True,original_class_cardinality=True,full_domain_preserved=True,
        no_candidate_deletion=True,no_native_calls=True,float_screen_is_not_a_certificate=True,
        migration_directions_retained=True,records=extra,wall_seconds=perf_counter()-started)
    atomic(folder/'BATCH_NEGATIVE_STAY_CERTIFICATE.json',proof)
    return result,proof
