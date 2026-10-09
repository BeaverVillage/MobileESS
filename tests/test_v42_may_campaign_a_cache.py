"""Same-date own physical input cache contracts, no Native/model builds."""
import copy
import pickle
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from v42_job_capability import Job, ServiceBoundary
from v42_a_stage_domain_v2.active import _graph
from v42_a_stage_domain_v2.fast_census import save_physical_cache
from v42_may_campaign.a_cache import load_current_date_physical_cache, _semantic_data
from v42_may_campaign.common import atomic, read, record


@dataclass
class CacheResource:
    capacities: dict
    fixed_gpu: dict


def own_cache(tmp_path):
    day = '2025-05-01'
    root = tmp_path / 'candidate-current'
    source = root / 'preflight_cases/B1' / day
    output = source.with_name(day + '_attempt2')
    inputs = root / 'inputs/B1' / day
    for folder in (source / 'STATIC/DATA', output, inputs): folder.mkdir(parents=True)
    bundle = dict(day=day, capacities={'SITE': 4}, causal_raw_input=True)
    job = Job('u', 'RUNNING', 0, 0, 0, 'SITE', 4, 1, duration_authority='frozen-current-Q50')
    bound = ServiceBoundary('current-bound', True, True, (0,), 4)
    resource = CacheResource({'SITE': 4}, {('SITE', 1): .5})
    domain = SimpleNamespace(stays=((0, 'SITE'),), blocks=(), duration=4, sha='complete-physical-domain',
                             cache=SimpleNamespace(r=resource, check=None))
    graph = _graph(job, set(domain.stays), (), domain, False)
    data = (bundle, {'u': job}, {'u': bound}, resource, {'u': {'runtime': 4}}, {'u': graph}, {'u': graph},
            dict(classes={'class': ['u']}, graph_seconds=1.))
    atomic(inputs / 'NATIVE_INPUT.json', bundle)
    atomic(inputs / 'WINDOWS.json', [dict(job_id='u', allowed_starts=[0])])
    atomic(source / 'STATIC/DATA/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json', bundle)
    data_path = source / 'STATIC/DATA/DATA.pkl'
    with data_path.open('wb') as stream: pickle.dump(data, stream, protocol=5)
    save_physical_cache(day, data, {'u': domain}, data_path, source / 'STATIC/DOMAIN')
    files = [record(inputs / name) for name in ('NATIVE_INPUT.json', 'WINDOWS.json')]
    atomic(inputs / 'INPUT_IDENTITY.json', dict(PASS=True, day=day, arm='B1', bundle=files[0], windows=files[1]))
    atomic(root / 'MAY31_INDEPENDENT_INPUT_VERIFICATION.json', dict(PASS=True, Native_calls=0,
        dates=[dict(PASS=True, day=day, arm='B1', files=files)], input_folders={'B1/' + day: str(inputs)}))
    request = dict(root=str(root), input_folder=str(inputs), output=str(output), day=day, arm='B1',
                   _current_date_physical_cache=str(source))
    return request, copy.deepcopy(data)


def test_verified_own_cache_returns_only_physics_and_leaves_source_files_immutable(tmp_path):
    request, fresh = own_cache(tmp_path)
    source = Path(request['_current_date_physical_cache'])
    protected = [record(p) for p in source.rglob('*') if p.is_file()]
    # Pickle/counter differences do not alter physical/scientific semantics.
    fresh[7]['graph_seconds'] = 999.
    domains = load_current_date_physical_cache(request, fresh)
    assert set(domains) == {'u'} and domains['u'].duration == 4
    assert domains['u'].cache.r == fresh[3]
    assert all(record(r['path']) == r for r in protected)
    receipt = read(Path(request['output']) / 'CURRENT_DATE_PHYSICAL_CACHE_REUSE.json')
    assert receipt['old_semantic_SHA'] == receipt['fresh_semantic_SHA']
    assert receipt['Native_calls'] == 0 and receipt['fresh_model_required']
    for name in ('prior_state_used', 'prior_native_point_used', 'prior_UB_LB_used', 'prior_native_runtime_used'):
        assert receipt[name] is False


@pytest.mark.parametrize('changed', ['cross_date', 'cross_root', 'same_attempt', 'history_directory'])
def test_cache_is_limited_to_same_new_campaign_and_date(tmp_path, changed):
    request, data = own_cache(tmp_path)
    if changed == 'cross_date': request['day'] = '2025-05-02'
    elif changed == 'cross_root': request['root'] = str(tmp_path / 'other-campaign')
    elif changed == 'same_attempt': request['output'] = request['_current_date_physical_cache']
    else: request['_current_date_physical_cache'] = str(Path(request['root']) / 'docs/old_result')
    with pytest.raises(PermissionError, match='SAME_DATE_PREFLIGHT_CACHE_ONLY'):
        load_current_date_physical_cache(request, data)


@pytest.mark.parametrize('changed', ['bundle', 'jobs', 'bounds', 'resources', 'raw', 'classes', 'graphs', 'original_graphs'])
def test_each_current_scientific_input_difference_is_rejected_without_fallback(tmp_path, changed):
    request, data = own_cache(tmp_path)
    if changed == 'bundle': data[0]['new-causal-value'] = 1
    elif changed == 'jobs': data[1]['u'] = replace(data[1]['u'], service_slots=5)
    elif changed == 'bounds': data[2]['u'] = replace(data[2]['u'], latest_completion=5)
    elif changed == 'resources': data[3].capacities['SITE'] = 5
    elif changed == 'raw': data[4]['u']['runtime'] = 5
    elif changed == 'classes': data[7]['classes'] = {'other-class': ['u']}
    elif changed == 'graphs':
        data = (*data[:5], {'u': replace(data[5]['u'], fixed=None)}, data[6], data[7])
    else:
        data = (*data[:6], {'u': replace(data[6]['u'], fixed=None)}, data[7])
    with pytest.raises(ValueError, match='SCIENTIFIC_INPUT_MISMATCH'):
        load_current_date_physical_cache(request, data)
    assert not (Path(request['output']) / 'CURRENT_DATE_PHYSICAL_CACHE_REUSE.json').exists()


@pytest.mark.parametrize('name', ['NATIVE_INPUT.json', 'WINDOWS.json'])
def test_current_native_or_windows_byte_drift_is_rejected(tmp_path, name):
    request, data = own_cache(tmp_path)
    path = Path(request['input_folder']) / name
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='FILE_SHA_OR_PATH_DRIFT'):
        load_current_date_physical_cache(request, data)


def test_original_domain_producer_sha_drift_is_rejected_before_loading_domains(tmp_path):
    request, data = own_cache(tmp_path)
    path = Path(request['_current_date_physical_cache']) / 'STATIC/DOMAIN' / request['day'] / 'PHYSICAL_DOMAIN_CACHE.json'
    receipt = read(path); receipt['producer_sources'][0]['sha256'] = '0' * 64
    atomic(path, receipt)
    with pytest.raises(ValueError, match='ORIGINAL_PRODUCER_IDENTITY'):
        load_current_date_physical_cache(request, data)


def test_prior_physical_cache_byte_drift_is_rejected_by_existing_sha_contract(tmp_path):
    request, data = own_cache(tmp_path)
    path = Path(request['_current_date_physical_cache']) / 'STATIC/DOMAIN' / request['day'] / 'PHYSICAL_DOMAIN_CACHE.pkl.gz'
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='FILE_SHA_OR_PATH_DRIFT'):
        load_current_date_physical_cache(request, data)


def test_absent_option_never_reads_any_prior_object():
    assert load_current_date_physical_cache({}, None) is None
