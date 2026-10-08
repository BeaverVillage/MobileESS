"""Reconstruct completed May12 masters and pricing directions without solves."""
import gzip,pickle,gc,traceback
from collections import defaultdict
from fractions import Fraction
from time import perf_counter
import numpy as np
from .policy import OUT,STATIC,OLDOUT,OLDSTATIC,DAY
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_phase1.runner import load_cache
from v42_a_stage_phase1.backend import update_graph,project_local_point
from v42_a_stage_early.candidate import expanded_graph,validate
from v42_a_stage_domain_v2.active import option_from_json
from v42_a_stage_compact_rowgen.assembly import build,partition
from v42_a_stage_compact_rowgen.lift import expanded_point
from v42_a_stage_phase1.core import primal_replay,verify_sign_convention,elastic_master,verify_zero
from v42_a_stage_phase1.oracle import corrected_certificate,true_objective
from v42_a_stage_phase1.producer import support_graph,native_block,price_snapshot

def save(name,obj):
    p=STATIC/name;p.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(p,'xb',compresslevel=1) as f:pickle.dump(obj,f,protocol=5)
    return record(p)

def recover_initial():
    started=perf_counter();old=OLDOUT/DAY
    audit=read(OUT/'MAY12_RECOVERY_AUDIT.json');initial=read(old/'INITIAL_VERIFICATION.json')
    if record(initial['state']['path'])!=initial['state']:raise ValueError('HISTORICAL_INITIAL_STATE_DRIFT')
    with gzip.open(initial['state']['path'],'rb') as f:state=pickle.load(f)
    base=state['reference'];data=state['data'];ledger=state['ledger'];candidates=[];checks=[]
    roster={r['class_id']:r for r in read(old/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    for i in (19,20,21):
        q=read(old/f'PHASE_I/S{i}/PRICE/PRICING_RESULT.json');groups=defaultdict(list)
        for c in q['selected_candidates']:groups[c['class_id']].append(c)
        for key,cs in groups.items():
            cache=load_cache(roster[key]);uid=data[7]['classes'][key][0]
            cp=read(old/f'PHASE_I/S{i}/PRICE/B/{key[:12]}/CONCRETE_RECOVERY.json')['global_coupling_pi']
            for c in cs:
                o=option_from_json(c['option'])
                verified=validate(cache,data[1][uid],data[2][uid],data[3],state['domains'][uid],data[4][uid],data[0],
                    {k:j for j,k in enumerate(state['axes'])},np.asarray(cp),len(data[7]['classes'][key]),Fraction(c['normalization_potential']),o,key)
                if verified['price']!=Fraction(c['price']) or verified['coefficient_sha256']!=c['coefficient_sha256'] or verified['price']>=-Fraction(1,100000000):
                    raise ValueError('OLD_NEGATIVE_CONCRETE_COLUMN_REPLAY_FAIL')
                graph=expanded_graph(data[5][uid],o,data[1][uid],state['domains'][uid],uid in data[7]['preserve_singleton_mixed_flow'])
                data,ledger=update_graph(data,state['domains'],key,graph);candidates.append(c)
                checks.append(dict(solve=i,class_id=key,candidate_id=c['candidate_id'],kind=c['kind'],price=c['price'],PASS=True))
            del cache;gc.collect()
        print('HISTORICAL_CONCRETE_ACTIVATION_REPLAY',i,len(candidates),flush=True)
    rebuilt=build(base,state['grows'],state['n'],state['axes'],data,state['domains'],ledger,candidates)
    rebuilt.update(scientific_descriptor=state['scientific_descriptor'],global_types=state['global_types'],atlas=state['atlas'])
    rec=read(old/'P1/S0/NATIVE_RESULT.json');identity=read(rec['model_identity']['path'])
    if rebuilt['compact'].fingerprint()!=identity['original_snapshot_sha256']:raise ValueError('RECOVERED_P1_MATRIX_NOT_IDENTICAL')
    if record(rec['raw_attributes']['path'])!=rec['raw_attributes']:raise ValueError('HISTORICAL_P1_RAW_DRIFT')
    raw=dict(np.load(rec['raw_attributes']['path']));x=expanded_point(rebuilt,raw['X'])
    replay=primal_replay(rebuilt['reference'],x);sign=verify_sign_convention(rebuilt['compact'],raw['Pi'],raw['RC'])
    if not replay['PASS'] or not sign['PASS']:raise ValueError('RECOVERED_P1_PRIMAL_DUAL_FAIL')
    zrec=read(old/'PHASE_I/S22/NATIVE_RESULT.json');zraw=dict(np.load(zrec['raw_attributes']['path']))
    zx=zraw['X'][:rebuilt['compact'].matrix.shape[1]];ex=expanded_point(rebuilt,zx)
    zr=primal_replay(rebuilt['reference'],ex);zm=elastic_master(rebuilt['compact'],rebuilt['grows'])
    z=verify_zero(zm,zraw['X'])
    if not z['PASS'] or not zr['PASS']:raise ValueError('RECOVERED_ZERO_NOT_VALID')
    recovered=save('RECOVERED_P1_STATE.pkl.gz',dict(state=rebuilt,raw=raw,phase1_raw=zraw,phase1_expanded=ex))
    atomic(OUT/'RECOVERED_CHECKPOINT_VERIFICATION.json',dict(PASS=True,state=recovered,
        exact_compact_P1_matrix_identity=rebuilt['compact'].fingerprint(),old_native_model=record(rec['model_identity']['path']),
        original_reference_fingerprint=rebuilt['reference'].fingerprint(),original_reference_replay=replay,sign=sign,
        phase1_zero=z,phase1_original_replay=zr,verified_concrete_columns=checks,native_calls=0,wall_seconds=perf_counter()-started))
    return rebuilt,raw

def run():
    started=perf_counter();old=OLDOUT/DAY
    r=OUT/'RECOVERED_CHECKPOINT_VERIFICATION.json'
    if r.exists():
        rec=read(r)['state']
        if record(rec['path'])!=rec:raise ValueError('RECOVERED_CHECKPOINT_DRIFT')
        with gzip.open(rec['path'],'rb') as f:p=pickle.load(f)
        rebuilt,raw=p['state'],p['raw']
    else:rebuilt,raw=recover_initial()
    data=rebuilt['data'];candidates=[c for m in rebuilt['metas'].values() for c in m['candidates']]
    x=expanded_point(rebuilt,raw['X']);replay=primal_replay(rebuilt['reference'],x)
    roster={r['class_id']:r for r in read(old/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']}
    # Reconstruct every saved full-domain pricing direction, independently.
    priced=read(old/'P1/S0/PRICE/FULL_PRICING_RESULT.json');negative=[];lrows,owned=partition(rebuilt['compact'],rebuilt['metas'],rebuilt['grows'])
    for receipt in priced['block_certificates']:
        if Fraction(receipt['oracle_point_price'])>=-Fraction(1,100000000):continue
        key=receipt['class_id'];cache=load_cache(roster[key]);cp=np.asarray(receipt['global_coupling_pi'])
        nr=read(old/f'P1/S0/PRICE/B/{key[:12]}/NATIVE_RESULT.json')
        if record(nr['raw_attributes']['path'])!=nr['raw_attributes']:raise ValueError('SAVED_ORACLE_RAW_DRIFT')
        a=dict(np.load(nr['raw_attributes']['path']));full=cache['snapshot'];B=cache['B']
        cert=corrected_certificate(full,B,cp,a['Pi']);oldcert=read(old/f'P1/S0/PRICE/B/{key[:12]}/EXACT_COMPLETE_BLOCK_CERTIFICATE.json')['certificate']
        if __import__('v42_a_stage_phase1.runner',fromlist=['serial']).serial(cert)!=oldcert or not cert['PASS']:raise ValueError('OLD_EXACT_PRICING_CERTIFICATE_DRIFT')
        pi=raw['Pi'];cols=sorted(j for j,k in owned.items() if k==key);rows=list(lrows[key])
        from dataclasses import replace
        s=rebuilt['compact'];active=replace(s,matrix=s.matrix[rows][:,cols].tocsr(),lower=s.lower[cols],upper=s.upper[cols],senses=s.senses[rows],rhs=s.rhs[rows],vtypes=np.full(len(cols),'C'),objectives=full.objectives)
        current=corrected_certificate(active,s.matrix[list(rebuilt['axes'].values())][:,cols],cp,pi[rows])
        delta=true_objective(B,cp,a['X'])-Fraction(current['exact_lower_bound'])
        if delta!=Fraction(receipt['oracle_point_price']) or delta>=-Fraction(1,100000000):raise ValueError('NEGATIVE_DIRECTION_PRICE_REPLAY_FAIL')
        graph=support_graph(data[5][data[7]['classes'][key][0]],cache['graph'],cache['units'],a['X'],job=data[1][data[7]['classes'][key][0]])
        reduced,RB,_,units=native_block(data,key,graph,tuple(rebuilt['axes']))
        projected=project_local_point(cache['units'],a['X'],units,reduced.matrix.shape[1])
        if not primal_replay(reduced,projected)['PASS']:raise ValueError('SAVED_DIRECTION_SUPPORT_INVALID')
        negative.append(dict(class_id=key,price=delta,graph=graph,support_sha256=graph.sha))
        print('RECOVERED_NEGATIVE_BLOCK',len(negative),key[:12],flush=True)
        del cache,a;gc.collect()
    if len(negative)!=92:raise ValueError('ACTUAL_NEGATIVE_BLOCK_COUNT_DRIFT')
    selected=sorted(negative,key=lambda z:(z['price'],z['class_id'],z['support_sha256']))[:64]
    data=rebuilt['data'];ledger=rebuilt['ledger']
    for c in selected:data,ledger=update_graph(data,rebuilt['domains'],c['class_id'],c['graph'])
    # Preserve existing exact concrete perspective columns: old activate() did
    # not pass them into build(), an additional representation loss audited here.
    new=build(rebuilt['reference'],rebuilt['grows'],rebuilt['n'],rebuilt['axes'],data,rebuilt['domains'],ledger,candidates)
    new.update(scientific_descriptor=rebuilt['scientific_descriptor'],global_types=rebuilt['global_types'],atlas=rebuilt['atlas'])
    from v42_a_stage_early.progress import capture,inclusion_witness
    em=elastic_master(rebuilt['reference'],rebuilt['grows']);nm=elastic_master(new['reference'],new['grows'])
    prior=capture(rebuilt['reference'],rebuilt['reference_descriptor'],em,dict(X=np.r_[x,np.zeros(len(em.artificial_rows))]))
    try:inclusion_witness(prior,new['reference'],new['reference_descriptor'],nm,rebuilt['n'])
    except ValueError as e:
        if str(e)!='PRIOR_WITNESS_FROZEN_ARTIFICIAL_WEIGHT_OR_SIGN_DRIFT':raise
        failure=traceback.format_exc()
    else:raise AssertionError('ACTUAL_HISTORICAL_WITNESS_FAILURE_NOT_REPRODUCED')
    changed=[dict(row=r,old=str(w),new=str(v),old_artificial_index=i) for i,(r,w,v) in enumerate(zip(em.artificial_rows,em.weights,nm.weights)) if w!=v]
    payload=save('ACTUAL_FAILURE_REGRESSION.pkl.gz',dict(previous=prior,new=new,old=rebuilt,negative=negative,raw=raw))
    atomic(OUT/'WITNESS_FAILURE_REPRODUCTION.json',dict(PASS=True,error_reproduced=True,error=failure,payload=payload,
        old_weights_count=len(em.weights),new_weights_count=len(nm.weights),changed_weights=changed,
        sign_change=em.artificial_signs!=nm.artificial_signs,artificial_Phi=str(prior['Phi']),
        underlying_artificial_free_old_replay=replay,new_columns_and_rows=[list(rebuilt['reference'].matrix.shape),list(new['reference'].matrix.shape)],
        native_calls=0,wall_seconds=perf_counter()-started))
    print('ACTUAL_WITNESS_FAILURE_REPRODUCED',len(changed),str(prior['Phi']),flush=True)
if __name__=='__main__':run()
