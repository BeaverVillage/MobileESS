"""Qualification/build only. No May19 optimize and no candidate pricing."""
from pathlib import Path
from dataclasses import replace
from fractions import Fraction
import gzip,pickle,subprocess,hashlib,zipfile
from collections import defaultdict
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import atomic,read,record,sha
from v42_a_stage_domain_v2.active import option_from_json,indexed_contains
from v42_a_stage_domain_v2.lexstage import Objective,LinearSnapshot
from v42_a_stage_phase1.backend import update_graph,assemble_original,evaluate
from v42_a_stage_phase1.producer import native_block
from v42_a_stage_phase1.core import elastic_master,primal_replay,phase_objective
from v42_a_stage_early.candidate import expanded_graph,point_for_option,exact_coupling
from .kernel import perspective,binary64
from .equivalence import verify as equivalence,role
from .projection import exact_replay
from .policy import ROOT,OUT,STATIC,PR178,POLICY
from . import BASE

def shift(unit,amount):
    def entry(e):
        return ('v',int(e[1])+amount) if e[0]=='v' else ('e',e[1],np.asarray(e[2])+amount,e[3]) if e[0]=='e' else e
    return dict(unit,v={family:{key:entry(e) for key,e in items.items()} for family,items in unit['v'].items()})

def prepare():
    OUT.mkdir(parents=True,exist_ok=True);STATIC.mkdir(parents=True,exist_ok=True)
    if (OUT/'RUN_STARTED.json').exists():raise PermissionError('ONE_EXPERIMENT_ONLY')
    batch_path=PR178/'M19/R0/TARGETED/PRICING_RESULT.json';batch=read(batch_path)['selected_candidates']
    if len(batch)!=64 or sum(c['kind']=='MIGRATION' for c in batch)!=32:raise ValueError('FROZEN_BATCH_IDENTITY_FAIL')
    initial=read(PR178/'INITIAL_VERIFICATION.json')
    if record(initial['state']['path'])!=initial['state']:raise ValueError('FROZEN_INITIAL_STATE_DRIFT')
    with gzip.open(initial['state']['path'],'rb') as f:state=pickle.load(f)
    base,old_desc,data,domains,ledger,axes,n,grows,old_lrows,old_owned=state
    initial_data=data;byclass=defaultdict(list)
    for c in batch:
        byclass[c['class_id']].append(c);uid=data[7]['classes'][c['class_id']][0];o=option_from_json(c['option'])
        if initial_data[5][uid].fixed:raise ValueError('FOLDED_FIXED_CONSTANT_TARGET_REQUIRES_DIFFERENT_PROJECTION')
        if not indexed_contains(data[1][uid],data[2][uid],data[3],domains[uid],o):raise ValueError('FROZEN_PHYSICAL_MEMBERSHIP_FAIL')
        graph=expanded_graph(data[5][uid],o,data[1][uid],domains[uid],uid in data[7]['preserve_singleton_mixed_flow'])
        data,ledger=update_graph(data,domains,c['class_id'],graph)
    reference,rdesc,rgrows,rlrows,rowned,raxes=assemble_original(base,grows,n,axes,data)
    expected=read(PR178/'M19/R0/EXPANSION_STOP.json')
    if reference.matrix.shape!=(expected['rows'],expected['cols']) or reference.matrix.nnz!=expected['nnz']:raise ValueError('PR178_EXPANDED_REFERENCE_DRIFT')
    checks=[];proofs=[];parts=[];global_parts=[base.matrix[list(grows),:n].tocsr()];lbs=[];ubs=[];ss=[];rhs=[];descriptors=[];metas={};offset=n
    ids={key:sorted(j for j,k in rowned.items() if k==key) for key in data[7]['classes']}
    for key,members in sorted(data[7]['classes'].items()):
        uid=members[0];N=len(members);cs=byclass[key];snap,B,const,units=native_block(data,key,data[5][uid],tuple(axes),averaged=True)
        cols=ids[key];first=cols[0] if cols else n
        original=replace(reference,matrix=reference.matrix[list(rlrows[key])][:,cols].tocsr(),lower=reference.lower[cols],upper=reference.upper[cols],
            senses=reference.senses[list(rlrows[key])],rhs=reference.rhs[list(rlrows[key])],vtypes=np.full(len(cols),'C'),objectives=(Objective('local_price',(),0),))
        original_B=reference.matrix[list(axes.values())][:,cols].tocsr()
        original_units=[shift(u,-first) for u in rdesc['units'] if u['uid'] in members]
        proofs.append(dict(class_id=key,**equivalence(original,original_B,original_units,snap,B,units,N)))
        cache=dict(snapshot=snap,B=B,graph=data[5][uid],units=units);points=[]
        for c in cs:
            o=option_from_json(c['option']);p=point_for_option(cache,data[1][uid],data[3],o,N);physical=exact_coupling(B,p)
            if physical!={int(i):Fraction(v) for i,v in c['coupling']}:raise ValueError('FROZEN_COUPLING_COEFFICIENT_LOSS')
            if not exact_replay(snap,p)['PASS']:raise ValueError('FROZEN_CONCRETE_EXACT_NATIVE_REPLAY_FAIL')
            points.append(p)
            pp=STATIC/'PATH_POINTS'/('P'+c['candidate_id'][:16]+'.npz');pp.parent.mkdir(exist_ok=True);np.savez_compressed(pp,X=p)
            checks.append(dict(candidate_id=c['candidate_id'],class_id=key,kind=c['kind'],cardinality=N,PASS=True,
                original_concrete_coupling=[[int(i),str(v)] for i,v in sorted(physical.items())],
                per_job_compact_coefficient=[[int(axes[list(axes)[i]]),str(v/N)] for i,v in sorted(physical.items())],
                concrete_point=record(pp),negative_price_reused_from_PR178=c['price'],pricing_calls=0,
                global_row_routing='all4944 original resource rows; other original global rows have zero direct coefficient and retained known/risk/CC4/grid variables and equations'))
        meta=dict(class_id=key,N=N,kernel_columns=snap.matrix.shape[1],offset=offset,points=points,units=units,reference_columns=cols,reference_units=original_units,candidates=cs)
        if cs:
            snap,B,pmeta=perspective(snap,B,points,N);meta.update(pmeta)
        meta['width']=snap.matrix.shape[1];metas[key]=meta
        coo=B.tocoo();global_parts.append(sp.csr_matrix((coo.data,([list(axes.values())[i] for i in coo.row],coo.col)),shape=(len(grows),snap.matrix.shape[1])))
        parts.append(snap.matrix);lbs.extend(snap.lower);ubs.extend(snap.upper);ss.extend(snap.senses);rhs.extend(snap.rhs)
        descriptors.extend(shift(u,offset) for u in units);offset+=snap.matrix.shape[1]
        print('COMPACT_BUILD',len(proofs),key[:12],snap.matrix.shape,len(cs),flush=True)
    local=sp.block_diag(parts,format='csr');A=sp.vstack((sp.hstack(global_parts,format='csr'),sp.hstack((sp.csr_matrix((local.shape[0],n)),local),format='csr')),format='csr')
    objectives=[base.objective('rho')]
    for name in ('migration_count','shift_magnitude','prestart_relocation'):
        terms=[];constant=Fraction(0)
        for u in descriptors:
            job=data[1][u['uid']];family='q' if name=='migration_count' else 'y'
            for k,e in u['v'][family].items():
                c=1 if name=='migration_count' else abs(k[1]-job.reference_start) if name=='shift_magnitude' else int(k[0]!=job.reference_site)
                if not c:continue
                if e[0]=='v':terms.append((int(e[1]),Fraction(c)))
                elif e[0]=='e':
                    constant+=Fraction(float(e[1]))*c;terms.extend((int(j),Fraction(float(a))*c) for j,a in zip(e[2],e[3]))
                else:constant+=Fraction(float(e[1]))*c
        for key,meta in metas.items():
            job=data[1][data[7]['classes'][key][0]]
            for j,candidate in zip(meta.get('compact_path_columns',()),meta['candidates']):
                o=option_from_json(candidate['option']);c=int(o.migrated) if name=='migration_count' else abs(o.start-job.reference_start) if name=='shift_magnitude' else int(o.initial_site!=job.reference_site)
                if c:terms.append((meta['offset']+j,Fraction(c)))
        objectives.append(Objective(name,tuple(terms),constant))
    compact=LinearSnapshot(A,np.r_[base.lower[:n],lbs],np.r_[base.upper[:n],ubs],np.r_[base.senses[list(grows)],ss],np.r_[base.rhs[list(grows)],rhs],np.full(A.shape[1],'C'),tuple(objectives)).require()
    rawrec=read(PR178/'M19/R0/NATIVE_RESULT.json')['raw_attributes'];raw={k:v for k,v in np.load(rawrec['path']).items()}
    prior=np.zeros(compact.matrix.shape[1]);prior[:n]=raw['X'][:n]
    lookup={}
    for u in old_desc['units']:
        key=next(k for k,us in initial_data[7]['classes'].items() if u['uid'] in us)
        for family,items in u['v'].items():
            for k,e in items.items():
                if e[0]=='v' or e[0]=='e':lookup[key,role(u),family,k]=lookup.get((key,role(u),family,k),0)+evaluate(e,raw['X'])
    assigned=set()
    for key,meta in metas.items():
        for u in meta['units']:
            for family,items in u['v'].items():
                for k,e in items.items():
                    if e[0]=='v':prior[meta['offset']+e[1]]=lookup.get((key,role(u),family,k),0.);assigned.add(meta['offset']+e[1])
        for u in meta['units']:
            for family,items in u['v'].items():
                for k,e in items.items():
                    if e[0]=='e' and len(e[2])==1 and meta['offset']+e[2][0] not in assigned:
                        j=meta['offset']+e[2][0];prior[j]=(lookup.get((key,role(u),family,k),0)-e[1])/e[3][0];assigned.add(j)
        if meta['candidates']:prior[meta['offset']+meta['residual_mass_column']]=meta['N']
    weights=np.load(initial['frozen_weights']['path'])['weights'];row_weights={};cursor=0
    for i in grows:row_weights[i]=Fraction(float(weights[cursor]));cursor+=2 if base.senses[i]=='=' else 1
    fullmaster=elastic_master(compact,grows,weights_by_row=row_weights);px=np.r_[prior,raw['X'][base.matrix.shape[1]:]]
    replay=primal_replay(fullmaster.snapshot,px)
    if not replay['PASS'] or str(phase_objective(fullmaster,px))!=read(PR178/'M19/R0/RAW_REPLAY.json')['Phi']:raise ValueError('PR178_PRIOR_INCLUSION_FAIL')
    np.savez_compressed(STATIC/'PR178_PRIOR_POINT.npz',X=px)
    nonzero=np.diff(compact.matrix.indptr[:len(grows)+1])>0
    selected=set(np.flatnonzero(nonzero & (abs(raw['Slack'][:len(grows)])<=1e-6)))|set(axes.values())
    residual=read(PR178/'M19/R0/RESIDUAL_ATTRIBUTION.json');selected.update(r['row'] for r in residual['top_rows'])
    atlas=np.load(read(PR178/'ROW_ATTRIBUTION_AUTHORITY.json')['atlas']['path']);upper=atlas['voltage_upper_rows'];names=list(atlas['node_names'])
    for time in (28,30,33):
        for node in ('83.2','mess_sta12_pcc.2'):selected.add(int(upper[(time-24)*len(names)+names.index(node)]))
    selected.update(range(len(grows),compact.matrix.shape[0]))
    with gzip.open(STATIC/'STATE.pkl.gz','wb') as f:pickle.dump(dict(compact=compact,reference=reference,reference_descriptor=rdesc,data=data,domains=domains,
        ledger=ledger,metas=metas,n=n,grows=grows,axes=axes,row_weights=row_weights,initial_rows=tuple(sorted(selected)),prior=px,atlas={k:v for k,v in atlas.items()}),f,pickle.HIGHEST_PROTOCOL)
    atomic(OUT/'FROZEN_BATCH_IDENTITY.json',dict(PASS=True,base_HEAD=BASE,PR178_batch=record(batch_path),candidate_ids=[c['candidate_id'] for c in batch],STAY=32,migration=32,pricing_calls=0,reselection=False))
    atomic(OUT/'EXACT_PROJECTION.json',dict(PASS=True,lane_sum_proofs=proofs,concrete_columns=checks,pure_vertices_equivalent_to_native_LP=False,
        retained_fractional_kernel=True,count_scaled_perspective_exact=True,compact_path_columns=64,residual_mass_columns=len(byclass),
        normalized_lambda='mu/N only in exact rational proof; no rounded reciprocal in compiled coefficients',
        bidirectional_proof='Every perspective point lifts to sum kernel z+sum(mu*p/N); inverse mu=0,k=N. Lane sum projection and equal rational split verified on all150 native class matrices, coefficients and boxes.',
        weights_changed=False,physics_or_tolerance_changes=False,domain_deletions=0,full_global_control_matrix_copied=True))
    atomic(OUT/'BUILD_VERIFICATION.json',dict(PASS=True,state=record(STATIC/'STATE.pkl.gz'),compact_rows=compact.matrix.shape[0],compact_cols=compact.matrix.shape[1],compact_nnz=compact.matrix.nnz,
        expanded_rows=reference.matrix.shape[0],expanded_cols=reference.matrix.shape[1],expanded_nnz=reference.matrix.nnz,
        initial_rows=len(selected),delayed_rows=compact.matrix.shape[0]-len(selected),compact_snapshot=compact.fingerprint(),
        preserved_point=record(STATIC/'PR178_PRIOR_POINT.npz'),prior_replay=replay,exact_Phi_before=str(phase_objective(fullmaster,px)),
        original_weights=initial['frozen_weights'],no_May19_optimize=True))
    atomic(OUT/'POLICY.json',POLICY)
    print('COMPACT_PREPARED',compact.matrix.shape,compact.matrix.nnz,len(selected),flush=True)

if __name__=='__main__':prepare()
