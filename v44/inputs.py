"""Inspect existing dated sources. Never generate or copy another day's state."""
from datetime import datetime
from pathlib import Path
import gzip
import json

from .common import read,record,sha,digest,NotReady,DOC,ROOT
from .config import DAYS,ARMS,axis,require_day

NATIVE_ROOT=Path('D:/MobileESS_V42/runtime/v42_may_campaign/candidate_20261009_implementation01/inputs/B1')
BUNDLE_ROOT=Path('D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/INPUT/BUNDLE')
TRAFFIC_ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/cache/v37_may_locked_final/traffic/shared/traffic')


def resolve_receipt(row):
    """Known workspace relocations require exactly the original bytes/SHA."""
    source=Path(row['path']);candidates=[source]
    text=source.as_posix()
    aliases=[('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/','D:/ChatGPT/Mobile ESS 2/'),
        ('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS/','D:/ChatGPT/Mobile ESS/'),
        ('C:/codex_mobileess_workspace/','D:/codex_mobileess_workspace/')]
    for old,new in aliases:
        if text.startswith(old):candidates.append(Path(new+text[len(old):]))
    # The original holdout's D: source mirror preserves byte-identical derivatives.
    for marker in ('docs/v42_may_b0_zero_margin_holdout/','v42_final/runtime_bundle/'):
        if marker in text:candidates.append(Path('D:/MobileESS_V42')/text[text.index(marker):])
    for p in candidates:
        if p.is_file() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']:return record(p)
    raise NotReady('MISSING_OR_SHA_UNVERIFIED_SOURCE:'+str(source))


def inspect_day(day,*,native_root=NATIVE_ROOT,bundle_root=BUNDLE_ROOT):
    a=axis(day);folder=Path(native_root)/day;bundle=Path(bundle_root)/('DAY_'+day.replace('-',''))
    files={};errors=[];warnings=[]
    def required(label,path):
        try:files[label]=record(path);return read(path)
        except (OSError,ValueError) as e:errors.append(label+':'+str(e));return None
    native=required('native',folder/'NATIVE_INPUT.json')
    required('windows',folder/'WINDOWS.json')
    plan=required('planning_input',bundle/'PLANNING_INPUT_BUNDLE.json')
    actual=required('actual_input',bundle/'ACTUAL_INPUT_BUNDLE.json')
    provenance=required('provenance',bundle/'SOURCE_PROVENANCE.json')
    required('power_authority',bundle/'POWER_AUTHORITY.json')
    if native and plan and actual:
        for label,doc in [('native',native),('plan',plan),('actual',actual)]:
            if doc.get('day')!=day:errors.append('DAY_MISMATCH:'+label)
        if datetime.fromisoformat(native['issue_time']).timestamp()!=a['issue_seconds'] or datetime.fromisoformat(plan['issue_time']).timestamp()!=a['issue_seconds']:
            errors.append('ISSUE_AXIS_MISMATCH')
        if len(native['capacities'])!=12 or len(native['initial_MESS_sites'])!=4:errors.append('PHYSICAL_SITE_UNIT_AXIS')
        if plan.get('runtime_authority')!='V10::T3_ISOTONIC_ROLLING14_calibrated':errors.append('RUNTIME_V10_AUTHORITY')
        if native['known_population']!=plan['known_population']:
            # Native is the original PR189 transformation; it has extra service fields.
            if {x['job_uid'] for x in native['known_population']}!={x['job_uid'] for x in plan['known_population']}:errors.append('KNOWN_ROSTER_MISMATCH')
        if not actual.get('post_issue_arrivals') and actual.get('post_issue_arrivals')!=[]:errors.append('UNKNOWN_EVENTS_MISSING')
        arrivals=actual.get('post_issue_arrivals',[])
        if any(datetime.fromisoformat(x['submit_time']).timestamp()<=a['issue_seconds'] for x in arrivals):errors.append('UNKNOWN_BEFORE_ISSUE')
        for label,key in [('R0_reference','reference'),('route_table','route_table'),('electrical','electrical_certificate'),('runtime_provider','runtime_provider')]:
            try:files[label]=resolve_receipt(native[key])
            except (NotReady,KeyError) as e:errors.append(str(e))
        if 'R0_reference' in files:
            if native['reference'].get('period',day)!=day:errors.append('R0_WRONG_DAY')
        if 'route_table' in files:
            try:
                table=json.loads(gzip.decompress(Path(files['route_table']['path']).read_bytes()))
                if len(table['service_ids'])!=24 or table['departure_slots']!=list(range(96)):errors.append('ROUTE_96_24_AXIS')
                periods={r.get('traffic_forecast_sha') for r in table['routes']}
                if periods!={native['traffic_forecast_sha']}:errors.append('TRAFFIC_FORECAST_BINDING')
                forecast=Path(files['route_table']['path']).with_name('TRAFFIC_FORECAST.npz')
                if not forecast.exists():errors.append('TRAFFIC_FORECAST_METADATA_MISSING')
                else:
                    import numpy as np
                    with np.load(forecast,allow_pickle=False) as z:meta=json.loads(str(z['metadata']))
                    if meta['forecast_day']!=day or meta['bundle_sha']!=native['traffic_forecast_sha']:errors.append('TRAFFIC_DAY_SHA_MISMATCH')
                    files['traffic_forecast']=record(forecast)
            except (OSError,ValueError,KeyError) as e:errors.append('TRAFFIC:'+str(e))
        if 'electrical' in files:
            e=read(files['electrical']['path'])
            if e['input_identity']['identity']['inputs']['day']!=day:errors.append('ELECTRICAL_WRONG_DAY')
        # No magic filename grants authority. Optional bindings point to existing
        # dated receipts and are checked against this exact issue/roster.
        bindings=read(DOC/'DAILY_AUTHORITY_BINDINGS.json') if (DOC/'DAILY_AUTHORITY_BINDINGS.json').is_file() else {}
        authority=bindings.get(day,{})
        for arm,receipt in authority.get('C1_correction_proofs',{}).items():
            if arm not in ('B1','B3'):errors.append('C1_PROOF_ARM_MISMATCH');continue
            try:files['C1_correction_proof_'+arm]=resolve_receipt(receipt)
            except NotReady as e:errors.append(str(e))
        running={r['job_uid']:r for r in native['known_population'] if r['state']=='RUNNING'}
        missing=[uid for uid,r in running.items() if r.get('current_site_if_running') is None]
        initial=authority.get('initial_running')
        if initial is None and day=='2025-05-01':
            p=Path('D:/MobileESS_V43/runtime/gate_b_c0_c1_actual96_attempt001/CASE/INITIALIZATION/SYNTHETIC_INITIALIZATION_POLICY.json')
            if p.is_file():initial=record(p)
        if initial:
            try:
                files['initial_running_authority']=resolve_receipt(initial);doc=read(files['initial_running_authority']['path'])
                if doc['inputs']['issue_seconds']!=a['issue_seconds'] or set(doc['mapping'])!=set(running) or not doc.get('PASS'):
                    errors.append('INITIAL_RUNNING_DAY_ROSTER_OR_PHYSICAL_PASS_MISMATCH')
                warnings.append('INITIAL_RUNNING_MODEL_ASSUMPTION_NOT_OBSERVED_SITE_CERTIFICATION')
            except (NotReady,KeyError) as e:errors.append(str(e))
        elif missing:errors.append(f'INITIAL_RUNNING_SOURCE_SITE_UNRESOLVED:{len(missing)}/{len(running)}')
        # The producer starts with deepcopy(MAY01_FINAL_NATIVE_INPUT_BUNDLE).
        # Equal numeric values do not constitute dated observations for later days.
        mess=authority.get('initial_MESS')
        if mess:
            try:
                files['initial_MESS_authority']=resolve_receipt(mess);doc=read(files['initial_MESS_authority']['path'])
                if doc.get('day')!=day or doc.get('issue_seconds')!=a['issue_seconds']:errors.append('INITIAL_MESS_DAY_ISSUE_MISMATCH')
                if doc.get('initial_sites')!=native['initial_MESS_sites'] or doc.get('SOC')!=native['battery']['initial']:errors.append('INITIAL_MESS_VALUES_MISMATCH')
            except NotReady as e:errors.append(str(e))
        elif day!='2025-05-01':errors.append('INITIAL_MESS_DATED_SOURCE_UNVERIFIED_TEMPLATE_MAY01_VALUES')
        else:warnings.append('MAY01_ORIGINAL_MESS_INITIAL_MODEL_ASSUMPTION_RETAINED_NOT_OBSERVED')
        descriptors=authority.get('request_descriptors')
        if descriptors is None and day=='2025-05-01':
            p=ROOT/'docs/v43/V43_R1_RECORDED_REQUEST_DESCRIPTOR_CACHE.json'
            if p.is_file():descriptors=record(p)
        if descriptors:
            try:
                files['request_descriptors']=resolve_receipt(descriptors);doc=read(files['request_descriptors']['path'])
                if set(doc['descriptors'])!={r['job_uid'] for r in arrivals}:errors.append('DESCRIPTORS_WRONG_DAY_UID_ROSTER')
                if doc.get('private_outcome_columns_read')!=[]:errors.append('DESCRIPTORS_PRIVATE_OUTCOME_READ')
                if not any(r['sha256']==files['actual_input']['sha256'] for r in doc['sources']):errors.append('DESCRIPTORS_ACTUAL_SOURCE_SHA')
            except (NotReady,KeyError) as e:errors.append(str(e))
        else:errors.append('DATED_PUBLIC_REQUEST_DESCRIPTORS_NOT_PREPARED')
        warnings.append('FORECAST_CAUSAL_AVAILABILITY_NOT_CERTIFIED')
    if provenance:
        for group in ('daily_sources','raw_realized_sources'):
            for name,row in provenance.get(group,{}).items():
                if isinstance(row,dict) and all(k in row for k in ('path','bytes','sha256')):
                    try:files[group+':'+name]=resolve_receipt(row)
                    except NotReady as e:errors.append(str(e))
        if provenance.get('day')!=day:errors.append('PROVENANCE_DAY_MISMATCH')
        if 'snapshot' in provenance:
            try:files['D1_snapshot']=resolve_receipt(provenance['snapshot'])
            except NotReady as e:errors.append(str(e))
    return dict(day=day,axis=a,native_folder=str(folder),actual_bundle=str(bundle),files=files,
        status='INPUT_READY' if not errors else 'INPUT_NOT_READY',blockers=sorted(set(errors)),warnings=warnings,
        Known_count=len(native['known_population']) if native else None,
        Unknown_count=len(actual.get('post_issue_arrivals',[])) if actual else None,
        daily_MESS_values=None if not native else dict(initial_sites=native['initial_MESS_sites'],SOC=native['battery']['initial']),
        initial_state_not_inferred_from_optimized_previous_day=True)


def manifest():
    days=[inspect_day(day) for day in DAYS]
    # Equal observations can be real; identical whole populations across days need review.
    known_hashes={};unknown_hashes={}
    for row in days:
        for label,seen,key in [('native',known_hashes,'known_population'),('actual_input',unknown_hashes,'post_issue_arrivals')]:
            if label not in row['files']:continue
            key_sha=digest(read(row['files'][label]['path'])[key])
            if key_sha in seen:row['blockers'].append('CROSS_DATE_IDENTICAL_POPULATION:'+seen[key_sha]);row['status']='INPUT_NOT_READY'
            seen[key_sha]=row['day']
    return dict(schema='V44_SEVEN_DAY_INPUT_MANIFEST_V1',days=days,
        cases=[dict(day=r['day'],arm=arm,status=r['status'],blockers=r['blockers']) for r in days for arm in ARMS],
        generated_or_imputed_sources=False,FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED')
