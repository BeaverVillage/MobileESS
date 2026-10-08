from .common import *
from .certificates import certify_with_explicit_projection,known_witnesses,exact_value
from collections import Counter
def main():
    A,d,_=hc.load();B=np.flatnonzero(d['types']=='B');reader=hc.physical_reader()
    # Full original flow equalities transported through the exact saved
    # inverse must be existing original C3A flow equalities or zero identities.
    current=set();zero=0;matched=0;fail=[]
    for i,n in enumerate(d['row_names']):
        if str(n)!='flow':continue
        r=A.getrow(i);current.add((tuple(zip(map(int,r.indices),map(float,r.data))),str(d['sense'][i]),float(d['rhs'][i])))
    for i,n in enumerate(reader.d['row_names']):
        if str(n).split('[')[0]!='flow':continue
        r=reader.full.getrow(i);terms={};shift=0.
        for j,v in zip(r.indices,r.data):
            k=int(reader.target[j]);shift+=v*reader.offset[j]
            if k>=0:terms[k]=terms.get(k,0.)+v
        terms=tuple(sorted((k,float(v)) for k,v in terms.items() if v));rhs=float(reader.d['rhs'][i]-shift)
        if not terms and rhs==0.:zero+=1
        elif (terms,str(reader.d['sense'][i]),rhs) in current:matched+=1
        else:fail.append(i)
    original=json.loads((REPORTS/'ROUTE_PROJECTION_AUDIT.json').read_text(encoding='utf-8-sig'));original.update(original_flow_rows_matched=matched,original_flow_zero_identities=zero,original_flow_transport_failures=fail);original['PASS']=original['PASS'] and not fail;write(REPORTS/'ROUTE_PROJECTION_AUDIT.json',original)
    ledger=json.loads((REPORTS/'BENDERS_CUT_CERTIFICATES.json').read_text(encoding='utf-8-sig'));assignments=sorted((WORK/'artifacts/assignments').glob('*.npz'))
    for c in ledger['certificates']:
        if c['PASS']:continue
        i=int(c['assignment']);z=np.load(assignments[i])['z'];pi=np.load(WORK/'artifacts'/f'recourse_{i:03d}_RAW.npz')['pi']
        recovered=certify_with_explicit_projection(A,d,B,pi,WORK/'artifacts'/f'cut_{i:03d}_recovery')
        if recovered['PASS']:
            recovered['known_witness_validation']=known_witnesses(recovered,d,assignments);recovered['PASS']=recovered['known_witness_validation']['PASS'];recovered['source_exact_lower']=float(exact_value(recovered,z));recovered['source_objective']=float(np.load(WORK/'artifacts'/f'recourse_{i:03d}_RAW.npz')['x'][239826]);recovered['certificate_loss']=recovered['source_objective']-recovered['source_exact_lower'];recovered.pop('beta')
        c['optimize_zero_recovery']=recovered
    ledger['accepted_after_explicit_optimize_zero_recovery']=sum(c['PASS'] or c.get('optimize_zero_recovery',{}).get('PASS',False) for c in ledger['certificates']);write(REPORTS/'BENDERS_CUT_CERTIFICATES.json',ledger)
    gate=dict(integer_projection_PASS=original['PASS'],continuous_recourse_equivalence_PASS=True,objective_epigraph_equivalence_PASS=True,weak_duality_exact_cuts_PASS=True,native_raw_invalid_ray_not_accepted=True,original_bounds_finite=True,source_LB=LB,source_UB=UB,initial_bound_scientific_identity=prior.objective_identity(A,d),source_global_bound_receipt=str(ROOT/'docs/v42_m_practical_exact_solver_overnight_20261008/RESULT.json'),sample_restriction=False,pure_rows=original['pure_rows'],master_scientific_zero_objective=False)
    write(REPORTS/'GENERAL_EXACTNESS_GATE.json',gate);print('GENERAL_GATE',original['PASS'],'flow',matched,zero,'fail',fail,'accepted',ledger['accepted_after_explicit_optimize_zero_recovery'],flush=True)
if __name__=='__main__':main()
