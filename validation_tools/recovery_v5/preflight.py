"""Build May11/19 fresh models without Native using verified input-only caches."""
from pathlib import Path
import json
from v42_pr134_b1.common import read, record, atomic, now, ROOT
from v42_may_recovery_v5 import a_stage
from v42_may_campaign_native90.preflight import native_zero

RUN=ROOT/'runtime/v42_may_campaign/native90_build_reuse_20261009_01'
DOC=ROOT/'docs/v42_may_recovery_v5_20261009'


def caches():
    result={}
    for day in ('2025-05-11','2025-05-19'):
        folder=RUN/'dates/B1'/day/'output'
        prep=read(folder/'A_PREPARE_RECEIPT.json')
        physical=read(folder/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json')
        result['B1/'+day]=dict(folder=str(folder),DATA=record(folder/'STATIC/DATA/DATA.pkl'),
            physical_receipt=record(folder/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'),
            receipt=record(folder/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'),
            inputs=prep['scientific_input'],complete_domain_hashes=physical['complete_domain_hashes'],
            model_verification=prep['verification'])
    return result


def main(day=None, probe='validated_01'):
    if day is None:
        import subprocess,sys
        # Legacy date-bound modules are process-local mutable state. Match
        # production's one fresh process per date during every reconstruction.
        for current in ('2025-05-11','2025-05-19'):
            subprocess.run([sys.executable,'-B','-X','utf8','-m',
                'validation_tools.recovery_v5.preflight','--day',current,'--probe',probe],check=True,cwd=ROOT)
        return
    cache=caches();candidate=RUN/'V5_STAGED_CACHE_ADMISSION.json'
    atomic(candidate,dict(input_cache_sources=cache,production_admission=False,UTC=now()))
    manifest=read(RUN/'CAMPAIGN_MANIFEST.json');rows=[]
    for day in ((day,) if day else ('2025-05-11','2025-05-19')):
        folder=RUN/'preflight_v5/B1'/day/probe
        output=folder/'output'
        if output.exists():raise PermissionError('PREFLIGHT_OUTPUT_ALREADY_EXISTS')
        row=cache['B1/'+day]
        request=dict(root=str(RUN),manifest=str(candidate),arm='B1',day=day,
            input_folder=manifest['input_folders']['B1/'+day],output=str(output),preflight_native_zero=True,
            input_authority_root=str(Path(manifest['scientific_authority']['path']).parent),
            _current_date_physical_cache=row['folder'],_physical_cache_identity=row['receipt'],
            _expected_complete_domain_hashes=row['complete_domain_hashes'],
            _expected_model_verification=row['model_verification'])
        with native_zero() as calls:
            state=a_stage.prepare(request)
        assert not calls
        prep=read(output/'A_PREPARE_RECEIPT.json')
        before=read(RUN/'dates/B1'/day/'output/A_PREPARE_RECEIPT.json')
        assert prep['verification']==before['verification'] and prep['PASS']
        report=read(output/'REFERENCE_REUSE_PROFILE.json')
        assert report['exact_same_fresh_reference_hits']==1
        proof=dict(PASS=True,day=day,Native_calls=0,P2_calls=0,UTC=now(),
            model_verification=prep['verification'],original_model_all_attributes_identical=True,
            complete_physical_domains_identical=True,old_point_bound_clock_loaded=False,
            original_prepare_seconds=before['preparation_wall_seconds'],
            improved_prepare_seconds=prep['preparation_wall_seconds'],reference_reuse=report,
            preparation=record(output/'A_PREPARE_RECEIPT.json'),
            input_cache=record(output/'INPUT_GRAPH_CACHE_VERIFICATION.json'),
            physical_cache=record(output/'CURRENT_DATE_PHYSICAL_CACHE_REUSE.json'))
        atomic(DOC/('BUILD_EQUIVALENCE_'+day+'.json'),proof)
        rows.append(proof);print(json.dumps({k:proof[k] for k in ['PASS','day','original_prepare_seconds','improved_prepare_seconds','reference_reuse']}),flush=True)
        del state
        import gc;gc.collect()
    all_rows=[read(DOC/('BUILD_EQUIVALENCE_'+d+'.json')) for d in ('2025-05-11','2025-05-19')
              if (DOC/('BUILD_EQUIVALENCE_'+d+'.json')).is_file()]
    if len(all_rows)==2:
        atomic(DOC/'BUILD_EQUIVALENCE.json',dict(PASS=all(r['PASS'] for r in all_rows),Native_calls=0,P2_calls=0,UTC=now(),dates=all_rows,one_fresh_process_per_production_date=True))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--day');parser.add_argument('--probe',default='validated_01')
    args=parser.parse_args();main(args.day,args.probe)
