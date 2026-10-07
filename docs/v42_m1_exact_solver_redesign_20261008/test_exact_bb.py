"""Bounded exact rational fixtures. ZERO native solver optimize calls."""
import itertools,tempfile,json,copy
from fractions import Fraction as F
from pathlib import Path
from bb_controller import ExactBB,history_hash,canonical,digest

def solve_square(A,b):
    M=[list(map(F,row))+[F(rhs)] for row,rhs in zip(A,b)];n=len(M)
    for j in range(n):
        k=next((k for k in range(j,n) if M[k][j]),None)
        if k is None:return None
        M[j],M[k]=M[k],M[j];v=M[j][j];M[j]=[x/v for x in M[j]]
        for i in range(n):
            if i!=j:
                v=M[i][j];M[i]=[a-v*b for a,b in zip(M[i],M[j])]
    return tuple(row[-1] for row in M)

class RationalFixture:
    def __init__(self,A,b,c,upper,initial):
        self.A=[tuple(map(F,row)) for row in A];self.b=list(map(F,b));self.c=tuple(map(F,c));self.n=len(c);self.upper=F(upper);self.initial=tuple(map(F,initial));self.identity=dict(fixture=digest(dict(A=A,b=b,c=c)),bounds='all [0,1]',binary_columns=list(range(self.n)))
        assert self.feasible(self.initial) and all(x in (0,1) for x in self.initial)
        assert self.objective(self.initial)==self.upper
    def objective(self,x):return sum(a*b for a,b in zip(self.c,x))
    def feasible(self,x):return all(0<=v<=1 for v in x) and all(sum(a*v for a,v in zip(row,x))<=rhs for row,rhs in zip(self.A,self.b))
    def exact_lp(self,fixings):
        A=list(self.A);b=list(self.b)
        for j in range(self.n):
            e=[F(0)]*self.n;e[j]=1;A.append(tuple(e));b.append(F(1));A.append(tuple(-x for x in e));b.append(F(0))
        for j,v in fixings:
            e=[F(0)]*self.n;e[j]=1;A.append(tuple(e));b.append(F(v));A.append(tuple(-x for x in e));b.append(F(-v))
        vertices=set()
        for active in itertools.combinations(range(len(A)),self.n):
            x=solve_square([A[i] for i in active],[b[i] for i in active])
            if x is not None and all(sum(a*v for a,v in zip(row,x))<=rhs for row,rhs in zip(A,b)):vertices.add(x)
        # A nonempty finite-bounded polytope has an extreme point. Thus exact
        # enumeration of every full-rank active set certifies infeasibility too.
        if not vertices:return None
        x=min(vertices,key=lambda x:(self.objective(x),x));return self.objective(x),x
    def oracle(self,node):
        answer=self.exact_lp(node['fixings']);r=dict(identity=self.identity,fixing_hash=node['fixing_hash'],proof_checked=True,LP_status='INFEASIBLE' if answer is None else 'OPTIMAL',optimal_LP_certificate_PASS=answer is not None,exact_infeasibility_PASS=answer is None,certified_LB=None,branch_variable=None,branch_is_original_binary=True,raw_fractional_branch_value=None,witness=None,receipt='solver-free exact vertex enumeration',Runtime=0,Work=0,basis_accepted=False)
        if answer is not None:
            value,x=answer;r.update(certified_LB=str(value),LP_objective=str(value),fractional_binary_count=sum(v.denominator!=1 for v in x))
            fractional=[j for j,v in enumerate(x) if v.denominator!=1]
            if fractional:
                j=min(fractional,key=lambda j:(-min(x[j],1-x[j]),j));r.update(branch_variable=j,raw_fractional_branch_value=float(x[j]))
            else:
                assert self.feasible(x) and all(v in (0,1) for v in x)
                r['witness']=dict(PASS=True,full_original_replay_PASS=True,raw_vector_unchanged=True,objective_exact=str(value),x=list(map(str,x)))
        return r
    def brute_force(self):
        values=[self.objective(x) for x in itertools.product((F(0),F(1)),repeat=self.n) if self.feasible(x)]
        return min(values) if values else None

def process(bb,oracle):
    node=bb.select()
    if node is None:return False
    all_open=[n for n in bb.state['nodes'].values() if n['state']=='OPEN' and not n['processed']]
    assert (F(node['LB']),node['depth'],node['id'])==min((F(n['LB']),n['depth'],n['id']) for n in all_open)
    result=oracle(node)
    if result.get('witness') and F(result['witness']['objective_exact'])>=F(bb.state['UB']):
        result['witness']=None # A valid LB already suffices; no UB update/replay acceptance.
    bb.begin(node);bb.apply(node['id'],result);return True

def run():
    fixtures=[RationalFixture([[-1,-1]],['-1/2'],[1,1],2,[1,1]),RationalFixture([[-2,-1],[1,0]],[-1,'1/2'],[0,1],1,[0,1]),RationalFixture([[-1,0],[0,-1]],[-1,-1],[1,1],2,[1,1])]
    receipts=[]
    for f in fixtures:
        lower=f.exact_lp([])[0];bb=ExactBB(f.identity,lower,f.upper,dict(validated_fixture=f.initial))
        while process(bb,f.oracle):pass
        audit=bb.audit();assert not audit['OPEN'];assert F(bb.state['UB'])==f.brute_force();assert F(audit['global_OPEN_min_LB_exact'])==f.brute_force()
        receipts.append(dict(PASS=True,fixture=f.identity,processed=bb.state['processed'],optimum=str(f.brute_force()),prune_reasons=[r['prune_reason'] for r in bb.state['ledger']],complete_coverage=audit))
    reasons=[reason for r in receipts for reason in r['prune_reasons']]
    assert 'EXACT_LP_INFEASIBILITY' in reasons and 'CERTIFIED_LB_AT_LEAST_VALIDATED_UB' in reasons and 'INTEGER_REPLAY_PASS_AND_CERTIFIED_OPTIMUM' in reasons
    f=fixtures[0];bb=ExactBB(f.identity,'1/2',2,dict(initial=[1,1]));process(bb,f.oracle)
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'checkpoint.json';bb.save(p);resumed=ExactBB.load(p,f.identity);fresh=copy.deepcopy(bb)
        while process(resumed,f.oracle):pass
        while process(fresh,f.oracle):pass
        assert canonical(resumed.state)==canonical(fresh.state),'RESUME_NOT_DETERMINISTIC'
        altered=json.loads(p.read_text());altered['state']['UB']='0';p.write_text(json.dumps(altered))
        try:ExactBB.load(p,f.identity);raise AssertionError('TAMPER_ACCEPTED')
        except AssertionError as e:assert str(e)=='CHECKPOINT_DIGEST_FAILURE'
        # Re-sign a missing-child checkpoint: structural coverage still rejects.
        altered=json.loads(json.dumps(dict(state=bb.state)));altered['state']['nodes']['0']['children'].pop();altered['SHA256']=digest(altered['state']);p.write_text(json.dumps(altered))
        try:ExactBB.load(p,f.identity);raise RuntimeError('LOST_CHILD_ACCEPTED')
        except AssertionError:pass
        bb.save(p)
        try:ExactBB.load(p,dict(other_authority=True));raise RuntimeError('WRONG_AXIS_ACCEPTED')
        except AssertionError:pass
    # Unresolved LPs retain the exact original root domain and inherited LB.
    unresolved=ExactBB(f.identity,'1/2',2,dict(initial=[1,1]));n=unresolved.select();unresolved.begin(n)
    r=f.oracle(n);r.update(LP_status='UNRESOLVED',certified_LB=None,branch_variable=None,witness=None,optimal_LP_certificate_PASS=False)
    unresolved.apply(0,r);assert unresolved.audit()['OPEN']==[0] and unresolved.audit()['unresolved_OPEN']==[0]
    # An integer witness alone cannot hide an uncertified objective gap.
    safe=ExactBB(f.identity,'1/2',2,dict(initial=[1,1]));n=safe.select();safe.begin(n);r=f.oracle(n)
    r.update(certified_LB='1/2',branch_variable=None,witness=dict(PASS=True,full_original_replay_PASS=True,raw_vector_unchanged=True,objective_exact='1'))
    safe.apply(0,r);assert safe.audit()['OPEN']==[0] and F(safe.state['UB'])==1
    # Solver-free exact dyadic certificate, including mixed row senses and
    # negative bounds. Compare with exact bounded polytope vertices.
    from support import hc,np,sparse,write
    A=sparse.csr_matrix([[1.,1.],[-1.,0.],[0.,1.]])
    d=dict(lower=np.array([-1.,0.]),upper=np.array([2.,3.]),objective=np.array([1.,2.]),constant=np.array(.25),rhs=np.array([1.,.5,2.]),sense=np.array(['>','<','<']))
    cert,pi,_,_=hc.exact_bounded_lagrangian(A,d,np.array([1.,-1.,-1.]))
    exact_bound=F(cert['exact_rational']);assert np.all(pi[d['sense']=='<']<=0) and np.all(pi[d['sense']=='>']>=0)
    for x,y in itertools.product([F(-1),F(-1,2),F(0),F(1),F(2)],[F(0),F(1,2),F(1),F(2),F(3)]):
        if x+y>=1 and -x<=F(1,2) and y<=2:assert exact_bound<=x+2*y+F(1,4)
    # Farkas contradiction x<=0, x>=1, bounds[0,1], lambda=(1,-1).
    infeas_d=dict(lower=np.array([0.]),upper=np.array([1.]),objective=np.array([0.]),constant=np.array(0.),rhs=np.array([0.,1.]),sense=np.array(['<','>']))
    farkas,_,_,_=hc.exact_bounded_lagrangian(sparse.csr_matrix([[1.],[1.]]),infeas_d,np.array([-1.,1.]));assert F(farkas['exact_rational'])==1
    result=dict(PASS=True,native_optimize_calls=0,fixtures=receipts,deterministic_best_bound=True,both_children_preserved=True,exhaustive_binary_optima_match=True,inherited_fixings_verified=True,checkpoint_resume_bit_identical=True,checkpoint_tamper_rejected=True,re_signed_missing_child_rejected=True,wrong_axis_rejected=True,unresolved_domains_preserved=True,witness_without_exact_optimality_not_fathomed=True,dyadic_bound_test_PASS=True,Farkas_exact_contradiction_PASS=True)
    write('EXACTNESS_TESTS.json',result);print('EXACTNESS_FIXTURES_PASS_ZERO_NATIVE_SOLVES',len(fixtures),flush=True)

if __name__=='__main__':run()
