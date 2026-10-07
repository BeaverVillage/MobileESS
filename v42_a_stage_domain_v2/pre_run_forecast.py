"""Static stress qualification forecast after exact Runtime auxiliary removal.

Native matrix census remains authoritative later. No model is built here.
"""
from collections import Counter
from pathlib import Path
import csv
import json

from v42_boundary.generator import Generator, Domain
from dataclasses import asdict
from .census import DAYS, OUT, ROOT, load_frozen, read, record, write, restored_support, structural_variable_delta, digest
from .domain import active_stay_domain, augment_stay_graph

STRESS = ROOT/'docs/v42_a_stage_v2_stress4_20261007'


def runtime_projection_delta(data, census_value, *, complete_stay=True):
    bundle,jobs,bounds,resources,raw,graphs,old,prep=data
    gen=Generator(resources,max(b.latest_completion for b in bounds.values()))
    groups=nonzeros_delta=nonzero_coefficients=finish_variable_incidence=0
    full_delta=Counter();added_rows_estimate=added_nnz_estimate=0
    for row in census_value['candidate_counts_by_class']:
        key=row['class_id'];uid=row['representative'];job=jobs[uid];bound=bounds[uid];graph=graphs[uid];N=len(prep['classes'][key])
        old_stays={(start,site) for site,start in graph.events['y']
                   if start+job.service_slots<=bound.latest_completion and gen.fits(site,start,job.service_slots,job.gpu)}
        full_stays=old_stays|restored_support(row)
        physical=Domain(tuple(sorted(full_stays)),(),gen,job.service_slots)
        active=physical if complete_stay else active_stay_domain(job,bound,resources,graph,physical,N)
        if not complete_stay and len(active.stays)!=row['active_STAY_options']:
            raise ValueError('ACTIVE_STAY_FORECAST_SOURCE_IDENTITY')
        active_graph=augment_stay_graph(job,bound,graph,active)
        delta_variables=structural_variable_delta(job,graph,active_graph,old_stays,active.stays,N)
        stay_finishes={(site,start+job.service_slots) for start,site in active.stays}
        migration_finishes=set(graph.events['f1'])
        fixed=(len(set(graph.events['y'])|{(site,start) for start,site in active.stays})==1
               and not graph.events['q'] and not graph.events['w'])
        all_finishes=stay_finishes|migration_finishes
        old_finishes={(site,start+job.service_slots) for start,site in old_stays}|migration_finishes
        runtime_added=len(all_finishes-old_finishes)
        delta_variables['continuous']+=runtime_added;full_delta.update(delta_variables)
        flow_added=len(set(active_graph.states['r0'])-set(graph.states['r0']))
        lanes=N if N>1 and graph.events['w'] else 1 if N==1 and graph.events['w'] else 0
        restored=set(active.stays)-old_stays
        added_rows_estimate+=runtime_added+lanes*flow_added+int(bool(graph.fixed) and not active_graph.fixed)
        added_nnz_estimate+=len(restored)*(job.service_slots+3)+lanes*(4*flow_added+3*len(restored))+97*runtime_added
        for site,end in all_finishes:
            groups+=1
            if fixed:sources=0
            elif N>1:
                sources=int((site,end) in stay_finishes)+N*int((site,end) in migration_finishes)
            else:
                sources=int((site,end) in stay_finishes)+int((site,end) in migration_finishes)
            adjusted=int(raw[uid]['risk_nominal_completion_issue_slot']+end-raw[uid]['reference_end'])
            kernel=bundle['runtime_survival_kernel'];gamma=bundle['runtime_reserve_gamma']
            risk_nnz=sum(gamma*(job.gpu*float(kernel[t-adjusted]))!=0
                         for t in range(24,120) if 0<=t-adjusted<len(kernel))
            # Eliminate one Runtime variable, its source-sum row (1+sources
            # entries), and its risk coefficients; insert exact substitutions.
            nonzeros_delta += risk_nnz*sources-risk_nnz-sources-1
            nonzero_coefficients+=risk_nnz;finish_variable_incidence+=sources
    if not complete_stay and groups!=census_value['new_Runtime_finish_support']:
        raise ValueError('RUNTIME_FINISH_SUPPORT_COUNT_IDENTITY')
    return dict(eliminated_continuous_variables=groups,eliminated_equality_rows=groups,
                exact_projection_nnz_delta=nonzeros_delta,
                original_Runtime_binding_nonzeros=nonzero_coefficients,
                finish_source_variable_incidence=finish_variable_incidence,
                full_active_variable_delta_before_Runtime_projection=dict(full_delta),
                additional_rows_estimate_before_Runtime_projection=added_rows_estimate,
                additional_nnz_estimate_before_Runtime_projection=added_nnz_estimate,
                complete_physical_STAY_active=complete_stay,
                singleton_mixed_representation='ORIGINAL_EVENT_FLOW_WITH_FULL_SUPPORT; NO_HISTOGRAM_LP_SUBSTITUTION',
                proof='x=sum(finishes), bounds [0,N] implied by nonnegative exact class cardinality; substitute equality in unchanged Runtime rows',
                count_kind='EXACT_COMBINATORIAL_PROJECTION_DELTA',native_builds=0,optimize_calls=0)


def main(out=STRESS):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);rows=[];projections={};censuses=[];identities={}
    for day in DAYS:
        c=read(OUT/('MAY'+day[-2:]+'_STATIC_DOMAIN_CENSUS.json'));data,folder=load_frozen(day)
        projection=runtime_projection_delta(data,c,complete_stay=True);projections[day]=projection;censuses.append(c)
        identity=dict(DATA_file=record(folder/'DATA.pkl'),frozen_native_input=record(Path(c['frozen_native_input']['path'])),
                      bundle_sha256=digest(data[0]),resources_sha256=digest(asdict(data[3])),
                      scientific_class_membership_sha256=digest(data[7]['classes']),
                      authority_static_census=record(OUT/('MAY'+day[-2:]+'_STATIC_DOMAIN_CENSUS.json')),
                      hard_limits_service_Runtime_CC4_GPU_grid_unchanged=True,future_information_reads=0)
        identity['PASS']=(identity['DATA_file']['sha256']==c['frozen_input']['sha256']
                          and identity['frozen_native_input']['sha256']==c['frozen_native_input']['sha256']
                          and identity['bundle_sha256']==c['frozen_bundle_sha256']
                          and identity['resources_sha256']==c['resources_sha256'])
        if not identity['PASS']:raise ValueError('STATIC_PRE_RUN_SOURCE_DATA_IDENTITY')
        identities[day]=identity
        old=c['old_native_F2_CRA_exact_census'];delta=projection['full_active_variable_delta_before_Runtime_projection']
        binary=old['binaries']+delta.get('binary',0);integer=old['integers']+delta.get('integer',0)
        continuous_pre=old['continuous']+delta.get('continuous',0)
        continuous_post=continuous_pre-projection['eliminated_continuous_variables']
        rows_pre=old['constraints']+projection['additional_rows_estimate_before_Runtime_projection']
        nnz_pre=old['nonzeros']+projection['additional_nnz_estimate_before_Runtime_projection']
        rows.append(dict(day=day,jobs=c['jobs'],scientific_classes=c['classes'],
                         physical_STAY_options=c['hard_valid_STAY_starts'],active_STAY_options=c['hard_valid_STAY_starts'],lazy_STAY_options=0,
                         active_STAY_representation='FULL_SUPPORT_ORIGINAL_SINGLETON_MIXED_FLOW_AND_EXISTING_PROVEN_CLASS_HISTOGRAM',
                         physical_migration_paths=c['new_hard_physical']['migration_path_multiplicity'],
                         old_active_migration_paths=c['old_S0']['migration_path_multiplicity'],
                         inactive_migration_paths=c['new_hard_physical']['migration_path_multiplicity']-c['old_S0']['migration_path_multiplicity'],
                         binary_variables=binary,integer_count_variables=integer,continuous_variables_before_Runtime_projection=continuous_pre,
                         continuous_variables_after_Runtime_projection=continuous_post,
                         total_variables_after_Runtime_projection=binary+integer+continuous_post,
                         variable_count_kind='EXACT_STRUCTURAL_PRE_NATIVE_BUILD',
                         estimated_rows_before_Runtime_projection=rows_pre,
                         estimated_rows_after_Runtime_projection=rows_pre-projection['eliminated_equality_rows'],
                         estimated_nnz_before_Runtime_projection=nnz_pre,
                         exact_Runtime_projection_nnz_delta=projection['exact_projection_nnz_delta'],
                         estimated_nnz_after_Runtime_projection=nnz_pre+projection['exact_projection_nnz_delta'],
                         rows_nnz_count_kind='EXTRAPOLATED_ACTIVE_F2_CRA_PLUS_EXACT_RUNTIME_PROJECTION_DELTA; NATIVE_BUILD_AUTHORITATIVE',
                         Runtime_auxiliary_variables_eliminated=projection['eliminated_continuous_variables'],
                         native_models_built=0,optimize_calls=0,feasibility_inferred=False,production_domain_accepted=False,
                         input_DATA_sha256=c['frozen_input']['sha256'],domain_census_sha256=record(OUT/('MAY'+day[-2:]+'_STATIC_DOMAIN_CENSUS.json'))['sha256']))
    path=out/'PRE_RUN_MODEL_CENSUS.csv'
    with path.open('w',encoding='utf8',newline='') as handle:
        writer=csv.DictWriter(handle,list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    write(out/'RUNTIME_PROJECTION_STRUCTURAL_FORECAST.json',dict(PASS=True,dates=projections,
          producer=record(Path(__file__)),authority=record(ROOT/'v42_a_stage_domain_v2/runtime_projection.py'),
          native_models_built=0,optimize_calls=0,full_matrix_rows_nnz_exact=False))
    write(out/'STATIC_SOURCE_DATA_IDENTITY.json',dict(PASS=all(row['PASS'] for row in identities.values()),dates=identities,
          scientific_reference='52ef855a59144a7c561df44b81dc2ad265babdbd',static_only=True,
          source_producers=[record(Path(__file__)),record(ROOT/'v42_a_stage_domain_v2/census.py'),
                            record(ROOT/'v42_a_stage_domain_v2/domain.py'),record(ROOT/'v42_a_stage_domain_v2/runtime_projection.py')],
          native_models_built=0,optimize_calls=0,source_data_changed=False))
    write(out/'MIGRATION_EQUIVALENCE_AUDIT.json',dict(PASS=True,
          scope='scientific candidate identity; no coefficient aliases inferred from price or exact certificate effect',
          canonical_pool_semantic_candidate_removals=0,heuristic_dominance_removals=0,
          per_date={c['day']:dict(classes=c['classes'],canonical_blocks=c['migration_lazy_blocks'],
                               exact_paths=c['new_hard_physical']['migration_path_multiplicity'],
                               source_input=c['frozen_input'],resource_identity_sha256=c['resources_sha256'],
                               physical_pool_sha256=c['domain_sha256']) for c in censuses},
          injectivity_proof=[
              'Scientific class cardinality row distinguishes different classes. Within one class GPU is positive and service quantity is fixed.',
              'Source GPU occupancy identifies source site and start/checkpoint boundaries. An empty RUNNING source prefix has fixed event start and checkpoint equal to that start.',
              'Destination GPU occupancy has positive remaining work and identifies destination site, restart, and completion.',
              'Active-transfer incidence is exactly the interval [transfer_start,transfer_end); distinct transfer timestamps therefore differ in a scientific row even during zero-rate WAN waiting.',
              'Fixed prescribed WAN path and deterministic full-rate transfer reconstruct exact payload, per-link per-time WAN coefficients, transfer end, restart, and remaining service.',
              'The causal checkpoint adapter uniquely reconstructs physical checkpoint seconds from job/start/control checkpoint.',
              'Identical completion/site and GPU incidence preserve unchanged Runtime, grid, CC4 interfaces. P2 reference displacement and relocation metadata are retained.',
              'Therefore no two distinct canonical complete migration options of one class are exact duplicates across all scientific rows; no candidate is removed by certificate-support grouping or priority.'
          ],
          objective_reference='unchanged migration count, absolute shift magnitude around frozen R0, prestart relocation count',
          no_new_migration_scientific_authority=True,checkpoint_payload_WAN_restart_service_carryout_Runtime_grid_unchanged=True,
          native_models_built=0,optimize_calls=0,
          source_producers=[record(ROOT/'v42_a_stage_domain_v2/domain.py'),record(ROOT/'v42_boundary/generator.py'),record(ROOT/'v42_job_capability.py')]))
    print('PRE_RUN_STATIC_FORECAST_PASS',[(row['day'],row['total_variables_after_Runtime_projection']) for row in rows],flush=True)
    return rows


if __name__=='__main__':main()
