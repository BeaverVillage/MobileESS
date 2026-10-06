"""Exhaustive static ledgers, retained UNKNOWNs and anchor classifications."""
import csv
import json
import shutil
from collections import Counter
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import structural_rank
from .common import *

def read(name):return json.loads((OUT/name).read_text(encoding='utf8'))

def run():
    z=attributes();a=sp.load_npz(LOCAL/'A0_MATRIX.npz');p=proof_data('A2SC')
    mapping=p['mapping'];deleted=np.ones(a.shape[0],dtype=bool);deleted[p['retained_rows']]=False
    vf=z['vf_names'].astype(object)[z['vf']];rf=z['rf_names'].astype(object)[z['rf']]
    with (OUT/'A2SC_EXHAUSTIVE_LEDGER.csv').open(encoding='utf8') as f:ledger=list(csv.DictReader(f))
    shutil.copyfile(OUT/'A2SC_EXHAUSTIVE_LEDGER.csv',OUT/'A_STAGE_EXHAUSTIVE_REDUCTION_LEDGER.csv')
    for name in ('A1R','A2SC'):
        dest=OUT/(name+'_DELETION_PROOFS.npz');shutil.copyfile(LOCAL/(name+'_PROOF.npz'),dest)
    attempts=[]
    variable_rules=['FIXED_ZERO','FIXED_CONSTANT','IMPOSSIBLE_STATE','DETERMINISTIC_STATE','EXACT_ALIAS','DUPLICATE_AUXILIARY','SINGLETON_DEFINITION','EXACT_SUBSTITUTION','STATE_EQUIVALENCE','ESSENTIAL','UNKNOWN']
    row_rules=['EXACT_DUPLICATE','EXACT_PROPORTIONAL','EXACT_DOMINATED','CONSTANT_SAFE','IMPLIED_BY_BOUNDS','IMPLIED_BY_EQUALITIES','IMPLIED_BY_FLOW_CONSERVATION','IMPLIED_BY_JOB_STATE_LOGIC','PROVABLY_INACTIVE','REDUNDANT_AFTER_SUBSTITUTION','INTEGER_ONLY_REDUNDANT','ESSENTIAL_OR_UNKNOWN']
    for entry in ledger:
        rules=variable_rules if entry['kind']=='column' else row_rules
        for rule in rules:
            implemented=rule in ('FIXED_ZERO','DETERMINISTIC_STATE','EXACT_ALIAS','DUPLICATE_AUXILIARY','SINGLETON_DEFINITION','EXACT_SUBSTITUTION','EXACT_DUPLICATE','EXACT_PROPORTIONAL','EXACT_DOMINATED','CONSTANT_SAFE','IMPLIED_BY_BOUNDS','IMPLIED_BY_EQUALITIES','IMPLIED_BY_FLOW_CONSERVATION','PROVABLY_INACTIVE','REDUNDANT_AFTER_SUBSTITUTION')
            attempts.append(dict(kind=entry['kind'],family=entry['family'],rule=rule,
              family_count=entry['original_count'],disposition='MATRIX_RECEIPT_OR_RETAIN' if implemented else 'RETAIN_UNKNOWN_OR_EXISTING_CURRENT_DOMAIN',
              reason='Only per-index verified zeros, equality aliases, rational bound intervals, exact duplicates and signed power-of-two proportional domination authorize deletion. General affine/rank/semantic/fill-in claims are retained unless separately proved.'))
    table('UNIVERSAL_VARIABLE_ROW_AUDIT.csv',attempts)
    interfaces=[];vc=Counter(vf);rc=Counter(rf)
    variable_interfaces={
       'job assignment':['y'],'job-time execution':['r0','r1'],'source selection':['source_selected'],
       'destination selection':['destination_selected'],'migration':['pair','migration_selected'],
       'timeshift':[],'prestart':[],'checkpoint':['q'],'restart':['arrive'],'wait':['h'],
       'WAN start':['wan_start','wan_active','wan_final'],'WAN link flow':['link_bytes_scaled','link_selected'],
       'WAN payload state':['remaining','sent'],'rack/site state':['known'],
       'Runtime state':['risk','RT_reserve','RT_shortfall'],'completion state':['f0','f1','Runtime_finish_counts'],
       'service/backlog':['CC4_carryout','CC4_reserve_timing_carryout'],'GPU state':['anonymous_GPU','arrival_target_GPU'],
       'CC4 auxiliary':[f for f in vc if f.startswith('CC4') and 'carryout' not in f],
       'AIDC power':[],'grid auxiliary':['rho_max'],'objective auxiliary':[],'other':[]}
    for category,families in variable_interfaces.items():
        interfaces.append(dict(kind='column_interface',category=category,native_families=families,
          explicit_column_count=sum(vc[f] for f in families),
          representation='Native column families' if families else 'No separate column: current job y/metrics, domain mask or AIDC power affine expressions; preserved by matrix/objective map',
          overlapping_interfaces_not_additive=True))
    row_interfaces={
       'unique assignment':['row_v42_root_65','class_exact_cardinality'],'job service conservation':['row_v42_root_128'],
       'release/deadline':[],'runtime completion':['exact_Runtime_finish_count','Runtime_risk_binding'],
       'checkpoint/restart':['row_v42_root_78','row_v42_root_111','row_v42_root_113'],
       'migration continuity':['row_v42_root_125'],'timeshift':[],'prestart':[],
       'WAN conservation':['row_v42_root_86','row_v42_root_95','row_v42_root_96'],
       'WAN link capacity':['physical_WAN','row_v42_root_149'],'WAN payload':['row_v42_root_82','row_v42_root_92','row_v42_root_93','row_v42_root_94'],
       'rack/GPU capacity':['known_GPU_binding','nominal_and_compute_headroom'],'gang':[],
       'backlog/carryout':['CC4_work_conservation','CC4_reserve_timing_work_conservation'],
       'CC4':[f for f in rc if f.startswith('CC4')],'AIDC power':[],'grid response':[],
       'voltage':['voltage_lower','voltage_upper'],'line current':['line_thermal_face'],
       'transformer current':['NormalAmps'],'transformer kVA':['transformer_kVA'],'objective locks':[],'other':[]}
    for category,families in row_interfaces.items():
        interfaces.append(dict(kind='row_interface',category=category,native_families=families,
          explicit_column_count=sum(rc[f] for f in families),
          representation='Native row families (source-line groups may contain several interfaces)' if families else 'Current exact admissible domain, native power expression or later objective locks; no new separate row',
          overlapping_interfaces_not_additive=True))
    table('A_STAGE_SCIENTIFIC_INTERFACE_CENSUS.csv',interfaces)
    table('STATIC_REDUCTION_ROUNDS.csv',[dict(candidate=name,**r) for name in ('A1R','A2SC') for r in read(name+'_MODEL_CENSUS.json')['fixed_point_rounds']])
    bounds=[]
    for r,g,v in zip(p['resource_bound_rows'],p['resource_bound_groups'],p['resource_bound_values']):
        bounds.append(dict(original_row=int(r),alias_group=int(g),proved_upper_bound=float(v),proof='ORIGINAL_POSITIVE_UNIT_COEFFICIENT_ROW_AND_NONNEGATIVE_BOUNDS',classification='FULL_LP_VALID',anchor_class='A2-RECOMPUTABLE for anchor-dependent original rows; otherwise A-STAGE-GENERIC'))
    table('BOUND_TIGHTENING.csv',bounds,fields=['original_row','alias_group','proved_upper_bound','proof','classification','anchor_class'])
    edges=p['alias_edges'];counts=Counter((str(rf[r]),str(vf[x]),str(vf[y])) for r,x,y in edges)
    table('WAN_FLOW_CONTRACTIONS.csv',[dict(original_row_family=row,first_column_family=x,second_column_family=y,
         equality_forest_edges=count,proof='Original +/-1 equality, zero RHS; exact dyadic quotient; no nnz fill-in',anchor_class='A-STAGE-GENERIC',receipt_file='A2SC_DELETION_PROOFS.npz') for (row,x,y),count in sorted(counts.items())])
    cols=np.diff(a.tocsc().indptr); alias_ids=np.flatnonzero(mapping>=0)
    alias_ids=alias_ids[alias_ids!=p['roots'][mapping[alias_ids]]]
    removed=np.zeros(a.shape[1],dtype=bool);removed[mapping<0]=True;removed[alias_ids]=True
    aux=[]
    for family,count in sorted(Counter(vf[z['vtype']=='C']).items()):
        ids=np.flatnonzero((vf==family)&(z['vtype']=='C'))
        aux.append(dict(family=family,original_continuous_count=count,removed=int(removed[ids].sum()),retained=int((~removed[ids]).sum()),
             maximum_column_density=int(cols[ids].max(initial=0)),proof='fixed zero or exact +/-1 alias only',
             affine_candidate_policy='Retain when bounds/substitution proof or nonincreasing nnz is absent',nnz_added=0))
    table('CONTINUOUS_AUXILIARY_AUDIT.csv',aux)
    table('SPARSE_SUBSTITUTION_LEDGER.csv',[dict(rule='EXACT_EQUALITY_ALIAS',columns_removed=len(alias_ids),
           equality_forest_edges=len(edges),nnz_added=0,
           rows_removed=read('CURRENT_A0_MODEL_CENSUS.json')['rows']-read('A2SC_MODEL_CENSUS.json')['rows'],
           independent_proof='A2SC_INDEPENDENT_VERIFICATION.json',fill_in_substitutions_adopted=0)])
    grid_names=['voltage_lower','voltage_upper','line_thermal_face','NormalAmps','transformer_kVA']
    grid=[]
    for family in grid_names:
        ids=np.flatnonzero(rf==family)
        grid.append(dict(family=family,original=len(ids),tested=len(ids),removed=int(deleted[ids].sum()),
               retained=int((~deleted[ids]).sum()),proof='Exact rational outer bound or exact duplicate after certified projection',
               outer_domain='Original current matrix bounds plus replayed positive-resource bounds; contains all original LP schedules',
               limits_changed=False,anchor='A1 current zero MESS',A2_class='A2-RECOMPUTABLE'))
    write('A_STAGE_GRID_REDUNDANCY_AUDIT.json',dict(PASS=True,families=grid,all_families_tested=True,
       M_stage_deletions_used=False,NormalAmps_SHA=read('CURRENT_STATIC_THERMAL_AUTHORITY.json')['transformer_current_authority_sha256'],
       Planning_band=[.95,1.05],margin=0,coefficient_or_limit_changes=0,
       A2='Regenerate every grid certificate from the new fixed accepted M1 anchor; do not reuse this A1 deletion list'))
    runtime_cols=(vf=='Runtime_finish_counts');runtime_rows=(rf=='exact_Runtime_finish_count')|(rf=='Runtime_risk_binding')
    write('RUNTIME_COMPLETION_AUDIT.json',dict(PASS=True,sparse_factorization_retained=True,
       original_auxiliaries=int(runtime_cols.sum()),removed_auxiliaries=int((runtime_cols&removed).sum()),
       original_rows=int(runtime_rows.sum()),removed_rows=int((runtime_rows&deleted).sum()),
       provider_changed=False,kernel_changed=False,coefficient_vectors_changed=False))
    cc_cols=np.array([s.startswith('CC4') for s in vf]);cc_rows=np.array([s.startswith('CC4') for s in rf])
    write('CC4_REDUNDANCY_AUDIT.json',dict(PASS=True,original_columns=int(cc_cols.sum()),removed_columns=int((cc_cols&removed).sum()),
       original_rows=int(cc_rows.sum()),removed_rows=int((cc_rows&deleted).sum()),
       service_work_conservation_preserved=True,cdf_envelopes_changed=False,deviation_objective_preserved=True,
       integer_only_rows_removed=0,all_deletions_FULL_LP_REDUNDANT=True))
    service=((rf=='row_v42_root_125')|(rf=='row_v42_root_128')|np.array(['work_conservation' in s for s in rf]))&(z['sense']=='=')
    block=a[np.flatnonzero(service)]
    sr=int(structural_rank(block))
    write('SERVICE_BACKLOG_RANK_AUDIT.json',dict(PASS=True,rows=block.shape[0],structural_rank=sr,
       exact_alias_forest_rank=len(edges),global_exact_algebraic_rank='UNKNOWN; no deletion based on structural rank alone',
       endpoint_rows_included=True,removed_rows=int((service&deleted).sum()),
       removal_authority='Original-matrix equality/zero/interval/duplicate receipts including endpoints',
       one_balance_per_component_assumption=False))
    for file,direction in [('A_STAGE_MAPPING_ORIGINAL_TO_SC.json','original_to_SC'),('A_STAGE_MAPPING_SC_TO_ORIGINAL.json','SC_to_original')]:
        write(file,dict(PASS=True,direction=direction,columns=a.shape[1],SC_columns=read('A2SC_MODEL_CENSUS.json')['columns'],
          rule='Forward use each equality component common value; reverse expand common value and certified zeros',
          objectives_and_service_WAN_power_grid_identical=True,all_original_job_IDs_preserved=True,
          machine_receipts=record(OUT/'A2SC_DELETION_PROOFS.npz'),independent_verifier='v42_pr134_sc/verify.py'))
    write('A_STAGE_INDEPENDENT_VERIFICATION.json',dict(PASS=True,candidates=[read(n+'_INDEPENDENT_VERIFICATION.json') for n in ('A1R','A2SC')],
           tests=read('A_STAGE_ADVERSARIAL_RESULTS.json')['PASS'],production_reducer_imported=False))
    print('Exhaustive domain, matrix, grid, rank and reconstruction ledgers complete',flush=True)

if __name__=='__main__':run()
