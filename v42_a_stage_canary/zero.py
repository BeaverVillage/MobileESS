"""The same qualified full relevant zero-migration projection for each day."""
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v42_a_stage_phase1.runner import load_cache
from v42_a_stage_compact_rowgen.prepare import shift
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective,integer_objective_proof
from v42_a_stage_lexfull.projection import restrict
from v42_pr134_b1.common import read,atomic
from .policy import OUT

def build(original,typed,day):
    roster=read(OUT/day/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records'];n=original['n'];G=len(original['grows']);axes=original['axes']
    if {r['class_id'] for r in roster}!=set(original['data'][7]['classes']):raise ValueError('COMPLETE_CLASS_COVERAGE_REQUIRED')
    parts=[];global_parts=[typed.matrix[:G,:n].tocsr()];units=[];offset=n;lower=[];upper=[];types=[];senses=[];rhs=[];receipts=[];graphs=dict(original['data'][5])
    terms={name:[] for name in ('migration_count','shift_magnitude','prestart_relocation')};constants={name:Fraction(0) for name in terms}
    for i,r in enumerate(sorted(roster,key=lambda r:r['class_id'])):
        key=r['class_id'];members=original['data'][7]['classes'][key];uid=members[0];cache=load_cache(r)
        s,B,c,u,model,receipt=restrict(original['data'],key,cache,axes)
        if len(members)>1:
            hist=next((v for v in u if v['stay_count']),None)
            if hist is not None and set(hist['v']['y'])!={(site,start) for start,site in original['domains'][uid].stays}:raise ValueError('FULL_INDEPENDENT_STAY_DOMAIN_COVERAGE_FAIL')
        coo=B.tocoo();global_parts.append(sp.csr_matrix((coo.data,([list(axes.values())[j] for j in coo.row],coo.col)),shape=(G,s.matrix.shape[1])))
        parts.append(s.matrix);lower.extend(s.lower);upper.extend(s.upper);types.extend(s.vtypes);senses.extend(s.senses);rhs.extend(s.rhs)
        for name in terms:
            o=s.objective(name);terms[name].extend((offset+j,v) for j,v in o.coefficients().items());constants[name]+=Fraction(o.constant)
        units.extend(dict(shift(v,offset),members=members) for v in u);offset+=s.matrix.shape[1]
        for member in members:graphs[member]=cache['graph']
        receipts.append(receipt);print('CANARY_ZERO_CLASS',day,i+1,len(roster),flush=True)
    local=sp.block_diag(parts,format='csr');A=sp.vstack((sp.hstack(global_parts,format='csr'),sp.hstack((sp.csr_matrix((local.shape[0],n)),local),format='csr')),format='csr')
    snap=LinearSnapshot(A,np.r_[typed.lower[:n],lower],np.r_[typed.upper[:n],upper],np.r_[typed.senses[:G],senses],np.r_[typed.rhs[:G],rhs],
        np.r_[typed.vtypes[:n],types],(typed.objective('rho'),)+tuple(Objective(name,tuple(terms[name]),constants[name]) for name in terms)).require()
    for name in terms:integer_objective_proof(snap,name)
    if snap.objective('migration_count').coefficients() or snap.objective('migration_count').constant:raise ValueError('ZERO_QUERY_MIGRATION_NOT_IDENTICALLY_ZERO')
    state=dict(original,data=(*original['data'][:5],graphs,*original['data'][6:]),reference=snap,reference_descriptor=dict(units=units))
    atomic(OUT/day/'FULL_ZERO_DOMAIN_VERIFICATION.json',dict(PASS=True,full_classes=len(roster),class_proofs=receipts,
        full_STAY=sum(r['full_physical_STAY'] for r in roster),full_migration=sum(r['full_physical_migration'] for r in roster),
        same_original_integer_zero_migration_projection=True,temporary_zero_query_not_yet_global_lock=True,
        rows=A.shape[0],cols=A.shape[1],nnz=A.nnz,snapshot_sha256=snap.fingerprint(),no_permanent_candidate_deletion=True))
    return state,snap
