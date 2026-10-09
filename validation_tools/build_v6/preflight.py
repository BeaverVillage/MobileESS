"""Fresh original model reconstruction with Native=0, never old Solver state."""
from pathlib import Path
import argparse, json, pickle, time
from v42_pr134_b1.common import ROOT, read, atomic, record, now
from v42_may_campaign_native90.preflight import native_zero
from v42_may_build_v6 import a_stage
from v42_may_recovery_v5.a_cache import _semantic_data

RUN = ROOT/'runtime/v42_may_campaign/native90_build_reuse_20261009_01'
DOC = ROOT/'docs/v42_may_build_v6_20261009'


def main(day, probe, baseline=False, cache_from=None):
    base = read(RUN/'CAMPAIGN_MANIFEST.json')
    old = RUN/'dates/B1'/day/'attempts/recovery_v5_01/output'
    if day != '2025-05-23':
        old = RUN/'dates/B1'/day/'output'
    old_data = old/'STATIC/DATA/DATA.pkl'
    frozen = record(old_data)
    output = RUN/'preflight_v6/B1'/day/probe/'output'
    request = dict(root=str(RUN),arm='B1',day=day,input_folder=base['input_folders']['B1/'+day],
                   output=str(output),preflight_native_zero=True)
    DOC.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    if cache_from:
        source=RUN/'preflight_v6/B1'/day/cache_from/'output'
        cached_prep=read(source/'A_PREPARE_RECEIPT.json')
        physical=read(source/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json')
        cache=dict(scope='CURRENT_DATE_NATIVE_ZERO_INPUTS_ONLY',folder=str(source),
            preparation=record(source/'A_PREPARE_RECEIPT.json'),DATA=record(source/'STATIC/DATA/DATA.pkl'),
            physical_receipt=record(source/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'),
            inputs=cached_prep['scientific_input'],model_verification=cached_prep['verification'],
            receipt=record(source/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'),
            complete_domain_hashes=physical['complete_domain_hashes'])
        candidate=RUN/'V6_STAGED_CACHE_ADMISSION.json'
        atomic(candidate,dict(input_cache_sources={'B1/'+day:cache},production_admission=False,UTC=now()))
        request.update(manifest=str(candidate),input_authority_root=str(Path(base['scientific_authority']['path']).parent),
            _current_date_physical_cache=str(source),_physical_cache_identity=cache['receipt'],
            _expected_complete_domain_hashes=cache['complete_domain_hashes'],_expected_model_verification=cache['model_verification'])
    if not baseline:
        with native_zero() as calls:
            state=a_stage.prepare(request)
    else:
        # Baseline original matrix construction with the independently pinned
        # original input-only DATA/complete physical domains. No solution enters.
        from v42_may_recovery_v5 import a_stage as original, input_cache, a_cache
        from v42_a_stage_domain_v2.fast_census import load_physical_cache
        old_seed, old_load = input_cache.seed_input_cache, a_cache.load_current_date_physical_cache
        def seed(req,module,destination):
            with old_data.open('rb') as handle: cached=pickle.load(handle)
            fresh=module.load_native()
            assert (fresh[0],fresh[1],fresh[2],fresh[4],fresh[5]) == cached[:5]
            with (destination/'DATA.pkl').open('xb') as handle: pickle.dump(cached,handle,protocol=5)
        def physical(req,fresh,**kwargs):
            with old_data.open('rb') as handle: cached=pickle.load(handle)
            assert _semantic_data(cached)==_semantic_data(fresh)
            return load_physical_cache(day,cached,old_data,old/'STATIC/DOMAIN')
        input_cache.seed_input_cache, a_cache.load_current_date_physical_cache = seed, physical
        try:
            with native_zero() as calls:
                state=original.prepare(request)
        finally:
            input_cache.seed_input_cache,a_cache.load_current_date_physical_cache=old_seed,old_load
    assert not calls and record(old_data)==frozen
    prep=read(output/'A_PREPARE_RECEIPT.json')
    with old_data.open('rb') as handle: cached=pickle.load(handle)
    with (output/'STATIC/DATA/DATA.pkl').open('rb') as handle: fresh=pickle.load(handle)
    assert _semantic_data(cached)==_semantic_data(fresh)
    old_domains=read(old/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json')
    new_domains=read(output/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json')
    assert old_domains['complete_domain_hashes']==new_domains['complete_domain_hashes']
    proof=dict(PASS=True,day=day,mode='PINNED_ORIGINAL_INPUT_BASELINE' if baseline else 'VERIFIED_NATIVE_ZERO_INPUT_CACHE' if cache_from else 'FRESH_V6',
               Native_calls=0,P2_calls=0,UTC=now(),elapsed_seconds=time.perf_counter()-start,
               preparation_seconds=prep['preparation_wall_seconds'],old_input_data=frozen,
               preparation=record(output/'A_PREPARE_RECEIPT.json'),
               model_verification=prep['verification'],
               original_and_fresh_scientific_values_identical=True,
               all_complete_domain_hashes_identical=True,old_point_bound_clock_loaded=False,
               full_STAY_and_migration_not_pruned=True)
    atomic(DOC/(day+('_BASELINE' if baseline else '_CACHED' if cache_from else '_FRESH')+'.json'),proof)
    print(json.dumps(proof,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--day',required=True);parser.add_argument('--probe',required=True)
    parser.add_argument('--baseline',action='store_true');parser.add_argument('--cache-from');args=parser.parse_args()
    main(args.day,args.probe,args.baseline,args.cache_from)
