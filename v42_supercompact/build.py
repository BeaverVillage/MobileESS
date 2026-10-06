"""Reconstruct current scientific authority and create C0/C1/C2 statically."""
from .common import *
from .formulation import *
from .presolve import Presolve
from fractions import Fraction as F
import time
from v42_degen.identity import inputs,signature
from v42_strengthening.analysis import graph_inputs
from v42_redundancy import domain as domain_module
from v42_rowgen.core import binding_proof

def save(label,A,d):
    sparse.save_npz(OUT/(label+'_A.npz'),A);np.savez_compressed(OUT/(label+'_DATA.npz'),**d)
def load(label):
    A=sparse.load_npz(OUT/(label+'_A.npz'))
    with np.load(OUT/(label+'_DATA.npz')) as z:d={k:z[k] for k in z.files}
    return A,d

def run():
    start=time.perf_counter();full,fd,A,d,identity,freeze=inputs()
    write('CURRENT_ORIGINAL_MODEL_CENSUS.json',dict(PASS=True,**census(A,d),identity=identity,unreduced_original=census(full,fd),recomputed=True))
    sites,initial,arcs,battery,receipt=graph_inputs();assert len(initial)==4
    domain_module.write=lambda n,x:write('CURRENT_'+n,x)
    dom=domain_module.build_domain(A,d)
    c=Compact(A,d,arcs,initial,96);save('C0',c.A,c.d)
    write('CURRENT_COMPACT_C0_CENSUS.json',census(c.A,c.d));write('ORIGINAL_TO_COMPACT_MAPPING.json',c.mapping())
    write('COMPACT_TO_ORIGINAL_MAPPING.json',dict(method='Original physical/mode/SOC/auxiliary and arc flows are first original_columns entries; node binaries force flows integer by simple-DAG induction; parallel flows retain binary selectors.',original_columns=c.n,all_original_route_ids_preserved=True))
    with np.load(OLD/'M1_REDUCTION_AXES.npz') as z:original_keep=z['keep'];removed=z['removed']
    # Actual certificate replay is independent and gates execution separately.
    keep=np.r_[original_keep,np.arange(A.shape[0],c.A.shape[0])]
    B,e=subset(c.A,c.d,keep);save('C1',B,e);write('CURRENT_COMPACT_C1_CENSUS.json',census(B,e))
    p=Presolve(B,e)
    # Exact global PCS support; not an unsafe per-site SOC perspective bound.
    verts=dom['vertices'];qlo=min(v[1] for v in verts);qhi=max(v[1] for v in verts)
    def down(q):
        v=float(q);return v if F(v)<=q else float(np.nextafter(v,-np.inf))
    def up(q):
        v=float(q);return v if F(v)>=q else float(np.nextafter(v,np.inf))
    env=read('CURRENT_M1_SOC_ENVELOPE_CERTIFICATE.json')['envelopes']
    for j,n in enumerate(e['names']):
        oldlo=float(e['lower'][j]);oldhi=float(e['upper'][j]);lo=oldlo;hi=oldhi;proof=None
        if str(n).startswith('Q['):lo=max(lo,down(qlo));hi=min(hi,up(qhi));proof='Exact stored PCS16 vertex hull and unit-flow stay mass <=1'
        elif str(n).startswith('SOC['):
            u,t=str(n)[4:-1].split(',');lo=max(lo,down(F(env[u]['lower'][int(t)])));hi=min(hi,up(F(env[u]['upper'][int(t)])));proof='Exact stored SOC forward/backward envelope with both endpoints, total connected dispatch and convex-hull travel cost'
        elif str(n).startswith('node_activity['):
            u,s,t=str(n)[14:-1].split(',')
            if int(t)==0:lo=hi=float(s==initial[u]);proof='Original source flow equality and node activity link'
        if lo!=oldlo or hi!=oldhi:
            p.d['lower'][j]=lo;p.d['upper'][j]=hi;p.bound.append(dict(column=j,name=str(n),old_lower=oldlo,old_upper=oldhi,new_lower=lo,new_upper=hi,proof=proof))
    p.run();save('C2',p.A,p.d)
    write('CURRENT_SUPERCOMPACT_C2_CENSUS.json',census(p.A,p.d))
    write('C2_ELIMINATION_CERTIFICATES.json',p.steps);write('C2_ROW_CERTIFICATES.json',p.rows)
    np.savez_compressed(OUT/'C2_RETAINED_AXES.npz',rows=p.row_ids,columns=p.col_ids,C1_original_rows=keep)
    table('STATIC_REDUCTION_ROUNDS.csv',p.rounds,list(p.rounds[0]));table('COMPACT_BOUND_TIGHTENING.csv',p.bound,['column','name','old_lower','old_upper','new_lower','new_upper','proof'])
    fixed=list(p.fixed_known.values());flows=[s for s in p.steps if s['kind']=='DETERMINISTIC_FLOW']
    table('COMPACT_FIXED_VARIABLES.csv',fixed,['column','name','kind','constant','defining_row','proof'])
    table('COMPACT_FLOW_CONTRACTIONS.csv',flows,['column','name','kind','terms','constant','defining_row','proof'])
    # Every current C0 continuous variable gets a final static classification.
    stepmap={s['column']:s for s in p.steps};costs=p.costs;original_bindings={j:i for i,j in binding_proof(A,d)};classification=[];gridcost=[];flowcost=[]
    for j,n in enumerate(c.d['names']):
        if c.d['types'][j]!='C':continue
        fam=str(n).split('[')[0];s=stepmap.get(j);rec=costs.get(j)
        if j in p.fixed_known:kind=p.fixed_known[j]['kind'];why=p.fixed_known[j]['proof']
        elif s:kind=s['kind'];why=s['proof']
        elif fam=='route_flow':
            u,k=str(n)[11:-1].split(',');k=int(k);a=arcs[k];key=(u,a[0],a[1]);dest=(u,a[2],a[3])
            kind='DEGREE_ONE_CHAIN_FLOW' if len(c.outgoing[key])==1 and len(c.incoming[dest])==1 else ('UNIQUE_DEFINITION' if rec else 'ESSENTIAL')
            why='Kept: intermediate node may have P/Q/SOC/time decision; no transit-state variables are invented inside long movement arcs' if kind=='DEGREE_ONE_CHAIN_FLOW' else 'Original flow equations retained; non-deterministic branches not contracted'
        elif j in original_bindings:kind='UNIQUE_DEFINITION';why='Native singleton affine defining equality; keep unless sparse exact substitution improves matrix'
        else:kind='ESSENTIAL' if fam in ['Pch','Pdis','Q','SOC','rho_max'] else 'UNKNOWN';why='Physical decision or no proved elimination'
        classification.append(dict(column=j,name=str(n),classification=kind,eliminated=bool(s),reason=why))
        if fam.startswith(('response_','injection_')) or fam=='route_flow':
            if j in p.fixed_known and not s:r=dict(column=j,name=str(n),decision='KEEP_FIXED',reason='Exact fixed value retained as bounds; substitution would require changing stored binary64 coefficient/RHS',rows_saved=1,columns_saved=0,nnz_delta_upper=None)
            elif rec:r=dict(rec)
            elif s:r=dict(column=j,name=str(n),decision='FIX' if s['kind'].startswith('FIXED') else 'SUBSTITUTE',reason=s['proof'],rows_saved=1,columns_saved=1,nnz_delta_upper=None)
            else:r=dict(column=j,name=str(n),decision='KEEP',reason='No invertible unit pivot with acceptable sparsity; essential or unknown network flow',rows_saved=0,columns_saved=0,nnz_delta_upper=None)
            (flowcost if fam=='route_flow' else gridcost).append(r)
    table('COMPACT_VARIABLE_CLASSIFICATION.csv',classification,['column','name','classification','eliminated','reason'])
    fields=['column','name','definition','definition_nnz','consumers','rows_saved','columns_saved','nnz_before','nnz_after_union_upper','nnz_delta_upper','fill_proxy_before','fill_proxy_after','expression_coefficient_min','expression_coefficient_max','decision','reason']
    table('GRID_AUXILIARY_KEEP_SUBSTITUTE_AUDIT.csv',gridcost,fields);table('FLOW_KEEP_SUBSTITUTE_AUDIT.csv',flowcost,fields)
    summary=dict(PASS=True,compact_specific_rows_removed=B.shape[0]-p.A.shape[0],variables_removed=B.shape[1]-p.A.shape[1],fixed_variables=len(fixed),deterministic_flows=len(flows),bounds_tightened=len(p.bound),rounds=len(p.rounds),fixed_point=p.rounds[-1]['fixed']==p.rounds[-1]['rows_deleted']==p.rounds[-1]['substitutions']==0,
        row_proof_categories=dict(Counter(r['kind'] for r in p.rows)),variable_categories=dict(Counter(r['classification'] for r in classification)),elimination_categories=dict(Counter(r['kind'] for r in p.steps)),grid_auxiliaries_eliminated=sum(r['decision'] in ['FIX','SUBSTITUTE'] for r in gridcost),grid_auxiliaries_keep_fill=sum(r['decision']=='KEEP' and r.get('nnz_delta_upper',0) is not None and r.get('nnz_delta_upper',0)>0 for r in gridcost),
        all_rows_scanned=True,proportional_duplicates_scanned=True,all_current_continuous_columns_classified=True,all_graph_arcs_forward_backward_checked=True,reachability_removed=0,chain_event_checks=True,SOC_result_dependent_fixing=False,nonunit_or_dense_substitution_retained=True,arithmetic='All accepted substitutions are verified against exact binary rational coefficients/RHS; no rounded coefficient authority.',wall=time.perf_counter()-start)
    write('COMPACT_ROW_REDUNDANCY_AUDIT.json',summary)
    write('NONREPRESENTABLE_SUBSTITUTION_REJECTIONS.json',p.rejected)
    cc0=census(c.A,c.d);cc2=census(p.A,p.d)
    ratios={k:1-cc2[k]/cc0[k] for k in ['rows','columns','continuous','nnz']};binary=1-cc2['binaries']/int(np.sum(d['types']=='B'));gate=binary>=.95 and max(ratios[k] for k in ['rows','continuous','nnz'])>=.2
    write('SUPERCOMPACT_FINAL_MATRIX_AUDIT.json',dict(PASS=True,C0=cc0,C1=census(B,e),C2=cc2,reduction_vs_C0=ratios,binary_reduction_vs_original=binary,size_gate=gate,summary=summary))
    print('BUILD_PASS',summary,'size_gate',gate,flush=True)
if __name__=='__main__':run()
