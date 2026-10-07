"""Build-free scientific domain census and immutable diagnostic membership.

Only frozen DATA.pkl and historical census receipts are read. No native model,
optimizer, input producer, Planning freeze, Actual, or Fresh path is imported.
Support counts are exact; future native matrix rows/nnz are labelled estimates.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import Path
import argparse
import csv
import hashlib
import json
import pickle
import struct
import time

from v42_boundary.generator import Generator
from v42_job_capability import Option, validate, checkpoint_records
from .domain import physical_domain, physical_starts, noflex_anchor, augment_stay_graph, active_stay_domain, contains

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_a_stage_domain_authority_v2_20261007'
DAYS = ('2025-05-10', '2025-05-12', '2025-05-17', '2025-05-19')
PRODUCTION = Path('C:/v42_pr134_sc_execution_20261007')
DIAGNOSTIC = ROOT / 'docs/v42_b1_adaptive_prescreening_rescue_20261007'
SHELLS = ROOT / 'docs/v42_b1_may19_prescreening_rescue_20261007'


def digest(value):
    def canonical(item):
        if isinstance(item, dict):return {str(key):canonical(val) for key,val in item.items()}
        if isinstance(item, (tuple,list)):return [canonical(val) for val in item]
        return item
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True, separators=(',', ':'),
                                     default=str, allow_nan=False).encode()).hexdigest()


def record(path):
    path = Path(path)
    with path.open('rb') as handle:
        sha = hashlib.file_digest(handle, 'sha256').hexdigest()
    return dict(path=str(path.resolve()), sha256=sha, bytes=path.stat().st_size)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                    encoding='utf8', newline='\n')


def load_frozen(day, production=PRODUCTION):
    if day not in DAYS:
        raise ValueError('STATIC_STRESS_DATE_CENSUS_SCOPE')
    folder = Path(production) / 'stages' / day / 'A1/1/output'
    path = folder / 'DATA.pkl'
    with path.open('rb') as handle:
        data = pickle.load(handle)
    if data[0]['day'] != day:
        raise ValueError('FROZEN_INPUT_DAY_IDENTITY')
    return data, folder


def diagnostic_sources(day):
    if day == '2025-05-17':
        path = DIAGNOSTIC / 'MAY17_MINIMAL_DOMAIN.json'
        return {'MAY17_35_RESCUE': (path, read(path)['selected'])}
    if day == '2025-05-19':
        path = DIAGNOSTIC / 'MAY19_MINIMAL_DOMAIN.json'
        result = {'PR165_38': (path, read(path)['latest_diagnostic_candidate'])}
        for shell in ('S_A', 'S_B', 'S_C', 'S_D'):
            path = SHELLS / 'evidence' / shell / 'SELECTED_DOMAIN_INPUT.json'
            result['PR166_' + shell] = path, read(path)
        if len(result['PR165_38'][1]) != 38:
            raise ValueError('PR165_EXPECTED_38_OPTIONS')
        return result
    return {}


def option_from_row(row, job, resources, gen):
    start = int(row['start']); site = str(row['site']); cp = int(row['checkpoint'])
    parts = tuple(tuple(part) for part in json.loads(row['segments']))
    if cp < 0:
        return Option(start, site, parts)
    tau = int(row['transfer_start']); dest = str(row['destination'])
    transfer = gen.transfer(site, dest, job.gpu, tau)
    physical = dict(checkpoint_records(job, start, min(start + job.service_slots, resources.control_end)))[cp]
    if 'physical_checkpoint_seconds' in row and float(row['physical_checkpoint_seconds']) != physical:
        raise ValueError('HISTORICAL_CHECKPOINT_PHYSICAL_IDENTITY')
    option = Option(start, site, parts, cp, physical, dest, tau, transfer.end, transfer.restart, transfer.wan)
    for name in ('transfer_end', 'restart_end'):
        if name in row and int(row[name]) != getattr(option, name):
            raise ValueError('HISTORICAL_' + name.upper() + '_IDENTITY')
    if 'wan' in row and tuple(tuple(part) for part in row['wan']) != option.wan:
        raise ValueError('HISTORICAL_WAN_TEMPLATE_IDENTITY')
    return option


def membership_row(row, job, bound, resources, domain, members, raw, bundle):
    option = option_from_row(row, job, resources, domain.cache)
    checks = dict(class_count=int(row['class_count']) == len(members),
                  representative=str(row['job_representative']) in members,
                  GPU=int(row['GPU']) == job.gpu,
                  service_slots=int(row['service_slots']) == job.service_slots,
                  reference_start=int(row['reference_start']) == job.reference_start,
                  action=row['action'] == option.action(job),
                  displacement=int(row['delta_start']) == option.start - job.reference_start,
                  absolute_displacement=int(row['abs_delta_start']) == abs(option.start - job.reference_start),
                  full_attribute_membership=contains(job, bound, resources, domain, option))
    # This is the unchanged completion_risk algebra, without importing native.
    adjusted = int(raw['risk_nominal_completion_issue_slot'] + option.segments[-1][2] - raw['reference_end'])
    kernel = bundle['runtime_survival_kernel']
    runtime = [(option.segments[-1][0], slot,
                bundle['runtime_reserve_gamma'] * (job.gpu * float(kernel[slot - adjusted])))
               for slot in range(24, 120) if 0 <= slot - adjusted < len(kernel)]
    from v42_final.reserve import risk_exposure
    independent_runtime = {key:bundle['runtime_reserve_gamma']*value for key,value in
                           risk_exposure(job.gpu,adjusted,option.segments[-1][0],kernel,range(24,120)).items()}
    checks['Runtime_bitwise_coefficient_identity'] = all(
        struct.pack('!d',value)==struct.pack('!d',independent_runtime[site,slot]) for site,slot,value in runtime)
    gpu = [(site, slot, job.gpu) for site, start, end in option.segments for slot in range(start, end)]
    attributes = dict(class_id=row['class_id'], class_members=members, job=asdict(job),
                      option=asdict(option), completion=option.segments[-1][2],
                      GPU_occupancy=gpu, Runtime_coefficient_vector=runtime,
                      WAN=option.wan, active_transfer_slots=list(range(option.transfer_start, option.transfer_end)) if option.migrated else [],
                      objective=dict(migration=int(option.migrated), shift_magnitude=abs(option.start-job.reference_start),
                                     prestart_relocation=int(option.initial_site != job.reference_site)),
                      frozen_boundary_without_prescreen={k:v for k,v in asdict(bound).items() if k != 'allowed_starts'},
                      grid_interface='unchanged frozen site/time GPU -> power -> signed grid coefficients',
                      CC4_interface='unchanged frozen global CC4; option adds known GPU only')
    return dict(PASS=all(checks.values()), checks=checks, option_id=row['option_id'],
                original_row=row, original_row_sha256=digest(row),
                scientific_attributes=attributes, scientific_attributes_sha256=digest(attributes),
                reference_distance_used_as_membership_filter=False)


def structural_variable_delta(job, oldgraph, newgraph, old_stays, new_stays, N):
    """Exact F2-CRA variable delta from inherited factor/local_units branches.

    This does not assert that historical A2SC elimination patterns transfer to
    the expanded matrix. Counts are for the unreduced active initial F2-CRA.
    """
    old_support = set(old_stays); new_support = set(new_stays)
    if oldgraph.fixed and newgraph.fixed:
        return Counter()
    if oldgraph.fixed and not newgraph.fixed:
        # A previously constant single path becomes a variable class allocation.
        return Counter(binary=len(new_support) if N == 1 else 0,
                       integer=len(new_support) if N > 1 else 0)
    extra_y = len(set(newgraph.events['y']) - set(oldgraph.events['y']))
    extra_f0 = len(set(newgraph.events['f0']) - set(oldgraph.events['f0']))
    extra_r0 = len(set(newgraph.states['r0']) - set(oldgraph.states['r0']))
    extra_stays = len(new_support - old_support)
    if N == 1:
        if oldgraph.events['w']:
            return Counter(binary=extra_y + extra_f0, continuous=extra_r0)
        return Counter(binary=extra_stays)
    result = Counter(integer=extra_stays)
    if oldgraph.events['w']:
        result.update(binary=N * extra_y, continuous=N * extra_r0)
    return result


def summarize_domain(domain, job):
    stay = Counter(); migration = Counter(); site = Counter(); displacement = Counter(); absolute = Counter()
    for start, location in domain.stays:
        stay['same_site' if location == job.reference_site else 'prestart'] += 1
        site[location] += 1; displacement[str(start-job.reference_start)] += 1; absolute[str(abs(start-job.reference_start))] += 1
    for start, source, cp, physical, dest, gpu, taus in domain.blocks:
        migration['blocks'] += 1; migration['paths'] += len(taus)
    return dict(stay_options=len(domain.stays), same_site_starts=stay['same_site'],
                compatible_site_starts=len(domain.stays), prestart_options=stay['prestart'],
                migration_lazy_blocks=migration['blocks'], migration_path_multiplicity=migration['paths'],
                total_physical_path_multiplicity=domain.count), site, displacement, absolute


def migration_axes(domain, job):
    source = Counter(); destination = Counter(); displacement = Counter(); absolute = Counter()
    for start,site,cp,physical,dest,gpu,taus in domain.blocks:
        multiplicity=len(taus);source[site]+=multiplicity;destination[dest]+=multiplicity
        displacement[str(start-job.reference_start)]+=multiplicity
        absolute[str(abs(start-job.reference_start))]+=multiplicity
    return source,destination,displacement,absolute


def census(day, production=PRODUCTION, out=OUT):
    started = time.perf_counter(); data, folder = load_frozen(day, production)
    bundle, jobs, bounds, resources, raw, graphs, oldgraphs, prep = data
    if sorted(u for us in prep['classes'].values() for u in us) != sorted(jobs):
        raise ValueError('CLASS_EXACT_CARDINALITY_MEMBERSHIP')
    gen = Generator(resources, max(b.latest_completion for b in bounds.values()))
    oldgen = Generator(resources, max(b.latest_completion for b in bounds.values()))
    historical = diagnostic_sources(day); selected = defaultdict(list)
    for name, (source, rows) in historical.items():
        for row in rows:
            selected[row['class_id']].append((name, row))
    memberships = defaultdict(list)
    classes = []; oldtotal = Counter(); newtotal = Counter(); bysite = Counter(); bydelta = Counter(); byabs = Counter()
    restoredsite = Counter(); restoreddelta = Counter(); restoredabs = Counter(); variable_delta = Counter()
    old_sites = Counter(); old_displacements = Counter(); old_abs = Counter()
    hashes = {}; noflex = []; removed_old = []; native_rows_estimate = 0; native_nnz_estimate = 0
    hist_binary = hist_integer = stay_nnz = 0; old_class_count_variables = 0
    old_runtime_count = 0; new_runtime_count = 0; old_graph_events = Counter(); new_graph_events = Counter()
    weighted_old = Counter(); weighted_new = Counter(); active_initial_paths = 0; lazy_stay_count=0; active_STAY_count=0
    migration_by_source=Counter();migration_by_destination=Counter();migration_by_displacement=Counter();migration_by_absolute=Counter()
    all_by_source=Counter();all_by_displacement=Counter();all_by_absolute=Counter();active_class_count_variables=0
    for index, (key, members) in enumerate(sorted(prep['classes'].items())):
        uid = members[0]; job = jobs[uid]; bound = bounds[uid]; graph = graphs[uid]; N = len(members)
        for member in members:
            if replace(job, uid=member) != jobs[member] or bound != bounds[member] or graph.sha != graphs[member].sha:
                raise ValueError('CLASS_PHYSICAL_OPTION_UNIFORMITY')
        legacy = oldgen.domain(job, bound)
        domain = physical_domain(job, bound, resources, gen)
        wide = replace(bound, allowed_starts=physical_starts(job, bound, resources.control_end))
        active=active_stay_domain(job,wide,resources,graph,domain,N)
        activegraph = augment_stay_graph(job, wide, graph, active)
        lazy_stay_count+=len(domain.stays)-len(active.stays);active_STAY_count+=len(active.stays)
        oldcounts, oldsites, olddelta, oldabsolute = summarize_domain(legacy, job)
        newcounts, sites, delta, absolute = summarize_domain(domain, job)
        migsource,migdest,migdelta,migabsolute=migration_axes(domain,job)
        migration_by_source.update(migsource);migration_by_destination.update(migdest)
        migration_by_displacement.update(migdelta);migration_by_absolute.update(migabsolute)
        all_by_source.update(sites);all_by_source.update(migsource)
        all_by_displacement.update(delta);all_by_displacement.update(migdelta)
        all_by_absolute.update(absolute);all_by_absolute.update(migabsolute)
        oldtotal.update(oldcounts); newtotal.update(newcounts)
        weighted_old.update({k:v*N for k,v in oldcounts.items()}); weighted_new.update({k:v*N for k,v in newcounts.items()})
        bysite.update(sites); bydelta.update(delta); byabs.update(absolute)
        old_sites.update(oldsites); old_displacements.update(olddelta); old_abs.update(oldabsolute)
        restored = sorted(set(domain.stays) - set(legacy.stays))
        for start, site in restored:
            restoredsite[site] += 1; restoreddelta[str(start-job.reference_start)] += 1; restoredabs[str(abs(start-job.reference_start))] += 1
        removed = sorted(set(legacy.stays) - set(domain.stays))
        if removed:
            removed_old.append(dict(class_id=key, support=removed, reason='REQUIRES_HARD_PHYSICAL_PROOF'))
        # Full legacy lazy blocks must remain scientifically present, including
        # every exact transfer start. Comparison is combinatorial, not sampled.
        new_blocks = {b[:-1]:set(b[-1]) for b in domain.blocks}
        old_migration_included = all(set(b[-1]) <= new_blocks.get(b[:-1], set()) for b in legacy.blocks)
        if not old_migration_included:
            raise ValueError('OLD_MIGRATION_PHYSICAL_PATH_REMOVED')
        anchor = noflex_anchor(job, bound, resources)
        anchor_included = anchor is None or (anchor.start, anchor.initial_site) in domain.stays
        noflex.append(dict(class_id=key, class_exact_cardinality=N, anchor_valid=anchor is not None,
                           anchor_included=anchor_included, reference_start=job.reference_start,
                           reference_site=job.reference_site))
        if not anchor_included:
            raise ValueError('A_NOFLEX_ANCHOR_REMOVED')
        for name, row in selected.get(key, []):
            memberships[name].append(membership_row(row, job, bound, resources, domain, members, raw[uid], bundle))
        delta_vars = structural_variable_delta(job, graph, activegraph, legacy.stays, active.stays, N)
        old_finishes = {(site,start+job.service_slots) for start,site in legacy.stays} | set(graph.events['f1'])
        new_finishes = {(site,start+job.service_slots) for start,site in active.stays} | set(graph.events['f1'])
        runtime_delta = len(new_finishes - old_finishes)
        delta_vars['continuous'] += runtime_delta; variable_delta.update(delta_vars)
        old_runtime_count += len(old_finishes); new_runtime_count += len(new_finishes)
        # Runtime finish rows and source-flow additions plus expanded direct
        # occupancy incidence. These are explicitly a conservative additive
        # matrix estimate, not a post-elimination census or solver memory claim.
        flow_added = len(set(activegraph.states['r0']) - set(graph.states['r0']))
        lanes = N if N > 1 and graph.events['w'] else 1 if N == 1 and graph.events['w'] else 0
        native_rows_estimate += runtime_delta + lanes * flow_added + int(bool(graph.fixed) and not activegraph.fixed)
        active_restored=set(active.stays)-set(legacy.stays)
        native_nnz_estimate += sum(job.service_slots + 3 for _ in active_restored) + lanes * (4*flow_added + 3*len(active_restored)) + 97*runtime_delta
        if N == 1: hist_binary += len(domain.stays)
        else: hist_integer += len(domain.stays)
        stay_nnz += len(domain.stays)*(job.service_slots+2)
        if N > 1 and not graph.fixed:old_class_count_variables += len(legacy.stays)
        if N > 1 and not activegraph.fixed:active_class_count_variables += len(active.stays)
        active_paths = len(active.stays) + oldcounts['migration_path_multiplicity']; active_initial_paths += active_paths
        old_graph_events.update({k:len(v) for k,v in {**graph.events,**graph.states}.items()})
        new_graph_events.update({k:len(v) for k,v in {**activegraph.events,**activegraph.states}.items()})
        classes.append(dict(class_id=key, representative=uid, members=members, class_exact_cardinality=N,
                            state=job.state, qos=job.qos, protected=job.protected,
                            old_S0=oldcounts, new_hard_physical=newcounts,
                            restored_STAY_options=len(restored), restored_STAY_support=restored,
                            old_STAY_removed=len(removed), old_migration_all_paths_included=old_migration_included,
                            active_initial_options=active_paths, active_STAY_options=len(active.stays),
                            lazy_STAY_options=len(domain.stays)-len(active.stays), active_variable_delta=dict(delta_vars),
                            old_allowed_starts=list(bound.allowed_starts), physical_allowed_starts=list(wide.allowed_starts),
                            STAY_candidate_counts_by_site=dict(sorted(sites.items())),
                            STAY_candidate_counts_by_start_displacement=dict(sorted(delta.items(),key=lambda x:int(x[0]))),
                            migration_path_counts_by_source_site=dict(sorted(migsource.items())),
                            migration_path_counts_by_destination_site=dict(sorted(migdest.items())),
                            all_physical_candidate_counts_by_source_site=dict(sorted((sites+migsource).items())),
                            all_physical_candidate_counts_by_start_displacement=dict(sorted((delta+migdelta).items(),key=lambda x:int(x[0]))),
                            physical_domain_sha256=domain.sha))
        hashes[key] = domain.sha
        # Keep only caches shared across classes; path blocks are never stored
        # as native columns or retained across all classes for this census.
        oldgen.templates.clear()
        if (index+1) % 25 == 0:
            print(day, 'STATIC_CLASSES', index+1, '/', len(prep['classes']), flush=True)
    if removed_old:
        raise ValueError('OLD_STAY_REMOVED_WITHOUT_HARD_PROOF')
    receipt = read(folder/'F2-CRA_MODEL_STATS.json'); compact = read(folder/'A2SC_MODEL_CENSUS.json')
    output = dict(PASS=True, day=day, authority='AIDC_A_STAGE_DOMAIN_AUTHORITY_V2',
                  scope='STATIC_LOCAL_HARD_VALID_DOMAIN; coupled feasibility and optimum not inferred',
                  jobs=len(jobs), frozen_population_jobs=len(bundle['known_population']), classes=len(classes),
                  class_exact_cardinality=sum(len(us) for us in prep['classes'].values()),
                  old_S0= dict(oldtotal), new_hard_physical=dict(newtotal),
                  old_S0_job_weighted=dict(weighted_old), new_hard_physical_job_weighted=dict(weighted_new),
                  counts_unit='class-level support choices; separate job-weighted multiplicities provided',
                  hard_valid_STAY_starts=newtotal['stay_options'], same_site_starts=newtotal['same_site_starts'],
                  compatible_site_starts=newtotal['compatible_site_starts'], prestart_options=newtotal['prestart_options'],
                  new_candidates_restored_relative_to_old_S0=newtotal['stay_options']-oldtotal['stay_options'],
                  migration_lazy_blocks=newtotal['migration_lazy_blocks'],
                  total_physical_path_multiplicity=newtotal['total_physical_path_multiplicity'],
                  active_initial_options=active_initial_paths,
                  active_initial_rule='complete STAY in proven histogram scopes (non-singleton or no migration); singleton mixed-flow S0+anchor and lazy STAY; new migration paths lazy',
                  active_STAY_options=active_STAY_count, lazy_STAY_options=lazy_stay_count,
                  complete_physical_STAY_universe_preserved=True, universal_complete_STAY_active=lazy_stay_count==0,
                  candidate_counts_by_class=classes,
                  STAY_candidate_counts_by_site=dict(sorted(bysite.items())),
                  STAY_candidate_counts_by_start_displacement=dict(sorted(bydelta.items(),key=lambda x:int(x[0]))),
                  STAY_candidate_counts_by_absolute_start_displacement=dict(sorted(byabs.items(),key=lambda x:int(x[0]))),
                  candidate_counts_by_site=dict(sorted(all_by_source.items())),
                  candidate_counts_by_start_displacement=dict(sorted(all_by_displacement.items(),key=lambda x:int(x[0]))),
                  candidate_counts_by_absolute_start_displacement=dict(sorted(all_by_absolute.items(),key=lambda x:int(x[0]))),
                  site_axis_semantics='initial/source site; migration destination axis separately reported',
                  migration_path_counts_by_source_site=dict(sorted(migration_by_source.items())),
                  migration_path_counts_by_destination_site=dict(sorted(migration_by_destination.items())),
                  migration_path_counts_by_start_displacement=dict(sorted(migration_by_displacement.items(),key=lambda x:int(x[0]))),
                  old_counts_by_site=dict(sorted(old_sites.items())),
                  old_counts_by_start_displacement=dict(sorted(old_displacements.items(),key=lambda x:int(x[0]))),
                  restored_counts_by_site=dict(sorted(restoredsite.items())),
                  restored_counts_by_start_displacement=dict(sorted(restoreddelta.items(),key=lambda x:int(x[0]))),
                  no_flex_anchor_inclusion=dict(PASS=all(a['anchor_included'] for a in noflex),
                                                valid_classes=sum(a['anchor_valid'] for a in noflex),
                                                invalid_anchor_classes=sum(not a['anchor_valid'] for a in noflex),
                                                global_feasibility_claimed=False, records=noflex),
                  old_domain_candidates_removed_only_by_hard_physics=True, old_STAY_removed=0,
                  old_migration_all_paths_included=True,
                  exact_duplicate_count=0, exact_duplicate_note='canonical (start,site) and migration block keys unique; distinct WAN timestamps retained',
                  safe_dominance_count=0, heuristic_dominance_permanent_cuts=0,
                  old_native_F2_CRA_exact_census={k:receipt[k] for k in ('columns','binaries','integers','continuous','constraints','nonzeros')},
                  old_reduced_S0_exact_census={k:compact[k] for k in ('columns','binaries','integers','continuous','rows','nnz')},
                  expected_active_initial_variable_delta=dict(variable_delta),
                  expected_active_initial_variable_delta_count_kind='EXACT_STRUCTURAL_FROM_F2_CRA_BRANCHES_NO_NATIVE_BUILD',
                  native_additional_rows_estimate=native_rows_estimate, native_additional_nnz_estimate=native_nnz_estimate,
                  matrix_size_estimate_kind='EXTRAPOLATED_ADDITIVE; A2SC reductions must be rederived later',
                  isolated_complete_STAY_support=dict(binary_variables=hist_binary, integer_count_variables=hist_integer,
                                                       class_count_variables=hist_integer, continuous_Runtime_finish_variables=newtotal['stay_options'],
                                                       cardinality_rows=len(classes), direct_incidence_nnz=stay_nnz,
                                                       universal_compact_substitution_adopted=False),
                  old_class_count_variables=old_class_count_variables,
                  active_class_count_variables=active_class_count_variables,
                  old_Runtime_finish_support=old_runtime_count, new_Runtime_finish_support=new_runtime_count,
                  old_graph_support_counts=dict(old_graph_events), active_graph_support_counts=dict(new_graph_events),
                  domain_sha256=digest(hashes), frozen_input=record(folder/'DATA.pkl'),
                  frozen_native_input=record(Path(production)/'inputs'/day/'NATIVE_INPUT.json'),
                  historical_native_census=record(folder/'F2-CRA_MODEL_STATS.json'), historical_reduced_census=record(folder/'A2SC_MODEL_CENSUS.json'),
                  resources_sha256=digest(asdict(resources)), frozen_bundle_sha256=digest(bundle),
                  census_producer=record(Path(__file__)), domain_producer=record(ROOT/'v42_a_stage_domain_v2/domain.py'),
                  native_model_builds=0, optimize_calls=0, Actual_reads=0, Fresh_runs=0, campaign_runs=0,
                  scientific_limits_changed=False, wall_seconds=time.perf_counter()-started)
    write(Path(out)/('MAY'+day[-2:]+'_STATIC_DOMAIN_CENSUS.json'), output)
    membership = dict(PASS=all(row['PASS'] for rows in memberships.values() for row in rows), day=day,
                      static_only=True, optimize_calls=0, native_model_builds=0,
                      all_original_scientific_attributes_preserved=True,
                      source_files={name:record(path) for name,(path,rows) in historical.items()},
                      groups={name:dict(expected_options=len(rows), checked_options=len(memberships[name]),
                                        PASS=len(rows)==len(memberships[name]) and all(r['PASS'] for r in memberships[name]),
                                        records=memberships[name]) for name,(path,rows) in historical.items()},
                      frozen_data=record(folder/'DATA.pkl'), resource_sha256=digest(asdict(resources)),
                      CC4_Runtime_service_GPU_grid_limits_changed=False,
                      reference_distance_permanent_cut_used=False)
    if historical:
        membership['PASS'] = membership['PASS'] and all(g['PASS'] for g in membership['groups'].values())
        if day == '2025-05-17':
            membership['MAY17_35_RESCUE_OPTIONS_INCLUDED'] = membership['PASS'] and len(memberships['MAY17_35_RESCUE']) == 35
            filename = 'MAY17_RESCUE_OPTION_MEMBERSHIP.json'
        else:
            membership['PR165_38_AND_PR166_S_A_S_B_S_C_S_D_INCLUDED'] = membership['PASS']
            filename = 'MAY19_PR165_PR166_OPTION_MEMBERSHIP.json'
        write(Path(out)/filename, membership)
        if not membership['PASS']:
            raise ValueError('HISTORICAL_RESCUE_MEMBERSHIP_FAIL')
    print(day, 'STATIC_CENSUS_PASS', output['new_candidates_restored_relative_to_old_S0'], 'restored STAY', flush=True)
    return output


def model_forecast(censuses, out=OUT):
    rows = []
    for census_value in censuses:
        day = census_value['day']; old = census_value['old_native_F2_CRA_exact_census']; compact = census_value['old_reduced_S0_exact_census']
        delta = census_value['expected_active_initial_variable_delta']; stay = census_value['isolated_complete_STAY_support']; phys = census_value['new_hard_physical']
        common = dict(day=day, jobs=census_value['jobs'], classes=census_value['classes'], optimize_calls=0, native_builds=0)
        rows.append(dict(common, domain='A_OLD_S0', comparison='historical native F2-CRA',
                         support_options=census_value['old_S0']['total_physical_path_multiplicity'],
                         class_count_variables=census_value['old_class_count_variables'], binary_variables=old['binaries'],
                         integer_count_variables=old['integers'], continuous_variables=old['continuous'], columns=old['columns'],
                         rows=old['constraints'], nnz=old['nonzeros'], variable_count_kind='EXACT_HISTORICAL_STRUCTURAL_RECEIPT',
                         rows_nnz_count_kind='EXACT_HISTORICAL_RECEIPT_READ_ONLY', model_adopted='historical evidence'))
        rows.append(dict(common, domain='B_NEW_COMPLETE_STAY_SUPPORT', comparison='isolated direct STAY incidence comparison; universal LP substitution rejected',
                         support_options=phys['stay_options'], class_count_variables=stay['class_count_variables'],
                         binary_variables=stay['binary_variables'], integer_count_variables=stay['integer_count_variables'],
                         continuous_variables=stay['continuous_Runtime_finish_variables'],
                         columns=stay['binary_variables']+stay['integer_count_variables']+stay['continuous_Runtime_finish_variables'],
                         rows=stay['cardinality_rows']+stay['continuous_Runtime_finish_variables'], nnz=stay['direct_incidence_nnz'],
                         variable_count_kind='EXACT_ISOLATED_SUPPORT_COUNT', rows_nnz_count_kind='SUPPORT_ONLY_DIRECT_INCIDENCE; NOT_FULL_NATIVE_MATRIX', model_adopted=False))
        rows.append(dict(common, domain='C_NEW_ACTIVE_INITIAL', comparison='complete STAY plus inherited old migration graph; F2-CRA before reduction',
                         support_options=census_value['active_initial_options'],
                         class_count_variables=census_value['active_class_count_variables'],
                         binary_variables=old['binaries']+delta.get('binary',0), integer_count_variables=old['integers']+delta.get('integer',0),
                         continuous_variables=old['continuous']+delta.get('continuous',0),
                         columns=old['columns']+sum(delta.values()),
                         rows=old['constraints']+census_value['native_additional_rows_estimate'], nnz=old['nonzeros']+census_value['native_additional_nnz_estimate'],
                         variable_count_kind='EXACT_STRUCTURAL_FROM_INHERITED_FACTORY_BRANCHES',
                         rows_nnz_count_kind='EXTRAPOLATED_ADDITIVE; NOT_A_NATIVE_MODEL_BUILD', model_adopted=True,
                         lazy_STAY_options=census_value['lazy_STAY_options']))
        rows.append(dict(common, domain='D_MIGRATION_LAZY_POOL', comparison='matrix-free scientific pool; only newly omitted migrations activate later',
                         support_options=phys['migration_path_multiplicity'], class_count_variables=0, binary_variables=0,
                         integer_count_variables=0, continuous_variables=0, columns=0, rows=0, nnz=0,
                         variable_count_kind='EXACT_ZERO_MATERIALIZATION', rows_nnz_count_kind='EXACT_ZERO_NATIVE_MATRIX_MATERIALIZATION',
                         model_adopted='lazy pool', lazy_blocks=phys['migration_lazy_blocks'],
                         potential_individual_path_columns=phys['migration_path_multiplicity']))
        rows.append(dict(common, domain='A_OLD_S0_A2SC', comparison='historical reduction; its reduction rates are not assumed to transfer',
                         support_options=census_value['old_S0']['total_physical_path_multiplicity'],
                         class_count_variables=census_value['old_class_count_variables'], binary_variables=compact['binaries'], integer_count_variables=compact['integers'],
                         continuous_variables=compact['continuous'], columns=compact['columns'], rows=compact['rows'], nnz=compact['nnz'],
                         variable_count_kind='EXACT_HISTORICAL_STRUCTURAL_RECEIPT', rows_nnz_count_kind='EXACT_HISTORICAL_RECEIPT_READ_ONLY', model_adopted='historical evidence'))
    fields = ['day','domain','comparison','jobs','classes','support_options','class_count_variables','binary_variables','integer_count_variables',
              'continuous_variables','columns','rows','nnz','variable_count_kind','rows_nnz_count_kind','model_adopted','lazy_blocks',
              'potential_individual_path_columns','lazy_STAY_options','native_builds','optimize_calls']
    path = Path(out)/'MODEL_SIZE_FORECAST.csv'; path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w',encoding='utf8',newline='') as handle:
        writer = csv.DictWriter(handle, fields, lineterminator='\n'); writer.writeheader(); writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production', type=Path, default=PRODUCTION)
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--day', choices=DAYS)
    args = parser.parse_args()
    days = (args.day,) if args.day else DAYS
    results = [census(day, args.production, args.out) for day in days]
    if len(results)==len(DAYS):model_forecast(results,args.out)


if __name__ == '__main__':
    main()
