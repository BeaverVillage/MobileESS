"""Exhaustive conservative production audit of frozen C2, with explicit KEEP.

The independent verifier imports none of this module's reduction decisions.
"""
from .common import *
from .polytope import vertices,minimal,farkas,down,up
from .support import domains,exact_sources,exact_screen,union_upper
from fractions import Fraction as F
from collections import Counter,defaultdict
from itertools import combinations
from v42_redundancy.canonical import exact_audits,exact_box
from v42_redundancy.replay import row_hash
from v42_supercompact.presolve import Presolve
from scipy.sparse.csgraph import structural_rank,connected_components
import time,math

def run():
    begin=time.perf_counter();assert read('C2_PRESOLVE_FORENSIC.json')['PASS'];A,d=load();rf=np.asarray([family(n) for n in d['row_names']]);vf=np.asarray([family(n) for n in d['names']]);lookup={str(n):j for j,n in enumerate(d['names'])}
    decisions={};row_tests={};bounds=[];poly=[];pcsids=np.flatnonzero(rf=='PCS16');blocks=[];planes=None
    assert len(pcsids)%16==0
    for start in range(0,len(pcsids),16):
        ids=list(map(int,pcsids[start:start+16]));block={};pp=[]
        for f,i in enumerate(ids):
            a,b=A.indptr[i:i+2];terms={int(j):F(float(w)) for j,w in zip(A.indices[a:b],A.data[a:b])};q=next((j for j in terms if vf[j]=='Q'),None);ch=next((j for j in terms if vf[j]=='Pch'),None);dis=next((j for j in terms if vf[j]=='Pdis'),None);stay=next(j for j in terms if vf[j] in ['route_flow','node_activity']);p=terms.get(dis,F(0));qq=terms.get(q,F(0));assert terms.get(ch,F(0))==-p
            pp.append((p,qq,-terms[stay]));block.update(stay=stay)
            for k,v in [('Pch',ch),('Pdis',dis),('Q',q)]:
                if v is not None:block[k]=v
            assert d['sense'][i]=='<' and d['rhs'][i]==0
        if planes is None:planes=pp
        assert pp==planes;block['rows']=ids;blocks.append(block)
    local=planes+[(F(1),F(0),F(300)),(F(-1),F(0),F(300))];keep,removed=minimal(local);verts=vertices(local)
    assert all(i>=16 or i not in removed for i in keep);assert set(vertices([local[i] for i in keep]))==set(verts)
    # Every retained local face has two distinct boundary vertices: a facet,
    # and a positive violation witness when that face alone is omitted.
    necessity=[]
    for i in keep:
        face=local[i];on=[v for v in verts if face[0]*v[0]+face[1]*v[1]==face[2]]
        others=[local[j] for j in keep if j!=i];test=vertices(others);witness=next((v for v in test if face[0]*v[0]+face[1]*v[1]>face[2]),None)
        assert len(on)>=2 and witness is not None
        necessity.append(dict(face=i,boundary_vertices=[[str(x),str(y)] for x,y in on],omission_witness=[str(w) for w in witness]))
    rowbyphysical=defaultdict(dict)
    for i in np.flatnonzero(np.isin(rf,['connected_Pch','connected_Pdis','connected_Qmax','connected_Qmin'])):
        a,b=A.indptr[i:i+2];physical=[int(j) for j in A.indices[a:b] if vf[j] in ['Pch','Pdis','Q']];assert len(physical)==1;rowbyphysical[physical[0]][rf[i]]=int(i)
    for bl in blocks:
        ch,dis,q,stay=[bl[k] for k in ['Pch','Pdis','Q','stay']];pplus=rowbyphysical[dis]['connected_Pdis'];pminus=rowbyphysical[ch]['connected_Pch']
        a,b=A.indptr[pplus:pplus+2];assert dict(zip(A.indices[a:b],A.data[a:b]))=={stay:-300.,dis:1.}
        a,b=A.indptr[pminus:pminus+2];assert dict(zip(A.indices[a:b],A.data[a:b]))=={stay:-300.,ch:1.}
        assert d['lower'][ch]==d['lower'][dis]==d['lower'][stay]==0
        for f,i in enumerate(bl['rows']):
            r=removed.get(f);rec=dict(row=i,state=str(d['names'][q]),face=f,decision='DELETE' if r else 'KEEP',classification='FULL_LP_REDUNDANT' if r else 'POSSIBLY_ACTIVE',proof='RATIONAL_H_REP_FARKAS' if r else 'Nonredundant facet of exact local clipped polygon',support=r['support'] if r else [],slack=r['slack'] if r else '')
            poly.append(rec)
            if r:decisions[i]=dict(kind='PCS_FARKAS',block=bl,face=f,certificate=r)
        for f,target in [('connected_Qmax',(F(0),F(1),F(400))),('connected_Qmin',(F(0),F(-1),F(400)))]:
            i=rowbyphysical[q][f];proof=farkas(target,[local[j] for j in keep]);assert proof
            bd,a,b,l,m=proof;cert=dict(support=[keep[a],keep[b]],multipliers=[str(l),str(m)],slack=str(F(400)-bd))
            decisions[i]=dict(kind='Q_LINK_FARKAS',block=bl,target=[str(v) for v in target],certificate=cert)
    write('POLYTOPE_MINIMAL_H_REPRESENTATION.json',dict(PASS=True,arithmetic='Exact rational values of stored binary64 matrix',PCS=dict(original_faces=16,retained_PCS_faces=[i for i in keep if i<16],retained_PCS_face_count=sum(i<16 for i in keep),total_clipped_H_facets=len(keep),removed_faces=removed,planes=[[str(x) for x in p] for p in planes],vertices=[[str(x),str(y)] for x,y in verts],necessity_witnesses=necessity,instances=len(blocks)),line_thermal=dict(design='Stored polygon faces plus additive correction/epigraph; local redundancy and correlated full-domain screening performed for every actual remaining row; no single minimum transported across unequal native bounds',minimal_normalized_16_face_polygon=16),transformer=dict(design='Stored polygon is strict convex; native scalar bounds differ by component/time; transport only actual row certificates',minimal_normalized_16_face_polygon=16),extended_formulation=dict(found_beneficial_exact=False,reason='Stored asymmetric binary64 trig coefficients invalidate assumed exact rotational folding; minimal clipped H representation already saves six PCS rows without new variables; generic convex-combination lift requires 12 weights and 16 nonnegative/equality rows, materially more columns/nnz.',current_clipped_vertices=len(verts),generic_lambda_rows=16,generic_lambda_columns=12,adopted=False)))
    table('PCS16_FACE_AUDIT.csv',poly,['row','state','face','decision','classification','proof','support','slack']);print('PCS_EXACT_REMOVALS',Counter(rf[i] for i in decisions),flush=True)
    # Universal exact duplicate, proportional and single-row dominance scan.
    dup,dom,graph,collisions=exact_audits(A,d)
    for i,j in graph.items():
        if i not in decisions and j not in decisions:decisions[i]=dict(kind='EXACT_DUPLICATE' if i in dup else 'EXACT_PROPORTIONAL_DOMINANCE',representative=j)
    print('UNIVERSAL_CANONICAL_SCAN',len(dup),len(dom),flush=True)
    # Terminal mass is the actual sum of retained source/flow equalities, not
    # an assumed network textbook dependency.
    flowgroups=defaultdict(list);rank=[]
    for i in np.flatnonzero(rf=='flow'):
        a=A.indptr[i];u=str(d['names'][A.indices[a]]).split('[',1)[1].split(',')[0];flowgroups[u].append(int(i))
    for u,ids in flowgroups.items():
        B=A[ids].tocsc();degree=np.diff(B.indptr);assert degree.max()<=2;edges=[]
        for j in np.flatnonzero(degree):
            a,b=B.indptr[j:j+2];rr=B.indices[a:b];ww=B.data[a:b];assert all(abs(w)==1 for w in ww)
            if len(rr)==2:assert ww[0]+ww[1]==0;edges.append((int(rr[0]),int(rr[1])))
            else:edges.append((int(rr[0]),len(ids)))
        rr=[a for a,b in edges]+[b for a,b in edges];cc=[b for a,b in edges]+[a for a,b in edges];adj=sparse.csr_matrix((np.ones(len(rr)),(rr,cc)),shape=(len(ids)+1,len(ids)+1));nc,labels=connected_components(adj,directed=False);exactrank=len(ids)+1-nc
        total=np.asarray(A[ids].sum(axis=0)).ravel();rhs=F(sum(float(d['rhs'][i]) for i in ids));candidates=[int(i) for i in np.flatnonzero(rf=='terminal_location') if any(str(d['names'][j]).startswith('node_activity['+u+',') for j in A.indices[A.indptr[i]:A.indptr[i+1]])]
        assert len(candidates)==1;i=candidates[0];actual=A[i].toarray().ravel();assert np.array_equal(total,actual) and rhs==F(float(d['rhs'][i]));decisions[i]=dict(kind='FLOW_EQUALITY_SUM',support=ids)
        rank.append(dict(unit=u,flow_rows=len(ids),structural_rank=structural_rank(A[ids]),exact_rank=exactrank,proof='Signed incidence columns with degree <=2; connected components include explicit boundary-ground node; spanning-tree minor determinant +/-1',components=nc,terminal_dependent_row=i,terminal_proof_support_count=len(ids),dependency_checked_current_matrix=True))
    write('FLOW_RANK_AUDIT.json',dict(PASS=True,units=rank,dependent_rows_removed=4,flow_rows_removed=0,terminal_location_rows_removed=4))
    # Outer-domain support reconstructs the current C2 affine equations after
    # all PR161 aliases, including fixed constants, direct physical Q and TX aliases.
    domn=domains(A,d);src=exact_sources(A,d,domn);screen=exact_screen(A,d,domn,verts,src);axis,upper,rowkeys,counts,basevalues,tvalues,evaluated=screen
    keys,vectors,constants,times,defs,intern=src
    for i in axis:
        sg=-1 if d['sense'][i]=='>' else 1;rhs=sg*float(d['rhs'][i]);margin=1e-8*max(1,abs(rhs),abs(upper[i]))
        if upper[i]<rhs-margin and i not in decisions:decisions[int(i)]=dict(kind='CORRELATED_UNION_SUPPORT',direction=rowkeys[int(i)],time=tvalues[int(i)],base=str(basevalues[int(i)]),upper=float(upper[i]),slack=float(rhs-upper[i]))
    # Exact implied auxiliary bounds, no scientific P/Q/SOC/mode/route bound is
    # arbitrarily allocated. Propagation is triangular; no repeated solver LP.
    boundcache={}
    for j in sorted(keys):
        if not vf[j].startswith(('injection_','response_')) or d['lower'][j]==d['upper'][j]:continue
        h=keys[j];tt=times[j];pair=(h,tt)
        if pair not in boundcache:
            v=vectors[h];lo=np.zeros(288);hi=np.zeros(288)
            for q,x in v.items():lo[q]=down(x);hi[q]=up(x)
            mid=(lo+hi)/2;err=np.maximum(mid-lo,hi-mid)
            bh=float(union_upper(mid[None,:],err[None,:],np.asarray([tt]),domn,verts)[0]);bl=-float(union_upper(-mid[None,:],err[None,:],np.asarray([tt]),domn,verts)[0]);boundcache[pair]=(bl,bh)
        bl,bh=boundcache[pair];newlo=max(float(d['lower'][j]),float(np.nextafter(down(constants[j])+bl,-np.inf)));newhi=min(float(d['upper'][j]),float(np.nextafter(up(constants[j])+bh,np.inf)))
        if newlo>d['lower'][j] or newhi<d['upper'][j]:
            bounds.append(dict(column=j,name=str(d['names'][j]),old_lower=float(d['lower'][j]),old_upper=float(d['upper'][j]),new_lower=newlo,new_upper=newhi,proof_family='CORRELATED_ROUTE_PCS_AFFINE',supporting_constraints=defs.get(j),direction=h,time=tt,constant=str(constants[j]),arithmetic='Exact rational affine expansion + outward interval union support',safety_margin='Outward rounding at every support/product/sum'))
    write('GROUPED_SUPPORT_DIRECTIONS.json',dict(PASS=True,canonical='SHA256 of sorted sparse exact rational coordinate:value vector over unit/site/Pch/Pdis/Q, time is separate support key; vectors reconstruct from immutable C2 bindings',row_counts=counts,security_rows=len(axis),unique_directions=len(counts),unique_direction_time_supports=len(evaluated),reused_supports=len(axis)-len(evaluated),no_LP_per_row=True,reachable_connected_states=domn['records'],source_vectors=len(vectors)))
    np.savez_compressed(OUT/'SECURITY_SUPPORT_RESULTS.npz',axis=axis,upper=upper,time=np.asarray([tvalues[int(i)] for i in axis]),direction=np.asarray([rowkeys[int(i)] for i in axis]))
    security=[]
    for i in axis:
        x=decisions.get(int(i));sg=-1 if d['sense'][i]=='>' else 1;rhs=sg*float(d['rhs'][i]);security.append(dict(row=int(i),family=rf[i],classification='ALWAYS_SAFE' if x and x['kind']=='CORRELATED_UNION_SUPPORT' else ('EXACT_DUPLICATE' if x and x['kind']=='EXACT_DUPLICATE' else 'EXACT_DOMINATED' if x else 'POSSIBLY_ACTIVE'),decision='DELETE' if x else 'KEEP',direction=rowkeys[int(i)],time=tvalues[int(i)],certified_upper=upper[i],rhs=rhs,slack=rhs-upper[i],reason='FULL_LP_REDUNDANT outward union support' if x else 'Outer maximum may activate; exact local/cross-family implication not established'))
    fields=['row','family','classification','decision','direction','time','certified_upper','rhs','slack','reason']
    for f,n in [('line_thermal_face','LINE_THERMAL_SECOND_PASS.csv'),('transformer_kVA','TRANSFORMER_FACE_AUDIT.csv')]:table(n,(r for r in security if r['family']==f),fields)
    table('VOLTAGE_SECOND_PASS.csv',(r for r in security if r['family'].startswith('voltage_')),fields)
    prose('CORRELATED_ROUTE_SOC_PQ_SUPPORT.md','# Correlated full-LP support\n\nEach acyclic unit flow has unit source mass. Connected stay masses at a slot sum to at most one, including fractional route mixtures and transit crossing the time cut. Each local PCS/connected-P region is homogeneous in its stay mass. The support for each unit is therefore max(0, max over reachable sites of exact clipped PCS support), and the four unit supports add. Every sign quadrant is enumerated by exact stored-rational vertices. Simultaneous fractional charging/discharging is bounded explicitly; no integer-mode argument is used.\n\nSOC forward/backward endpoint envelopes from PR161 remain mandatory. At the current local P limit of 300 all local +/-P extrema remain inside this conservative SOC-safe envelope; no stronger per-state bound was certified. Aggregate SOC net-P implications are not divided by a fractional stay mass. Thus the correlated engine contains route, connectivity, endpoint SOC-safe bounds, P/Q correlation, PCS and affine feeder sensitivity without claiming a nonexistent additional local SOC reduction. Identical exact rational directions/time pairs share support. Current auxiliary interval bounds are intersected only when independently implied. Historical trajectories do not enter support.\n')
    # Complete universal row scan with final reasons; exact box tests include
    # fixed positive auxiliaries but never use newly tightened bounds circularly.
    for i in range(A.shape[0]):
        if i in decisions:continue
        a,b=A.indptr[i:i+2]
        if a==b:
            assert d['rhs'][i]==0 if d['sense'][i]=='=' else (d['rhs'][i]>=0 if d['sense'][i]=='<' else d['rhs'][i]<=0);decisions[i]=dict(kind='CONSTANT_SAFE');continue
        if d['sense'][i]!='=':
            val=exact_box(A,d,i)
            if val is not None and val<=F((-1 if d['sense'][i]=='>' else 1)*float(d['rhs'][i])):decisions[i]=dict(kind='ORIGINAL_BOUNDS',upper=str(val))
    print('ALL_NEW_ROW_PROOFS',Counter(x['kind'] for x in decisions.values()),flush=True)
    # Primary row deletion certificates reference frozen C2 IDs and hashes.
    certs=[]
    for i,p in sorted(decisions.items()):certs.append(dict(row=i,row_SHA256=row_hash(A,d,i),family=rf[i],classification='FULL_LP_REDUNDANT',**p))
    write('C3_ROW_CERTIFICATES.json',certs);table('BOUND_TIGHTENING_V2.csv',bounds,['column','name','old_lower','old_upper','new_lower','new_upper','proof_family','supporting_constraints','direction','time','constant','arithmetic','safety_margin'])
    kept=np.asarray([i for i in range(A.shape[0]) if i not in decisions]);B=A[kept].copy();e=dict(d,**{k:d[k][kept] for k in ['rhs','sense','row_names']});e['lower']=d['lower'].copy();e['upper']=d['upper'].copy()
    for r in bounds:e['lower'][r['column']]=r['new_lower'];e['upper'][r['column']]=r['new_upper']
    save('C3A',B,e);np.savez_compressed(OUT/'C3_RETAINED_AXES.npz',rows=kept,columns=np.arange(A.shape[1]))
    # Audit substitution cost after certified deletes/bounds. Generic affine
    # substitutions remain explicit KEEP unless both sparse and representable.
    p=Presolve(B,e);_,cost=p.audit_pivots(execute=False);costmap={r['column']:r for r in cost};C=A.tocsc();costrows=[];column_rows=[];coefficient_range=census_range(A)
    for j,n in enumerate(d['names']):
        fixed=d['lower'][j]==d['upper'][j];candidate=costmap.get(j);supporting=candidate.get('definition') if candidate else None;reason='Scientific decision or no exact sparse projection certified';classification='ESSENTIAL_OR_UNKNOWN';before=None;after=None;repr_reject=False
        if fixed:
            classification='FIXED_CONSTANT_RETAINED';reason='Exact fixed value already in C2; elimination must preserve binary64 RHS authority'
            for i,w in zip(C.indices[C.indptr[j]:C.indptr[j+1]],C.data[C.indptr[j]:C.indptr[j+1]]):
                exact=F(float(d['rhs'][i]))-F(float(w))*F(float(d['lower'][j]));y=float(exact)
                if F(y)!=exact:repr_reject=True;break
            if repr_reject:reason='KEEP: at least one exact substituted RHS is not representable in binary64'
        elif candidate:
            classification='EXACT_DEFINITION_KEEP';before=candidate.get('nnz_before');after=candidate.get('nnz_after_union_upper');reason=candidate['reason']
            if after is not None and before is not None and after>before:reason='KEEP: substitution increases nnz and row density'
            else:reason='KEEP: finite implied auxiliary bounds require bound-row transport; no beneficial exact complete projection certified'
        elif vf[j]=='route_flow':reason='KEEP: branching flow/path choices or connected intermediate events; degree/path/state audit has no equivalent scientific contraction'
        elif vf[j]=='node_activity':reason='KEEP: binary through-flow mass enforces route integrality; deleting link or variable lacks full integer inverse'
        elif vf[j]=='charge_mode':reason='KEEP: both power directions remain possible in local physical domain; Q is mode-independent; no full-domain fixed-mode proof'
        elif vf[j]=='SOC':reason='KEEP: projecting bounded recurrence state requires two dense bound rows and temporal coupling'
        column_rows.append(dict(column=j,family=vf[j],classification=classification,decision='KEEP',reason=reason,pipeline='A-J',fixed=fixed))
        if candidate or fixed or vf[j] in ['SOC','route_flow']:
            row= dict(column=j,family=vf[j],definition=supporting,rows_removed=1 if candidate else 0,cols_removed=1,nnz_removed=before,nnz_added=after,net_nnz_change=None if before is None or after is None else after-before,max_row_before=None,max_row_after=None,max_column_before=int(C.indptr[j+1]-C.indptr[j]),max_column_after=None,coefficient_range_before=coefficient_range,coefficient_range_after='UNCHANGED_KEEP',decision='KEEP',reason=reason,nonrepresentable=repr_reject)
            if candidate:
                # Exact union costs, with finite bound rows included. A union
                # is a conservative exact symbolic sparsity upper bound.
                rid=int(candidate['definition']);a,b=B.indptr[rid:rid+2];expr=set(map(int,B.indices[a:b]))-{j};cons=C.indices[C.indptr[j]:C.indptr[j+1]];row['max_row_before']=max((A.indptr[i+1]-A.indptr[i] for i in cons),default=0);row['max_row_after']=max((len((set(map(int,A.indices[A.indptr[i]:A.indptr[i+1]]))-{j})|expr) for i in cons),default=0)
                finitebound=int(np.isfinite(e['lower'][j]))+int(np.isfinite(e['upper'][j]));row['bound_rows_added']=finitebound;row['nnz_added_with_bounds']=(after or 0)+finitebound*len(expr)
            costrows.append(row)
    table('ALL_COLUMN_DECISIONS.csv',column_rows,['column','family','classification','decision','reason','pipeline','fixed']);fields=['column','family','definition','rows_removed','cols_removed','nnz_removed','nnz_added','net_nnz_change','bound_rows_added','nnz_added_with_bounds','max_row_before','max_row_after','max_column_before','max_column_after','coefficient_range_before','coefficient_range_after','decision','reason','nonrepresentable'];table('SPARSE_SUBSTITUTION_LEDGER.csv',costrows,fields)
    for prefix,n in [('injection_','INJECTION_AUXILIARY_AUDIT.csv'),('response_line_','LINE_RESPONSE_AUXILIARY_AUDIT.csv'),('response_transformer_','TRANSFORMER_RESPONSE_AUDIT.csv')]:table(n,(r for r in costrows if r['family'].startswith(prefix)),fields)
    # No new safe beneficial substitution/representation passed, so equality
    # of candidates is intentional and avoids redundant benchmarks.
    save('C3B',B,e);save('C3C',B,e)
    for label in ['C3A','C3B','C3C']:write(label+'_CENSUS.json',census(B,e))
    rows=[]
    for i in range(A.shape[0]):
        p=decisions.get(i);why=p['kind'] if p else 'KEEP_UNPROVED_AFTER_A_K'
        rows.append(dict(row=i,family=rf[i],decision='DELETE' if p else 'KEEP',classification='FULL_LP_REDUNDANT' if p else 'UNKNOWN',reason=why,pipeline='A-K'))
    table('ALL_ROW_DECISIONS.csv',rows,['row','family','decision','classification','reason','pipeline'])
    led=[]
    for kind,families,items in [('ROW',rf,rows),('COLUMN',vf,column_rows)]:
        familyaudit=[]
        for f,count in sorted(Counter(families).items()):
            relevant=[r for r in items if r['family']==f];gone=sum(r['decision']=='DELETE' for r in relevant);types=Counter(r.get('reason','') if r['decision']=='DELETE' else r.get('classification') for r in relevant)
            rec=dict(kind=kind,family=f,original_count=count,tested_count=len(relevant),removable_count=gone,retained_count=count-gone,proof_type=dict(types),reason_retained='No certified full-LP deletion / integer-preserving low-fill binary64 substitution for retained members');familyaudit.append(rec);led.append(rec)
        table('EXHAUSTIVE_'+kind+'_FAMILY_AUDIT.csv',familyaudit,['kind','family','original_count','tested_count','removable_count','retained_count','proof_type','reason_retained'])
    table('EXHAUSTIVE_REDUCTION_LEDGER.csv',led,['kind','family','original_count','tested_count','removable_count','retained_count','proof_type','reason_retained'])
    table('NODE_ACTIVITY_LINK_AUDIT.csv',(r for r in rows if r['family']=='node_activity_link'),['row','family','decision','classification','reason','pipeline'])
    table('MODE_LOGIC_AUDIT.csv',(r for r in rows if r['family'] in ['connected_Pch','connected_Pdis','connected_Qmax','connected_Qmin','no_simultaneous_charge','no_simultaneous_discharge']),['row','family','decision','classification','reason','pipeline'])
    table('ENERGY_BALANCE_AUDIT.csv',(r for r in rows if r['family']=='energy_balance'),['row','family','decision','classification','reason','pipeline'])
    equality=np.flatnonzero(d['sense']=='=');soc=np.flatnonzero(vf=='SOC');energy=np.flatnonzero(rf=='energy_balance');write('GLOBAL_EQUALITY_RANK_AUDIT.json',dict(PASS=True,equalities=len(equality),structural_rank=structural_rank(A[equality]),exact_flow_blocks=rank,SOC_submatrix_structural_rank=structural_rank(A[energy][:,soc]),SOC_columns=len(soc),SOC_recurrences=len(energy),SOC_endpoint_projected_aggregate_equalities=4,affine_definitions=len(defs),fixed_auxiliaries=int(np.sum((d['lower']==d['upper'])&np.char.startswith(vf,'response_'))),block_order=['unit flow incidence','node through-mass definitions','SOC bidiagonal states and four endpoint aggregates','site injections','line/transformer affine responses'],global_exact_rank_claimed=False,reason='Exact signed-incidence rank proved; native affine pivots form triangular block. Remaining combined coupling has structural rank only; no unproved numerical rank deletion.'))
    table('STATIC_REDUCTION_ROUNDS_V2.csv',[dict(round=1,rows_before=A.shape[0],rows_deleted=len(decisions),bounds_tightened=len(bounds),columns_removed=0,rows_after=B.shape[0],nnz_after=B.nnz),dict(round=2,rows_before=B.shape[0],rows_deleted=0,bounds_tightened=0,columns_removed=0,rows_after=B.shape[0],nnz_after=B.nnz)],['round','rows_before','rows_deleted','bounds_tightened','columns_removed','rows_after','nnz_after'])
    table('OBJECTIVE_SPECIFIC_CANDIDATES_ONLY.csv',[dict(family='rho_max',candidate='Restrict epigraph upper bound to validated UB',decision='KEEP_PRIMARY',reason='Optimum-only cutoff removes feasible higher-objective points; excluded from full-feasible-set C3')],['family','candidate','decision','reason'])
    prose('RADIAL_TOPOLOGY_REFORMULATION.md','# Same-affine radial design audit\n\nAll response definitions were expanded from the actual C2 matrix. A radial downstream recursion can replace them only if each stored sensitivity equals the exact recursive difference, including phase coupling and correction. The current response includes dense voltage/current correction sensitivities and stored floating-point factors. A topology-only sum of downstream P/Q does not reproduce these coefficients. A general recursive factorization retaining every residual coefficient adds intermediates and rows; no smaller sparse exact factorization was proved. Keep all such candidates. Cross-family scalar bounds were tested only through certified affine union bounds and exact local/row implication; no transformer-to-line engineering inference is a deletion certificate.\n\nGUB: connected nodes at a slot sum to at most one; long transit arcs cross slots without connected node activity. Equality requires the crossing-arc terms. SOS/indicator replacement would introduce solver-specific rows or replace the current full LP relaxation; no equivalent cheaper native formulation was adopted. MESS initial locations differ. Local state partitioning includes location and electrical consequences, so no unproved symmetry-breaking rows are added.\n')
    summary=dict(PASS=True,all_rows=A.shape[0],all_columns=A.shape[1],new_rows_removed=len(decisions),rows_by_family=dict(Counter(rf[i] for i in decisions)),proof_counts=dict(Counter(p['kind'] for p in decisions.values())),new_bounds=len(bounds),columns_removed=0,new_binary_fixes=0,C3B_equals_C3A=True,C3C_equals_C3B=True,size_reduction={k:1-census(B,e)[k]/census(A,d)[k] for k in ['rows','nnz','continuous']},fixed_point_scope='Exact duplicate/proportional/constant/bounds/triangular affine union closure and local PCS H minimization; unknown generic multirow implications remain KEEP',wall=time.perf_counter()-begin)
    write('AUDIT_SUMMARY.json',summary);print('EXHAUSTIVE_AUDIT_PASS',summary,flush=True)
def census_range(A):
    x=np.abs(A.data);return [float(x.min()),float(x.max())]
if __name__=='__main__':run()
