"""Same-date scientific input cache; Solver states, points and clocks are excluded."""
from dataclasses import asdict
from pathlib import Path
import pickle
import os
from .common import read, record, atomic, digest


def verify_cache_authority(request, source):
    doc=read(request['manifest'])
    cache=doc.get('input_cache_sources',{}).get(request['arm']+'/'+request['day'])
    if (cache is None or Path(cache['folder']).resolve()!=Path(source).resolve()
            or Path(source).resolve()!=Path(request['root']).resolve()/'dates/B1'/request['day']/'output'):
        raise PermissionError('V5_SAME_DATE_INPUT_CACHE_ADMISSION_REQUIRED')
    for name in ('DATA','physical_receipt'):
        if record(cache[name]['path'])!=cache[name]:
            raise ValueError('V5_INPUT_CACHE_BYTE_DRIFT:'+name)
    for name, receipt in cache['inputs'].items():
        expected=Path(request['input_folder'])/name
        if Path(receipt['path']).resolve()!=expected.resolve() or record(expected)!=receipt:
            raise ValueError('V5_INPUT_CACHE_FROZEN_INPUT_IDENTITY_DRIFT:'+name)
    return cache


def admitted_cache_output(request, output):
    from .policy import attempt_path
    output=Path(output).resolve();root=Path(request['root']).resolve()
    if output==attempt_path(root,'B1',request['day'])/'output':
        return True
    preflight=root/'preflight_v5'/'B1'/request['day']
    return request.get('preflight_native_zero') is True and output.is_relative_to(preflight) and output.name=='output'


def seed_input_cache(request, module, base):
    if not request.get('_current_date_physical_cache'):
        return False
    if request['day'] == '2025-05-19':
        # This date's original DATA producer took 30.6 s, while admitting its
        # graph pickle with independent class verification took substantially
        # longer. Recompute the original DATA; only physical-domain cache
        # verification and fresh-matrix reference reuse remain enabled.
        atomic(Path(request['output'])/'INPUT_GRAPH_CACHE_VERIFICATION.json',dict(
            PASS=True,graph_cache_reused=False,mode='FRESH_ORIGINAL_DATA_PRODUCER',
            Native_calls=0,P2_calls=0,old_Solver_point_or_bound_or_clock_loaded=False,
            independent_full_model_verification_required=True))
        return False
    source=Path(request['_current_date_physical_cache'])
    cache=verify_cache_authority(request,source)
    with Path(cache['DATA']['path']).open('rb') as stream:
        cached=pickle.load(stream)
    bundle,jobs,bounds,seconds,resources,raw=module.load_native()
    # Read the original date input producer again, then compare every original
    # field before admitting its graph cache. UID/class population is retained.
    fresh=(bundle,jobs,bounds,resources,raw)
    old=cached[:5]
    if (bundle!=old[0] or jobs!=old[1] or bounds!=old[2] or resources!=old[3] or raw!=old[4]):
        raise ValueError('V5_CACHED_INPUT_FRESH_ORIGINAL_VALUES_DIFFER')
    signatures={}
    from v42_root.data import scientific_signature
    from v42_boundary.generator import Generator
    identity=Generator(resources,max(b.latest_completion for b in bounds.values())).identity
    for uid, job in sorted(jobs.items()):
        key=digest(scientific_signature(job,bounds[uid],identity,raw[uid],bundle))
        signatures.setdefault(key,[]).append(uid)
    if sorted(map(tuple,signatures.values()))!=sorted(map(tuple,cached[7]['classes'].values())):
        raise ValueError('V5_CACHED_INPUT_INDEPENDENT_CLASS_MEMBERSHIP_DRIFT')
    data=(*fresh,cached[5],cached[6],dict(cached[7]))
    temporary=Path(base)/'DATA_CACHE_SEED.pending'
    with temporary.open('xb') as stream:
        pickle.dump(data,stream,protocol=5)
    os.replace(temporary,Path(base)/'DATA.pkl')
    atomic(Path(request['output'])/'INPUT_GRAPH_CACHE_VERIFICATION.json',dict(PASS=True,
        source_DATA=cache['DATA'],fresh_original_inputs_equal=True,jobs=len(jobs),classes=len(signatures),
        Native_calls=0,P2_calls=0,old_Solver_point_or_bound_or_clock_loaded=False,
        input_only_fields=['bundle','jobs','bounds','resources','raw','graphs','original_graphs','class_membership']))
    return True
