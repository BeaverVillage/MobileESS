"""Solver-free conditional P2 authority; P1 remains minimize rho."""
from practical_support import *
from fractions import Fraction as F

CONTRACT='docs/v42_single_worker_single_thread_a1_m1/M1_OBJECTIVE_CONTRACT.json'

def projected(terms,authority,n):
    coefficients={};constant=F(0);omitted=0
    for name,value in terms.items():
        c=F.from_float(float(value));expr,offset=authority.expression(name)
        omitted+=name not in authority.names;constant+=c*offset
        for j,w in expr.items():assert 0<=j<n;coefficients[j]=coefficients.get(j,F(0))+c*w
    vector=np.zeros(n);failures=[]
    for j,c in coefficients.items():
        vector[j]=float(c)
        if F.from_float(vector[j])!=c:failures.append(dict(column=j,exact=str(c),binary64=float(c)))
    con=float(constant)
    if F.from_float(con)!=constant:failures.append(dict(ObjCon_exact=str(constant),binary64=con))
    return vector,con,dict(source_terms=len(terms),native_omitted_zero_terms=omitted,nonzero_C3A_coefficients=int(np.count_nonzero(vector)),nonrepresentable_count=len(failures),examples=failures[:10],binary64_exact=not failures),coefficients,constant

def run():
    A,d,_=hc.load();assert verifier.verify(ROOT,d)['PASS']
    original=subprocess.check_output(['git','show',authority.SCIENTIFIC+':'+CONTRACT],cwd=ROOT)
    assert original==subprocess.check_output(['git','show','HEAD:'+CONTRACT],cwd=ROOT)
    contract=json.loads(original);auth=hc.Authority();vectors={};results=[]
    assert contract['P2']==['movement_energy','movement_count']
    with np.load(OUT/'runs/cuts0_control/BEST_VALID_POINT.npz') as z:x=z['x'].copy()
    reader=hc.physical_reader();full=reader.inverse(x)
    for component,terms in [('movement_energy',contract['movement_energy_coefficients']),('movement_count',{name:1. for name in contract['movement_count_variables']})]:
        vector,constant,report,exact_coeff,exact_constant=projected(terms,auth,A.shape[1])
        assert vector.shape==d['objective'].shape
        # PhysicalReplay owns a separate inverse implementation. Its original
        # vector may snap route auxiliaries under inherited replay tolerance;
        # retain that discrepancy and do not alter the scientific P1 point.
        full_lookup={str(name):j for j,name in enumerate(reader.d['names'])}
        physical_sum=math.fsum(float(c)*float(full[full_lookup[name]]) for name,c in terms.items() if name in full_lookup)
        compact_sum=math.fsum(float(c)*float(x[j]) for j,c in exact_coeff.items())+float(exact_constant)
        report.update(component=component,constant_exact=str(exact_constant),independent_full_vector_value=physical_sum,projected_C3A_value=compact_sum,difference=abs(physical_sum-compact_sum),independent_inverse_within_1e_8=abs(physical_sum-compact_sum)<=1e-8)
        vectors[component]=vector;vectors[component+'_constant']=np.array(constant);results.append(report)
    vectors['names']=d['names'];path=OUT/'P2_OBJECTIVES.npz';tmp=path.with_suffix('.npz.tmp')
    with tmp.open('wb') as f:np.savez_compressed(f,**vectors);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    from v42_two.contract import P1_EPS,COMPONENT_EPS
    atomic(OUT/'P2_AUTHORITY_PREPARATION.json',dict(UTC=stamp(),optimize_calls=0,P1_scientific_objective_unchanged=True,conditional_only=True,P1_target_not_yet_reached=True,P2_executed=False,contract_git_path=CONTRACT,contract_scientific_commit=authority.SCIENTIFIC,contract_SHA256=hashlib.sha256(original).hexdigest(),P2_order=contract['P2'],P1_lock_epsilon=P1_EPS,component_lock_epsilon=COMPONENT_EPS,projected_objectives_SHA256=sha(path),independent_inverse_identity=auth.inverse_provenance,components=results,ready_if_P1_accepted=all(r['binary64_exact'] and r['independent_inverse_within_1e_8'] for r in results),gate='Fresh original full replay, unchanged P1 objective identity and full global domain coverage at gap <=0.005, followed by inherited v42_integrated.certificate.make acceptance. P2 cannot begin before this gate.'))
    print('P2_AUTHORITY_PREPARED_OPTIMIZE_0',[(r['component'],r['binary64_exact'],r['difference']) for r in results])

if __name__=='__main__':run()
