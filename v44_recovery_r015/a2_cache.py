"""Accepted same-date A1 domain IO binding, preserving every domain check.

The inherited verifier owns only V42 preflight directory layouts. V44 has a
sealed accepted-A1 proof instead. Adapt only that ownership preamble and the
byte-identical producer locations; retain its entire semantic/domain tail.
"""
from contextlib import contextmanager
from copy import deepcopy
import inspect
from pathlib import Path
import re
import textwrap
from unittest.mock import patch

from v44.common import ROOT, DOC, read, record, verify, atomic


def ownership(request, fresh_data, case_proof):
    proof = read(case_proof)
    if proof.get('schema') != 'V44_ACCEPTED_A1_PHYSICAL_CACHE':
        raise PermissionError('DATED_ACCEPTED_A1_CACHE_PROOF_REQUIRED')
    verify(proof['sources'] + [proof['result'], proof['cache']] + list(proof['inputs'].values()))
    parent_file = Path(proof['result']['path']).resolve()
    parent = read(parent_file)
    day = request['day']
    source = Path(request['_current_date_physical_cache']).resolve()
    output = Path(request['output']).resolve()
    inputs = Path(request['input_folder']).resolve()
    campaign = Path(request['campaign_root']).resolve()
    a1 = campaign/day/'B1'/parent_file.parent.parent.name/'A1'
    if (request.get('arm') != 'B1' or request.get('stage') != 'A1'
            or parent_file != a1/'RESULT.json'
            or not re.fullmatch(r'attempt\d{3}', a1.parent.name)
            or Path(request['root']).resolve() != a1
            or Path(request['case_root']).resolve() != a1.parent
            or (proof['day'], parent.get('day'), parent.get('arm'), parent.get('stage')) != (day, day, 'B1', 'A1')
            or not parent.get('PASS') or not parent.get('FULL_feasible')
            or not parent.get('independent_Global_LB_validated')
            or not 0 <= parent.get('certified_gap', 1) <= .005):
        raise PermissionError('SAME_CAMPAIGN_DATE_ACCEPTED_A1_OWNER_REQUIRED')
    a2_attempt = output.parent.parent
    if (output.name != 'OUTPUT' or output.parent.name != 'A2'
            or a2_attempt.parent != campaign/day/'B3'
            or not re.fullmatch(r'attempt\d{3}', a2_attempt.name)
            or source == output):
        raise PermissionError('SAME_DATE_B3_A2_FRESH_OUTPUT_REQUIRED')
    expected_source = Path(parent.get('accepted_cache_output', str(a1/'OUTPUT'))).resolve()
    cache_path = source/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'
    if (source != expected_source or record(cache_path) != proof['cache']
            or request.get('_physical_cache_identity') != proof['cache']):
        raise PermissionError('ACCEPTED_A1_EXACT_CACHE_LOCATION_AND_SHA_REQUIRED')
    manifest_path = DOC/'SEVEN_DAY_INPUT_MANIFEST.json'
    dated = next(row for row in read(manifest_path)['days'] if row['day'] == day)
    for name, label in [('NATIVE_INPUT.json','native'), ('WINDOWS.json','windows')]:
        actual = record(inputs/name)
        expected = proof['inputs'][name]
        if any(actual[k] != expected[k] or actual[k] != dated['files'][label][k] for k in ('bytes','sha256')):
            raise ValueError('DATED_A1_CACHE_INPUT_DRIFT:' + name)
    if fresh_data[0].get('day') != day:
        raise ValueError('A_CURRENT_DATE_CACHE_FRESH_DATA_DAY')
    prepared = read(source/'A_PREPARE_RECEIPT.json')
    cache = read(cache_path)
    if (not prepared.get('PASS') or request.get('_expected_model_verification') != prepared['verification']
            or request.get('_expected_complete_domain_hashes') != cache['complete_domain_hashes']):
        raise ValueError('ACCEPTED_A1_MODEL_AND_DOMAIN_PROOF_DRIFT')
    return (campaign, source, output, inputs, day, Path(case_proof), manifest_path, inputs/'NATIVE_INPUT.json')


def verifier_body(function):
    source = textwrap.dedent(inspect.getsource(function))
    left = source.index("    option = request.get('_current_date_physical_cache')")
    right = source.index("    data_path = source / 'STATIC/DATA/DATA.pkl'", left)
    prefix = ("    check()\n"
              "    root, source, output, inputs, day, input_identity_path, generation_path, bundle_path = _v44_ownership(request, fresh_data)\n")
    return source[:left] + prefix + source[right:]


def load(request, fresh_data, *, case_proof, original_loader, check=lambda:None, progress=None):
    from v42_may_campaign_native90 import a_cache
    from v42_a_stage_domain_v2 import fast_census
    from v43_followup.physical_cache import relocated_receipt, PRODUCERS, WRITER
    if (original_loader.__module__ != a_cache.__name__
            or original_loader.__name__ != 'load_current_date_physical_cache'
            or Path(original_loader.__code__.co_filename).resolve() != ROOT/'v42_may_campaign_native90/a_cache.py'):
        raise PermissionError('EXACT_ORIGINAL_DOMAIN_VERIFIER_REQUIRED')
    ownership(request, fresh_data, case_proof)
    raw_path = Path(request['_physical_cache_identity']['path']).resolve()
    raw_receipt = record(raw_path)
    raw = read(raw_path)
    historical_root = Path(raw['cache_writer']['path']).resolve().parent.parent
    pins = {relative:record(ROOT/relative) for relative in (*PRODUCERS,WRITER)}
    projected, aliases = relocated_receipt(raw, historical_root=historical_root,
                                          current_root=ROOT, pinned_sources=pins)
    original_read = a_cache.read
    def routed_read(path):
        if Path(path).resolve() == raw_path:
            if record(raw_path) != raw_receipt:
                raise ValueError('ORIGINAL_CACHE_RECEIPT_MUTATED')
            return deepcopy(projected)
        return original_read(path)
    namespace = dict(original_loader.__globals__, read=routed_read,
                     _v44_ownership=lambda r,d:ownership(r,d,case_proof))
    body = verifier_body(original_loader)
    exec(compile(body, __file__ + '.generated', 'exec'), namespace)
    with patch.object(fast_census, 'read', routed_read):
        domains = namespace[original_loader.__name__](request, fresh_data, check=check, progress=progress)
    if set(domains) != set(fresh_data[1]) or record(raw_path) != raw_receipt:
        raise ValueError('COMPLETE_DOMAIN_UID_OR_IMMUTABILITY_DRIFT')
    expected = request['_expected_model_verification']
    stay = migration = 0
    for members in fresh_data[7]['classes'].values():
        domain = domains[members[0]]
        if any(domains[uid] is not domain for uid in members):
            raise ValueError('EXACT_CLASS_DOMAIN_EXPANSION_REQUIRED')
        stay += len(domain.stays)
        migration += sum(len(block[-1]) for block in domain.blocks)
    if (len(domains),len(fresh_data[7]['classes']),stay,migration) != (
            expected['jobs'],expected['classes'],expected['full_STAY'],expected['full_migration']):
        raise ValueError('ORIGINAL_FULL_DOMAIN_CARDINALITY_DRIFT')
    atomic(Path(request['output'])/'V44_ACCEPTED_A1_DOMAIN_REUSE.json',dict(
        PASS=True,case_proof=record(case_proof),original_cache=raw_receipt,source_relocations=aliases,
        unchanged_semantic_and_complete_domain_tail=True,jobs=len(domains),classes=len(fresh_data[7]['classes']),
        full_STAY=stay,full_migration=migration,Native_calls=0,old_point_UB_LB_clock_transferred=False,
        fresh_A2_model_required=True,source_cache_files_modified=False))
    return domains


@contextmanager
def install():
    import v44.daily as daily
    original = daily.load_current_date_physical_cache
    def routed(request, fresh_data, *, case_proof, original_loader, check=lambda:None, progress=None):
        if read(case_proof).get('schema') != 'V44_ACCEPTED_A1_PHYSICAL_CACHE':
            return original(request,fresh_data,case_proof=case_proof,original_loader=original_loader,
                            check=check,progress=progress)
        return load(request,fresh_data,case_proof=case_proof,original_loader=original_loader,
                    check=check,progress=progress)
    with patch.object(daily, 'load_current_date_physical_cache', routed):
        yield
