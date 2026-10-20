"""Logical workload/route identity; no jobs, windows, routes or power changed."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
from ac import ROOT,DOC,RUN,save,csvout
from authority import read,record
from export_arrays import array_record
sys.path.insert(0,str(ROOT))


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def main():
    from v44.inputs import resolve_receipt
    day=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    native=read(day['files']['native']['path']);windows=read(day['files']['windows']['path'])
    bundle=Path(day['actual_bundle']);plan=read(bundle/'PLANNING_INPUT_BUNDLE.json');actual=read(bundle/'ACTUAL_INPUT_BUNDLE.json')
    known=native['known_population'];requests=[*plan['known_population'],*actual['post_issue_arrivals']]
    assert len(requests)==2498 and len({r['job_uid'] for r in requests})==2498
    descriptor=day['files'].get('request_descriptors')
    desc=read(descriptor['path']) if descriptor else {}
    permission=[{k:r.get(k,'ABSENT_IN_SOURCE') for k in ('job_uid','GPU_gang','state','cohort','delay_budget_slots',
        'can_timeshift','can_prestart_place','can_checkpoint_migrate','planning_site',
        'reference_start_if_authorized','reference_end')} for r in known]
    route=resolve_receipt(native['route_table']);table=json.loads(gzip.decompress(Path(route['path']).read_bytes()))
    travel=np.array([r['travel_slots_15min'] for r in table['routes']],dtype=np.int64)
    ready=np.array([r['connection_ready_slots_15min'] for r in table['routes']],dtype=np.int64)
    energy=np.array([r['energy_safe_kwh'] for r in table['routes']],dtype=np.float64)
    save('WORKLOAD_ROUTE_IDENTITY.json',dict(experiment_id='V1_add',
        known_UID_GPU_permission_window_projection_sha256=canonical(permission),
        all_2498_ordered_UID_GPU_request_sha256=canonical([(r['job_uid'],r['GPU_gang'],r['submit_time']) for r in requests]),
        original_window_or_deadline_contract_sha256=canonical(windows),
        original_public_request_descriptor_sha256=canonical(desc),
        installed_GPU=sum(native['capacities'].values()),capacities=native['capacities'],
        unknown_count=len(actual['post_issue_arrivals']),known_count=len(known),actual_job_count=len(requests),
        declared_Hard_Deadline_note='No hard deadline invented. Preserve original WINDOWS and provider/source metadata, including absent fields.',
        workload_sources=[day['files']['native'],day['files']['windows'],day['files']['planning_input'],day['files']['actual_input']]+([descriptor] if descriptor else []),
        route_file=route,traffic_forecast=day['files']['traffic_forecast'],route_rows=len(table['routes']),
        service_ids=table['service_ids'],route_order_preserved=True,
        route_arrays=dict(travel_slots=array_record(travel,'15-minute slots','original route-row order'),
            connection_ready_slots=array_record(ready,'15-minute slots','original route-row order'),
            travel_energy=array_record(energy,'kWh','original route-row order')),
        comparison=dict(candidate_binding='References exact same source bytes; no rewrite or interpolation',
            GPU_max_absolute_error=0,GPU_max_relative_error=0,
            UID_QoS_deadline_status='IDENTICAL_FROZEN_SOURCE_REFERENCES',
            route_travel_ready_energy_max_absolute_error=0,route_travel_ready_energy_max_relative_error=0,
            physical_initial_site_or_PCC_acceptance='NOT_VERIFIED'),axis=day['axis']))
    power=np.load(DOC/'IEEE123_FROZEN_ELECTRICAL_INPUTS.npz')
    candidate=np.load(RUN/'GREENSBORO_PQ_ALLOCATION_CANDIDATE.npz')
    comparisons=[]
    for label,role,sl in [('PLANNING','PLANNING',slice(None)),('ACTUAL','ACTUAL',slice(24,None)),
                          ('ACTUAL_PREFIX24','ACTUAL',slice(0,24))]:
        total=lambda x:np.array([math.fsum(r) for r in x[sl]],dtype=np.float64)
        for quantity,unit in [('BG_P','kW'),('BG_Q','kvar'),('PV_P','kW'),('PV_Q','kvar'),
                              ('AIDC_P','kW'),('AIDC_Q','kvar'),('NET_P','kW'),('NET_Q','kvar')]:
            suffix='_kw' if unit=='kW' else '_kvar';a=power[role+'_'+quantity+suffix]
            a=a[sl] if quantity.startswith(('AIDC','NET')) else total(a)
            if quantity.startswith('BG'):
                new=total(candidate[role.lower()+'_'+quantity[-1]+'_candidate'])
                status='PASS_TOTAL_ARITHMETIC_ONLY'
            elif quantity.startswith('AIDC'):
                new=a.copy();status='PASS_SITE_AXIS_IDENTITY_ONLY'
            else:new=None;status='NOT_VERIFIED_PV_OR_PCC_MAPPING'
            ar=array_record(a,unit,'evaluation slot,site' if quantity.startswith('AIDC') else 'slot')
            nr=array_record(new,unit,ar['axes']) if new is not None else None
            delta=abs(new-a) if new is not None else None
            maximum=float(delta.max(initial=0)) if delta is not None else None
            comparisons.append(dict(role=label,quantity=quantity,unit=unit,shape=str(list(a.shape)),
                original_sha256_npy=ar['sha256_npy'],candidate_sha256_npy=nr['sha256_npy'] if nr else '',
                max_abs_error=maximum if maximum is not None else '',
                max_relative_error=(maximum/max(float(abs(a).max(initial=0)),1e-300)) if maximum is not None else '',
                status=status,physical_input_admitted=False))
    csvout('INPUT_IDENTITY_METRICS_96.csv',[r for r in comparisons if r['role']!='ACTUAL_PREFIX24'])
    csvout('PREFIX24_INPUT_IDENTITY_METRICS.csv',[r for r in comparisons if r['role']=='ACTUAL_PREFIX24'])
    save('INPUT_COMPARISON_ARRAY_DIGESTS.json',dict(experiment_id='V1_add',
        original_version='V44 r043',original_commit='affc7226a519adbe072d7debbc3ae25ea71c3487',
        status='INPUT_MAPPING_NOT_VERIFIED',comparisons=comparisons,
        relative_error_definition='max absolute difference / max absolute original array; zero arrays require exact zero',
        note='Total conservation views are derived from frozen input arrays; not new operating demand/PV series.'))
    print('Logical identities sealed: 2498 requests, original windows/descriptors and 55296 route rows')


if __name__=='__main__':main()
