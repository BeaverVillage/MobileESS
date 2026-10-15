"""Versioned, observed-PENDING-only research data access contracts.

R1/R2 are assumptions, never Kestrel WAN measurements or customer consent.
The existing FLEX30 membership and explicit-protection exclusions are reused;
no empirical QoS window, initial placement or RUNNING migration is changed.
"""
from copy import deepcopy
import math

from .experimental_qos import participation_for, FROZEN_SEED
from .actual import _require_public_metadata
from .policy import digest

SCHEMA = 'V42_RESEARCH_PRESITE_DATA_ACCESS_V1'
SOURCE_KEYS = ('qos', 'protected', 'batch_eligible', 'can_prestart_place',
    'data_access_forbidden', 'forbidden_destinations', 'authorized_destinations')
PROTECTED = {'high', 'urgent', 'interactive', 'protected'}


def source_authority(row, source_record, *, now):
    """Project one already arrived immutable request; never event truth."""
    from .current_ac_admission import epoch
    uid = str(row.get('job_uid', row.get('uid', '')))
    submit = epoch(row.get('submit_time', row.get('submit_seconds')))
    if not uid or submit > now or not math.isfinite(submit):
        raise ValueError('OBSERVED_REQUEST_SOURCE_PREFIX_REQUIRED')
    facts = {k: deepcopy(row[k]) for k in SOURCE_KEYS if k in row}
    public = dict(uid=uid, submit_seconds=submit, gpu=row.get('GPU_gang', row.get('gpu')),
        compatible_sites=list(row['compatible_sites']), facts=facts)
    _require_public_metadata(public)
    result = dict(public=public, source_record=deepcopy(source_record), source_sha=source_record['sha256'],
        observed_at_seconds=submit, verified_fields=list(facts),
        request_version_history=row.get('request_version_history', 'UNVERIFIED_SOURCE_PROXY'),
        raw_request_metadata_is_historical_permission_receipt=False)
    result['authority_sha'] = digest(result)
    return result


def make_spec(*, scenario, source_records, native_wan_sha, shared_sites,
              ready_delay_slots=0, payload_multiplier=1., bandwidth_fraction=.25,
              preparation_seconds=900.):
    if scenario not in ('R1', 'R2'):
        raise ValueError('DISTINCT_R1_OR_R2_SCIENCE_REQUIRED')
    spec = dict(schema=SCHEMA, scenario=scenario, case='RESEARCH_PRESITE',
        participation='FLEX30', seed=FROZEN_SEED,
        membership='EXISTING_PREREGISTERED_UID_EPISODE_SHA256_THRESHOLD',
        missing_batch_model='EXISTING_EXPERIMENTAL_ASSUMED_NORMAL_BATCH_FOR_FLEX30_ONLY',
        missing_batch_is_verified_fact=False, source_explicit_prohibition_has_priority=True,
        source_records=deepcopy(source_records), native_wan_sha=native_wan_sha,
        shared_sites=sorted(shared_sites), ready_delay_slots=ready_delay_slots,
        payload_multiplier=float(payload_multiplier), bandwidth_fraction=float(bandwidth_fraction),
        preparation_seconds=float(preparation_seconds),
        payload_model='ASSUMED_INPUT_BYTES_PROXY_FROM_EXISTING_WAN_BYTES_PER_GPU',
        actual_input_payload_measured=False, actual_WAN_measured=False,
        access_population='ONLY_OBSERVED_FLEX30_ELIGIBLE_PENDING',
        additional_QoS_delay_granted_seconds=0, checkpoint_migration_granted=False,
        initial_site_selection_changed=False, R1_certifies_WAN_transfer=False,
        demand_PV_prediction='CURRENT_PUBLIC_OBSERVATION_HOLD',
        service_prediction='PUBLIC_Q50_NO_REALIZED_DURATION_OR_COMPLETION',
        slot_seconds=900, assumptions_are_source_facts=False)
    validate_spec(spec)
    return spec


def validate_spec(spec):
    if (spec.get('schema') != SCHEMA or spec.get('scenario') not in ('R1', 'R2')
            or spec.get('participation') != 'FLEX30' or spec.get('seed') != FROZEN_SEED
            or spec.get('additional_QoS_delay_granted_seconds') != 0
            or spec.get('checkpoint_migration_granted') is not False
            or spec.get('assumptions_are_source_facts') is not False
            or type(spec.get('ready_delay_slots')) is not int or spec['ready_delay_slots'] < 0
            or not spec.get('shared_sites') or not spec.get('source_records')
            or any(not math.isfinite(spec.get(k, math.nan)) or spec[k] <= 0
                   for k in ('payload_multiplier', 'bandwidth_fraction'))
            or spec['bandwidth_fraction'] > 1
            or not math.isfinite(spec.get('preparation_seconds', math.nan)) or spec['preparation_seconds'] < 0):
        raise ValueError('FROZEN_RESEARCH_DATA_ACCESS_CONTRACT_REQUIRED')


class ResearchPresiteProvider:
    def __init__(self, spec, *, native_wan):
        validate_spec(spec)
        from .m_engine import file_record
        if any(file_record(r['path']) != r for r in spec['source_records']):
            raise ValueError('RESEARCH_SOURCE_BYTES_DRIFT')
        if digest(native_wan) != spec['native_wan_sha']:
            raise ValueError('ORIGINAL_WAN_MODEL_SOURCE_DRIFT')
        self.spec = deepcopy(spec); self.science_sha = digest(spec)
        self.wan = deepcopy(native_wan); self.observed = {}; self.audit = []
        self._observed_seals = {}
        self.transfers = {}; self.transfer_history = []

    def _frozen(self):
        if digest(self.spec) != self.science_sha or digest(self.wan) != self.spec['native_wan_sha']:
            raise ValueError('RESEARCH_PRESITE_CONTRACT_MUTATED')

    def register_observed(self, m, authority, *, now):
        self._frozen(); _require_public_metadata(m)
        if (authority.get('authority_sha') != digest({k:v for k,v in authority.items() if k != 'authority_sha'})
                or authority['source_record'] not in self.spec['source_records']
                or authority['source_sha'] != authority['source_record']['sha256']
                or authority['observed_at_seconds'] > now):
            raise ValueError('EXACT_OBSERVED_SOURCE_REQUEST_AUTHORITY_REQUIRED')
        p = authority['public']
        if (p['uid'] != m['uid'] or p['submit_seconds'] != m['submit_seconds']
                or p['gpu'] != m['gpu'] or set(p['compatible_sites']) != set(m['compatible_sites'])
                or m['submit_seconds'] > now):
            raise ValueError('PUBLIC_REQUEST_SOURCE_CONTRACT_DRIFT')
        if m['uid'] in self.observed and self.observed[m['uid']] != authority:
            raise ValueError('OBSERVED_SOURCE_AUTHORITY_MUST_NOT_CHANGE')
        self.observed[m['uid']] = deepcopy(authority)
        self._observed_seals[m['uid']] = authority['authority_sha']

    def _eligibility(self, m, destination, now):
        authority = self.observed.get(m['uid'])
        if authority is None:
            return 'OBSERVED_SOURCE_AUTHORITY_MISSING', None
        if (authority.get('authority_sha') != self._observed_seals.get(m['uid'])
                or authority['authority_sha'] != digest({k:v for k,v in authority.items() if k!='authority_sha'})):
            raise ValueError('REGISTERED_SOURCE_AUTHORITY_MUTATED')
        public = authority['public']
        if (public['uid'] != m['uid'] or public['gpu'] != m['gpu']
                or public['submit_seconds'] != m['submit_seconds']
                or set(public['compatible_sites']) != set(m['compatible_sites'])):
            raise ValueError('REGISTERED_PUBLIC_REQUEST_CONTRACT_DRIFT')
        facts = authority['public']['facts']
        if m.get('origin_unknown') is not True or m.get('state') != 'PENDING':
            return 'ONLY_ACTUALLY_ARRIVED_UNKNOWN_PENDING', authority
        if m['submit_seconds'] > now or m.get('accumulated_compute_seconds', 0) > 0:
            return 'NO_FUTURE_UID_OR_ALREADY_EXECUTING_JOB', authority
        if not m.get('reference_site'):
            return 'EXISTING_BASIC_PLACEMENT_REQUIRED', authority
        if destination not in m['compatible_sites'] or destination not in self.spec['shared_sites']:
            return 'SOURCE_COMPATIBLE_AND_RESEARCH_ACCESS_DESTINATION_REQUIRED', authority
        if (facts.get('can_prestart_place') is False or facts.get('data_access_forbidden') is True
                or destination in facts.get('forbidden_destinations', [])
                or 'authorized_destinations' in facts and destination not in facts['authorized_destinations']):
            return 'EXPLICIT_SOURCE_PROHIBITION', authority
        # A driver-generated default False/None is not a source prohibition.
        # Only the byte-bound original descriptor facts above can establish one.
        if (facts.get('protected') is True or m.get('protected') is True
                or str(facts.get('qos', m.get('qos'))).lower() in PROTECTED
                or str(m.get('qos')).lower() in PROTECTED
                or facts.get('batch_eligible') is False or m.get('batch_eligible') is False):
            return 'SOURCE_PROTECTED_OR_EXPLICIT_NONBATCH', authority
        membership = participation_for(m['uid'], m.get('episode_id'), seed=self.spec['seed'])
        if not membership['membership']['FLEX30']:
            return 'OUTSIDE_EXISTING_FLEX30_RESEARCH_BATCH_CONTRACT', authority
        return None, authority

    def _wan_capacity(self, link, begin, end, *, day_begin, bandwidth):
        values = self.wan.get('link_capacity_bytes_15min', {}).get(link)
        if not values:
            return False
        for slot in range(math.floor((begin-day_begin)/900), math.ceil((end-day_begin)/900)):
            if slot < 0 or slot >= len(values) or bandwidth > values[slot]/900 + 1e-9:
                return False
        return True

    def _concurrency_reason(self, proposal, *, exclude=None):
        start, end = proposal['transfer_begin_seconds'], proposal['transfer_end_seconds']
        existing = [r for uid,r in self.transfers.items() if uid != exclude
                    and r['transfer_begin_seconds'] < end and r['transfer_end_seconds'] > start]
        boundaries = sorted({start, end, *[max(start, r['transfer_begin_seconds']) for r in existing],
                              *[min(end, r['transfer_end_seconds']) for r in existing]})
        for a,b in zip(boundaries, boundaries[1:]):
            active = [r for r in existing if r['transfer_begin_seconds'] < b and r['transfer_end_seconds'] > a]
            if len(active) + 1 > self.wan['maximum_active_transfers']:
                return 'RESEARCH_WAN_MAXIMUM_ACTIVE_TRANSFERS'
            for link in proposal['WAN_path']:
                used = sum(r['bandwidth_bytes_per_second'] for r in active if link in r['WAN_path'])
                if not self._wan_capacity(link, a, b, day_begin=proposal['day_begin_seconds'],
                                          bandwidth=used+proposal['bandwidth_bytes_per_second']):
                    return 'RESEARCH_WAN_LINK_CAPACITY'
        return None

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
                    payload = self.wan['bytes_per_gpu']*m['gpu']*self.spec['payload_multiplier']
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

    def commit_transfer(self, proposal, *, current_metadata, now):
        self._frozen()
        reason, _ = self._eligibility(current_metadata, proposal.get('candidate_site'), now)
        if reason:
            raise ValueError('CURRENT_SOURCE_ELIGIBILITY_REQUIRED:'+reason)
        if (self.spec['scenario'] != 'R2' or proposal.get('science_sha') != self.science_sha
                or proposal.get('proposal_sha') != digest({k:v for k,v in proposal.items() if k != 'proposal_sha'})
                or proposal.get('status') != 'PREPARATION_REQUIRED' or proposal.get('reason') is not None
                or proposal.get('uid') != current_metadata['uid'] or current_metadata['state'] != 'PENDING'
                or current_metadata.get('accumulated_compute_seconds', 0) != 0
                or proposal['time_seconds'] != now):
            raise ValueError('EXACT_PENDING_RESEARCH_TRANSFER_PROPOSAL_REQUIRED')
        reason = self._concurrency_reason(proposal, exclude=proposal['uid'])
        if reason:
            return False, reason
        if proposal['uid'] in self.transfers:
            raise ValueError('TRANSFER_MUST_NOT_RESTART_OR_EXTEND_QOS')
        self.transfers[proposal['uid']] = deepcopy(proposal)
        self.transfer_history.append(dict(deepcopy(proposal), committed=True, GPU_started=False))
        return True, None

    def export(self):
        self._frozen()
        return dict(spec=deepcopy(self.spec), science_sha=self.science_sha,
            observed_authorities=deepcopy(self.observed), candidates=deepcopy(self.audit),
            transfers=deepcopy(self.transfer_history), Source_metadata_changed=False,
            actual_WAN_or_customer_permission_certified=False, Original_QoS_extended=False)
