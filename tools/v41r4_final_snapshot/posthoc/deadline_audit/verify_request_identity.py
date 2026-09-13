from audit_deadlines import *

def main():
    a=Archive(); maps=json.loads((HERE/'source_map.json').read_text(encoding='utf-8')); results=[]
    for unit in maps:
        day,policy=unit['day'],unit['policy']
        rawpath=f'{RUN}/{day}/{policy}/dayahead/authority/JOB_REQUEST_INPUTS.parquet'
        inputs=pq.read_table(io.BytesIO(a.read(rawpath))).to_pylist()
        inputs={str(row['id']):row for row in inputs}
        selected=[r for r in a.j(unit['joint'])['decision']['AIDC_decision'] if r['AIDC_site']!='UNASSIGNED']
        for r in selected:
            raw=inputs[str(r['job_uid'])]
            assert r['qos']==raw['qos'] and r['state_at_issue']==raw['state_at_issue']
            assert r['requested_GPU']==raw['gpus_requested']
            assert r['requested_walltime_seconds']==raw['wallclock_req'].total_seconds()
            assert r['safe_duration_slots']==math.ceil(r['safe_duration_seconds']/900)
        results.append(dict(day=day,policy=policy,selected_records=len(selected),all_selected_requests_found=True,
            requested_GPU_state_qos_walltime_equal=True,safe_duration_ceil_identity=True,source=rawpath))
    assert sum(r['selected_records'] for r in results)==184368
    save('request_identity_checks.json',results);save('request_identity_sources_used.json',a.used)
    print(json.dumps(dict(status='PASS',selected_job_request_identities=184368,policy_days=124)))

if __name__=='__main__':main()
