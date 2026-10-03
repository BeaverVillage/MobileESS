from .common import OUT, SOURCE, SCIENCE, REF, BASE, BASE_LB, UB_REF, sha, read, write, table
from collections import Counter, defaultdict
import gzip
import pickle
import numpy as np

def graph_inputs():
    from v42_bootstrap.m1 import native_inputs
    with (SOURCE / 'DATA.pkl').open('rb') as f:
        bundle = pickle.load(f)[0]
    sites, initial, routes, battery, receipt = native_inputs(bundle)
    arcs = [(s,t,s,t+1,None) for s in sites for t in range(96)]
    arcs += [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    return sites, initial, arcs, battery, receipt

def variable_family(name, stay_count):
    prefix = name.split('[',1)[0]
    if prefix == 'arc':
        return 'stay_arcs' if int(name.rsplit(',',1)[1][:-1]) < stay_count else 'movement_travel_arcs'
    if prefix == 'charge_mode':
        return 'charge_mode'
    return prefix

def fraction_stats(values):
    values = np.asarray(values, dtype=float)
    mask = (values > 1e-6) & (values < 1-1e-6)
    # The diagnostic threshold is independent of all solver tolerances.
    mass = np.minimum(values, 1-values)
    return dict(variable_count=int(values.size), fractional_count=int(mask.sum()),
                fractionality_ratio=float(mask.mean()) if len(values) else 0.,
                fractionality_mass=float(mass.sum()),
                diagnostic_fractionality_mass=float(mass[mask].sum()),
                max_fractionality=float(mass[mask].max(initial=0.)),
                close_to_half_count=int((abs(values-.5)<=.05).sum()))

def census(d, point, sites, initial, arcs, label='M1_ROOT'):
    grouped = defaultdict(list)
    byunit = defaultdict(list)
    byslot = defaultdict(list)
    stay_count = len(sites)*96
    vals = dict(zip(map(str,d['names']),map(float,point)))
    for name, typ, value in zip(d['names'],d['types'],point):
        if typ == 'C':
            continue
        name = str(name)
        family = variable_family(name, stay_count)
        unit, suffix = name.split('[',1)[1][:-1].split(',',1)
        slot = arcs[int(suffix)][1] if name.startswith('arc[') else int(suffix)
        grouped[family].append(value)
        byunit[family,unit].append(value)
        byslot[family,unit,slot].append(value)
    families = []
    for absent in ('location_connection_binary','other_MESS_discrete_helper'):
        grouped.setdefault(absent,[])
    for family, values in grouped.items():
        row = dict(family=family, **fraction_stats(values))
        row['MESS_counts'] = {u:fraction_stats(byunit[family,u]) for u in initial}
        families.append(row)
    rows = []
    for u in initial:
        for t in range(96):
            stay = [vals.get(f'arc[{u},{i*96+t}]',0.) for i in range(len(sites))]
            Y = sum(stay)
            row = dict(MESS=u,slot=t,stay_mass=Y,max_site_share=max(stay),location_split=Y-max(stay),
                       positive_site_count=sum(v>1e-6 for v in stay),
                       C=sum(vals.get(f'Pch[{u},{s},{t}]',0.) for s in sites),
                       D=sum(vals.get(f'Pdis[{u},{s},{t}]',0.) for s in sites),
                       charge_mode=vals[f'charge_mode[{u},{t}]'],SOC=vals[f'SOC[{u},{t}]'])
            for fam in grouped:
                st = fraction_stats(byslot[fam,u,t])
                row[fam+'_fractional_count'] = st['fractional_count']
                row[fam+'_fractionality_mass'] = st['fractionality_mass']
            rows.append(row)
    table(label+'_FRACTIONAL_FAMILY_CENSUS.csv',
          [{**r,'MESS_counts':__import__('json').dumps(r['MESS_counts'],sort_keys=True)} for r in families])
    table(label+'_FRACTIONAL_SLOT_CENSUS.csv',rows)
    result = dict(total_integer_variables=sum(r['variable_count'] for r in families),
                  total_fractional_binaries=sum(r['fractional_count'] for r in families),
                  fractionality_mass=sum(r['fractionality_mass'] for r in families),families=families,
                  diagnostic_fractional_definition='1e-6 < x < 1 - 1e-6',
                  close_to_half_definition='abs(x-0.5) <= 0.05',
                  mass_definition='sum min(x,1-x) over every integer/binary variable; diagnostic threshold used only for fractional counts and separately reported diagnostic mass',
                  absent_location_helpers_have_count_zero=True,
                  absent_discrete_families=['location_connection_binary','other_MESS_discrete_helper'],
                  split_slots=sum(r['positive_site_count']>1 for r in rows),
                  max_location_split=max(r['location_split'] for r in rows),
                  max_site_count=max(r['positive_site_count'] for r in rows),
                  max_C=max(r['C'] for r in rows),max_D=max(r['D'] for r in rows),
                  max_simultaneous_C_D=max(min(r['C'],r['D']) for r in rows))
    write(label+'_FRACTIONAL_SUMMARY.json',result)
    return result,rows

def audit_A(rows,pmax):
    violations = []
    for r in rows:
        for cut,value in [('A1',r['C']-pmax*r['charge_mode']),
                          ('A2',r['D']-pmax*(1-r['charge_mode'])),
                          ('A3',r['C']+r['D']-pmax*r['stay_mass'])]:
            violations.append(dict(MESS=r['MESS'],slot=r['slot'],cut=cut,
                                   C=r['C'],D=r['D'],Y=r['stay_mass'],d=r['charge_mode'],
                                   signed_violation=value,positive_violation=max(0.,value),violated=value>1e-8))
    table('CUT_A_ROOT_VIOLATION.csv',violations)
    summary = dict(violation_tolerance=1e-8,cut_count=len(violations),
                   violated_cut_count=sum(r['violated'] for r in violations),
                   max_violation=max(r['positive_violation'] for r in violations),
                   total_positive_violation=sum(r['positive_violation'] for r in violations),
                   affected_MESS_time=sorted({(r['MESS'],r['slot']) for r in violations if r['violated']}),
                   by_cut={c:dict(violated_count=sum(r['violated'] for r in violations if r['cut']==c),
                                  max_violation=max(r['positive_violation'] for r in violations if r['cut']==c)) for c in ('A1','A2','A3')},
                   top_50_offenders=sorted(violations,key=lambda r:r['positive_violation'],reverse=True)[:50])
    summary['AGGREGATE_CUTS_CURRENT_ROOT_EFFECT'] = 'SUPPORTED' if summary['violated_cut_count'] else 'NOT_SUPPORTED'
    write('CUT_A_ROOT_VIOLATION_SUMMARY.json',summary)
    return summary

def baseline():
    from v42_degen.identity import inputs, signature, digest
    from v42_integrated.matrix import audit
    A,d,B,e,identity,freeze = inputs()
    reference = read(REF/'M1_PR135_MODEL_IDENTITY.json')
    assert signature(B,e) == reference['reference']
    assert (B.shape[0],B.shape[1],int((d['types']=='B').sum()),B.nnz) == (886017,316743,208312,8447855)
    sites,initial,arcs,battery,receipt = graph_inputs()
    path = SOURCE/'LP_reduced_POINT.npz'
    with np.load(path) as z:
        point = z['values'].copy()
    previous = read(SCIENCE/'ROOT_LP_reduced.json')
    audited = audit(A,d,point,tolerance=1e-8)
    assert point.shape == d['names'].shape and audited['PASS']
    assert abs(audited['objective']-previous['objective']) < 1e-12
    assert previous['status']==2 and previous['settings']['Threads']==1
    assert abs(audited['objective']-BASE_LB)<=1e-8
    preservation = dict(PASS=True,base_exact_head=BASE,scientific_signature=reference['reference'],
                        rows=B.shape[0],columns=B.shape[1],binaries=int((d['types']=='B').sum()),nnz=B.nnz,
                        identity=identity,A1_freeze_SHA=identity['A1_freeze_sha256'],
                        NormalAmps_SHA=identity['NormalAmps_authority'],source_data_SHA=sha(SOURCE/'DATA.pkl'),
                        source_route_SHA=receipt['route_file']['sha256'],battery=receipt['battery'],
                        source_asset_SHAs={str(SOURCE/n):sha(SOURCE/n) for n in ('FULL.mps','REDUCED.mps','FULL_A.npz','FULL_DATA.npz','REDUCTION_AXES.npz','DATA.pkl')},
                        native_row_names_source='Exact immutable REDUCED.mps ROWS namespace',
                        voltage=[.95,1.05],margin=0.,P1_P2_objective_SHA=sha(SCIENCE/'M1_OBJECTIVE_CONTRACT.json'),
                        no_new_binary=True,no_route_domain_change=True,A1_optimization_calls=0)
    expected=[];in_rows=False
    with (SOURCE/'REDUCED.mps').open(encoding='utf8') as f:
        for line in f:
            fields=line.split()
            if fields==['ROWS']:in_rows=True;continue
            if fields==['COLUMNS']:break
            if in_rows and len(fields)==2 and fields[0] in ('E','L','G'):expected.append(fields[1])
    assert len(expected)==B.shape[0]
    preservation['native_row_names_SHA']=digest(np.asarray(expected))
    preservation['original_family_row_labels_SHA']=digest(e['row_names'])
    write('M1_STRENGTHENING_BASE_IDENTITY.json',preservation)
    OUT.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(OUT/'BASELINE_ROOT_LP_SOLUTION.npz',names=d['names'],values=point,integer_types=d['types'])
    write('BASELINE_ROOT_LP_RECEIPT.json',dict(PASS=True,mode='READ_ONLY_REUSE',source_path=str(path),source_SHA=sha(path),
          copied_solution_SHA=sha(OUT/'BASELINE_ROOT_LP_SOLUTION.npz'),
          source_LP_result_SHA=sha(SCIENCE/'ROOT_LP_reduced.json'),source_LP=previous,
          all_full_rows_audit=audited,reference_root_LB=BASE_LB,primal_objective=audited['objective'],
          primal_minus_reference_root_LB=audited['objective']-BASE_LB,objective_match_tolerance=1e-8,
          model_identity_SHA=sha(OUT/'M1_STRENGTHENING_BASE_IDENTITY.json'),
          baseline_new_optimize_calls=0,integer_solution=False,UB_certificate=None))
    census_result,rows=census(d,point,sites,initial,arcs)
    violations=audit_A(rows,battery.p_limit)
    print('BASELINE',audited,'CENSUS',census_result['total_fractional_binaries'],census_result['fractionality_mass'],
          'A',violations['violated_cut_count'],violations['max_violation'],flush=True)
    return A,d,B,e,point,sites,initial,arcs,battery

if __name__=='__main__':
    baseline()
