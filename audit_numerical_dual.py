"""No native model/solve: raw metrics and exact certificate experiments."""
from pathlib import Path
from fractions import Fraction as F
import json,hashlib,csv,time
import numpy as np
from scipy import sparse
from v42_m_stage_root.dual_authority import ARRAY_FIELDS,array_sha
from v42_degen.identity import inputs,digest
from v42_dw_root.partition import axes
from v42_m_stage_root.numerical_certificate import canonicalize,independent_csc,residual,support,down

ROOT=Path(__file__).resolve().parent
HISTORY=ROOT/'docs/v42_m1_rmp43_reproduction_20261006'
OUT=ROOT/'docs/v42_m1_numerical_dual_certificate_20261006'
RAW=HISTORY/'RMP43_REVALIDATION_BEFORE_GATE.npz'
EPS=1e-8
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(n,v):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/n).write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf8')
def load():
    meta=read(RAW.with_suffix('.json'))
    assert sha(RAW)==meta['snapshot_SHA']
    with np.load(RAW) as z:v={k:z[k] for k in z.files}
    assert {k:array_sha(v[k]) for k in ARRAY_FIELDS}==meta['identity']
    A=sparse.csr_matrix((v['data'],v['indices'],v['indptr']),shape=tuple(v['shape']))
    return A,v,meta
def maximum(a):return float(np.max(a,initial=0))
def metrics(A,v,meta,families):
    x,pi,rc,s=v['point'],v['pi'],v['rc'],v['sense']
    sign=np.where(s=='<',np.maximum(pi,0),np.where(s=='>',np.maximum(-pi,0),0))
    row_res=A@x-v['rhs'];vio=np.where(s=='=',abs(row_res),np.where(s=='<',np.maximum(row_res,0),np.maximum(-row_res,0)))
    station=v['objective']-A.T@pi-rc
    finite_lo=np.isfinite(v['lower'])&(abs(v['lower'])<1e90)
    finite_hi=np.isfinite(v['upper'])&(abs(v['upper'])<1e90)
    free=~finite_lo&~finite_hi
    # Reconstruct RC cone constraints using native VBasis, not tolerance-based X rounding.
    vb=v['raw_VBasis'];rc_vio=np.where(vb==-1,np.maximum(-rc,0),np.where(vb==-2,np.maximum(rc,0),abs(rc)))
    rc_vio[(finite_lo&finite_hi)&(v['lower']==v['upper'])]=0
    # Complementarity includes original inequality slacks and shifted finite bounds.
    bound_comp=np.zeros_like(rc)
    lb=finite_lo&(vb==-1);ub=finite_hi&(vb==-2)
    bound_comp[lb]=abs(rc[lb]*(x[lb]-v['lower'][lb]))
    bound_comp[ub]=abs(rc[ub]*(v['upper'][ub]-x[ub]))
    bound_comp[(vb==0)|(vb==-3)]=abs(rc[(vb==0)|(vb==-3)]*x[(vb==0)|(vb==-3)])
    row_comp=abs(pi*row_res);row_comp[s=='=']=0
    support=np.where(rc>=0,v['lower'],v['upper']);mask=rc!=0
    unsupported=np.flatnonzero(mask&(~np.isfinite(support)|(abs(support)>=1e90)))
    terms=np.zeros_like(rc);terms[mask]=rc[mask]*support[mask]
    primal=float(v['objective']@x+v['constant'])
    dual=float(pi@v['rhs']+v['constant']+terms.sum()) if not len(unsupported) else None
    family={}
    for f in sorted(set(families)):
        ix=np.flatnonzero(families==f)
        k=int(ix[np.argmax(sign[ix])]);family[str(f)]=dict(rows=len(ix),maximum_sign_violation=maximum(sign[ix]),
            violating_rows=int(np.count_nonzero(sign[ix])),largest_native_row_name=str(v['row_names'][k]),
            sign_violation_over_OptimalityTol=maximum(sign[ix])/meta['parameters']['OptimalityTol'])
    bad=[dict(index=int(j),name=str(v['names'][j]),RC=float(rc[j]),absolute_RC=abs(float(rc[j])),
              RC_over_OptimalityTol=abs(float(rc[j]))/meta['parameters']['OptimalityTol'],
              lower=str(v['lower'][j]),upper=str(v['upper'][j]),VBasis=int(vb[j]),free=bool(free[j]),
              lower_only=bool(finite_lo[j] and not finite_hi[j])) for j in unsupported]
    values=dict(DualVio_reconstructed=max(maximum(sign),maximum(rc_vio)),
        DualResidual_reconstructed=maximum(abs(station)),ComplVio_reconstructed=max(maximum(bound_comp),maximum(row_comp)),
        primal_row_violation=maximum(vio),primal_equality_residual=maximum(abs(row_res[s=='='])),
        primal_bound_violation=max(maximum(v['lower']-x),maximum(x-v['upper'])),
        maximum_sign_violation=maximum(sign),maximum_unsupported_RC=maximum(abs(rc[unsupported])))
    native=meta.get('native_quality_before_gate',{})
    native_ok=all(not isinstance(native.get(k), (int,float)) or native[k]<=EPS for k in ('DualVio','DualResidual','ComplVio'))
    candidate=bool(native_ok and values['DualVio_reconstructed']<=EPS and values['DualResidual_reconstructed']<=EPS
        and values['ComplVio_reconstructed']<=EPS and values['primal_row_violation']<=1e-6
        and values['primal_bound_violation']<=EPS and np.isfinite(pi).all() and np.isfinite(rc).all())
    r=dict(raw_snapshot_SHA=sha(RAW),native_solve_calls=0,OptimalityTol=meta['parameters']['OptimalityTol'],
        values=values,values_over_OptimalityTol={k:w/meta['parameters']['OptimalityTol'] for k,w in values.items()},
        native_quality_attributes={k:native.get(k,'NOT_SAVED_IN_HISTORICAL_SNAPSHOT') for k in ('DualVio','DualResidual','ComplVio')},
        quality_source='Independent unscaled reconstruction from raw X/Pi/RC/VBasis/CSR; not invented native attribute reads',
        Gurobi_quality_definition_source='https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/quality.html',
        max_sign_violation_by_family=family,infinite_support_variables=bad,free_variables_total=int(free.sum()),
        primal_objective=primal,raw_dual_objective_including_original_bound_terms=dual,
        raw_primal_dual_objective_difference=abs(primal-dual) if dual is not None else None,
        raw_dual_unavailable_reason='Seven nonzero RCs select infinite upper supports; raw Pi also has an invalid row sign' if len(unsupported) else None,
        floating_residual_candidate_within_existing_authority=candidate,
        EXACT_DUAL_AUTHORITY_PASS=False,small_residual_not_ignored=True,canonicalization_not_yet_acceptance=True)
    write('RAW_NUMERICAL_AUDIT.json',r);return r
def run_metrics():
    A,v,meta=load();_,_,B,e,identity,freeze=inputs();owner,row_owner=axes()
    families=np.array([str(n).split('[',1)[0] for n in e['row_names'][row_owner<0]]+['DW_convexity']*4)
    r=metrics(A,v,meta,families)
    print(json.dumps(dict(values=r['values'],floating_candidate=r['floating_residual_candidate_within_existing_authority'],native_solve_calls=0)),flush=True)
    return A,v,meta,B,e,owner,row_owner,r
def rational_artifact(name,pi):
    rows=sorted(i for i,p in pi.items() if p)
    np.savez_compressed(OUT/name,rows=np.array(rows,dtype=np.int64),
        numerators=np.array([str(pi[i].numerator) for i in rows]),denominators=np.array([str(pi[i].denominator) for i in rows]))
def fraction_record(q):return dict(numerator=str(q.numerator),denominator=str(q.denominator),float_diagnostic=float(q))
def attempt():
    start=time.perf_counter();A,v,meta,B,e,owner,row_owner,raw=run_metrics()
    write('AUDIT_PREREGISTRATION.json',dict(native_solve_calls=0,raw_snapshot_SHA=sha(RAW),
        policy='User-authorized numerical boundary canonicalization only with existing residual authority; exact original-equality free stationarity and convexity dual correction, then independent rational support.',
        EPS=EPS,row_EPS=1e-6,no_primal_or_model_change=True,fullscale_polish_maximum_calls_if_FAIL=1,
        root_CG=False,early_BAP=False,BAP7200=False,P2=False))
    if not raw['floating_residual_candidate_within_existing_authority']:
        write('OFFLINE_CERTIFICATE_RESULT.json',dict(PASS=False,EXACT_DUAL_AUTHORITY_PASS=False,reason='RAW_RESIDUAL_OUTSIDE_AUTHORITY',native_solve_calls=0));return
    source=ROOT/'docs/v42_m1_dw_certified_dual_bound/PROVEN_COORDINATE_ENCLOSURES.npz'
    proof=read(source.with_name('COORDINATE_ENCLOSURE_PROOF.json'))
    assert proof['PASS'] and sha(source)==proof['artifact_SHA']
    rows=np.flatnonzero(row_owner<0);cols=np.flatnonzero(owner<0)
    original=B[rows][:,cols];saved=A[:len(rows),:len(cols)].tocsr()
    assert all(np.array_equal(getattr(original,k),getattr(saved,k)) for k in ('indptr','indices','data'))
    assert np.array_equal(v['rhs'][:len(rows)],e['rhs'][rows]) and np.array_equal(v['sense'][:len(rows)],e['sense'][rows])
    assert all(np.array_equal(v[k][:len(cols)],e[k][cols]) for k in ('objective','lower','upper','names'))
    assert v['row_names'][-4:].tolist()==['DW_convexity[MESS01]','DW_convexity[MESS02]','DW_convexity[MESS03]','DW_convexity[MESS04]']
    rr={int(r):i for i,r in enumerate(rows)};cc={int(c):j for j,c in enumerate(cols)}
    with np.load(source) as z:pairs=z['binding_row_column']
    assert all(int(i) in rr and int(j) in cc for i,j in pairs)
    pivots=[(rr[int(i)],cc[int(j)]) for i,j in pairs]
    try:
        print('EXACT_RATIONAL_CANONICALIZATION_STARTED',flush=True)
        pi,q,terms,p=canonicalize(A,v,pivots,range(len(rows),len(rows)+4),True,EPS)
        rational_artifact('CANONICAL_RATIONAL_DUAL.npz',pi)
        write('CANONICALIZATION_TRACE.json',dict(raw_snapshot_SHA=sha(RAW),raw_preserved=True,
            sign_boundary_changes=[dict(row=i,raw_value=fraction_record(x),canonical_value=0) for i,x in p['projected']],
            equality_repairs=[dict(row=i,column=j,change=fraction_record(x)) for i,j,x in p['equality_repairs']],
            exact_retained_convexity_offsets=[dict(row=i,delta=fraction_record(x)) for i,x in p['convexity_offsets']],
            original_pivot_source_SHA=sha(source),pivot_rows=len(pivots),native_bound_or_matrix_changes=0,
            maximum_dual_change=float(p['maximum_change']),maximum_change_under_existing_EPS=float(p['maximum_change'])<=EPS))
        print('INDEPENDENT_CSC_RATIONAL_AUDIT_STARTED',flush=True)
        qi,ti,Li,free=independent_csc(A,v,pi)
        assert all(q.get(j,F(0))==r for j,r in qi.items()) and ti==terms and Li==p['exact_value']
        cp=read(ROOT/'docs/v42_m_stage_exact_completion/DW_CHECKPOINT_LATEST.json')
        assert len(cp['pool'])==1841
        offset=len(cols);minimum=min(qi[j] for j in range(offset,A.shape[1]))
        with (OUT/'CANONICAL_1841_RC_EXACT.csv').open('w',encoding='utf8',newline='') as f:
            w=csv.writer(f);w.writerow(['column','MESS','column_SHA','native_RC_raw','canonical_RC_numerator','canonical_RC_denominator','canonical_RC_float','exact_dual_feasible'])
            for k,h in enumerate(cp['pool']):
                r=qi[offset+k];w.writerow([k,h['MESS'],h['column_SHA'],v['rc'][offset+k],r.numerator,r.denominator,float(r),r>=0])
        # Save every independently recomputed RC and bound support term, not only the seven defects.
        np.savez_compressed(OUT/'RECOMPUTED_RC_BOUND_DUAL_TERMS.npz',
            rc_numerators=np.array([str(qi[j].numerator) for j in range(A.shape[1])]),
            rc_denominators=np.array([str(qi[j].denominator) for j in range(A.shape[1])]),
            lower_dual_numerators=np.array([str(max(qi[j],F(0)).numerator) for j in range(A.shape[1])]),
            lower_dual_denominators=np.array([str(max(qi[j],F(0)).denominator) for j in range(A.shape[1])]),
            upper_dual_numerators=np.array([str(min(qi[j],F(0)).numerator) for j in range(A.shape[1])]),
            upper_dual_denominators=np.array([str(min(qi[j],F(0)).denominator) for j in range(A.shape[1])]),
            bound_term_numerators=np.array([str(ti.get(j,F(0)).numerator) for j in range(A.shape[1])]),
            bound_term_denominators=np.array([str(ti.get(j,F(0)).denominator) for j in range(A.shape[1])]))
        primal=F(float(v['constant']))+sum((F(float(c))*F(float(x)) for c,x in zip(v['objective'],v['point']) if c),F(0))
        difference=primal-Li;safe=down(Li-F(EPS))
        max_RC_change=max(abs(qi[j]-F(float(v['rc'][j]))) for j in range(A.shape[1]))
        rmppass=minimum>=0 and free==len(cols)-1 and abs(difference)<=F(EPS) and F(safe)<=Li and max_RC_change<=F(EPS)
        write('RMP_RATIONAL_SUPPORT_CERTIFICATE.json',dict(PASS=rmppass,scope='Only the current 1841-column RMP; not full-domain pricing closure or an integer UB',
            independent_CSR_CSC_identity_PASS=True,original_bounds_only=True,infinite_support_rejected=True,
            all_original_free_stationarity_exact_zero=free,all_83058_RC_recomputed=True,
            retained_1841_exact_dual_feasibility_PASS=minimum>=0,minimum_retained_exact_RC=float(minimum),
            primal_objective=fraction_record(primal),dual_objective=fraction_record(Li),
            primal_dual_difference=fraction_record(difference),maximum_native_RC_to_canonical_change=float(max_RC_change),
            existing_numerical_authority=EPS,safe_rational_LB=safe,fixed_safety_subtracted=EPS,
            numerical_comparison_not_the_weak_duality_proof=True,canonical_dual_SHA=sha(OUT/'CANONICAL_RATIONAL_DUAL.npz'),native_calls=0))
        # A fresh same-canonical-dual full-domain lower certificate uses analytic
        # ORIGINAL local interval support, not stale native pricing bounds.
        print('FULL_DOMAIN_ORIGINAL_BOUND_SUPPORT_STARTED',flush=True)
        G=B[rows];gp={i:p for i,p in pi.items() if i<len(rows)}
        qfull=residual(G,e['objective'],gp)
        global_terms,global_support=support({int(j):qfull.get(int(j),F(0)) for j in cols},e['lower'],e['upper'])
        global_rhs=F(float(e['constant']))+sum((p*F(float(e['rhs'][rows[i]])) for i,p in gp.items()),F(0))
        global_value=global_rhs+global_support;beta=[];delta=[];local=[]
        for m in range(4):
            mm=np.flatnonzero(owner==m)
            tt,value=support({int(j):qfull.get(int(j),F(0)) for j in mm},e['lower'],e['upper'])
            alpha=pi.get(len(rows)+m,F(0));b=value-alpha
            beta.append(b);delta.append(min(F(0),b-F(EPS)));local.append(value)
        corrected=global_value+sum((pi.get(len(rows)+m,F(0))+delta[m] for m in range(4)),F(0))
        # Independent full original-coordinate CSC support, same canonical Pi.
        C=G.tocsc();independent=[]
        for j in range(G.shape[1]):
            a,b=C.indptr[j:j+2]
            r=F(float(e['objective'][j]))-sum((gp[int(i)]*F(float(w)) for i,w in zip(C.indices[a:b],C.data[a:b]) if int(i) in gp),F(0))
            assert r==qfull.get(j,F(0))
            independent.append(r)
        _,whole_support=support(dict(enumerate(independent)),e['lower'],e['upper'])
        assert global_value+sum(local,F(0))==global_rhs+whole_support and corrected<=global_rhs+whole_support
        fullpass=corrected<=primal and all(pi.get(len(rows)+m,F(0))+delta[m]<=local[m] for m in range(4))
        write('FULL_DOMAIN_CORRECTED_LB_CERTIFICATE.json',dict(PASS=fullpass,corrected_exact=fraction_record(corrected),safe_corrected_LB=down(corrected),
            aggregate_with_inherited_valid_floor=max(.5687115725336208,down(corrected)),
            scope='All original local MESS domains are subsets of their ORIGINAL finite coordinate bounds; interval support is a rigorous full-domain bound, not an optimal pricing claim',
            beta_lower_bounds=[fraction_record(b) for b in beta],delta=[fraction_record(d) for d in delta],
            global_support_value=fraction_record(global_value),independent_full_original_CSC_PASS=True,
            canonical_dual_SHA=sha(OUT/'CANONICAL_RATIONAL_DUAL.npz'),stale_pricing_bound_used=False,full_domain_native_pricing_calls=0,
            root_CG_converged=False,integer_UB=None,not_a_materiality_reproof=True))
        result=dict(PASS=bool(rmppass and fullpass),EXACT_DUAL_AUTHORITY_PASS=bool(rmppass and fullpass),
            raw_native_dual_remains_strict_sign_FAIL=True,user_authorized_canonical_rational_witness=True,
            native_solve_calls=0,polish_required=not bool(rmppass and fullpass),root_CG=False,early_BAP=False,BAP7200=False,P2=False,
            raw_snapshot_SHA=sha(RAW),canonical_dual_SHA=sha(OUT/'CANONICAL_RATIONAL_DUAL.npz'),
            primal_dual_difference=float(difference),maximum_RC_change=float(max_RC_change),audit_wall_seconds=time.perf_counter()-start)
        write('OFFLINE_CERTIFICATE_RESULT.json',result);print(json.dumps(result),flush=True)
    except (ValueError,AssertionError) as ex:
        write('OFFLINE_CERTIFICATE_RESULT.json',dict(PASS=False,EXACT_DUAL_AUTHORITY_PASS=False,reason=repr(ex),native_solve_calls=0,polish_required=True))
        print(json.dumps(read(OUT/'OFFLINE_CERTIFICATE_RESULT.json')),flush=True)
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--certificate',action='store_true');parser.add_argument('--raw',type=Path);parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.raw:RAW=args.raw.resolve()
    if args.out:OUT=args.out.resolve()
    attempt() if args.certificate else run_metrics()
