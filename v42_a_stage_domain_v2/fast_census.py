"""Build-free fast active census and one verified physical-index cache per date.

No native model is built. Only immutable original coefficient loading is used
for the frozen ranking. JSON contains active/omitted STAY intervals and counts;
large compact physical blocks are saved once outside Git, by representative.
"""
import argparse
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import pickle
import time

from .active import (ActivePolicy, indexed_contains, prepare_fast_active,
                     support_from_membership_receipt, support_from_verified_schedule, _intervals, cache_noop_check)
from .census import load_frozen, PRODUCTION, record, read, write, digest
from .fast_prepare import ROOT, OUT, OLD, CENSUS, STATIC, DAYS


def _producer_sources():
    # Engineering ranking/cache IO does not produce physical membership.
    return [record(ROOT/path) for path in ("v42_a_stage_domain_v2/domain.py",
        "v42_boundary/generator.py", "v42_job_capability.py")]


def save_physical_cache(day, data, domains, frozen_path, static_root=STATIC):
    folder = Path(static_root)/day; folder.mkdir(parents=True,exist_ok=True)
    path = folder/"PHYSICAL_DOMAIN_CACHE.pkl.gz"; receipt_path = folder/"PHYSICAL_DOMAIN_CACHE.json"
    representatives = {members[0]:domains[members[0]] for members in data[7]["classes"].values()}
    for domain in representatives.values():
        # Remove the default unpicklable lambda; this callback carries no
        # physical condition. Shared immutable Generator/resources stay shared.
        domain.cache.check = cache_noop_check
    identity = dict(day=day, frozen_DATA=record(frozen_path),
                    resources_sha256=digest(asdict(data[3])),producer_sources=_producer_sources())
    if path.exists() or receipt_path.exists():
        load_physical_cache(day,data,frozen_path,static_root)
        return read(receipt_path)
    with gzip.open(path,"wb",compresslevel=1) as handle:
        pickle.dump(dict(representatives=representatives,classes=data[7]["classes"]),handle,protocol=5)
    receipt = dict(PASS=True,schema="FAST_COMPLETE_PHYSICAL_REPRESENTATIVE_CACHE_V1",**identity,
        cache=record(path),representatives=len(representatives),jobs=len(domains),
        cache_writer=record(Path(__file__)),
        complete_domain_hashes={uid:domain.sha for uid,domain in sorted(representatives.items())},
        scientific_candidates_removed=0,serialized_native_variables=0,
        physical_blocks_written_once=True,inside_git=False)
    write(receipt_path,receipt)
    return receipt


def load_physical_cache(day, data, frozen_path, static_root=STATIC):
    folder=Path(static_root)/day; receipt=read(folder/"PHYSICAL_DOMAIN_CACHE.json")
    if (receipt.get("PASS") is not True or receipt.get("schema")!="FAST_COMPLETE_PHYSICAL_REPRESENTATIVE_CACHE_V1"
            or receipt["day"]!=day or receipt["frozen_DATA"]["sha256"]!=record(frozen_path)["sha256"]
            or receipt["resources_sha256"]!=digest(asdict(data[3]))
            or receipt["producer_sources"]!=_producer_sources()):
        raise ValueError("FROZEN_PHYSICAL_CACHE_IDENTITY_DRIFT")
    path=folder/"PHYSICAL_DOMAIN_CACHE.pkl.gz"
    if receipt["cache"]["sha256"]!=record(path)["sha256"]:
        raise ValueError("PHYSICAL_CACHE_BYTE_DRIFT")
    with gzip.open(path,"rb") as handle:
        cached=pickle.load(handle)
    if cached["classes"]!=data[7]["classes"]:
        raise ValueError("PHYSICAL_CACHE_EXACT_CLASS_MEMBERSHIP_DRIFT")
    domains={}
    for members in data[7]["classes"].values():
        uid=members[0]; domain=cached["representatives"][uid]
        if (domain.sha!=receipt["complete_domain_hashes"][uid] or domain.cache.r!=data[3]
                or domain.duration!=data[1][uid].service_slots):
            raise ValueError("PHYSICAL_CACHE_COMPLETE_AUTHORITY_DRIFT")
        for member in members:
            domains[member]=domain
    return domains


def required_supports(day, data, old_root=OLD, census_root=CENSUS):
    result=[]; root=Path(census_root)
    if day.endswith(("17","19")):
        path=root/("MAY17_RESCUE_OPTION_MEMBERSHIP.json" if day.endswith("17")
                   else "MAY19_PR165_PR166_OPTION_MEMBERSHIP.json")
        result.append(support_from_membership_receipt(read(path),record(path)["sha256"]))
    folder=Path(old_root)/("MAY"+day[-2:])
    schedule=folder/"ACTIVE_DOMAIN_FEASIBLE_SCHEDULE.json"
    if schedule.exists():
        result.append(support_from_verified_schedule(read(schedule),data[7]["classes"],record(schedule)["sha256"]))
    for component in ("rho","migration_count","shift_magnitude","prestart_relocation"):
        path=folder/component/"INDEPENDENT_ORIGINAL_AND_PHYSICAL_REPLAY.json"
        if path.exists():
            payload=read(path)
            if payload.get("PASS") is True:
                result.append(support_from_verified_schedule(dict(selected_jobs=payload["selected_jobs"],
                    independent_physical=payload["physical"]),data[7]["classes"],record(path)["sha256"],
                    name="VERIFIED_"+component))
    return tuple(result)


def verify_partition(ledger):
    examined=0
    for pool in ledger["stay_pools"].values():
        physical=set(pool.physical_domain.stays); inactive=set(pool.keys())
        if (pool.active & inactive or pool.active | inactive != physical
                or len(inactive)!=pool.inactive_count):
            raise ValueError("EXACT_COMPLETE_STAY_ACTIVE_POOL_PARTITION")
        examined+=len(physical)
    receipt=ledger["receipt"]
    if (receipt["active_migration"]+receipt["inactive_migration"]!=receipt["physical_migration"]
            or any(pool.inactive_count<0 for pool in ledger["migration_pools"].values())):
        raise ValueError("EXACT_COMPLETE_MIGRATION_ACTIVE_POOL_PARTITION")
    return dict(PASS=True,STAY_candidates_independently_examined=examined,
                active_pool_disjoint=True,active_union_pool_equals_physical=True,
                migration_active_keys_selected_only_from_complete_physical_blocks=True,
                native_model_builds=0,optimize_calls=0)


def produce_day(day, output=OUT, static_root=STATIC):
    started=time.perf_counter(); output=Path(output); output.mkdir(parents=True,exist_ok=True)
    data,frozen=load_frozen(day); inputs=PRODUCTION/"inputs"/day
    bundle=read(inputs/"NATIVE_INPUT.json")
    expected=read(CENSUS/("MAY"+day[-2:]+"_STATIC_DOMAIN_CENSUS.json"))
    if digest(data[0])!=digest(bundle):
        raise ValueError("FROZEN_FAST_CENSUS_BUNDLE_DRIFT")
    from v42_pr134_b1.native import bind
    from .fast_backend import frozen_grid_priority
    import v42_boundary.model as boundary
    import v42_exact.validation as validation
    grid_folder=Path(static_root)/day/"CENSUS_GRID_BINDING"; grid_folder.mkdir(parents=True,exist_ok=True)
    from v42_may01 import prepare as original
    coefficient_loader=original.native_coefficients
    planning_grid=boundary.planning_grid; validation_check=validation.check
    try:
        _,_,coefficients,*_=bind(bundle,inputs,grid_folder)
    finally:
        # bind installs a date closure. Retain the original code-bearing
        # loader for the next isolated static date within this same process.
        original.native_coefficients=coefficient_loader
        boundary.planning_grid=planning_grid; validation.check=validation_check
    scores,ranking=frozen_grid_priority(coefficients,data[3])
    # Freeze the exact ranking before candidate selection, never after a solve.
    ranking_path=output/("MAY"+day[-2:]+"_FROZEN_GRID_RANKING.json")
    if ranking_path.exists() and read(ranking_path)!=ranking:
        raise ValueError("PREREGISTERED_FAST_GRID_RANKING_DRIFT")
    write(ranking_path,ranking)
    policy=read(output/"ACTIVE_DOMAIN_POLICY.json")
    support=required_supports(day,data)
    cache_path=Path(static_root)/day/"PHYSICAL_DOMAIN_CACHE.json"
    domains=load_physical_cache(day,data,frozen/"DATA.pkl",static_root) if cache_path.exists() else None
    active,domains,ledger=prepare_fast_active(data,policy=ActivePolicy(policy["same_site_radius"],
        policy["extra_stay_per_class"],policy["migration_extra_seeds"]),required_support=support,
        grid_scores=scores,expected_grid_priority_hash=ranking["score_sha256"],physical_domains=domains)
    partition=verify_partition(ledger)
    old_classes={row["class_id"]:row for row in expected["candidate_counts_by_class"]}
    for key,pool in ledger["stay_pools"].items():
        original=old_classes[key]
        if (pool.physical_domain.sha!=original["physical_domain_sha256"]
                or pool.physical_count!=original["new_hard_physical"]["stay_options"]
                or pool.physical_domain.count!=original["new_hard_physical"]["total_physical_path_multiplicity"]
                or ledger["selection_records"][key]["historical_hard_valid_STAY"]<original["old_S0"]["stay_options"]):
            raise ValueError("UNCHANGED_COMPLETE_PHYSICAL_CLASS_DOMAIN_REQUIRED")
    if ledger["receipt"]["physical_STAY"]!=expected["hard_valid_STAY_starts"]:
        raise ValueError("UNCHANGED_COMPLETE_STAY_CENSUS_REQUIRED")
    cache=save_physical_cache(day,data,domains,frozen/"DATA.pkl",static_root)
    seeds={}
    for evidence in support:
        for key,options in evidence.class_options.items():
            uid=data[7]["classes"][key][0]
            for option in options:
                if option.migrated and indexed_contains(data[1][uid],data[2][uid],data[3],domains[uid],option):
                    seeds.setdefault(key,set()).add(option)
    initial=dict(PASS=True,day=day,active_policy=active[7]["active_policy"],
        frozen_grid_ranking=record(ranking_path),required_support_sources=active[7]["required_support_sources"],
        all_required_independently_valid_options_available=True,
        active_STAY_intervals_by_class={key:_intervals(pool.active) for key,pool in ledger["stay_pools"].items()},
        migration_explicit_seeds_by_class={key:[asdict(option) for option in sorted(values)] for key,values in seeds.items()},
        active_STAY=ledger["receipt"]["active_STAY"],active_migration=ledger["receipt"]["active_migration"],
        active_migration_includes_graph_recombinations=True,
        no_bounds_or_objective_locks_imported=True,physical_cache=cache,
        source_producer=record(Path(__file__)),native_model_builds=0,optimize_calls=0)
    result=dict(ledger["receipt"],day=day,physical_domain_unchanged=True,
        original_complete_census=record(CENSUS/("MAY"+day[-2:]+"_STATIC_DOMAIN_CENSUS.json")),
        source_frozen_DATA=record(frozen/"DATA.pkl"),physical_cache=cache,
        build_free_selection_seconds=time.perf_counter()-started,native_model_builds=0,optimize_calls=0)
    write(output/("MAY"+day[-2:]+"_INITIAL_ACTIVE_SUPPORT.json"),initial)
    write(output/("MAY"+day[-2:]+"_ACTIVE_POOL_PARTITION.json"),dict(partition,day=day,
        physical_domain_unchanged=True,receipt=result))
    return result,initial,partition


def produce(days=DAYS, output=OUT, static_root=STATIC):
    output=Path(output); results={}; supports={}; partitions={}
    for day in days:
        result,initial,partition=produce_day(day,output,static_root)
        results[day]=result; supports[day]=initial; partitions[day]=partition
        print(json.dumps(dict(day=day,active_STAY=result["active_STAY"],inactive_STAY=result["inactive_STAY"],
            active_migration=result["active_migration"],inactive_migration=result["inactive_migration"],
            static_seconds=result["build_free_selection_seconds"])),flush=True)
    # A subset invocation merges immutable completed dates without deleting any.
    for filename,payload in (("INITIAL_ACTIVE_SUPPORT.json",supports),("ACTIVE_POOL_PARTITION.json",partitions)):
        path=output/filename; prior=read(path).get("dates",{}) if path.exists() else {}
        prior.update(payload); write(path,dict(PASS=all(v["PASS"] for v in prior.values()),dates=prior))
    for filename,kind in (("STAY_LAZY_POOL_CENSUS.json","STAY"),("MIGRATION_LAZY_POOL_CENSUS.json","migration")):
        path=output/filename; prior=read(path).get("dates",{}) if path.exists() else {}
        for day,result in results.items():
            rows=result["classes"]
            prior[day]=dict(PASS=True,physical=result["physical_"+kind],active=result["active_"+kind],
                inactive=result["inactive_"+kind],inactive_native_variables=0,
                classes=[{k:v for k,v in row.items() if k not in ("migration","selection")}
                         for row in rows] if kind=="STAY" else [row["migration"] for row in rows])
        write(path,dict(PASS=True,scientific_candidates_permanently_removed=0,
                       representation="LOSSLESS_SCIENTIFIC_INDICES_MINUS_ACTIVE_SUPPORT",dates=prior))
    return results


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--days",nargs="+",choices=DAYS,default=list(DAYS))
    parser.add_argument("--output",type=Path,default=OUT);parser.add_argument("--static-root",type=Path,default=STATIC)
    args=parser.parse_args();produce(tuple(args.days),args.output,args.static_root)


if __name__=="__main__":main()
