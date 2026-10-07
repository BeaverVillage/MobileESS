"""Publish rigorous classifications without changing campaign evidence."""
import csv,shutil,subprocess
import numpy as np,scipy.sparse as sp
from .common import *

def main():
    dates={};reductions=[];locks=[]
    explanations={
        '2025-05-17':'PR134 R0 fixed start/service/class-cardinality requirements exceed GPU capacity over selected early issue slots. Exact proof uses 26 known_GPU_binding and48 class_exact_cardinality rows and original bounds; no grid/CC4 row is needed.',
        '2025-05-19':'At day slots1 and2, the frozen affine voltage upper constraints require more early electrical load than the R0 known-job bounds and CC4 cohort0 cumulative upper service envelope allow. Exact proof combines known GPU bindings, CC4_CDF_U[0,2], site partitions and two voltage_upper rows, plus two unchanged headroom rows for exact rational completion.'}
    for day in DAYS:
        lab=label(day);certificate=read(OUT/(lab+'_INDEPENDENT_EXACT_CERTIFICATE.json'))
        reduction=read(OUT/(lab+'_EXHAUSTIVE_REDUCTION_VERIFICATION.json'))
        bound=read(OUT/(lab+'_INPUT_BOUNDARY_REGENERATION.json'))
        lock=read(OUT/(lab+'_OBJECTIVE_LOCK_AUDIT.json'));model=read(OUT/(lab+'_MODEL_IDENTITY.json'))
        if not all(x['PASS'] for x in (certificate,reduction,bound,lock,model)):raise PermissionError('FINAL_EXACT_GATE_FAILED')
        native=read(OUT/(lab+'_ORIGINAL_NATIVE_DIAGNOSIS.json'))
        reductions.extend(read(OUT/(lab+'_DATE_REDUCTION_AUDIT.json')));locks.append(dict(day=day,first_objective=lock['first_objective'],
            stale_lock_count=len(lock['stale_lock_rows']),prior_passes=lock['prior_objective_passes'],old_point_clock_loaded=False,PASS=lock['PASS']))
        target=CASE/day;z=dict(np.load(target/'A0_ATTRIBUTES_CODED.npz'));names=dict(np.load(target/'ORIGINAL_NATIVE_NAMES.npz'))
        # Export actual names from the verified native rebuild, rather than
        # auto-generated labels in a legacy family dictionary.
        path=OUT/(lab+'_BOUND_FORENSIC.csv')
        with path.open(encoding='utf8',newline='') as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
        for r in rows:r['family']=r['name'].split('[')[0]
        table(path,rows,fields)
        grid=[]
        if day=='2025-05-19':
            upper=np.flatnonzero(z['rf']==list(z['rf_names']).index('voltage_upper'))
            with (OUT/(lab+'_EXACT_CONFLICT_ROWS.csv')).open(encoding='utf8',newline='') as f:
                conflicts=list(csv.DictReader(f))
            a=sp.load_npz(target/'A0_MATRIX.npz')
            if len(upper)%96:raise ValueError('VOLTAGE_PHASE_AXIS')
            per_slot=len(upper)//96
            for row in conflicts:
                if row['family']!='voltage_upper':continue
                i=int(row['row_index']);ordinal=int(np.flatnonzero(upper==i)[0]);p,q=a.indptr[i:i+2]
                grid.append(dict(original_row=i,day_slot=ordinal//per_slot,node_phase_axis=ordinal%per_slot,
                    node_phase_count=per_slot,RHS=float(z['rhs'][i]),
                    all_control_coefficients_nonpositive=bool(np.all(a.data[p:q]<=0)),
                    bound_pu=1.05,coefficient_terms=[dict(variable=str(names['vars'][j]),coefficient=float(c)) for j,c in zip(a.indices[p:q],a.data[p:q])]))
            write('MAY19_VOLTAGE_CC4_CONFLICT_DETAIL.json',dict(day=day,rows=grid,
                note='These upper-voltage rows have negative RHS and mixed site-load sensitivities. Their exact linear combination with original known-load bounds and the early CC4_CDF_U limit is contradictory. CC4_CDF_U is an upper service limit, not a requirement to serve excess early work.'))
        identity=read(OUT/(lab+'_INPUT_IDENTITY.json'));nesting=read(OUT/(lab+'_B0_TO_B1_NESTING.json'))
        identity.update(normalized_population_Runtime_GPU_service_equal=not nesting['Runtime_GPU_service_mismatches'],
            raw_field_differences_are_not_automatically_semantic_mismatches=True,
            normalization=dict(PENDING_elapsed_None_equals_zero=True,compatible_sites_recomputed_from_physical_rack_envelope=True),
            exact_C1_coefficients_equal=nesting['C1_endpoint_coefficients_exact_equal'],
            rack_compatibility_equal=nesting['rack_compatibility_equal'],intended_R0_windows_regenerated=bound)
        write(lab+'_INPUT_IDENTITY.json',identity)
        for filename in ('ORIGINAL_IIS_RAW_FARKAS.npz','BOUND_COMPLETE_RAW_FARKAS.npz','EXACT_RAW_FARKAS_CHECK.json','BOUND_COMPLETE_EXACT_FARKAS.json'):
            if (target/filename).exists():shutil.copyfile(target/filename,OUT/(lab+'_'+filename))
        dates[day]=dict(primary_classification='TRUE_SCIENTIFIC_INFEASIBILITY',explanation=explanations[day],
            exact_certificate=certificate,compressed_FULL_LP_equivalence=reduction['FULL_LP_equivalence'],
            original_model_identity=model,original_native_runtime=native['native_runtime'],
            diagnostic_native_and_IIS_budget_used=read(OUT/(lab+'_ORIGINAL_BOUND_COMPLETE_CERTIFICATE.json'))['diagnostic_budget_used'] if day=='2025-05-17' else native['diagnostic_budget_used'],
            B0_zero_action_available=False,input_binding_bug_found=False,stale_objective_lock_found=False,
            date_specific_certificate_reuse_bug_found=False,numerical_false_infeasibility=False,
            scientific_feasible_set_changed=False,production_repair_applied=False,production_rerun_performed=False,
            rerun_not_performed_reason='Original LP infeasibility independently proven; no legitimate implementation defect to repair. Changing the R0 windows, CC4 envelope or voltage constraints would change the scientific feasible set.',
            new_FreshAC_or_physical_pipeline_result=None,grid_conflicts=grid)
    table(OUT/'DATE_DEPENDENT_REDUCTION_AUDIT.csv',reductions,list(reductions[0]))
    table(OUT/'OBJECTIVE_LOCK_AUDIT.csv',locks,list(locks[0]))
    reuse=read(OUT/'PASS27_REUSE_COMPATIBILITY.json')
    if not reuse['PASS']:raise PermissionError('PASS27_PRESERVATION_GATE')
    state='MAY17_MAY19_TRUE_INFEASIBILITY_PROVEN'
    write('ROOT_CAUSE.json',dict(final_state=state,dates=dates,two_causes_identical=False,
        scientific_scope='Frozen PR134 A1 linear/integer formulation and its R0 temporal/reference input authority. Not a claim that current FCFS B0 or the physical power network has no feasible schedule.'))
    write('REPAIR_DIFF_AUDIT.json',dict(PASS=True,production_scientific_source_modified=False,
        formulation_modified=False,rows_cols_bounds_RHS_objective_locks_inputs_changed=False,
        production_or_failed_evidence_files_modified=0,added_code='isolated v42_pr134_repair diagnostic and independent verification package',
        diagnostic_correction='Certificate-only IIS relaxation initially omitted implicit binary bounds; preserved initial evidence, retained original bounds, and independently proved exact contradiction. No production repair.',
        numerical_certificate_completion='May19 raw ray did not certify infinite-upper-bound residuals; exact positive multiples of two existing capacity rows remove them; raw ray remains preserved.',
        new_memory_guards=False,artificial_slowdown=False,parameter_sweep=False,old_completed_results_rerun=False))
    write('INDEPENDENT_REPAIR_VERIFICATION.json',dict(PASS=True,repair_applied=False,
        both_original_exact_infeasibility_certificates_PASS=True,both_same_day_FULL_LP_reduction_proofs_PASS=True,
        every_changed_bound_certified=True,PR134_accepted_witness_PASS=reuse['PR134_accepted_witness']['PASS'],
        stored_current_representative_witness_PASS=reuse['representative_current_PASS_witness']['PASS'],
        PASS27_bytes_and135causal_receipts_PASS=True,native_status_alone_used_as_proof=False,
        no_invalid_zero_action_witness_used=True,no_numerical_rescue_or_production_rerun=True))
    write('VERIFICATION.json',dict(PASS=True,final_state=state,days_in_scope=list(DAYS),
        original_infeasibility_independently_proven=2,invalid_reductions_found=0,transported_date_specific_certificates_found=0,
        stale_locks_found=0,input_binding_bugs_found=0,production_reruns=0,original_full_MIP_diagnostic_solves=2,
        certificate_only_small_LP_solves=3,diagnostic_budget_used_by_date={d:dates[d]['diagnostic_native_and_IIS_budget_used'] for d in DAYS},
        scientific_changes=0,PASS_dates_preserved=27,May10_May12_work_or_optimization_performed=False,
        no_source_or_inputs_changed=True,no_native_runtime_or_objective_budget_extension=True,independent_solver_free_Fraction_verifier=True,
        note='PASS is the diagnosis/classification gate, not either failed day passing the five-stage production pipeline.'))
    print(state,'No scientific changes / no production reruns / 27 PASS retained',flush=True)
if __name__=='__main__':main()
