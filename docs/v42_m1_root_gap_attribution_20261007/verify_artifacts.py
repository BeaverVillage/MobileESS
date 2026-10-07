"""Read-only artifact verification; --final writes only VERIFICATION.json.

No native model construction, optimize call, pipeline execution, process
termination, scientific source mutation, or Git command occurs here.
Interim mode prints a compact snapshot and creates no report file.  Strict
raw numerical feasibility is separate from workflow/provenance integrity.
"""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                  MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
sys.dont_write_bytecode = True
import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PARENT = ROOT/'docs/v42_m1_ultracompact_exact_20261006'
sys.path.insert(0, str(ROOT))
BASE = '1d922c91eb27056a5ccc79c92ef18146707099ab'
KNOWN_LB = .5687116003498334
UB = .6694159238756877
TOL = 1e-8
EXPECTED = {'C3A_A.npz':'45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8',
            'C3A_DATA.npz':'20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467',
            'C3A_VALID_START.npz':'be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5'}
REQUIRED = ['USER_AUTHORIZED_ABORT.json','ABORTED_1H_RUN_SNAPSHOT.json',
    'BASE_AUTHORITY.json','C3A_IDENTITY_AUDIT.json','PURE_LP_RESULT.json',
    'PURE_LP_POINT.npz','DISCRETE_VARIABLE_FAMILY_MAP.csv','FRACTIONALITY_CENSUS.csv',
    'FRACTIONALITY_BY_TIME.csv','FRACTIONALITY_BY_MESS.csv','CRITICAL_LINE_TIME_AUDIT.csv',
    'ROOT_GAP_CAUSAL_TRACE.md','LOCAL_INTEGER_HULL_AUDIT.json',
    'CANDIDATE_VALID_INEQUALITIES.csv','INEQUALITY_INDEPENDENT_VERIFICATION.json',
    'LP_STRENGTHENING_TRACE.csv','SELECTIVE_INTEGRALITY_RESULTS.csv','FINAL_REVIEW_KO.md']


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def truth(value):
    return value is True or str(value).lower() == 'true'


def close(a,b,tolerance=1e-13):
    return abs(float(a)-float(b)) <= tolerance


def normalized_cut(cut):
    return (cut['id'],cut['family'],cut['MESS'],int(cut['slot']),cut['site'],
            tuple(sorted((int(j),float(w)) for j,w in cut['terms'].items() if float(w))),
            float(cut['rhs']))


class Audit:
    def __init__(self, final=False):
        self.final = final
        self.checks = []
        self.inputs = {}
        self.numeric = []
        self.details = {}

    def capture(self,path):
        path = Path(path)
        self.inputs.setdefault(str(path),sha(path))
        return path

    def js(self,name):
        return json.loads(self.capture(OUT/name).read_text(encoding='utf-8'))

    def csv(self,name,path=None):
        with self.capture(path or OUT/name).open(encoding='utf-8',newline='') as stream:
            return list(csv.DictReader(stream))

    def npz(self,name,path=None):
        with np.load(self.capture(path or OUT/name),allow_pickle=False) as archive:
            return {key:archive[key] for key in archive.files}

    def check(self,name,condition,details=None,pending=False):
        self.checks.append(dict(name=name,state='PENDING' if pending else
            'PASS' if bool(condition) else 'FAIL',details=details))

    def matrix_replay(self,A,d,x,label,claimed=None):
        residual = A@x-d['rhs']
        violation = np.where(d['sense']=='=',abs(residual),
            np.where(d['sense']=='<',residual,-residual))
        row = float(violation.max(initial=0))
        bound = float(max((d['lower']-x).max(initial=0),(x-d['upper']).max(initial=0)))
        passed = bool(np.isfinite(x).all() and row <= TOL and bound <= TOL)
        record = dict(label=label,PASS=passed,max_row_violation=row,
                      max_bound_violation=bound,tolerance_unchanged=TOL)
        self.numeric.append(record)
        if claimed is not None:
            self.check(label+'_raw_replay_result_honestly_preserved',
                truth(claimed['PASS']) == passed and
                close(claimed['max_row_violation'],row,1e-12) and
                close(claimed['max_bound_violation'],bound,1e-12),record)
        return record


def selected_matrix(A,d,cuts):
    rr=[];cc=[];vv=[]
    for i,cut in enumerate(cuts):
        for j,w in cut['terms'].items():
            rr.append(i);cc.append(int(j));vv.append(float(w))
    extra = sparse.csr_matrix((vv,(rr,cc)),shape=(len(cuts),A.shape[1]))
    S = sparse.vstack([A,extra],format='csr')
    e = dict(d,rhs=np.r_[d['rhs'],[float(q['rhs']) for q in cuts]],
               sense=np.r_[d['sense'],np.full(len(cuts),'<')])
    return S,e,extra


def verify(final=False, deep=False):
    audit = Audit(final)
    # Record the verifier and all authority/proof readers themselves as inputs.
    audit.capture(__file__)
    for name in ['independent_hull.py','folded_pcs_hull.py','numerical_bound_audit.py']:
        audit.capture(OUT/name)
    scope=audit.js('EXPERIMENT_SCOPE.json')
    audit.check('authorized_experiment_scope_and_budget',
        scope['base_exact_head']==BASE and scope['pure_LP_calls_original_plus_explicitly_authorized_recovery']==2
        and scope['LP_cut_round_limit']==10 and scope['deterministic_batch_size']==32
        and scope['material_global_LB_improvement_threshold']==.001
        and scope['valid_global_LB_baseline']==KNOWN_LB and scope['selective_tests_max']==2
        and scope['selective_TimeLimit']==300 and scope['root_only_max_calls']==1
        and scope['root_only_NodeLimit']==1 and scope['root_only_TimeLimit']==900
        and scope['baseline_rows_deleted']==scope['scientific_changes']==0
        and scope['all_solver_Threads']==1 and scope['root_only_requires_material_valid_global_LB_improvement']
        and scope['LP_objective_gain_is_not_global_bound_gain'] and scope['no_more_full_3600_MILP'])
    base = audit.js('BASE_AUTHORITY.json')
    audit.check('exact_PR162_selected_authority',base['PASS'] and base['exact_base']==BASE
        and base['selected_authority']['selected']=='C3A')
    changed=[]
    for name,expected in base['parent_namespace_hashes'].items():
        path=ROOT/name
        if not path.exists() or sha(path)!=expected:
            changed.append(name)
        if path.exists():audit.capture(path)
    audit.check('parent_namespace_all_hashes_unchanged',not changed,
        dict(files=len(base['parent_namespace_hashes']),changed=changed))
    for name,expected in EXPECTED.items():
        audit.check('selected_'+name+'_SHA256',sha(audit.capture(PARENT/name))==expected)
    A=sparse.load_npz(PARENT/'C3A_A.npz')
    d=audit.npz('',PARENT/'C3A_DATA.npz')
    start=audit.npz('',PARENT/'C3A_VALID_START.npz')['point']
    audit.check('selected_census_exact',(A.shape[0],A.shape[1],int((d['types']=='B').sum()),A.nnz)
        ==(582808,306040,9322,5351612))
    identity=audit.js('C3A_IDENTITY_AUDIT.json')
    audit.check('all_discretes_relaxed_same_bounds',identity['PASS']
        and identity['all_integer_variables_relaxed_same_bounds']
        and not identity['physical_formulation_changed'])

    aborted=audit.js('USER_AUTHORIZED_ABORT.json')
    snapshot=audit.js('ABORTED_1H_RUN_SNAPSHOT.json')
    audit.check('abort_not_completed_TimeLimit_failure_or_restart',
        aborted['classification']=='USER_AUTHORIZED_ABORT_FOR_ROOT_GAP_DIAGNOSIS'
        and aborted['abort_completed'] and not aborted['process_exists_after_stop']
        and all(aborted[k] is False for k in ['completed_one_hour_benchmark','TIME_LIMIT_result',
            'solver_failure','optimization_restarted'])
        and not snapshot['completed_benchmark'] and not snapshot['TimeLimit_result'])
    audit.check('stale_native_observation_not_terminal_runtime',
        aborted['exact_native_Runtime_Work_NodeCount_SolCount_at_termination_available'] is False
        and snapshot['exact_terminal_native_attributes_available'] is False
        and aborted['observation_age_at_abort_seconds']>0)
    for name,receipt in aborted['preserved_files'].items():
        path=OUT/'aborted_1h_provenance'/name
        audit.check('abort_provenance_'+name,sha(audit.capture(path))==receipt['sha256'])
    audit.check('aborted_known_incumbent_preserved',sha(audit.capture(
        OUT/aborted['incumbent_file']))==EXPECTED['C3A_VALID_START.npz'])

    pure=audit.js('PURE_LP_RESULT.json');point=audit.npz('PURE_LP_POINT.npz')
    sizes={'x':A.shape[1],'dual':A.shape[0],'reduced_cost':A.shape[1],
           'slack':A.shape[0],'active':A.shape[0]}
    audit.check('complete_finite_pure_LP_arrays',all(k in point and point[k].shape==(n,)
        and np.isfinite(point[k]).all() for k,n in sizes.items()))
    audit.check('LP_active_indices_and_original_types_preserved',
        np.array_equal(point['active'],abs(point['slack'])<=TOL)
        and np.array_equal(point['original_types'],d['types']))
    pure_replay=audit.matrix_replay(A,d,point['x'],'PURE_LP',pure['independent_relaxed_matrix_replay'])
    audit.check('raw_numeric_FAIL_not_hidden_by_native_OPTIMAL',
        truth(pure['PASS']) == (pure['Status']==2 and pure_replay['PASS']))
    audit.check('requested_pure_LP_parameters_and_no_gap_relabel',
        all(pure['settings'][k]==v for k,v in dict(Method=2,Threads=1,Crossover=0,
            FeasibilityTol=TOL,OptimalityTol=TOL,IntFeasTol=TOL).items())
        and pure['no_native_MILP_gap_reported'] and pure['integer_optimum_unknown'])
    pure_calls=sum(int(audit.js(n)['optimize_calls']) for n in
                   ['PURE_LP_ONCE.json','PURE_LP_RECOVERY_ONCE.json'])
    authorization=audit.js('EXTRA_LP_USER_AUTHORIZATION.json')
    audit.check('exactly_two_pure_LP_calls_recovery_human_authorized',
        pure_calls==2 and authorization['explicit_human_authorization'] is True
        and pure['total_pure_LP_calls_including_failed_capture']==2)

    mapping=audit.csv('DISCRETE_VARIABLE_FAMILY_MAP.csv')
    ledger={int(r['column']):r for r in audit.csv('',PARENT/'ALL_COLUMN_DECISIONS.csv')}
    mapped={int(r['column']):r for r in mapping}
    discrete=set(map(int,np.flatnonzero(d['types']!='C')))
    audit.check('every_9322_original_discrete_mapped_once',len(mapping)==9322
        and len(mapped)==9322 and set(mapped)==discrete)
    audit.check('semantic_map_matches_typed_axis_and_ledger',all(
        str(d['names'][j])==r['name'] and r['family']==ledger[j]['family']
        and float(r['LP_value'])==point['x'][j]
        and close(r['min_x_1mx'],min(point['x'][j],1-point['x'][j]))
        and r['ledger_decision']==ledger[j]['decision']
        and truth(r['fractional'])==bool(TOL<point['x'][j]<1-TOL)
        for j,r in mapped.items()))
    semantic_errors=[]
    for r in mapping:
        family,axes=r['name'].split('[',1);axes=axes[:-1].split(',')
        unit,site,t=(axes[0],'ALL',axes[1]) if family=='charge_mode' else axes
        if (family,unit,site,int(t))!=(r['family'],r['MESS'],r['site'],int(r['slot'])):
            semantic_errors.append(r['name'])
    audit.check('every_discrete_unit_site_time_from_original_named_axis',not semantic_errors,
                dict(errors=semantic_errors))
    semantic=audit.js('SEMANTIC_AUTHORITY.json')
    source_checks=[(PARENT/'ALL_COLUMN_DECISIONS.csv',semantic['ledger_SHA']),
                   (ROOT/'v42_native/mess.py',semantic['native_source_SHA']),
                   (ROOT/'v42_supercompact/formulation.py',semantic['compact_source_SHA'])]
    route=semantic['graph_receipt']['route_file']
    source_checks.append((Path(route['path']),route['sha256']))
    audit.check('semantic_authority_sources_unchanged',semantic['PASS']
        and semantic['discrete_columns_mapped']==9322
        and semantic['unchanged_P1_P2'] and all(sha(audit.capture(p))==h for p,h in source_checks))
    by_family=Counter(r['family'] for r in mapping)
    fractional=Counter(r['family'] for r in mapping if truth(r['fractional']))
    audit.check('real_discrete_families',by_family=={'node_activity':8938,'charge_mode':384})
    for name,groups in [('FRACTIONALITY_CENSUS.csv',['family']),
                        ('FRACTIONALITY_BY_MESS.csv',['MESS','family'])]:
        records=audit.csv(name)
        expected=defaultdict(lambda:[0,0])
        for r in mapping:
            key=tuple(r[k] for k in groups);expected[key][0]+=1
            expected[key][1]+=truth(r['fractional'])
        actual={tuple(r[k] for k in groups):[int(r['binary_count']),int(r['fractional_count'])]
                for r in records if int(r['binary_count'])}
        audit.check(name+'_counts_reconcile',actual==dict(expected))
        metrics_errors=[]
        for r in records:
            vals=np.asarray([float(m['LP_value']) for m in mapping
                if tuple(m[k] for k in groups)==tuple(r[k] for k in groups)],dtype=float)
            if not len(vals):continue
            mass=np.minimum(vals,1-vals)
            metrics={'fractionality_rate':np.mean((vals>TOL)&(vals<1-TOL)),
                'max_min_x_1mx':mass.max(initial=0),'sum_min_x_1mx':mass.sum(),
                'mean_min_x_1mx':mass.mean()}
            if any(not close(r[k],v,1e-10) for k,v in metrics.items()):
                metrics_errors.append(tuple(r[k] for k in groups))
        audit.check(name+'_fractionality_metrics_reconcile',not metrics_errors,
                    dict(errors=metrics_errors))
    time_rows=audit.csv('FRACTIONALITY_BY_TIME.csv')
    expected=defaultdict(lambda:[0,0])
    for r in mapping:
        key=(r['MESS'],int(r['slot']));expected[key][0]+=1
        expected[key][1]+=truth(r['fractional'])
    actual={(r['MESS'],int(r['slot'])):[int(r['binary_count']),int(r['fractional_count'])]
            for r in time_rows}
    audit.check('byTime_terminal96_and_all_discretes_reconcile',len(time_rows)==388
        and len(actual)==388 and all(actual[k]==v for k,v in expected.items())
        and sum(v[0] for v in actual.values())==9322
        and sum(v[1] for v in actual.values())==sum(fractional.values())
        and sum(int(r['slot'])==96 for r in time_rows)==4,
        dict(binary_total=sum(v[0] for v in actual.values()),fractional_total=sum(v[1] for v in actual.values())))

    proof=audit.js('INEQUALITY_INDEPENDENT_VERIFICATION.json')
    folded=audit.js('FOLDED_INEQUALITY_INDEPENDENT_VERIFICATION.json')
    mutations=audit.js('INEQUALITY_MUTATION_REJECTION.json')
    hull=audit.js('LOCAL_INTEGER_HULL_AUDIT.json')
    audit.check('independent_exact_validity_and_pointwise_P1_P2_preservation',
        proof['PASS'] and folded['PASS'] and not proof['production_constructor_imported_or_called']
        and proof['rational_local_vertex_test'] and proof['integer_feasible_set_preserved_if_adopted']
        and proof['original_P1_P2_preserved_for_every_integer_feasible_point']
        and not proof['rejected'] and not folded['rejected'])
    mutation_changed=[]
    for name,expected_hash in mutations['immutable_proof_file_hashes_after'].items():
        if sha(audit.capture(OUT/name))!=expected_hash:mutation_changed.append(name)
    audit.check('fourteen_mutations_rejected_without_overwriting_proof',mutations['PASS']
        and mutations['mutation_count']==mutations['rejected_count']==14
        and all(r['rejected'] for r in mutations['mutations'])
        and mutations['immutable_proof_file_hashes_before']==mutations['immutable_proof_file_hashes_after']
        and not mutation_changed,dict(changed=mutation_changed))
    audit.check('local_hull_conservative_scope_not_global_hull',hull['PASS']
        and hull['scope']=='ONE_SLOT_ONLY' and not hull['complete_global_hull']
        and hull['no_solver_calls'] and hull['rational_arithmetic']
        and all(not b['full_global_integer_hull_claim'] for b in hull['blocks']))

    candidates=audit.js('CANDIDATE_COEFFICIENTS.json')
    candidate_map={r['id']:r for r in candidates}
    basic_approved={r['id'] for r in proof['candidate_results'] if r['PASS']}
    folded_approved={r['id'] for r in folded['reports'] if r['PASS']}
    audit.check('all_candidate_IDs_independently_verified_once',
        len(candidate_map)==len(candidates)==proof['total_candidate_count']
        and set(candidate_map)==basic_approved|folded_approved)
    candidate_csv=audit.csv('CANDIDATE_VALID_INEQUALITIES.csv')
    audit.check('candidate_CSV_matches_candidate_pool',len(candidate_csv)==len(candidates)
        and {r['id'] for r in candidate_csv}==set(candidate_map))
    selected=audit.js('SELECTED_CUTS.json')
    audit.check('selected_cuts_unique_exact_subset_of_proven_pool',
        len({r['id'] for r in selected})==len(selected)
        and all(r['id'] in candidate_map and normalized_cut(r)==normalized_cut(candidate_map[r['id']])
                for r in selected))
    selected_start_worst=max((sum(float(w)*start[int(j)] for j,w in r['terms'].items())
        -float(r['rhs']) for r in selected),default=0.)
    audit.check('validated_start_satisfies_selected_cuts',selected_start_worst<=TOL,
                dict(max_signed_violation=selected_start_worst,tolerance=TOL))

    trace=audit.csv('LP_STRENGTHENING_TRACE.csv')
    trace_by_round={int(float(r['round'])):r for r in trace}
    audit.check('round_trace_unique_contiguous_up_to_ten',len(trace)==len(trace_by_round)
        and sorted(trace_by_round)==list(range(len(trace))) and len(trace)-1<=10)
    token_records=[]
    for path in sorted(OUT.glob('LP_ROUND_*_ONCE.json')):
        token=json.loads(audit.capture(path).read_text(encoding='utf-8'))
        round_no=int(path.name.split('_')[2]);calls=int(token['optimize_calls'])
        token_records.append(dict(round=round_no,calls=calls,path=path.name,
                                  operator_checkpoint=token.get('operator_checkpoint',False)))
        audit.check(path.name+'_one_call_guard',1<=round_no<=10 and calls in (0,1)
            and (calls==0 and token.get('operator_checkpoint',False) or
                 calls==1 and int(token['round'])==round_no))
        if calls and round_no not in trace_by_round:
            audit.check(path.name+'_result_finished',False,pending=not final)
    audit.check('at_most_ten_unique_LP_round_optimize_calls',
        sum(r['calls'] for r in token_records)<=10
        and len({r['round'] for r in token_records if r['calls']})
           ==sum(r['calls'] for r in token_records))
    audit.check('every_completed_cut_round_has_exactly_one_guarded_call',
        all(sum(t['calls'] for t in token_records if t['round']==j)==1
            for j in trace_by_round if j>0))
    audit.details['LP_round_tokens']=token_records
    if (OUT/'ROUND_BOUNDARY_CHECKPOINT_TOKEN.json').exists():
        checkpoint=audit.js('ROUND_BOUNDARY_CHECKPOINT_TOKEN.json')
        transition=audit.js('CUT_LOOP_CHECKPOINT_TRANSITION.json')
        audit.check('checkpoint_no_solve_no_repeat_no_scientific_change',
            checkpoint['optimize_calls']==0 and checkpoint['operator_checkpoint']
            and transition['round1_completed_before_pause'] and not transition['active_solve_terminated']
            and not transition['round1_repeated'] and not transition['scientific_parameters_changed']
            and transition['round2_precheckpoint_optimize_calls']==0)
    certificates={}
    for round_no,r in sorted(trace_by_round.items()):
        n=int(float(r['total_cuts']));prefix=selected[:n]
        audit.check(f'round_{round_no}_matrix_size_prefix_no_row_deletion',
            n<=len(selected) and int(float(r['rows']))==A.shape[0]+n
            and int(float(r['columns']))==A.shape[1]
            and int(float(r['nnz']))==A.nnz+sum(len(q['terms']) for q in prefix)
            and n==32*round_no)
        if round_no==0:continue
        native_log=audit.capture(OUT/f'LP_STRENGTHENING_ROUND_{round_no:02d}.log').read_text(encoding='utf-8')
        native_size=re.search(r'Optimize a model with (\d+) rows, (\d+) columns and (\d+) nonzeros',native_log)
        native_params={k:v for k,v in re.findall(r'^([A-Za-z]+)\s+(\S+)\s*$',native_log,re.M)}
        audit.check(f'round_{round_no}_native_log_size_method_threads_tolerances',
            native_size is not None and tuple(map(int,native_size.groups()))==
                (A.shape[0]+n,A.shape[1],A.nnz+sum(len(q['terms']) for q in prefix))
            and all(k in native_params and float(native_params[k])==v for k,v in
                dict(Method=2,Threads=1,Crossover=0,FeasibilityTol=TOL,OptimalityTol=TOL,IntFeasTol=TOL).items()))
        result=audit.js(f'LP_ROUND_{round_no:02d}_RESULT.json')
        xp=audit.npz(f'LP_ROUND_{round_no:02d}_POINT.npz')
        audit.check(f'round_{round_no}_point_dimensions_and_finite',
            xp['x'].shape==(A.shape[1],) and np.isfinite(xp['x']).all()
            and (round_no==1 or all(k in xp and xp[k].shape==(size,)
                and np.isfinite(xp[k]).all() for k,size in
                [('dual',A.shape[0]+n),('slack',A.shape[0]+n),('reduced_cost',A.shape[1])])))
        numeric=audit.matrix_replay(A,d,xp['x'],f'LP_ROUND_{round_no:02d}',result['independent_replay'])
        extra_max=max((sum(float(w)*xp['x'][int(j)] for j,w in q['terms'].items())
                      -float(q['rhs']) for q in prefix),default=0.)
        audit.check(f'round_{round_no}_added_cut_numeric_result_preserved',
            close(extra_max,result['max_added_cut_violation'],1e-10)
            and truth(result['raw_matrix_feasible_certificate'])==
                bool(numeric['PASS'] and extra_max<=TOL))
        cert_path=OUT/f'LP_ROUND_{round_no:02d}_EXACT_LB_CERTIFICATE.json'
        if cert_path.exists():
            certificate=audit.js(cert_path.name);certificates[round_no]=certificate
            audit.check(f'round_{round_no}_certificate_point_and_prefix_identity',
                certificate['dual_point_SHA256']==sha(OUT/f'LP_ROUND_{round_no:02d}_POINT.npz')
                and certificate['selected_cuts_count']==n
                and certificate['matrix_nonzeros']==A.nnz+sum(len(q['terms']) for q in prefix)
                and Fraction.from_float(certificate['lower_bound'])<=Fraction(certificate['exact_rational']))
        elif round_no>1:
            audit.check(f'round_{round_no}_exact_certificate_required',False)
        valid=max(KNOWN_LB,certificates[round_no]['lower_bound'] if round_no in certificates else KNOWN_LB)
        audit.check(f'round_{round_no}_certified_bound_not_unsafe_ObjBound_or_ObjVal',
            close(r['valid_global_LB'],valid) and close(r['delta_LB'],valid-KNOWN_LB)
            and close(r['gap_ref'],(UB-valid)/UB)
            and close(r['LP_objective_gain'],float(r['rho'])-pure['objective']))
    audit.check('final_selected_count_matches_last_completed_round',
        len(selected)==int(float(trace[-1]['total_cuts'])))

    if final or deep:
        # Recheck every selected cut from original authority; no constructor is called.
        from independent_hull import Authority,exact
        from folded_pcs_hull import verify_folded_candidate
        authority=Authority();errors=[]
        from independent_hull import SOURCE as original_source
        for path in [original_source/'FULL_A.npz',original_source/'FULL_DATA.npz',
                     original_source/'DATA.pkl',
                     ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_ELIMINATION_CERTIFICATES.json',
                     ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz',
                     ROOT/'v42_strengthening/analysis.py',ROOT/'v42_bootstrap/m1.py']:
            audit.capture(path)
        audit.capture(authority.receipt['route_file']['path'])
        # Actual target axes come from saved original row maps, not aliased
        # response-column names.  Check affine totals without reusing expand().
        c3axes=audit.npz('',PARENT/'C3_RETAINED_AXES.npz')
        c2axes=audit.npz('',ROOT/'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz')
        original_axes=audit.npz('',original_source/'REDUCTION_AXES.npz')
        critical=audit.csv('CRITICAL_LINE_TIME_AUDIT.csv')
        originalA=authority.load_matrix()
        critical_errors=[]
        expected_active=set(map(int,np.flatnonzero((d['row_names']=='line_thermal_face') & point['active'])))
        if {int(r['row']) for r in critical}!=expected_active or len(critical)!=len(expected_active):
            critical_errors.append(dict(reason='ACTIVE_NATIVE_ROWS_CENSUS_MISMATCH'))
        rho=int(np.flatnonzero(d['names']=='rho_max')[0])
        branch_receipt=audit.js('CRITICAL_BRANCH_AUTHORITY.json')
        planning=audit.npz('',Path(branch_receipt['branch_axis_source']))
        branch_names=planning['branch_names']
        audit.check('frozen_branch_name_authority_unchanged',branch_receipt['PASS']
            and sha(Path(branch_receipt['branch_axis_source']))==branch_receipt['planning_SHA256']
            and sha(audit.capture(branch_receipt['certificate_source']))==branch_receipt['certificate_SHA256']
            and sha(original_source/'DATA.pkl')==branch_receipt['source_DATA_SHA256'])
        for r in critical:
            i=int(r['row'])
            native=int(original_axes['keep'][int(c2axes['C1_original_rows'][
                int(c2axes['rows'][int(c3axes['rows'][i])])])])
            original_js=originalA.indices[originalA.indptr[native]:originalA.indptr[native+1]]
            names=[str(authority.full['names'][j]) for j in original_js]
            ids=[re.fullmatch(r'response_line_(?:P|Q|correction)\[(\d+),(\d+)\]',n) for n in names]
            ids={(int(m[1]),int(m[2])) for m in ids if m}
            js=A.indices[A.indptr[i]:A.indptr[i+1]]
            ws=A.data[A.indptr[i]:A.indptr[i+1]]
            rw=float(ws[np.flatnonzero(js==rho)[0]])
            req_lp=float((ws@point['x'][js]-rw*point['x'][rho]-d['rhs'][i])/(-rw))
            req_start=float((ws@start[js]-rw*start[rho]-d['rhs'][i])/(-rw))
            ok=(native==int(r['original_native_row']) and
                str(authority.full['row_names'][native])=='line_thermal_face'
                and ids=={(int(r['slot']),int(r['line_index']))}
                and names==r['original_native_variables'].split(';')
                and rw<0 and close(r['rho_coefficient'],rw)
                and close(r['LP_required_rho'],req_lp,1e-9)
                and close(r['integer_start_required_rho'],req_start,1e-9)
                and close(r['delta_required_rho'],req_start-req_lp,1e-9)
                and close(float(r['baseline_required_rho'])+float(r['LP_MESS_rho_contribution']),req_lp,1e-9)
                and close(float(r['baseline_required_rho'])+float(r['integer_start_MESS_rho_contribution']),req_start,1e-9)
                and r['branch_name']==str(branch_names[int(r['line_index'])])
                and r['branch_authority_SHA256']==branch_receipt['planning_SHA256'])
            if not ok:critical_errors.append(dict(row=i,native_row=native,reason='AXIS_OR_AFFINE_CLOSURE_MISMATCH'))
        audit.check('critical_actual_native_line_time_branch_and_affine_totals',not critical_errors,
                    dict(rows=len(critical),errors=critical_errors))
        for cut in selected:
            try:
                if cut['family']=='FOLDED_PCS_CONNECTED_POWER':
                    verify_folded_candidate(cut,{'start':start},authority)
                else:
                    terms,rhs=authority.reconstructed_candidate(cut)
                    assert terms=={int(j):exact(w) for j,w in cut['terms'].items() if w}
                    assert rhs==exact(cut['rhs'])
                    assert sum((w*exact(start[j]) for j,w in terms.items()),Fraction(0))-rhs<=exact(TOL)
            except Exception as exc:errors.append(dict(id=cut['id'],error=repr(exc)))
        audit.check('every_selected_cut_original_authority_independent_recheck',not errors,
                    dict(cuts=len(selected),errors=errors))
        # Check recorded vertices and completeness against the original physical axes.
        geometry_errors=[];vertices_checked=0
        for block in hull['blocks']:
            unit,t=block['MESS'],int(block['slot']);energy=authority.energy(unit,t)
            expected_states={(k,m) for k in authority.reachable[unit]
                if authority.arcs[k][1]<=t<authority.arcs[k][3] for m in (0,1)}
            observed_states={(int(s['arc']),int(s['mode'])) for s in block['states']}
            if observed_states!=expected_states:geometry_errors.append(dict(MESS=unit,slot=t,reason='STATE_CENSUS_MISMATCH'))
            for state in block['states']:
                arc=authority.arcs[int(state['arc'])];mode=int(state['mode'])
                travel=exact(arc[-1].energy_kwh) if arc[-1] is not None and arc[1]==t else Fraction(0)
                alpha=energy['charge'] if mode==1 else energy['discharge']
                connected=arc[-1] is None
                assert len(state['continuous_vertices'])==state['vertex_count']
                for vertex in state['continuous_vertices']:
                    p,q,e0,e1=(Fraction(vertex[k]) for k in ['power','Q','SOC0','SOC1'])
                    ok=(0<=p<=exact(authority.battery.p_limit) and
                        -exact(authority.battery.pcs_kva)<=q<=exact(authority.battery.pcs_kva)
                        and exact(authority.battery.minimum)<=e0<=exact(authority.battery.maximum)
                        and exact(authority.battery.minimum)<=e1<=exact(authority.battery.maximum)
                        and e1==e0+alpha*p-travel
                        and (t!=0 or e0==exact(authority.battery.initial))
                        and (t!=95 or e1==exact(authority.battery.terminal)))
                    if connected:
                        sign=-1 if mode==1 else 1
                        ok=ok and all(a*sign*p+b*q<=cap for a,b,cap in authority.pcs(unit,arc[0],t))
                    else:ok=ok and p==q==0
                    if not ok:geometry_errors.append(dict(MESS=unit,slot=t,arc=state['arc'],mode=mode,reason='ORIGINAL_VERTEX_VIOLATION'))
                    vertices_checked+=1
            if sum(s['vertex_count'] for s in block['states'])!=block['continuous_vertex_count']:
                geometry_errors.append(dict(MESS=unit,slot=t,reason='VERTEX_CENSUS_MISMATCH'))
        audit.check('local_vertices_original_PCS_SOC_route_geometry_replay',not geometry_errors,
                    dict(vertices_checked=vertices_checked,errors=geometry_errors))
        from numerical_bound_audit import exact_bounded_lagrangian
        baseline_audit=audit.js('NUMERICAL_LP_BOUND_AUDIT.json')
        calculated,_,_,_=exact_bounded_lagrangian(A,d,point['dual'])
        old=baseline_audit['independently_valid_exact_certificate']
        audit.check('baseline_exact_LB_recomputed',calculated['exact_rational']==old['exact_rational']
            and calculated['lower_bound']==old['lower_bound'])
        if certificates:
            targets={max(certificates),max(certificates,key=lambda j:certificates[j]['lower_bound'])}
            for round_no in sorted(targets):
                n=int(float(trace_by_round[round_no]['total_cuts']))
                S,e,_=selected_matrix(A,d,selected[:n])
                dual=audit.npz(f'LP_ROUND_{round_no:02d}_POINT.npz')['dual']
                calculated,_,_,_=exact_bounded_lagrangian(S,e,dual)
                old=certificates[round_no]
                audit.check(f'round_{round_no}_best_or_final_exact_LB_recomputed',
                    calculated['exact_rational']==old['exact_rational']
                    and calculated['lower_bound']==old['lower_bound'])

    summary_path=OUT/'LP_STRENGTHENING_SUMMARY.json'
    summary=audit.js(summary_path.name) if summary_path.exists() else None
    best=max(float(r['valid_global_LB']) for r in trace)
    material=best-KNOWN_LB>=.001
    if summary is None:
        audit.check('controlled_cut_loop_finished',False,pending=not final)
    else:
        audit.check('controlled_cut_loop_summary_certified_gain',
            close(summary['best_valid_global_LB'],best)
            and close(summary['absolute_improvement'],best-KNOWN_LB)
            and summary['materially_strengthened']==material and summary['rounds']==len(trace)-1
            and summary['cuts']==len(selected) and summary['baseline_rows_deleted']==0
            and summary['MILP_calls_during_loop']==0)

    selective_tokens=list(OUT.glob('SELECTIVE_*_ONCE.json'))
    audit.check('at_most_two_selective_tests',len(selective_tokens)<=2)
    selective_families=[];time_overruns=[]
    for token_path in sorted(selective_tokens):
        token=audit.js(token_path.name);family=token['family'];selective_families.append(family)
        audit.check(token_path.name+'_census_motivation_parameters',token['optimize_calls']==1
            and family in fractional and fractional[family]>0 and token['TimeLimit']<=300
            and token['Threads']==1 and token['integer_columns']==by_family[family])
        result_path=OUT/f'SELECTIVE_{family}_RESULT.json'
        if not result_path.exists():
            audit.check(f'SELECTIVE_{family}_finished',False,pending=not final);continue
        r=audit.js(result_path.name)
        audit.check(f'SELECTIVE_{family}_partial_integrality_scope',r['Threads']==1
            and r['TimeLimit']<=300 and r['partial_integrality_only']
            and not r['production_acceptance'] and r['remaining_original_discrete_relaxed']==9322-by_family[family]
            and not r['changed_scientific_parameters'])
        audit.check(f'SELECTIVE_{family}_native_bound_finite_and_not_above_known_feasible_UB',
            math.isfinite(r['native_LB']) and r['native_LB']<=UB+TOL
            and math.isfinite(r['conservative_native_LB'])
            and r['conservative_native_LB']<r['native_LB'])
        audit.details.setdefault('selective_native_bound_convention',[]).append(dict(
            family=family,Status=r['Status'],native_LB=r['native_LB'],
            conservative_native_LB=r['conservative_native_LB'],
            is_exact_rational_dual_certificate=False,
            convention='nextafter(native_MILP_ObjBound - 1e-8, -inf)',
            cannot_certify_remaining_relaxed_discretes_as_integer=True))
        overrun=max(0.,r['Runtime']-r['TimeLimit'])
        time_overruns.append(dict(family=family,Runtime=r['Runtime'],configured_TimeLimit=r['TimeLimit'],
            overrun_seconds=overrun,strict_runtime_within_300_seconds=r['Runtime']<=300))
        audit.check(f'SELECTIVE_{family}_native_finish_granularity',overrun<=1.,time_overruns[-1])
    audit.details['selective_time_limit_enforcement']=time_overruns
    audit.details['one_second_finish_reporting_allowance_is_not_a_parameter_or_budget_change']=True
    if final:
        audit.check('two_justified_actual_discrete_family_tests_completed',
            set(selective_families)=={'node_activity','charge_mode'} and len(selective_families)==2)
        if (OUT/'SELECTIVE_INTEGRALITY_RESULTS.csv').exists():
            selective_csv=audit.csv('SELECTIVE_INTEGRALITY_RESULTS.csv')
            audit.check('selective_csv_two_unique_results',len(selective_csv)==2
                and {r['family'] for r in selective_csv}==set(selective_families))
        else:
            audit.check('selective_csv_two_unique_results',False)
    root_token_path=OUT/'C3S_ROOT_ONCE.json'
    root_calls=0
    if root_token_path.exists():
        token=audit.js(root_token_path.name);root_calls=token['optimize_calls']
        audit.check('one_root_only_call_requires_material_certified_gain',material and root_calls==1
            and token['NodeLimit']==1 and token['TimeLimit']<=900)
        settings=token['settings']
        audit.check('C3S_native_root_parameters',all(settings[k]==v for k,v in dict(
            Method=2,Threads=1,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,
            FeasibilityTol=TOL,NodeLimit=1).items()) and settings['TimeLimit']<=900)
        needed=['C3S_AUTHORITY.json','C3S_MODEL_CENSUS.json','C3S_START_REPLAY.json','C3S_ROOT_RESULT.json']
        for name in needed:
            audit.check(name+'_required', (OUT/name).exists(),pending=not final and not (OUT/name).exists())
        if all((OUT/name).exists() for name in needed):
            authority=audit.js(needed[0]);census=audit.js(needed[1]);startcheck=audit.js(needed[2]);r=audit.js(needed[3])
            audit.check('C3S_authority_original_rows_and_start_preserved',authority['PASS']
                and authority['C3A_matrix_SHA256']==EXPECTED['C3A_A.npz']
                and authority['C3A_data_SHA256']==EXPECTED['C3A_DATA.npz']
                and census['baseline_rows_deleted']==0 and census['added']['columns']==0
                and census['C3S']['rows']==A.shape[0]+len(selected)
                and startcheck['PASS'] and startcheck['start_SHA256']==EXPECTED['C3A_VALID_START.npz']
                and not startcheck['point_changed'] and not startcheck['physical_P1_P2_changed'])
            audit.check('C3S_single_root_scope',r['optimize_calls']==1 and r['NodeLimit']==1
                and r['TimeLimit']<=900 and r['root_diagnostic_only']
                and not r['production_acceptance'] and not r['full_BB_executed'])
    else:
        audit.check('root_only_conditional_not_triggered_without_material_gain',not material,
                    dict(material_certified_gain=material,root_calls=0),pending=material and not final)
    audit.details['root_only_optimize_calls']=root_calls
    for name in REQUIRED:
        exists=(OUT/name).exists()
        audit.check(name+'_required_artifact',exists,pending=not exists and not final)
        if exists:audit.capture(OUT/name)
    changed=[path for path,digest in audit.inputs.items() if sha(Path(path))!=digest]
    audit.check('all_report_inputs_unchanged_during_verification',not changed,
                dict(changed=changed),pending=bool(changed) and not final)
    workflow=all(c['state']!='FAIL' for c in audit.checks)
    complete=all(c['state']=='PASS' for c in audit.checks)
    strict=all(r['PASS'] for r in audit.numeric)
    return dict(PASS=workflow and complete and strict,
        workflow_integrity_PASS=workflow, workflow_checks_complete=complete,
        strict_raw_numeric_feasibility_PASS=strict,
        raw_numeric_failures_are_not_hidden=not strict,
        mode='FINAL' if final else 'INTERIM_DEEP_READ_ONLY' if deep else 'INTERIM_READ_ONLY',
        no_optimize_calls=True,no_native_build_calls=True,no_git_commands=True,
        original_selected_hashes=EXPECTED,exact_base=BASE,
        counts=dict(original_discrete=9322,fractional=sum(fractional.values()),
            by_family=dict(by_family),fractional_by_family=dict(fractional),
            byTime_rows=len(time_rows),terminal96_rows=4,
            LP_round_optimize_calls=sum(r['calls'] for r in token_records),
            pure_LP_calls=pure_calls,selective_calls=len(selective_tokens),root_only_calls=root_calls),
        checks=audit.checks,raw_numeric_replays=audit.numeric,details=audit.details,
        input_SHA256=audit.inputs,
        post_verification_SHA256_manifest_must_be_created_separately=True,
        scientific_constraint_tolerance_unchanged=TOL,
        certified_global_bound_baseline=KNOWN_LB,best_certified_global_bound=best,
        material_certified_improvement=material)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final',action='store_true')
    parser.add_argument('--deep',action='store_true',
        help='Reconstruct best/final exact certificates and local geometry without writing a report.')
    args=parser.parse_args()
    started=time.perf_counter()
    try:
        report=verify(args.final,args.deep)
    except Exception as exc:
        report=dict(PASS=False,workflow_integrity_PASS=False,workflow_checks_complete=False,
            strict_raw_numeric_feasibility_PASS=False,verification_exception=repr(exc),
            no_optimize_calls=True,no_native_build_calls=True,no_git_commands=True)
    report['verification_runtime_seconds']=time.perf_counter()-started
    if args.final:
        (OUT/'VERIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,
            indent=2,allow_nan=False)+'\n',encoding='utf-8')
    summary={k:v for k,v in report.items() if k not in ['checks','input_SHA256','raw_numeric_replays','details']}
    summary['failed_checks']=[r for r in report.get('checks',[]) if r['state']=='FAIL']
    summary['pending_checks']=[r['name'] for r in report.get('checks',[]) if r['state']=='PENDING']
    print(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),flush=True)


if __name__=='__main__':
    main()
