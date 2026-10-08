"""Full relevant zero-migration domain qualification, without optimization."""
import gzip,pickle
from fractions import Fraction
from time import perf_counter
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_phase1.runner import load_cache
from v42_a_stage_compact_rowgen.prepare import shift
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective,integer_objective_proof
from .projection import restrict,objectives
from .policy import ROOT,OUT,STATIC

def prepare():
    if (OUT/'LEX_FULL_BUILD_VERIFICATION.json').exists():raise PermissionError('ZERO_MIG_FULL_BUILD_ALREADY_EXISTS')
    if not read(OUT/'P2_MIGRATION_PROBE_RESULT.json')['accepted']:raise PermissionError('GLOBAL_MIGRATION_ZERO_REQUIRED')
    started=perf_counter();build=read(OUT/'INTEGER_BUILD_VERIFICATION.json')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    original=p['state'];base=p['typed'];n=original['n'];G=len(original['grows']);axes=original['axes']
    roster=read(ROOT/'docs/v42_a_stage_phase1_pricing_20261007/BLOCK_PRICING_ORACLE_VERIFICATION.json')['records']
    if {r['class_id'] for r in roster}!=set(original['data'][7]['classes']):raise ValueError('FULL_CLASS_COVERAGE_REQUIRED')
    graphs=dict(original['data'][5]);blocks=[];global_parts=[base.matrix[:G,:n].tocsr()];couplings=[];units=[];models={};receipts=[];offset=n
    lower=[];upper=[];types=[];senses=[];rhs=[];terms={name:[] for name in ('migration_count','shift_magnitude','prestart_relocation')};constants={name:Fraction(0) for name in terms}
    for i,r in enumerate(sorted(roster,key=lambda r:r['class_id'])):
        key=r['class_id'];members=original['data'][7]['classes'][key];uid=members[0];cache=load_cache(r)
        s,B,c,u,model,receipt=restrict(original['data'],key,cache,axes)
        if len(members)>1:
            hist=next((v for v in u if v['stay_count']),None)
            if hist is not None and set(hist['v']['y'])!={(site,start) for start,site in original['domains'][uid].stays}:raise ValueError('INDEPENDENT_FULL_STAY_DOMAIN_COVERAGE_FAIL')
        coo=B.tocoo();global_parts.append(sp.csr_matrix((coo.data,([list(axes.values())[j] for j in coo.row],coo.col)),shape=(G,s.matrix.shape[1])))
        blocks.append(s.matrix);lower.extend(s.lower);upper.extend(s.upper);types.extend(s.vtypes);senses.extend(s.senses);rhs.extend(s.rhs)
        for name in terms:
            o=s.objective(name);terms[name].extend((offset+j,v) for j,v in o.coefficients().items());constants[name]+=Fraction(o.constant)
        for v in u:units.append(dict(shift(v,offset),members=members))
        models[key]=dict(offset=offset,width=s.matrix.shape[1],**model);offset+=s.matrix.shape[1]
        for member in members:graphs[member]=cache['graph']
        receipts.append(dict(**receipt,physical_STAY=r['full_physical_STAY'],physical_migration_excluded_only_by_certified_zero_lock=r['full_physical_migration']))
        print('ZERO_MIG_FULL_CLASS',i+1,len(roster),key[:12],s.matrix.shape,flush=True)
    local=sp.block_diag(blocks,format='csr');A=sp.vstack((sp.hstack(global_parts,format='csr'),sp.hstack((sp.csr_matrix((local.shape[0],n)),local),format='csr')),format='csr')
    objs=(base.objective('rho'),)+tuple(Objective(name,tuple(terms[name]),constants[name]) for name in terms)
    snap=LinearSnapshot(A,np.r_[base.lower[:n],lower],np.r_[base.upper[:n],upper],np.r_[base.senses[:G],senses],np.r_[base.rhs[:G],rhs],np.r_[base.vtypes[:n],types],objs).require()
    if snap.objective('migration_count').coefficients() or snap.objective('migration_count').constant:raise ValueError('GLOBAL_MIGRATION_NOT_IDENTICALLY_ZERO')
    for name in terms:integer_objective_proof(snap,name)
    data=(*original['data'][:5],graphs,*original['data'][6:]);state=dict(original,data=data,reference=snap,reference_descriptor=dict(units=units))
    path=STATIC/'FULL_ZERO_MIG_INTEGER_STATE.pkl.gz'
    with gzip.open(path,'xb') as f:pickle.dump(dict(state=state,snapshot=snap,local_lifts=models),f,protocol=5)
    receipt=dict(PASS=True,full_scientific_relevant_domain=True,all_classes=len(roster),full_STAY=sum(r['full_physical_STAY'] for r in roster),
        full_migration=sum(r['full_physical_migration'] for r in roster),migration_candidates_removed_permanently=False,
        all_global_original_rows=G,all_relevant_original_native_rows_retained_or_exact_zero_projected=True,
        row_closure_analytic_all_rows_present=True,column_closure_analytic_full_relevant_pool=True,
        rows=A.shape[0],cols=A.shape[1],nnz=A.nnz,integer_columns=int(np.count_nonzero(snap.vtypes!='C')),
        snapshot_sha256=snap.fingerprint(),class_proofs=receipts,state=record(path),build_seconds=perf_counter()-started)
    atomic(OUT/'LEX_FULL_BUILD_VERIFICATION.json',receipt)
    atomic(OUT/'LEX_FULL_ENTRY_GATE.json',dict(PASS=True,build=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),
        migration_zero_certificate=read(OUT/'P2_MIGRATION_PROBE_RESULT.json')['certificate'],rho_lock_epsilon=1e-7,
        integer_locks_exact=True,integer_objectives_integral=True,branch_children_both_preserved=True))
    print('FULL_ZERO_MIG_BUILD',receipt['rows'],receipt['cols'],receipt['nnz'],receipt['build_seconds'],flush=True)
if __name__=='__main__':prepare()
