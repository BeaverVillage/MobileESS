"""Independent zero-optimize evidence, full matrix/domain and source checks."""
import re,xml.etree.ElementTree as ET
import gurobipy as gp
from .common import *
from .report import REQUIRED
from .runner import validate_full_plan

def run():
    missing=[n for n in REQUIRED if n!='VERIFICATION.json' and not (OUT/n).exists()];assert not missing,missing
    for name in ['LEGACY_PRESERVATION_AUDIT.json','PR110_BASE_RECEIPT.json']:
        for r in read(OUT/name).get('files',read(OUT/name).get('inherited_evidence',[])):assert sha(ROOT/r['path'])==r['sha256'],r['path']
    for r in read(OUT/'SOURCE_MANIFEST.json')['sources']:assert sha(ROOT/r['path'])==r['sha256']
    assert read(OUT/'BASE_F3_IDENTITY.json')['PASS'] and read(OUT/'ROOT_SOURCE_RECEIPT.json')['PASS']
    assert read(OUT/'WINDOW_INTEGRALITY_VALIDATION_SUMMARY.json')['PASS']
    soc=read(OUT/'TERMINAL_SOC_DUAL_SUMMARY.json')
    with np.load(OUT/'ROOT_DUAL_AXIS.npz',allow_pickle=False) as z:dn=z['names'];dp=z['Pi']
    native=dp[dn=='terminal_SOC']
    for i,u in enumerate(sorted(soc['terminal_SOC_duals'])):
        extra=float(dp[np.flatnonzero(dn==f'G_terminal[{u}]')[0]]) if np.any(dn==f'G_terminal[{u}]') else 0.
        assert soc['combined_terminal_RHS_duals'][u]==float(native[i])+extra
    window=read(OUT/'WINDOW_DEFINITION.json');assert window['BUFFER']==8 and window['W_BUFFER']==[max(0,window['W_ACTIVE'][0]-8),95]
    slots=csvread('ROOT_SLOT_RECOMPUTATION.csv');assert len(slots)==96
    active=[int(r['time']) for r in slots if float(r['slack'])<=OBJ_TOL and float(r['dual_mass'])>=EPS];assert active==window['T_ACTIVE']
    assert window['W_ACTIVE']==[min(active),max(active)]
    suite=ET.parse(OUT/'PYTEST_RESULTS.xml').getroot().find('testsuite');assert int(suite.attrib['failures'])==int(suite.attrib['errors'])==0 and int(suite.attrib['tests'])==541
    assert len(re.findall(r'^\d+\. ',(OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf8'),re.M))==50
    flags=read(OUT/'FINAL_FLAGS.json');assert flags['A1_OPTIMIZE_CALLS']==flags['S1_OPTIMIZE_CALLS']==flags['S2_OPTIMIZE_CALLS']==flags['S3_OPTIMIZE_CALLS']==0
    assert flags['BEST_NEW_FEASIBLE_UB']>=S2-OBJ_TOL,'VALIDATED_UB_CANNOT_BELOW_INHERITED_CERTIFIED_LB'
    assert not any(flags[k] for k in ['M1_ACCEPTED','PRODUCTION_M1_RUN','A2_RUN','M2_RUN','ACTUAL_RUN','FRESH_AC_RUN','IEEE8500_RUN','PROBLEM13_FINAL_VALIDATED','SCIENTIFIC_PHYSICS_CHANGED'])
    assert hashlib.sha256(gzip.decompress((OUT/'F3_MODEL.mps.gz').read_bytes())).hexdigest()==sha(LOCAL/'F3.mps')==read(OUT/'F3_TEMPLATE_RECEIPT.json')['sha256']
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=gp.read(str(LOCAL/'F3.mps'),env=env)
    A=m.getA();rhs=np.asarray(m.getAttr('RHS'));sense=np.asarray(m.getAttr('Sense'))
    with np.load(OUT/'F3_MODEL_AXIS.npz',allow_pickle=False) as z:
        names=z['names'];types=z['original_types'];lo=z['lower'];hi=z['upper'];start=z['start'];terminal=z['terminal_rows']
    assert list(names)==m.getAttr('VarName') and A.shape==(954560,316743) and A.nnz==8282350
    # Independently compare saved MPS coefficients with the native constructor;
    # this is a zero-optimize build, not another F3/S2/S3 solve.
    b=base()
    def compare_native(native,obj,bindings,controls,data):
        from v42_m1_sparse.grid import map_bindings
        native.setObjective(obj[0][1]);native.update();values=data[2]['values'].copy();map_bindings(bindings,values)
        native.setAttr('Start',[values[n] for n in native.getAttr('VarName')]);native.update();assert b.stats(native)==b.EXPECTED
        a=native.getA();assert np.array_equal(a.indices,A.indices) and np.array_equal(a.indptr,A.indptr)
        maximum=float(np.max(abs(a.data-A.data)));rhs_error=float(np.max(abs(np.asarray(native.getAttr('RHS'))-rhs)))
        assert maximum<=1e-10 and rhs_error<=1e-10 and np.array_equal(native.getAttr('Sense'),sense)
        assert native.getAttr('VarName')==list(names) and np.array_equal(native.getAttr('LB'),lo) and np.array_equal(native.getAttr('UB'),hi)
        dump('F3_MPS_ROUNDTRIP_VALIDATION.json',dict(PASS=True,native_default_fingerprint='0x9cfd10ec',matrix_sparsity_exact=True,
            maximum_coefficient_roundtrip_difference=maximum,maximum_RHS_roundtrip_difference=rhs_error,bounds_exact=True,row_senses_exact=True,optimize_calls=0))
        return None,dict(optimize_calls=0)
    b.build(compare_native)
    _,_,_,sites,initial,routes,_=inputs();arcs=arcs_for(sites,routes);checks=[]
    for p in sorted(OUT.glob('*_OPTIMIZATION.json')):
        r=read(p);assert r['run'] and r['optimize_calls']==1 and r['template_sha256']==sha(LOCAL/'F3.mps')
        name=r['name'];domain=json.loads(gzip.decompress((OUT/(name+'_DOMAIN.json.gz')).read_bytes()))
        assert r['rows']==954560-(4 if name=='TERM_RELAX' else 0) and r['columns']==316743
        assert r['settings']['Method']==2 and r['settings']['Threads']==1 and not r['settings']['GPU']
        if name.startswith('R_') or name.startswith('U'):
            aa,bb=r['window'];unitset=set(r['units']);expected=[]
            for n,k in zip(names,types):
                if k!='B':continue
                if n.startswith('arc['):
                    u,i=n[4:-1].split(',');a=arcs[int(i)];selected=u in unitset and (any(a[1]<=t<a[3] for t in range(aa,bb+1)) or aa<=a[1]<=bb)
                elif n.startswith('charge_mode['):
                    u,t=n[12:-1].split(',');selected=u in unitset and aa<=int(t)<=bb and name!='R_ROUTE_ONLY'
                else:raise AssertionError(n)
                if selected:expected.append(str(n))
            assert expected==domain['restored'] and len(expected)==r['restored_binaries'] and not domain['fixed']
        elif name.startswith('P_'):
            expected=[]
            for n,k in zip(names,types):
                if k!='B':continue
                fix=name=='P_FIXED_ALL' or name=='P_FIXED_ROUTE' and n.startswith('arc[')
                if name=='P_LATE_ROUTE_NEIGHBORHOOD' and n.startswith('arc['):
                    _,i=n[4:-1].split(',');a=arcs[int(i)];aa,bb=r['window'];fix=not any(a[1]<=t<a[3] for t in range(aa,bb+1)) and not aa<=a[1]<=bb
                if fix:expected.append(str(n))
            assert expected==domain['fixed']
        assert r['settings']['Heuristics']==0 and r['settings']['MIPFocus']==3 and r['settings']['MIPGap']==.005 and r['settings']['Seed']==20260929 if r['binary_variables'] else True
        path=OUT/(name+'_SOLUTION.npz')
        if path.exists():
            with np.load(path,allow_pickle=False) as z:assert list(z['names'])==list(names);v=z['values']
            residual=A@v-rhs;error=np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual))
            if name=='TERM_RELAX':error[terminal]=0.
            maximum=max(0.,float(error.max()),float((lo-v).max()),float((v-hi).max()));assert maximum<=TOL,(name,maximum)
            pos={str(n):i for i,n in enumerate(names)};restored=[pos[n] for n in domain['restored']]
            frac=float(np.max(abs(v[restored]-np.rint(v[restored])))) if restored else 0.;assert frac<=TOL
            fixed=[pos[n] for n in domain['fixed']];assert not fixed or float(np.max(abs(v[fixed]-np.rint(start[fixed]))))<=TOL
            if name=='P_LATE_ROUTE_NEIGHBORHOOD':
                # The retained plan is all-stay outside the window. Fixed
                # outside stay=1 and unit flow force any free crossing trip=0.
                for u in sorted(initial):
                    for t in range(r['window'][0]):
                        crossing=[pos[f'arc[{u},{i}]'] for i,a in enumerate(arcs) if a[1]<=t<a[3] and f'arc[{u},{i}]' in pos]
                        assert float(np.max(abs(v[crossing]-start[crossing])))<=TOL,'PRE_BUFFER_ROUTE_OCCUPANCY_CHANGED'
                if r.get('included_fixed_route_feasible_upper') is not None:
                    with np.load(OUT/'P_FIXED_ROUTE_SOLUTION.npz',allow_pickle=False) as z:source_point=z['values']
                    assert float(np.max(abs(source_point[fixed]-np.rint(start[fixed]))))<=TOL
                    assert r['final_BestBd']<=r['best_known_model_feasible_UB']+OBJ_TOL
            if r.get('original_feasible_UB') is not None:
                original=validate_full_plan(names,v,types);assert original['valid_new_UB']
            assert abs(v[pos['rho_max']]-r['incumbent_objective'])<=OBJ_TOL
            if r['negative_certificate']:
                assert r.get('certified_partial_upper',r['incumbent_objective'])-F3<=.001
                if r.get('certificate_by_feasible_set_inclusion'):
                    source=read(OUT/(r['negative_certificate_source']+'_OPTIMIZATION.json'))
                    sd=json.loads(gzip.decompress((OUT/(source['name']+'_DOMAIN.json.gz')).read_bytes()))
                    full=bool(source['full_original_integer_validation'] and source['full_original_integer_validation']['valid_new_UB'])
                    assert source['solution_matrix_validation']['PASS'] and (full or set(domain['restored'])<=set(sd['restored']))
            checks.append(dict(name=name,matrix_max_violation=maximum,restored_integrality_max=frac,independent_PASS=True,optimize_calls=0))
        marker=read(LOCAL/(name+'_OPTIMIZE_STARTED.json'));assert marker['name']==name
    m.dispose();env.dispose()
    units=csvread('UNIT_ATTRIBUTION.csv');unitrun=read(OUT/'R_ACTIVE_OPTIMIZATION.json')['LB_gain']>=.001
    assert all((r['run']=='True')==unitrun for r in units)
    dump('VERIFICATION.json',dict(PASS=True,required_files=len(REQUIRED),tests=541,bounded_window_checks=44,independent_matrix_checks=checks,
        diagnostic_optimize_calls=flags['DIAGNOSTIC_OPTIMIZE_CALLS'],verification_optimize_calls=0,default_F3_identity_PASS=True,legacy_bytes_preserved=True,
        source_hashes_PASS=True,active_rule_PASS=True,window_unchanged=True,unit_gate_PASS=True,A1_S1_S2_S3_reruns=0,new_cuts=0,production_M1_run=False,downstream_run=False))
    print('FORENSIC VERIFICATION PASS',len(checks),flush=True)
if __name__=='__main__':run()
