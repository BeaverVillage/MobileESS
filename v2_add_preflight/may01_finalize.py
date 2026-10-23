"""Finalize provenance and classifications; no simulation or solver calls."""
import csv,gzip,json
from collections import defaultdict
import numpy as np
from .may01_common import *

def evidence():
    init();native=read(OUT/'MESS8_COMPACT_NATIVE0_BUILD_REPORT.json');assert native['all_Native_rows_literal_original']
    # Add the source-winding diagnostic to the common hardware comparison.
    rows=list(csv.DictReader((OUT/'MAY01_SVR_HARDWARE_COMPARISON.csv').open(encoding='utf-8')))
    yy=read(OUT/'SOURCE_YY_PORT_TIME_COMPARISON.json');b=yy['cases'][0]['actual']
    if not any(r['candidate']=='H0_SOURCE_YY' for r in rows):
        rows.append(dict(candidate='H0_SOURCE_YY',banks=3,global_loading_percent=100*b['rho_global'],MV_percent=100*b['rho_MV'],LV_percent=100*b['rho_LV'],
            Vmin=b['event_Vmin'],Vmax=b['event_Vmax'],eval_Vmin=b['evaluation_event_Vmin'],eval_Vmax=b['evaluation_event_Vmax'],
            low_seconds=b['voltage_violation_seconds']['low'],high_seconds=b['voltage_violation_seconds']['high'],
            full_TIME_PASS=False,evaluated_TIME_PASS=b['evaluated_TIME_PASS'],Planning_TIME_PASS=False,selected=False,
            receipt=str(RUN/'source_yy/ZERO/2025-05-01_ACTUAL/RECEIPT.json')))
        table('MAY01_SVR_HARDWARE_COMPARISON.csv',rows)
    certificate=read(OUT/'MAY01_ALL24_PORT_VOLTAGE_CERTIFICATION.json')
    certificate['source_YY_diagnostic']=dict(hardware=record(OUT/'SOURCE_YY_ALL24_HARDWARE_READBACK.json'),
        envelope=record(OUT/'SOURCE_YY_ALL24_PORT_ENVELOPE.json'),TIME_Fresh=record(OUT/'SOURCE_YY_PORT_TIME_COMPARISON.json'),
        all24_components_thermal_ready=True,whole120_operational_voltage_PASS=False,Primary_frozen=False)
    put('MAY01_ALL24_PORT_VOLTAGE_CERTIFICATION.json',certificate)
    mapping=list(csv.DictReader((OUT/'LITERAL_NATIVE_ORIGINAL_ROW_ID_MAP.csv').open(encoding='utf-8')))
    initial_count=native['rows']-415592
    initial=mapping[:initial_count];assert len(initial)==initial_count
    keep=defaultdict(set)
    for r in initial:keep[int(r['slot'])].add(int(r['original_row']))
    proof=list(csv.DictReader((OUT/'PRESCREENING_PROOF_AND_REMOVED_ROWS.csv').open(encoding='utf-8')))
    proof=[r for r in proof if r['family']!='ON_DEMAND_ORIGINAL_DEFINING_EQUALITY']
    for r in proof:r['rounding_proof_index']=str(OUT/'ORIGINAL_COMPONENT_ROUNDING_BOUND_AUDIT.json')
    total=0
    for t in range(96):
        p=RUN/'compact'/f'{t:02d}'
        with np.load(p/'AUXILIARY_EQUALITY_MAP.npz') as z:a={k:z[k] for k in z.files}
        inactive=np.array([int(i) not in keep[t] for i in a['original_row']])
        target=p/'INITIAL_UNMATERIALIZED_EQUALITY_IDS.npz'
        np.savez_compressed(target,original_row=a['original_row'][inactive],original_column=a['original_column'][inactive])
        total+=int(inactive.sum());rec=record(target)
        proof.append(dict(slot=t,family='ON_DEMAND_ORIGINAL_DEFINING_EQUALITY',removed_rows=int(inactive.sum()),
            original_IDs_and_bounds=rec['path'],archive_sha256=rec['sha256'],selector='all entries',
            proof='Unique defining equality; activate literal original row and original variable bounds when consumed',
            restoration='Original MATRIX/DOMAIN rows or full C/constant lift, all IDs retained',objective_rows_removed=0,
            rounding_proof_index='Native active rows use literal original coefficients, no projection products'))
    assert total==3290976-native['initial_auxiliaries_materialized']
    table('PRESCREENING_PROOF_AND_REMOVED_ROWS.csv',proof)
    eq=read(OUT/'AUXILIARY_EQUALITY_RESTORATION_MAP.json')
    eq.update(scope='Complete reconstruction map; adopted Native materializes required subset lazily',
        initial_Native_aux_materialized=native['initial_auxiliaries_materialized'],initial_unmaterialized_equalities=total)
    put('AUXILIARY_EQUALITY_RESTORATION_MAP.json',eq)
    census=list(csv.DictReader((OUT/'FULL_CONSTRAINT_FAMILY_CENSUS.csv').open(encoding='utf-8')))
    projected={r['family']:r for r in census if r['scope']=='PROJECTED_GRID_96'}
    for r in census:
        r['structurally_duplicate_original_ID_rows']=0;r['unproved_expression_duplicates_removed']=0
        r['phase_time_terminal_identity_preserved']=True
        if r['scope']=='REFERENCE_GRID':
            p=projected.get(r['family'],{})
            r['bound_proved_safe_rows']=p.get('bound_proved_safe_rows',0)
            r['exact_constant_response_rows']=p.get('exact_constant_response_rows','NOT_A_RESPONSE_ROW')
            r['constraint_generation_eligible_rows']=0 if r['family'].endswith('binding') else int(r['rows'])-int(r['bound_proved_safe_rows'])
            r['equivalence_required_for_elimination']='Original defining equality + full domain reconstruction' if r['family'].endswith('binding') else 'All-face original-coordinate oracle or certified bound'
        elif r['scope']=='PROJECTED_GRID_96':
            if r['family'].startswith('parent_line_thermal_face') and not r.get('shared_rho_deduplicated'):
                r['columns']=int(r['columns'])-95;r['shared_rho_deduplicated']=True
            r['columns_definition']='Distinct global control coordinates; rho counted once'
        else:
            r['bound_proved_safe_rows']=0;r['constraint_generation_eligible_rows']=0
            r['equivalence_required_for_elimination']='No mobility row removed'
    table('FULL_CONSTRAINT_FAMILY_CENSUS.csv',census)
    print('FINAL CLASSIFICATIONS',total,'unmaterialized exact equalities',flush=True)

if __name__=='__main__':evidence()
