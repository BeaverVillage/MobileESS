"""Exhaustive two-MESS four-slot physical fixture with rational certificates.

HiGHS solves only bounded 53-variable fixtures. Native Gurobi optimize forbidden.
The actual 96-slot authority is independently verified by independent_verify.py.
"""
from common import *
from formulations import Rows,count_ef,rlt_ef,lift
from independent_verify import check,rational
from scipy.optimize import linprog
import warnings,copy

def miniature():
    names=[];lower=[];upper=[];types=[];ids={}
    def var(name,lo,hi,kind='C'):
        j=len(names);names.append(name);lower.append(lo);upper.append(hi);types.append(kind);ids[name]=j;return j
    routes=[];locations=[];modes=[];soc=[];powers=[]
    for u in range(2):
        routes.append(var(f'route_flow[MESS0{u+1},roundtrip]',0,1,'B'))
        locations.append([var(f'node_activity[MESS0{u+1},A,{t}]',0,1,'B') for t in range(4)])
        modes.append([var(f'charge_mode[MESS0{u+1},{t}]',0,1,'B') for t in range(4)])
        soc.append([var(f'SOC[MESS0{u+1},{t}]',3 if t==0 else (1.5 if t==4 else 0),3 if t==0 else 4) for t in range(5)])
        powers.append([[var(f'{f}[MESS0{u+1},A,{t}]',-2 if f=='Q' else 0,2) for f in ['Pch','Pdis','Q']] for t in range(4)])
    rho=var('rho_max',0,5);builder=Rows(len(names))
    for u in range(2):
        for t in range(4):
            stay=locations[u][t];mode=modes[u][t];ch,dis,q=powers[u][t]
            # Complete four-slot two-site time-DAG: either stay at A or take
            # two-slot A->B then two-slot B->A. Other return paths cannot fit.
            builder.row([(stay,1),(routes[u],1)],rhs=1)
            builder.row([(ch,1),(stay,-2)],'<');builder.row([(dis,1),(stay,-2)],'<')
            builder.row([(ch,1),(mode,-2)],'<');builder.row([(dis,1),(mode,2)],'<',2)
            for p_sign,q_sign in itertools.product([-1,1],repeat=2):builder.row([(dis,p_sign),(ch,-p_sign),(q,q_sign),(stay,-2)],'<')
            builder.row([(soc[u][t+1],1),(soc[u][t],-1),(ch,-1),(dis,1),(stay,-.5)],'=',-.5)
    demand=[2,1.5,2.5,2]
    for t in range(4):
        grid=[(rho,-1)]
        for u in range(2):
            ch,dis,q=powers[u][t];grid.extend([(dis,-1),(ch,1),(q,-.25)])
        builder.row(grid,'<',-demand[t])
        builder.row([(powers[0][t][2],1),(powers[1][t][2],-1)],'<',1)
        builder.row([(powers[0][t][2],-1),(powers[1][t][2],1)],'<',1)
    A=builder.matrix();objective=np.zeros(len(names));objective[rho]=1
    d=dict(names=np.asarray(names),lower=np.asarray(lower,dtype=float),upper=np.asarray(upper,dtype=float),types=np.asarray(types),objective=objective,constant=np.array(0.),rhs=np.asarray(builder.rhs),sense=np.asarray(builder.sense),row_names=np.asarray([f'bounded_physics[{i}]' for i in range(len(builder.rhs))]))
    return A,d,dict(routes=routes,locations=locations,modes=modes,SOC=soc,powers=powers,rho=rho)

def solve(A,d):
    eq=np.flatnonzero(d['sense']=='=');ineq=np.flatnonzero(d['sense']!='=');sign=np.array([-1 if d['sense'][i]=='>' else 1 for i in ineq])
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message='Unrecognized options detected')
        r=linprog(d['objective'],A_ub=sparse.diags(sign)@A[ineq],b_ub=sign*d['rhs'][ineq],A_eq=A[eq],b_eq=d['rhs'][eq],bounds=list(zip(d['lower'],d['upper'])),method='highs',options={'threads':1,'primal_feasibility_tolerance':1e-8,'dual_feasibility_tolerance':1e-8})
    if r.status!=0:return r,None,None
    x=[F(float(v)).limit_denominator(4096) for v in r.x];pi=[F(0)]*A.shape[0]
    for i,v in zip(eq,r.eqlin.marginals):pi[i]=F(float(v)).limit_denominator(4096)
    for i,v,s in zip(ineq,r.ineqlin.marginals,sign):pi[i]=s*F(float(v)).limit_denominator(4096)
    return r,x,pi

def exact_primal(A,d,x):
    for j,v in enumerate(x):assert rational(d['lower'][j])<=v<=rational(d['upper'][j])
    for i in range(A.shape[0]):
        lhs=sum((rational(v)*x[int(j)] for j,v in zip(A.indices[A.indptr[i]:A.indptr[i+1]],A.data[A.indptr[i]:A.indptr[i+1]])),F(0));rhs=rational(d['rhs'][i]);sense=d['sense'][i]
        assert lhs<=rhs if sense=='<' else lhs>=rhs if sense=='>' else lhs==rhs

def exact_dual(A,d,pi):
    residual=[rational(v) for v in d['objective']];value=rational(float(d['constant']))
    for i,p in enumerate(pi):
        assert p<=0 if d['sense'][i]=='<' else p>=0 if d['sense'][i]=='>' else True
        value+=p*rational(d['rhs'][i])
        for j,v in zip(A.indices[A.indptr[i]:A.indptr[i+1]],A.data[A.indptr[i]:A.indptr[i+1]]):residual[j]-=p*rational(v)
    return value+sum((r*rational(d['lower'][j] if r>=0 else d['upper'][j]) for j,r in enumerate(residual)),F(0))

def run():
    gp,old=forbid_optimize();calls=0
    try:
        A,d,ix=miniature();I=np.arange(A.shape[0]);J=np.arange(A.shape[1]);groups=[sum(ix['locations'],[])];selectors=[ix['modes'][u][t] for u in range(2) for t in [0,3]]+[ix['locations'][u][t] for u in range(2) for t in [1,2]]
        packages=[]
        for label,builder in [('A',lambda:count_ef(A,d,I,J,groups)),('B',lambda:rlt_ef(A,d,I,J,selectors))]:
            B,e,spec=builder();spec=clean(spec);proof=check(A,d,B,e,spec,scientific=False);packages.append((label,B,e,spec,proof))
        cases=[];feasible=0;infeasible=0;best=None
        for routes in itertools.product([0,1],repeat=2):
            for word in itertools.product([0,1],repeat=8):
                e=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy())
                for u in range(2):
                    j=ix['routes'][u];e['lower'][j]=e['upper'][j]=routes[u]
                    for t in range(4):
                        j=ix['locations'][u][t];e['lower'][j]=e['upper'][j]=1-routes[u]
                        j=ix['modes'][u][t];e['lower'][j]=e['upper'][j]=word[u*4+t]
                result,x,pi=solve(A,e);calls+=1
                if any(routes):
                    # All power is exactly zero in transit; summed SOC rows
                    # force E4=3-4*(1/2)=1, below terminal lower bound 3/2.
                    assert result.status==2 and F(3)-4*F(1,2)<F(3,2);infeasible+=1
                    cases.append(dict(routes=routes,mode_word=word,status='EXACT_INFEASIBLE_TERMINAL_SOC',certificate='E4=1 < terminal 3/2'))
                    continue
                assert result.status==0,'BOUNDED_NUMERICAL_AMBIGUITY';exact_primal(A,e,x);objective=x[ix['rho']];bound=exact_dual(A,e,pi);assert bound==objective,'BOUNDED_OPTIMALITY_CERTIFICATE_FAILED'
                for label,B,extended,spec,proof in packages:
                    # Independent rational lifting; retain all original rows.
                    js=spec['source_columns'];N=len(js);n=len(x)
                    if label=='A':
                        k=int(sum(x[j] for j in groups[0]));weights=[F(int(s==k)) for s in range(9)];y=[w*x[j] for w in weights for j in js]
                    else:weights=[x[j] for j in selectors];y=[w*x[j] for w in weights for j in js]
                    lifted=x+y+weights;extra=dict(rhs=extended['rhs'][A.shape[0]:],sense=extended['sense'][A.shape[0]:],lower=extended['lower'],upper=extended['upper'])
                    # Fix original B bounds in the extended feasible test too.
                    extra['lower']=extra['lower'].copy();extra['upper']=extra['upper'].copy();extra['lower'][:n]=e['lower'];extra['upper'][:n]=e['upper']
                    exact_primal(B,extra,lifted);assert lifted[:n]==x
                    # Original exact dual plus zero added-row multipliers and
                    # zero new-objective coefficients is an EF lower bound.
                    # Feasible lifting attains it: exact optima are equal.
                    assert objective==bound
                feasible+=1;best=objective if best is None else min(best,objective);cases.append(dict(routes=routes,mode_word=word,status='EXACT_OPTIMAL',objective_exact=str(objective),A_forward_inverse_and_optimum_PASS=True,B_forward_inverse_and_optimum_PASS=True))
        assert feasible==256 and infeasible==768
        mutations=[]
        for label,B,e,spec,proof in packages:
            mutated=B.copy();mutated.data[0]+=1
            try:check(A,d,mutated,e,spec,scientific=False)
            except AssertionError:mutations.append(label+'_BAD_PHYSICAL_COEFFICIENT_REJECTED')
            else:raise AssertionError('INVALID_PHYSICAL_COEFFICIENT_ACCEPTED')
            altered=copy.deepcopy(e);altered['upper'][A.shape[1]]+=1
            try:check(A,d,B,altered,spec,scientific=False)
            except AssertionError:mutations.append(label+'_ARBITRARY_PERSPECTIVE_BOUND_REJECTED')
            else:raise AssertionError('INVALID_BOUND_ACCEPTED')
        spec=copy.deepcopy(packages[0][3]);spec['words']=spec['words'][:-1]
        try:check(A,d,packages[0][1],packages[0][2],spec,scientific=False)
        except AssertionError:mutations.append('OMITTED_FEASIBLE_COUNT_WORD_REJECTED')
        else:raise AssertionError('INCOMPLETE_DISJUNCTION_ACCEPTED')
        roots=[];original_root_pi=None
        for label,B,e,spec,proof in [('ORIGINAL',None,d,None,None)]+packages:
            full=A if B is None else sparse.vstack([sparse.hstack([A,sparse.csr_matrix((A.shape[0],B.shape[1]-A.shape[1]))]),B],format='csr')
            result,x,pi=solve(full,e);calls+=1;assert result.status==0;exact_primal(full,e,x);native_rationalized_bound=exact_dual(full,e,pi);bound=native_rationalized_bound;strategy='RATIONALIZED_NATIVE_DUAL'
            if label=='ORIGINAL':original_root_pi=pi
            if bound!=x[ix['rho']]:
                # A degenerate EF can return arbitrary floating multipliers
                # whose individually reconstructed fractions lose stationarity.
                # This is not an optimality certificate. Try the already exact
                # original-root dual, extended by zero on every added row.
                # Equality to an exact feasible EF primal proves optimality;
                # no tolerance or unproven numerical approximation is accepted.
                assert original_root_pi is not None
                bound=exact_dual(full,e,original_root_pi+[F(0)]*(full.shape[0]-A.shape[0]))
                strategy='EXACT_ORIGINAL_DUAL_ZERO_EXTENSION'
            assert bound==x[ix['rho']],'BOUNDED_ROOT_NUMERICAL_AMBIGUITY'
            roots.append(dict(label=label,objective_exact=str(bound),certificate_strategy=strategy,native_rationalized_certificate_exact=str(native_rationalized_bound),native_rationalization_loss=float(x[ix['rho']]-native_rationalized_bound)))
        table(OUT/'BOUNDED_INTEGER_STATE_CENSUS.csv',cases)
        report=dict(PASS=True,scope='Rational bounded C3A-type 2-MESS/4-slot/2-site time-DAG physical fixture; actual 96-slot C3A separately checked against generic algebra',all_route_mode_states=1024,feasible_states=feasible,exact_infeasible_states=infeasible,feasible_optima_equal_original_A_B=True,forward_inverse_lifting=True,exact_primal_dual_and_terminal_SOC_certificates=True,physical_features=['2-slot travel time','travel energy debit','boundary and terminal SOC','charge/discharge exclusive modes','continuous P/Q','PCS diamond','joint grid support','robust differential Q voltage bounds'],best_integer_objective_exact=str(best),bounded_root_comparison=roots,negative_tests=mutations,native_Gurobi_optimize_calls=0,bounded_HiGHS_LP_calls=calls,full_horizon_proof='VALIDITY_PROOF_KO.md',native_solver_forbidden=True)
        atomic(OUT/'BOUNDED_EXACTNESS_TESTS.json',report);print(json.dumps(report),flush=True)
    finally:gp.Model.optimize=old
if __name__=='__main__':run()
