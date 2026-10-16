"""Arrival-only deterministic R1 assumption, separate from Source consent."""
from copy import deepcopy
from hashlib import sha256

from v43_actual.vendor.policy import digest
from v43_actual.vendor.trajectory_tracking import require_tracking_public

SEED = 'V43_MAY01_R1_FLEX30_20261016_V1'


def permitted_destinations(metadata):
    sites = set(metadata['compatible_sites'])
    for name in ('source_allowed_destinations', 'allowed_destinations'):
        if name in metadata and metadata[name] is not None:
            sites &= set(metadata[name])
    for name in ('source_forbidden_destinations', 'forbidden_destinations', 'destination_prohibitions'):
        sites -= set(metadata.get(name, ()))
    return sorted(sites)


class ArrivalParticipation:
    def __init__(self, seed=SEED):
        self.seed = seed
        self.receipts = {}

    def observe(self, metadata, now):
        require_tracking_public(metadata)
        if metadata.get('origin_unknown') is not True or metadata.get('is_observed') is not True:
            raise ValueError('R1_OBSERVED_UNKNOWN_ONLY')
        if metadata['submit_seconds'] > now or metadata.get('state') != 'PENDING':
            raise ValueError('R1_ARRIVAL_PENDING_ONLY')
        uid = metadata['uid']
        identity = dict(uid=uid, submit_seconds=metadata['submit_seconds'], gpu=metadata['gpu'],
            compatible_sites=metadata['compatible_sites'], protected=metadata.get('protected'),
            qos=metadata.get('qos'), source_site=metadata.get('source_site'), destinations=permitted_destinations(metadata))
        identity_sha = digest(identity)
        if uid in self.receipts:
            prior = self.receipts[uid]
            if prior['arrival_identity_sha'] != identity_sha:
                raise ValueError('R1_ARRIVAL_IDENTITY_CHANGED')
            return deepcopy(prior)
        eligible = (metadata.get('protected') is False and metadata.get('qos') in ('normal', 'standby')
            and metadata.get('source_pre_site_forbidden') is not True
            and metadata.get('presite_explicitly_forbidden') is not True
            and bool(set(identity['destinations']) - {metadata.get('source_site') or sorted(metadata['compatible_sites'])[0]}))
        h = sha256((self.seed + '\0' + uid).encode('utf-8')).hexdigest()
        selected = eligible and int(h, 16) * 10 < 3 * (1 << 256)
        row = dict(uid=uid, arrival_identity_sha=identity_sha, observed_at_seconds=now, seed=self.seed,
            hash_hex=h, threshold='HASH_UINT256 / 2**256 < 0.30', eligible=eligible,
            participant=selected, authority='R1_ASSUMED', Source_verified=False,
            destinations=identity['destinations'] if selected else [],
            input_data_prepositioned_assumed=selected, additional_realtime_WAN_assumed_zero=selected,
            running_migration_permission=False, intentional_timeshift_permission=False,
            future_uid_population_reads=0)
        row['receipt_sha'] = digest(row)
        self.receipts[uid] = row
        return deepcopy(row)


def change_authority(metadata, site, now):
    require_tracking_public(metadata)
    r = metadata.get('r1_flex30', {})
    payload = {k:v for k,v in r.items() if k != 'receipt_sha'}
    if (metadata.get('origin_unknown') is not True or metadata.get('state') != 'PENDING'
            or metadata['submit_seconds'] > now):
        return 'R1_OBSERVED_PENDING_UNKNOWN_REQUIRED'
    if r.get('receipt_sha') != digest(payload) or r.get('uid') != metadata['uid']:
        return 'R1_ARRIVAL_RECEIPT_REQUIRED'
    if not r.get('participant') or r.get('authority') != 'R1_ASSUMED':
        return 'R1_NOT_PARTICIPATING'
    if r.get('observed_at_seconds', float('inf')) > now:
        return 'R1_FUTURE_AUTHORITY_FORBIDDEN'
    if site not in permitted_destinations(metadata) or site not in r.get('destinations', ()):
        return 'SOURCE_DESTINATION_FORBIDDEN'
    if not r.get('input_data_prepositioned_assumed') or not r.get('additional_realtime_WAN_assumed_zero'):
        return 'R1_NO_PREPOSITIONED_DATA_OR_VERIFIED_WAN'
    return None
