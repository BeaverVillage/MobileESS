"""Bounded legacy-mechanics CG integration; one sequential worker, no production hooks."""
from pathlib import Path
from fractions import Fraction as F
from time import perf_counter
from hashlib import sha256
from types import SimpleNamespace
import argparse, json, subprocess
import numpy as np
from .case import load, read, file_sha
from .budget import ContinuedBudget,write
from .master import build_master
from .adapter import CGAdapter, exact_price, strict_admission, checkpoint, validate_checkpoint
from .pricing import certify_price
from .certificate import check_global, node_bound_details
from .diagnostics import diagnose
from v42_m1_hybrid.pricing import make_prices,build_pricing_model
from v42_m1_research.check_ub import matrix_replay,vector_sha


def source_hash():
    h=sha256()
    for p in sorted(Path(__file__).parent.glob('*.py')):h.update(p.name.encode());h.update(p.read_bytes())
    return h.hexdigest()


def bind_prices(case,decomp,seed_prices,source_rows,pi):
    full={str(int(i)):str(F(float(v))) for i,v in zip(source_rows,pi) if v}
    for u,b in decomp.units.items():
        for k,v in seed_prices.seed_unit_duals[u].items():full[str(int(b.original_rows[int(k)]))]=v
    return make_prices(case,decomp,full)


def discover(block,search_price,point,budget,folder,label):
    folder.mkdir(parents=True,exist_ok=True)
    native=np.array([float(F(search_price.get(str(j),'0'))) for j in range(block.A.shape[1])])
    begin=perf_counter();model,variables,build=build_pricing_model(block,native,'MILP',point)
    budget.build_seconds+=perf_counter()-begin
    try:
        model.Params.MIPGap=0.
        receipt=budget.optimize(model,label,6.)
        raw=None;admission=None
        if model.SolCount:
            raw=np.asarray(variables.X);admission=strict_admission(block,raw,block.original_columns)
            file=folder/'DISCOVERY_RAW.npz';np.savez_compressed(file,point=raw,original_columns=block.original_columns)
        else:file=None
        write(folder/'DISCOVERY.json',dict(native=receipt,build=build,local_admission=admission,
              raw_path=str(file) if file else None,objective_is_discovery_only=True,
              numerical_MIP_bound_certificate_authority=False))
        return file if admission and admission['PASS'] else None
    finally:model.dispose()


def original_master_audit(case,decomp,identity,model,variables,rows,source_rows):
    x=np.asarray(variables.X);rawpi=np.asarray(rows.Pi);pi=rawpi.copy()
    for i,e in identity['row_scale_exponents'].items():pi[int(i)]=np.ldexp(pi[int(i)],e)
    senses=case.d['sense'][source_rows];bad=((senses=='<')&(pi[:len(source_rows)]>0))|((senses=='>')&(pi[:len(source_rows)]<0))
    if not np.isfinite(pi).all() or bad.any():raise ValueError('MASTER_ORIGINAL_SIGN_FAIL_NO_CLIPPING')
    point=np.zeros(case.A.shape[1]);n=len(decomp.nonunit_columns);point[decomp.nonunit_columns]=x[:n]
    for weight,item in zip(x[n:],identity['catalog']):
        b=decomp.units[item['unit']]
        if item['source']=='ORIGINAL_VERIFIED_UB_SEED':col=case.point[b.original_columns]
        else:col=np.load(item['source'],allow_pickle=False)['point']
        point[b.original_columns]+=weight*col
    relaxed=dict(case.d,types=np.full(case.A.shape[1],'C'))
    replay=matrix_replay(case.A,relaxed,point)
    if not replay['PASS'] or abs(replay['objective']-model.ObjVal)>1e-8:
        raise ValueError('MASTER_ORIGINAL_COORDINATE_REPLAY_FAIL')
    eta=np.asarray(pi[len(source_rows):]);rc=np.asarray(variables.RC)
    return pi,eta,dict(original_LP_replay=replay,strict_inequality_signs=True,
                      numerical_only=True,objective=float(model.ObjVal),lambda_values=x[n:].tolist(),
                      lambda_RC=rc[n:].tolist(),lambda_upper_bounds_preserved=True),point


def ceiling_audit(case,decomp,identity,point,objective,target):
    # Stop-rule authority requires exact column membership AND an exact master witness.
    # Native objective alone is never an upper certificate for the full DW hull.
    if objective>=target:return dict(status='NOT_TRIGGERED_OBJECTIVE_ABOVE_TARGET',certified=False)
    for item in identity['catalog']:
        b=decomp.units[item['unit']]
        x=case.point[b.original_columns] if item['source']=='ORIGINAL_VERIFIED_UB_SEED' else np.load(item['source'],allow_pickle=False)['point']
        for i in range(b.A.shape[0]):
            a,z=b.A.indptr[i:i+2]
            value=sum((F(float(c))*F(float(x[j])) for j,c in zip(b.A.indices[a:z],b.A.data[a:z])),F(0))-F(float(b.d['rhs'][i]))
            s=b.d['sense'][i]
            if (s=='=' and value!=0) or (s=='<' and value>0) or (s=='>' and value<0):
                return dict(status='NUMERICAL_CEILING_ONLY_NOT_PROVEN',certified=False,
                            first_nonexact_column=item['point_sha'],row=i,residual=str(value))
    # Exact full original coupling, variable box, convexity and column weights must
    # also be replayed. Fail closed; do not promote a merely numerical RMP witness.
    return dict(status='EXACT_MASTER_WITNESS_NOT_PROVEN',certified=False)


def run(spec,output,*,resume=False):
    start=perf_counter();root=Path(__file__).resolve().parents[1];output=Path(output).resolve()
    gate=read(root/'docs/v42_m_stage_trajectory_hull/INTEGRATION_GATES.json')
    if not gate['PASS'] or gate['source_hash']!=source_hash():raise ValueError('FIXTURE_GATE_OR_SOURCE_FREEZE_DRIFT')
    if gate.get('native_pilot_stopped',False):
        raise ValueError('PILOT_STOPPED_NO_AUTOMATIC_REPLAY')
    prior=root/'runtime/v42_trajectory_hull/first_CG_round01'
    native_authority=gate.get('native_ledger')
    previous_ledger=root/native_authority['path'] if native_authority else prior/'LEDGER.json'
    if native_authority and file_sha(previous_ledger)!=native_authority['sha256']:
        raise ValueError('CUMULATIVE_NATIVE_AUTHORITY_DRIFT')
    carried=read(previous_ledger)['measured_native_seconds']
    remaining_campaign=max(0.,gate.get('campaign_native_ceiling',carried+300)-carried)
    budget=ContinuedBudget(output,previous_ledger,additional_limit=min(300.,remaining_campaign),resume=resume)
    case,decomp,seed,admission=load(spec);write(output/'SOURCE_ADMISSION.json',admission)
    identity={k:spec[k] for k in ('stage','case_sha','selected_matrix_sha','selected_domain_sha','fixed_input_sha','fixed_decision_sha')}
    base=root/'runtime/v42_trajectory_hull/may01_pilot01';trial=root/'runtime/v42_trajectory_hull/master_single_trial01'
    previous=[read(base/'round_0_CERTIFICATE_PACKET.json'),read(trial/'NEW_PRICE_CERTIFICATE_PACKET.json'),read(prior/'CERTIFICATE_PACKET.json')]
    catalog={u:[] for u in decomp.units}
    for u in decomp.units:
        catalog[u].extend(previous[0]['units'][u]['columns']);catalog[u].extend(previous[1]['units'][u]['columns'])
    saved=dict(np.load(prior/'MASTER_SOLUTION.npz',allow_pickle=False));pi=saved['Pi_original'];eta=pi[len(saved['source_rows']):];srows=saved['source_rows']
    old_true=dict(np.load(trial/'MASTER_SOLUTION.npz',allow_pickle=False));before=read(prior/'RESULT.json')
    best=F(str(before['old_LB']));candidate_before=F(before['independent_certificate']['exact_bound']);best_candidate=candidate_before;last_objective=before['master_objective_after'];rounds=[];stop=None
    if resume:
        cp=validate_checkpoint(output/'CHECKPOINT.json',identity,decomp)
        if cp['terminal']:raise ValueError('TERMINAL_CHECKPOINT_NO_AUTOMATIC_CONTINUATION')
        catalog=cp['catalog'];saved=dict(np.load(cp['dual_file'],allow_pickle=False));pi=saved['Pi_original'];eta=pi[len(saved['source_rows']):];srows=saved['source_rows'];best=F(cp['best']);last_objective=cp['objective'];rounds=cp['rounds']
    adapter=CGAdapter(case,decomp,srows,catalog,output)
    if resume:
        adapter.current_round=cp['round'];adapter.column_id=cp['column_id'];adapter.columns=cp['new_column_records']
        sm=np.load(cp['smooth_file']);adapter.smooth_pi=sm['pi'];adapter.smooth_conv=sm['alpha'];adapter.smooth_weight=cp['smooth_weight'];adapter.last_true_pi=pi.copy()
    else:
        adapter.smooth_pi=old_true['Pi_original'][:len(srows)].copy();adapter.smooth_conv=old_true['Pi_original'][len(srows):].copy();adapter.last_true_pi=adapter.smooth_pi.copy()
        diagnose(case,decomp,prior,output/'FIRST_ROUND_ANOMALY.json')
    seed_prices=make_prices(case,decomp,seed);initial_columns=sum(len(v) for v in catalog.values())+4
    target=float(F(97,100)*F(spec['ub_exact']))
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    write(output/'PREREGISTRATION.json',dict(source_commit=source_commit,source_hash=source_hash(),
        maximum_rounds=3,pricing_seconds_per_unit=20,discovery_MILP_seconds=6,
        certification_node_seconds=[8,3,3],master_seconds=15,workers=1,Threads=1,
        additional_native_cap=300,cumulative_cap=600,carried=budget.carried,
        multi_column_acceleration=False,early_BAP=False,B3_M1='NOT_RUN_NO_FIXED_INPUT',B3_M2='NOT_RUN_NO_FIXED_INPUT'))
    try:
        for iteration in range(adapter.current_round,3):
            if budget.remaining<98:stop='NATIVE_BUDGET_RESERVE';break
            adapter.current_round=iteration+1
            true_prices=bind_prices(case,decomp,seed_prices,srows,pi)
            etas={u:str(F(float(eta[k]))) for k,u in enumerate(decomp.units)};adapter.bind_true_prices(true_prices,etas)
            smooth_pi,smooth_eta=adapter.smooth(pi[:len(srows)],eta)
            discovery_pi=np.concatenate((smooth_pi,smooth_eta));search_prices=bind_prices(case,decomp,seed_prices,srows,discovery_pi)
            candidates=[];requested_by_unit={}
            for m,(u,b) in enumerate(decomp.units.items()):
                folder=output/('round_%d'%adapter.current_round)/u/'discovery'
                raw=discover(b,{str(j):str(q) for j,q in search_prices.exact_objectives[u].items()},case.point[b.original_columns],budget,folder,'R%d_%s_DISCOVERY'%(adapter.current_round,u))
                options=[]
                if raw:options.append(raw)
                # Current-case cached pricing columns are discovery candidates, not bound authority.
                for p in previous:
                    for item in p['units'][u].get('columns',[]):
                        if file_sha(item['path'])!=item['sha256']:raise ValueError('CACHED_COLUMN_DRIFT')
                        options.append(Path(item['path']))
                admissible=[]
                for path in options:
                    z=np.load(path,allow_pickle=False);x=z['point'];local=strict_admission(b,x,z['original_columns']);rc=exact_price(x,adapter.blocks[m].true_price)-adapter.blocks[m].eta
                    if local['PASS'] and rc<0 and vector_sha(x) not in adapter.seen[m]:admissible.append((rc,path))
                if admissible:candidates.append(adapter.admit(m,min(admissible,key=lambda v:v[0])[1]))
                requested_by_unit[u]=6.
            write(output/('round_%d_DISCOVERY_ADMISSION.json'%adapter.current_round),candidates)
            count=sum(c.get('added',False) for c in candidates)
            if not count:stop='NO_VALID_TRUE_NEGATIVE_RC_COLUMN';break
            begin=perf_counter();model,v,rows,mid,srows=build_master(case,decomp,catalog,output/('round_%d'%adapter.current_round)/'master');budget.build_seconds+=perf_counter()-begin
            try:
                native=budget.optimize(model,'R%d_MASTER'%adapter.current_round,15.)
                if int(model.Status)!=2:stop='MASTER_NOT_OPTIMAL';break
                previous_pi=pi.copy();pi,eta,audit,point=original_master_audit(case,decomp,mid,model,v,rows,srows)
                obj=float(model.ObjVal)
                dual_file=output/('TRUE_DUAL_%d.npz'%adapter.current_round)
                np.savez_compressed(dual_file,Pi_original=pi,Pi_solver=np.asarray(rows.Pi),source_rows=srows,X=np.asarray(v.X))
                write(output/('round_%d_MASTER_AUDIT.json'%adapter.current_round),audit)
                ceiling=ceiling_audit(case,decomp,mid,point,obj,target)
            finally:model.dispose()
            prices=bind_prices(case,decomp,seed_prices,srows,pi)
            packet=dict(case_sha=case.case_sha,coupling_dual=prices.coupling_dual,nonunit_dual=prices.seed_nonunit_dual,units={})
            for u,b in decomp.units.items():
                bank=[]
                for p in previous:
                    bank.extend(n['proof']['dual'] for n in p['units'][u]['tree'].values() if n.get('proof') and n['proof']['kind']=='DUAL')
                rec=certify_price(b,{str(j):str(q) for j,q in prices.exact_objectives[u].items()},prices.seed_unit_duals[u],budget,output/('round_%d'%adapter.current_round)/u/'certification',label='R%d_%s_CERT'%(adapter.current_round,u),node_limits=(8,3,3),saved_duals=bank)
                packet['units'][u]=rec;requested_by_unit[u]+=14.
            begin=perf_counter();cert=check_global(case,decomp,packet);budget.certificate_seconds+=perf_counter()-begin
            write(output/('round_%d_PACKET.json'%adapter.current_round),packet);write(output/('round_%d_GLOBAL_CERTIFICATE.json'%adapter.current_round),cert)
            candidate=F(cert['exact_bound']);best=max(best,candidate);etas={u:F(float(eta[k])) for k,u in enumerate(decomp.units)}
            gaps={}
            for u,b in decomp.units.items():
                q={str(j):str(v) for j,v in prices.exact_objectives[u].items()}
                points=[case.point[b.original_columns]]+[np.load(item['path'],allow_pickle=False)['point'] for item in catalog[u]]
                numerical_min=min(exact_price(x,q) for x in points)
                gaps[u]=float(numerical_min-F(cert['exact_integer_price_bounds'][u]))
            reduced={u:str(F(cert['exact_integer_price_bounds'][u])-etas[u]) for u in decomp.units}
            closure=all(F(v)>=0 for v in reduced.values())
            fixed=candidate-sum((F(v) for v in cert['exact_integer_price_bounds'].values()),F(0))
            row=dict(round=adapter.current_round,new_columns=count,total_columns=4+sum(len(x) for x in catalog.values()),
                master_before=last_objective,master_after=obj,master_native=native,
                true_dual_changed_rows=int(np.count_nonzero(pi!=previous_pi)),candidate_exact=str(candidate),
                certified_DW_LB=cert['independently_certified_LB'],published_LB=float(best),
                unit_price_LBs=cert['exact_integer_price_bounds'],pricing_gap_diagnostic=gaps,
                pricing_gap_uses_numerically_admitted_columns_not_exact_upper_certificates=True,
                fixed_terms_exact=str(fixed),convexity_duals={u:str(v) for u,v in etas.items()},
                missing_trajectory_RC_LBs=reduced,closure=closure,formulation_ceiling=ceiling,
                true_RC_admissions=candidates,pricing_requested_seconds=requested_by_unit)
            rounds.append(row);last_objective=obj
            checkpoint(adapter,budget,output/'CHECKPOINT.json',identity,dual_file)
            cp=read(output/'CHECKPOINT.json');cp.update(terminal=False,best=str(best),objective=obj,rounds=rounds,column_id=adapter.column_id,new_column_records=adapter.columns);write(output/'CHECKPOINT.json',cp)
            validate_checkpoint(output/'CHECKPOINT.json',identity,decomp)
            print(json.dumps(dict(round=adapter.current_round,master=obj,LB=float(best),candidate=float(candidate),gaps=gaps,Native=budget.used)),flush=True)
            if ceiling['certified'] and obj<target:stop='COLUMN_GENERATION_FORMULATION_CEILING';break
            if closure:stop='FULL_PRICING_BOUND_CLOSURE';break
            # No repeated rounds when the pricing gap remains large and even the
            # independently certified candidate fails to improve the last candidate.
            if max(gaps.values())>.001 and candidate<=best_candidate+F('0.001'):
                stop='LARGE_PRICING_CERTIFICATE_GAP_NO_CERTIFIED_DIRECTION';break
            best_candidate=max(best_candidate,candidate)
            previous.append(packet);adapter.last_true_pi=previous_pi[:len(srows)].copy()
        stop=stop or 'MAXIMUM_THREE_DISCOVERY_MASTER_ROUNDS'
    except Exception as exc:
        stop='FAIL_CLOSED:'+repr(exc);write(output/'FAILURE.json',dict(error=repr(exc)))
    result=dict(case_identity=identity,source_commit=source_commit,source_hash=source_hash(),stop=stop,
        rounds=rounds,before=dict(total_columns=initial_columns,master=before['master_objective_after'],
            DW_LB=before['independent_DW_candidate'],published_LB=before['new_certified_global_LB'],
            unit_LBs=before['exact_unit_pricing_LBs_after'],Native=budget.carried),
        after=dict(total_columns=4+sum(len(x) for x in catalog.values()),master=last_objective,
            DW_LB=rounds[-1]['certified_DW_LB'] if rounds else before['independent_DW_candidate'],
            published_LB=max(before['new_certified_global_LB'],float(best)),
            certified_delta=max(0.,float(best)-before['new_certified_global_LB']),
            gap_percent=100*(before['UB']-max(before['new_certified_global_LB'],float(best)))/before['UB'],
            Native=budget.used,additional_Native=budget.used-budget.carried,
            closure=rounds[-1]['closure'] if rounds else False),
        target_LB_for_3pct=target,production_promoted=False,B3_M1='NOT_RUN_NO_FIXED_INPUT',B3_M2='NOT_RUN_NO_FIXED_INPUT',
        build_seconds=budget.build_seconds,certificate_seconds=budget.certificate_seconds,wall_seconds=perf_counter()-start)
    write(output/'RESULT.json',result)
    if (output/'CHECKPOINT.json').exists():
        cp=read(output/'CHECKPOINT.json');cp['terminal']=True;write(output/'CHECKPOINT.json',cp)
    print(json.dumps(result,indent=2),flush=True);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--spec',required=True);parser.add_argument('--output',required=True);parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    run(read(args.spec),args.output,resume=args.resume)
