"""Separate R2 per-job literature examples, preserving Provider V1 decisions.

The paper's benchmark sizes are scenario examples, not measured Kestrel input
sizes or a task-type classifier. Only the payload expression differs from V1.
No native solve, power flow, Actual driver or future population is used here.
"""
from copy import deepcopy
import ast
import inspect
import json
import math
from pathlib import Path
import textwrap

from .m_engine import file_record
from .policy import digest
from .research_presite_contract import ResearchPresiteProvider, make_spec, validate_spec

SCHEMA = 'V42_RESEARCH_R2_PER_JOB_LITERATURE_EXAMPLES_V1'
PAYLOAD_MODEL = 'ASSUMED_PER_JOB_PAYLOAD_FROM_LITERATURE_EXAMPLES'
PAYLOAD_MB = (100, 233, 500, 600, 650)
DOI = '10.1109/TSUSC.2021.3086087'
ORIGINAL_PROVIDER_SHA = '84b090927ac98391d54463f57a39db5ea30511c8c94e36576d575227281edd9d'
LITERATURE_FACT_SHA = '881be8b6ded5e4a041ee79950d602d0982d6496dfa39ce78623a86dfd80413c1'


def original_provider_record():
    record = file_record(Path(__file__).with_name('research_presite_contract.py'))
    if record['sha256'] != ORIGINAL_PROVIDER_SHA:
        raise ValueError('ORIGINAL_RESEARCH_PROVIDER_BYTES_DRIFT')
    return record


def _literature(record):
    if record['sha256'] != LITERATURE_FACT_SHA or file_record(record['path']) != record:
        raise ValueError('PRIMARY_LITERATURE_FACT_BYTES_DRIFT')
    facts = json.loads(Path(record['path']).read_text(encoding='utf-8-sig'))
    anchors = [a for a in facts.get('anchors', []) if a.get('doi') == DOI]
    if (len(anchors) != 1 or anchors[0].get('benchmark_input_sizes_MB') != list(PAYLOAD_MB)
            or anchors[0].get('V42_MB_interpretation_bytes') != 1_000_000
            or anchors[0].get('V42_Kestrel_task_type_mapping') is not None):
        raise ValueError('EXACT_PUBLISHED_BENCHMARK_EXAMPLES_REQUIRED')
    return anchors[0]


def make_literature_spec(*, payload_MB, bandwidth_fraction, preparation_seconds,
                         literature_fact_record, source_records, native_wan_sha, shared_sites):
    """Freeze an explicit example per job; GPU gang never scales its payload."""
    if type(payload_MB) is not int or payload_MB not in PAYLOAD_MB:
        raise ValueError('PUBLISHED_PAYLOAD_MB_EXAMPLE_REQUIRED')
    if (bandwidth_fraction not in (.25, 1.) or type(bandwidth_fraction) is bool
            or preparation_seconds not in (0, 900) or type(preparation_seconds) is bool):
        raise ValueError('APPROVED_V42_BANDWIDTH_PREPARATION_SENSITIVITY_REQUIRED')
    anchor = _literature(literature_fact_record)
    original = original_provider_record()
    sources = deepcopy(source_records)
    for record in (original, literature_fact_record):
        if record not in sources:
            sources.append(deepcopy(record))
    spec = make_spec(scenario='R2', source_records=sources, native_wan_sha=native_wan_sha,
        shared_sites=shared_sites, ready_delay_slots=0, payload_multiplier=1.,
        bandwidth_fraction=bandwidth_fraction, preparation_seconds=preparation_seconds)
    spec.update(literature_schema=SCHEMA, payload_model=PAYLOAD_MODEL,
        absolute_payload_MB_per_job=payload_MB, absolute_payload_bytes_per_job=payload_MB*1_000_000,
        payload_scales_with_GPU_gang=False, Kestrel_task_type_mapping=None,
        literature_fact_record=deepcopy(literature_fact_record), literature_DOI=DOI,
        literature_locator=anchor['locator'], original_provider_record=original,
        published_examples_are_Kestrel_measurements=False,
        source_payload_measurement_available=False,
        bandwidth_and_preparation_provenance='EXISTING_APPROVED_V42_WAN_MODEL_SENSITIVITY_NOT_PAPER_MEASUREMENT',
        payload_multiplier_role='V1_SCHEMA_COMPATIBILITY_ONLY_NOT_USED_BY_PER_JOB_PAYLOAD')
    validate_literature_spec(spec)
    return spec


def validate_literature_spec(spec):
    validate_spec(spec)
    value = spec.get('absolute_payload_MB_per_job')
    if (spec.get('literature_schema') != SCHEMA or spec.get('scenario') != 'R2'
            or spec.get('payload_model') != PAYLOAD_MODEL
            or type(value) is not int or value not in PAYLOAD_MB
            or spec.get('absolute_payload_bytes_per_job') != value*1_000_000
            or spec.get('payload_multiplier') != 1. or spec.get('ready_delay_slots') != 0
            or spec.get('bandwidth_fraction') not in (.25, 1.)
            or spec.get('preparation_seconds') not in (0., 900.)
            or spec.get('payload_scales_with_GPU_gang') is not False
            or spec.get('Kestrel_task_type_mapping') is not None
            or spec.get('published_examples_are_Kestrel_measurements') is not False
            or spec.get('source_payload_measurement_available') is not False
            or spec.get('actual_input_payload_measured') is not False
            or spec.get('actual_WAN_measured') is not False
            or spec.get('literature_DOI') != DOI
            or spec.get('original_provider_record') != original_provider_record()
            or spec['original_provider_record'] not in spec['source_records']
            or spec.get('literature_fact_record') not in spec['source_records']):
        raise ValueError('EXACT_SEPARATE_PER_JOB_LITERATURE_SCENARIO_REQUIRED')
    _literature(spec['literature_fact_record'])


def provider_decision_equivalence():
    """Read/compare static syntax only; never transform or execute source text."""
    original_provider_record()
    before = ast.parse(textwrap.dedent(inspect.getsource(ResearchPresiteProvider.propose)))
    after = ast.parse(textwrap.dedent(inspect.getsource(LiteratureTransferProvider.propose)))
    def payload_node(tree):
        found = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                 and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id == 'payload']
        if len(found) != 1:
            raise ValueError('SINGLE_STATIC_PAYLOAD_ASSIGNMENT_REQUIRED')
        return found[0]
    old, new = payload_node(before), payload_node(after)
    old_expression, new_expression = ast.unparse(old.value), ast.unparse(new.value)
    if new_expression != "self.spec['absolute_payload_bytes_per_job']":
        raise ValueError('PER_JOB_PAYLOAD_EXPRESSION_DRIFT')
    old.value = ast.Constant(value='PAYLOAD_EXPRESSION_ONLY')
    new.value = ast.Constant(value='PAYLOAD_EXPRESSION_ONLY')
    left, right = ast.dump(before, include_attributes=False), ast.dump(after, include_attributes=False)
    if left != right:
        raise ValueError('ORIGINAL_PROVIDER_DECISION_LOGIC_DRIFT')
    return dict(status='PASS_SINGLE_PAYLOAD_EXPRESSION_DIFFERENCE',
        original_expression=old_expression, literature_expression=new_expression,
        normalized_static_AST_sha=digest(left), original_provider=original_provider_record(),
        adapter=file_record(__file__), runtime_source_execution=False)


class LiteratureTransferProvider(ResearchPresiteProvider):
    def __init__(self, spec, *, native_wan):
        validate_literature_spec(spec)
        provider_decision_equivalence()
        super().__init__(spec, native_wan=native_wan)

    def propose(self, m, destination, now, *, day_begin, qos_receipt=None):
        """Data/resource prerequisite only. Candidate AC and ranking remain mandatory."""
        self._frozen()
        reason, authority = self._eligibility(m, destination, now)
        result = dict(uid=m['uid'], episode_id=m.get('episode_id', m['uid']),
            time_seconds=now, basic_site=m.get('reference_site'), candidate_site=destination,
            state=m.get('state'), compatible=destination in m['compatible_sites'],
            research_scenario=self.spec['scenario'], science_sha=self.science_sha,
            eligible=reason is None, status='REJECTED' if reason else 'DATA_CONTRACT_READY_FOR_CHECK', reason=reason,
            source_authority_sha=None if authority is None else authority['authority_sha'],
            verified_source_fields=[] if authority is None else authority['verified_fields'],
            eligibility_basis='EXPLICIT_RESEARCH_FLEX30_BATCH_ASSUMPTION_PRESERVING_SOURCE_EXCLUSIONS',
            data_access_type='PRESTAGED_SHARED_INPUT' if self.spec['scenario']=='R1' else 'TRANSFER_AWARE',
            provenance_class='ASSUMED', customer_permission_claim=False, measured_WAN_claim=False,
            current_candidate_AC_required=True, GPU_rack_and_QoS_recheck_required=True,
            no_initial_site_algorithm_change=True, no_RUNNING_migration=True, selected=False,
            ready_at_seconds=None, WAN_path=[], WAN_segments=[], payload_bytes=None,
            transfer_seconds=0., preparation_seconds=0., bandwidth_bytes_per_second=0.)
        if reason:
            self.audit.append(deepcopy(result)); return result
        if self.spec['scenario'] == 'R1':
            result['ready_at_seconds'] = math.ceil(m['submit_seconds']/900)*900 + 900*self.spec['ready_delay_slots']
        elif m['uid'] in self.transfers:
            transfer = self.transfers[m['uid']]
            if transfer['candidate_site'] != destination:
                result.update(status='REJECTED', reason='EXISTING_TRANSFER_TO_OTHER_DESTINATION')
            else:
                result.update({k:deepcopy(transfer[k]) for k in ('ready_at_seconds','WAN_path','WAN_segments',
                    'payload_bytes','transfer_seconds','preparation_seconds','bandwidth_bytes_per_second',
                    'transfer_begin_seconds','transfer_end_seconds','day_begin_seconds')})
                result['transfer_committed'] = True
        else:
            paths = [p for p in self.wan.get('paths', []) if p['source']==m['reference_site'] and p['destination']==destination]
            if len(paths) != 1 or not paths[0]['links']:
                result.update(status='REJECTED', reason='ORIGINAL_WAN_PATH_UNAVAILABLE')
            else:
                links = paths[0]['links']; slot = int((now-day_begin)//900)
                rates = [self.wan.get('link_capacity_bytes_15min', {}).get(link, [])[slot]/900
                         for link in links if 0 <= slot < len(self.wan.get('link_capacity_bytes_15min', {}).get(link, []))]
                if len(rates) != len(links) or min(rates) <= 0:
                    result.update(status='REJECTED', reason='ORIGINAL_WAN_CAPACITY_UNAVAILABLE')
                else:
                    bandwidth = min(rates)*self.spec['bandwidth_fraction']
                    payload = self.spec['absolute_payload_bytes_per_job']
                    transfer_seconds = max(900., math.ceil(payload/bandwidth/900)*900)
                    prepare = self.spec['preparation_seconds']
                    ready = math.ceil((now+transfer_seconds+prepare)/900)*900
                    result.update(ready_at_seconds=ready, WAN_path=links, payload_bytes=payload,
                        bandwidth_bytes_per_second=bandwidth, transfer_seconds=transfer_seconds,
                        preparation_seconds=prepare, transfer_begin_seconds=now,
                        transfer_end_seconds=now+transfer_seconds, day_begin_seconds=day_begin,
                        WAN_segments=[dict(resource='wan:'+link, begin=now, end=now+transfer_seconds, quantity=bandwidth)
                            for link in links]+[dict(resource='active:WAN',begin=now,end=now+transfer_seconds,quantity=1)])
                    result['reason'] = self._concurrency_reason(result, exclude=m['uid'])
                    if result['reason']:
                        result['status'] = 'REJECTED'
        if not result['reason'] and result['ready_at_seconds'] is not None:
            ready = max(now, result['ready_at_seconds'])
            earliest = max(m['submit_seconds'], m.get('release_seconds') or -math.inf,
                           m.get('hard_earliest_start_seconds') or -math.inf)
            start = max(ready, earliest)
            if m.get('hard_latest_start_seconds') is not None and start > m['hard_latest_start_seconds']:
                result.update(status='REJECTED', reason='SOURCE_LATEST_START_WINDOW')
            elif m.get('completion_deadline_seconds') is not None and start+m['t50_seconds'] > m['completion_deadline_seconds']:
                result.update(status='REJECTED', reason='SOURCE_PUBLIC_Q50_COMPLETION_DEADLINE')
            elif qos_receipt is None:
                result.update(status='REJECTED', reason='UNCHANGED_ORIGINAL_QOS_RECEIPT_REQUIRED')
            else:
                receipt = qos_receipt.to_dict() if hasattr(qos_receipt, 'to_dict') else qos_receipt
                delayed = start > now or result.get('transfer_committed', False)
                burden = start-result.get('transfer_begin_seconds', now)
                if delayed and (start not in receipt.get('allowed_starts_seconds', [])
                        or start > receipt.get('latest_start_seconds', -math.inf)
                        or burden > receipt.get('budget_seconds', 0)):
                    result.update(status='REJECTED', reason='ORIGINAL_QOS_HAS_NO_PREPARATION_DELAY_AUTHORITY')
                elif start > now:
                    result.update(status='PREPARATION_REQUIRED', reason=None)
                else:
                    result.update(status='READY', reason=None)
        result['proposal_sha'] = digest(result)
        self.audit.append(deepcopy(result))
        return result
