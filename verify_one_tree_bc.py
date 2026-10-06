"""Exhaustive small native tests before any full-scale call."""
import itertools,time,json
import numpy as np
import gurobipy as gp
from scipy import sparse
from v42_benders.fixtures import CASES,build as physical_fixture
from v42_integrated.matrix import arrays,audit
from v42_rowgen.native import build,transport_audit
from v42_rowgen.core import security_axis,separate,exact_residual
from v42_one_tree_bc.core import OneTree,Separator,expression
from v42_one_tree_bc.files import OUT,write,table
ALIASES={'line_threshold':'line_thermal_face','degenerate_duplicate':'line_thermal_face',
 'adversarial_voltage_upper':'voltage_upper','adversarial_transformer':'transformer_current'}
def config(m,lazy=False):
    for k,v in dict(Threads=1,Seed=20260929,FeasibilityTol=1e-8,
        OptimalityTol=1e-8,IntFeasTol=1e-8,MIPGap=.005,TimeLimit=10,
        LazyConstraints=int(lazy),PreCrush=1,LogToConsole=0).items():m.setParam(k,v)
def validate(A,d,x):
    r=audit(A,d,x,integral=True,tolerance=1e-8)
    r['PASS']=r['PASS'] and separate(A,d,x)['PASS']
    return r
def once(A,d,env,bits=None):
    if bits is not None:
        d=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy())
        ix=np.flatnonzero(d['types']!='C');d['lower'][ix]=bits;d['upper'][ix]=bits
    grid=security_axis(d);axis=np.flatnonzero(~np.isin(np.arange(A.shape[0]),grid))
    m,v=build(A,d,axis,env);config(m,True)
    cb=OneTree(A,d,m.getVars(),lambda x:validate(A,d,x))
    try:
        transport_audit(m,A,d,axis)
        m.optimize(cb)  # Exactly one invocation per independent small fixture.
        r=dict(status=m.Status,objective=m.ObjVal if m.SolCount else None,
            counts=dict(cb.counts),error=cb.error,optimize_calls=1,
            final_original_PASS=bool(m.SolCount and validate(A,d,np.asarray(m.getAttr('X')))['PASS']))
        return r,cb
    finally:m.dispose()
def run():
    OUT.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
    write('M1_ONE_TREE_BC_FIXTURE_RESULTS.json',dict(PASS=False,status='IN_PROGRESS',fullscale_calls=0))
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
    summary=[];assignments=[];failure=None;counts={}
    try:
        # Independent <=, >=, = reconstruction and exact residual probes.
        C=sparse.csr_matrix([[1.,-.1],[1.,.1],[0.,0.],[1.,1.]])
        e=dict(rhs=np.array([.2,.2,-1.,.3]),sense=np.array(['<','>','<','=']),
               row_names=np.array(['line_thermal_face']*4),lower=np.zeros(2),upper=np.ones(2),
               types=np.array(['B','B']),objective=np.ones(2),constant=np.array(0.))
        sep=Separator(C,e)
        from fractions import Fraction
        for x in (np.array([.1,.2]),np.array([.3,-.1]),np.zeros(2)):
            assert list(sep.evaluate(x)['violated'])==[i for i in range(4) if exact_residual(C,e,x,i)>Fraction(1e-8)]
        mm=gp.Model(env=env);vv=mm.addVars(2);mm.update()
        for i in range(4):
            expr=expression(C,[vv[0],vv[1]],i)
            a,b=C.indptr[i:i+2]
            assert np.array_equal(np.asarray([expr.getCoeff(j) for j in range(expr.size())]),C.data[a:b])
            assert [expr.getVar(j).index for j in range(expr.size())]==list(C.indices[a:b])
            mm.addLConstr(expr,str(e['sense'][i]),float(e['rhs'][i]))
        mm.update();assert np.array_equal(mm.getAttr('Sense'),e['sense']) and np.array_equal(mm.getAttr('RHS'),e['rhs'])
        mm.dispose()
        # Force an optimal fractional node and original-row user-cut submission.
        C=sparse.csr_matrix([[1.,1.,0.],[.6,.7,-1.],[1.,1.1,-1.]])
        e=dict(rhs=np.array([.5,0.,0.]),sense=np.array(['>','<','<']),
            row_names=np.array(['route_fixture','nongrid_cost_fixture','line_thermal_face']),
            lower=np.zeros(3),upper=np.array([1.,1.,10.]),types=np.array(['B','B','C']),
            objective=np.array([0.,0.,1.]),constant=np.array(0.))
        m,v=build(C,e,np.array([0,1]),env);config(m,True)
        m.Params.Presolve=0;m.Params.Heuristics=0;m.Params.Cuts=0
        nodecb=OneTree(C,e,m.getVars(),lambda x:validate(C,e,x))
        m.optimize(nodecb)
        assert m.Status==2 and abs(m.ObjVal-1.)<=1e-8 and nodecb.error is None
        assert nodecb.counts['MIPNODE_rows_added']>0 and nodecb.counts['MIPNODE_separations']>0,dict(nodecb.counts)
        assert len({a['original_row_id'] for a in nodecb.registry})==len(nodecb.registry)
        assert validate(C,e,np.asarray(m.getAttr('X')))['PASS']
        fractional_test=dict(PASS=True,status=m.Status,objective=m.ObjVal,counts=dict(nodecb.counts),registry=nodecb.registry)
        # Exercise the official repeated-rejection protocol without another solve.
        class Receiver:
            def __init__(self):self.lazy=[]
            def cbLazy(self,expr,sense,rhs):self.lazy.append((expr,sense,rhs))
            def terminate(self):raise AssertionError('AUTHORIZED_RESUBMISSION_MUST_NOT_ABORT')
        receiver=Receiver();before=len(nodecb.registry)
        nodecb.submit(receiver,2,'MIPSOL',0,1.)
        nodecb.submit(receiver,2,'MIPSOL',0,1.)
        assert len(receiver.lazy)==2 and len(nodecb.registry)==before
        assert all(a[1]=='<' and a[2]==0. for a in receiver.lazy)
        m.dispose()
        for case in CASES:
            mono=physical_fixture(env,case);config(mono);A,d=arrays(mono)
            d['row_names']=np.asarray([ALIASES.get(str(n),str(n)) for n in d['row_names']])
            mono.optimize();r,cb=once(A,d,env)
            expected=mono.Status
            if cb.error or expected!=r['status'] or (expected==2 and (not r['final_original_PASS'] or abs(mono.ObjVal-r['objective'])>1e-7)):
                failure=dict(case=case,assignment=None,monolithic_status=expected,one_tree=r)
                summary.append(dict(case=case,unfixed=r,PASS=False));mono.dispose();break
            ix=np.flatnonzero(d['types']!='C');variables=mono.getVars()
            feasible=infeasible=0
            for bits in itertools.product([0.,1.],repeat=len(ix)):
                for j,b in zip(ix,bits):variables[j].LB=b;variables[j].UB=b
                mono.optimize();rr,cc=once(A,d,env,np.asarray(bits))
                passed=cc.error is None and mono.Status==rr['status'] and (mono.Status==3 or (rr['final_original_PASS'] and abs(mono.ObjVal-rr['objective'])<=1e-7))
                assignments.append(dict(case=case,bits=''.join(str(int(b)) for b in bits),
                    monolithic_status=mono.Status,one_tree_status=rr['status'],PASS=passed))
                for k,v in cc.counts.items():counts[k]=counts.get(k,0)+v
                if not passed:
                    failure=dict(case=case,assignment=assignments[-1],one_tree=rr);break
                if mono.Status==2:feasible+=1
                else:infeasible+=1
            summary.append(dict(case=case,unfixed=r,feasible=feasible,infeasible=infeasible,PASS=failure is None))
            mono.dispose()
            print('FIXTURE',case,'PASS',failure is None,'assignments',len(assignments),flush=True)
            if failure:break
        result=dict(PASS=failure is None,fixtures=summary,exhaustive_assignments=len(assignments),
            counts=counts,first_failure=failure,coefficient_sense_RHS_identity_PASS=True,
            independent_exact_rational_separator_PASS=True,unique_registry_entries=True,
            user_authorized_native_lazy_rejection_resubmission=True,
            fullscale_calls=0,wall=time.perf_counter()-start,
            STOP_before_fullscale=failure is not None,
            numerical_authority=1e-8,MIPGap=.005)
        result['fractional_MIPNODE_original_cut_test']=fractional_test
        result['authorized_repeat_rejection_registry_unique_test']=True
        write('M1_ONE_TREE_BC_FIXTURE_RESULTS.json',result)
        if assignments:table('M1_ONE_TREE_BC_FIXTURE_ASSIGNMENTS.csv',assignments)
        # Retain callback protocol records even if fixture gate fails.
        table('M1_ONE_TREE_BC_FIXTURE_ROW_REGISTRY.csv',cb.registry,
            ['original_row_id','row_name','family','callback_type','node_number','violation','first_added_wall','original_row_SHA'])
        table('M1_ONE_TREE_BC_FIXTURE_CALLBACK_LEDGER.csv',cb.ledger,
            ['callback_type','node_number','start_wall','end_wall','checked_rows','violations','added','ambiguous_exact_checks','valid_full_original','full_objective','maximum_upper','error'])
        print(json.dumps(result,indent=2),flush=True)
    finally:env.dispose()
if __name__=='__main__':run()
