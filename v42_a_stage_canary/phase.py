"""Same exact SUM/hybrid, row promotion, full pricing and inclusion loop."""
from fractions import Fraction
from dataclasses import asdict
from time import perf_counter
import numpy as np
from v42_pr134_b1.common import atomic,record
from v42_a_stage_phase1.core import elastic_master,phase_objective,primal_replay,verify_sign_convention,verify_zero
from v42_a_stage_compact_rowgen.rowgen import restricted,certified_separate
from v42_a_stage_compact_rowgen.assembly import partition,build,compact_inverse
from v42_a_stage_compact_rowgen.lift import expanded_point
from v42_a_stage_phase1.backend import update_graph,artificial_point as point_with_replay
from v42_a_stage_early.progress import capture,inclusion_witness
from .policy import OUT,POLICY
from .pricing import full_pricing
from .targeted import targeted
from v42_a_stage_practical.attribution import analyze
from v42_a_stage_early.candidate import expanded_graph

def artificial_point(master,point):
    lifted,replay=point_with_replay(master,point)
    if not replay['PASS']:raise ValueError('ARTIFICIAL_POINT_INDEPENDENT_REPLAY_FAILED')
    return lifted

def activate(state,negative,x,folder):
    G=state['grows'];master=elastic_master(state['reference'],G)
    expanded=expanded_point(state,x)
    point=np.r_[expanded,np.zeros(len(master.artificial_rows))]
    prior=capture(state['reference'],state['reference_descriptor'],master,dict(X=point))
    data=state['data'];ledger=state['ledger'];selected=sorted(negative,key=lambda z:(z['price'],z['class_id'],z['support_sha256']))[:64]
    for c in selected:data,ledger=update_graph(data,state['domains'],c['class_id'],c['graph'])
    new=build(state['reference'],G,state['n'],state['axes'],data,state['domains'],ledger,[])
    nm=elastic_master(new['reference'],G)
    witness,mapped=inclusion_witness(prior,new['reference'],new['reference_descriptor'],nm,state['n'])
    # Phi>0 prior artificials must be recomputed for the expanded source rows;
    # point capture below is used by Phase-I separately before this helper.
    if not witness['PASS']:raise ValueError('EXACT_PRIOR_POINT_INCLUSION_FAIL')
    new['scientific_descriptor']=state['scientific_descriptor'];new['global_types']=state['global_types'];new['atlas']=state['atlas']
    inverse=compact_inverse(new,mapped[:new['reference'].matrix.shape[1]])
    if not primal_replay(new['compact'],inverse)['PASS']:raise ValueError('COMPACT_INVERSE_FAIL')
    atomic(folder/'ACTIVATION.json',dict(PASS=True,prior_inclusion=witness,selected=[dict(class_id=c['class_id'],price=str(c['price']),support_sha256=c['support_sha256']) for c in selected],
        full_native_LP_kernel_support=True,physical_integer_column_claim=False,candidate_deletion=False))
    return new,inverse

def run(native,state,day,certified_zero_point=None):
    G=state['grows'];folder=OUT/day;included=set(range(len(G),state['compact'].matrix.shape[0]))|set(state['axes'].values())
    prior=state['prior_compact'];s=state['compact'];activity=s.matrix@prior-s.rhs
    nonzero=np.diff(s.matrix.indptr[:len(G)+1])>0
    included.update(np.flatnonzero(nonzero&(abs(activity[:len(G)])<=1e-6)))
    full=elastic_master(s,G);p=artificial_point(full,prior)
    contributions=np.zeros(len(G))
    for i,w,x in zip(full.artificial_rows,full.weights,p[s.matrix.shape[1]:]):contributions[i]+=float(w)*x
    included.update(np.argsort(-contributions,kind='stable')[:50]);phase_traces=[];stagnation=0;activation_round=0;bestPhi=None
    if certified_zero_point is not None:
        x=np.asarray(certified_zero_point);allmaster=elastic_master(s,G)
        zero=verify_zero(allmaster,artificial_point(allmaster,x))
        ex=expanded_point(state,x);rep=primal_replay(state['reference'],ex)
        if not zero['PASS'] or not rep['PASS']:raise ValueError('PHASE_I_CHECKPOINT_ZERO_NOT_VERIFIED')
        atomic(folder/'PHASE_I_ZERO_CERTIFICATE.json',dict(PASS=True,zero=zero,full_original_replay=rep,
            Phi=0.,activation_rounds=0,independently_replayed_checkpoint=True,native_reoptimization_calls=0))
    while certified_zero_point is None:
        native.remaining();s=state['compact'];rows=tuple(sorted(included));r=restricted(s,rows)
        global_rows=tuple(j for j,i in enumerate(rows) if i<len(G));master=elastic_master(r,global_rows)
        f=folder/'PHASE_I'/('S'+str(len(phase_traces)));f.mkdir(parents=True,exist_ok=True)
        rec,raw=native.solve(master.snapshot,f,'PHASE_I')
        if rec['status']!=2 or not all(k in raw for k in ('X','Pi','RC')):raise RuntimeError('PHASE_I_NOT_OPTIMAL')
        rp=primal_replay(master.snapshot,raw['X']);sign=verify_sign_convention(master.snapshot,raw['Pi'],raw['RC'])
        if not rp['PASS'] or not sign['PASS']:raise ValueError('PHASE_I_RAW_REPLAY_FAIL')
        x=raw['X'][:s.matrix.shape[1]];sep=certified_separate(s,x,included);Phi=phase_objective(master,raw['X'])
        atomic(f/'ROW_SEPARATION.json',sep);phase_traces.append(dict(solve=len(phase_traces),Phi=float(Phi),exact_Phi=str(Phi),row_closed=sep['PASS'],added_rows=len(sep['violated_rows']),Runtime=rec['native_seconds'],Work=rec['Work'],rows=r.matrix.shape[0],cols=master.snapshot.matrix.shape[1],nnz=master.snapshot.matrix.nnz))
        atomic(folder/'PHASE_I_TRACE.json',dict(trajectory=phase_traces,activation_rounds=activation_round))
        if not sep['PASS']:
            included.update(sep['violated_rows'])
            if len(phase_traces)>=POLICY['row_promotion_after']:included=set(range(s.matrix.shape[0]))
            continue
        allmaster=elastic_master(s,G);fullpoint=artificial_point(allmaster,x);zero=verify_zero(allmaster,fullpoint)
        if zero['PASS']:
            ex=expanded_point(state,x);rep=primal_replay(state['reference'],ex)
            if not rep['PASS']:raise ValueError('ORIGINAL_ARTIFICIAL_FREE_REPLAY_FAIL')
            atomic(folder/'PHASE_I_ZERO_CERTIFICATE.json',dict(PASS=True,zero=zero,full_original_replay=rep,Phi=float(Phi),activation_rounds=activation_round))
            break
        pi=np.zeros(s.matrix.shape[0]);pi[list(rows)]=raw['Pi'];fmraw=dict(X=fullpoint,Pi=pi)
        local,owned=partition(s,state['metas'],G)
        attribution,effect,baseline=analyze(allmaster,fmraw,state['data'],state['axes'],owned,state['atlas'],f/'ATTRIBUTION')
        priced,selected=targeted(native,None,1,s,allmaster,fmraw,state['data'],state['domains'],state['ledger'],state['axes'],local,owned,
            attribution['target_classes'],effect,baseline,f/'PRICE')
        if not selected:
            remaining=[r['class_id'] for r in attribution['classes_ranked'] if r['inactive_candidates_available'] and r['class_id'] not in attribution['target_classes']]
            if remaining:priced,selected=targeted(native,None,1,s,allmaster,fmraw,state['data'],state['domains'],state['ledger'],state['axes'],local,owned,
                remaining,effect,baseline,f/'REMAINING_PRICE')
            if not selected:raise RuntimeError('FULL_PHYSICAL_QUERY_RECOVERY_EXHAUSTED_WITHOUT_VALID_NEGATIVE_CONCRETE_COLUMN')
        # Preserve the current complete Phase-I witness, including its actual
        # original-row artificials, before rebuilding native support.
        ex=expanded_point(state,x);em=elastic_master(state['reference'],G);ep=artificial_point(em,ex)
        old=capture(state['reference'],state['reference_descriptor'],em,dict(X=ep));data=state['data'];ledger=state['ledger']
        candidates=[c for m in state['metas'].values() for c in m['candidates']]
        for c in selected:
            uid=data[7]['classes'][c['class_id']][0]
            graph=expanded_graph(data[5][uid],c['option'],data[1][uid],state['domains'][uid],uid in data[7]['preserve_singleton_mixed_flow'])
            data,ledger=update_graph(data,state['domains'],c['class_id'],graph);candidates.append(dict(c,option=asdict(c['option']),price=str(c['price'])))
        new=build(state['reference'],G,state['n'],state['axes'],data,state['domains'],ledger,candidates);nm=elastic_master(new['reference'],G)
        witness,mapped=inclusion_witness(old,new['reference'],new['reference_descriptor'],nm,state['n'])
        atomic(f/'PRIOR_INCLUSION.json',witness)
        if not witness['PASS']:raise ValueError('PHASE_I_PREVIOUS_POINT_NOT_FEASIBLE')
        inverse=compact_inverse(new,mapped[:new['reference'].matrix.shape[1]])
        fullnew=elastic_master(new['compact'],G);included_point=np.r_[inverse,mapped[new['reference'].matrix.shape[1]:]]
        if not primal_replay(fullnew.snapshot,included_point)['PASS'] or phase_objective(fullnew,included_point)!=old['Phi']:raise ValueError('PREVIOUS_PHI_INCLUSION_NOT_PRESERVED')
        atomic(f/'PHYSICAL_ACTIVATION.json',dict(PASS=True,STAY=priced['selected_STAY'],migration=priced['selected_migration'],
            exact_preserved_Phi=str(phase_objective(fullnew,included_point)),physical_membership_and_exact_negative_RC_verified=True,
            raw_increase_not_real_worsening=True,permanent_deletions=False))
        new.update(scientific_descriptor=state['scientific_descriptor'],global_types=state['global_types'],atlas=state['atlas'])
        state=new;activation_round+=1;included=set(range(new['compact'].matrix.shape[0]))
        if bestPhi is not None:stagnation=stagnation+1 if (bestPhi-Phi)/bestPhi<Fraction(1,100) else 0
        bestPhi=Phi if bestPhi is None else min(bestPhi,Phi)
        if stagnation>=3:raise RuntimeError('THREE_CERTIFIED_ROW_CLOSED_NONMATERIAL_ROUNDS')
    # Original P1: every row is now retained, every omitted full-native class
    # is priced by the same May19 oracle and independent rational dual replay.
    traces=[]
    while True:
        s=state['compact'];f=folder/'P1'/('S'+str(len(traces)));f.mkdir(parents=True,exist_ok=True)
        rec,raw=native.solve(s,f,'ORIGINAL_P1')
        if rec['status']!=2 or not all(k in raw for k in ('X','Pi','RC')):raise RuntimeError('P1_NOT_OPTIMAL')
        replay=primal_replay(s,raw['X']);sign=verify_sign_convention(s,raw['Pi'],raw['RC'])
        if not replay['PASS'] or not sign['PASS']:raise ValueError('P1_RAW_FAIL')
        ex=expanded_point(state,raw['X']);original=primal_replay(state['reference'],ex)
        if not original['PASS']:raise ValueError('P1_ORIGINAL_REPLAY_FAIL')
        local,owned=partition(s,state['metas'],G)
        priced,negative=full_pricing(native,s,None,raw,None,state['data'],state['domains'],state['ledger'],state['axes'],state['n'],G,local,owned,f/'PRICE')
        traces.append(dict(Runtime=rec['native_seconds'],Work=rec['Work'],objective=rec['objective'],valid_LB=priced['full_domain_phase1_lower_bound'],row_closed=True,pricing_closed=priced['no_negative_omitted_block_certified']))
        atomic(folder/'P1_TRACE.json',dict(trajectory=traces))
        if priced['no_negative_omitted_block_certified']:
            if priced['full_domain_phase1_lower_bound'] is None:raise ValueError('P1_CLOSURE_WITHOUT_VALID_GLOBAL_LB')
            atomic(folder/'P1_RESULT.json',dict(PASS=True,P1_LP_closure=True,valid_LB=float(Fraction(priced['full_domain_phase1_lower_bound'])),exact_valid_LB=priced['full_domain_phase1_lower_bound'],
                P1_LP_value=rec['objective'],full_pricing=record(f/'PRICE/FULL_PRICING_RESULT.json'),row_replay=original))
            return state,raw['X'],ex,priced
        if not negative:raise ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')
        state,_=activate(state,negative,raw['X'],f)
