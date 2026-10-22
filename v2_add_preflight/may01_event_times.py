"""Calendar/phase interpretation of the sealed native voltage events."""
import csv,gzip,io
from datetime import datetime,timezone,timedelta
from .may01_common import *

def run():
    init();from .may01_voltage import engine
    e=engine('CALENDAR_AXIS_ONLY');axis=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]['axis']
    lines={r['element']:r for r in e.inventory['lines']};phase={}
    for x in e.line_axes:
        bus=lines[x['element']]['buses'][x['terminal']-1].split('.')[0].lower()
        phase[bus,int(x['node'])]=x['physical_phase']
    source=gzip.decompress((OUT/'MAY01_ALL_NODE_VOLTAGE_VIOLATIONS.csv.gz').read_bytes()).decode('utf-8')
    rows=[];kv={};aest=timezone(timedelta(hours=10))
    for r in csv.DictReader(io.StringIO(source)):
        node=r['node'];bus,ph=node.rsplit('.',1);ph=int(ph)
        if bus not in kv:e.d.Circuit.SetActiveBus(bus);kv[bus]=e.d.Bus.kVBase()
        group='IDC480' if bus.startswith('full_mobile_idc') else ('STA480' if bus.startswith('high_mv_sta') else ('ADDED_SVR_MV' if bus.startswith('v2svr') else ('ORIGINAL_MV' if kv[bus]>1 else 'ORIGINAL_LV')))
        origin=axis['issue_seconds'] if r['role']=='ACTUAL' else axis['day_start_seconds']
        start=float(r['physical_seconds']);until=float(r['until_seconds'])
        rows.append(dict(role=r['role'],node=node,native_node=ph,physical_phase=phase.get((bus,ph),'ABC'[ph-1] if ph in (1,2,3) and kv[bus]>1 else 'see upstream path'),
            scope=r['scope'],node_group=group,slot=int(r['slot']),native_seconds=start,
            start_AEST=datetime.fromtimestamp(origin+start,aest).isoformat(),end_AEST=datetime.fromtimestamp(origin+until,aest).isoformat(),
            duration_seconds=r['duration_seconds'],voltage_pu=r['pu'],kind=r['kind'],control_timing=r['control_timing'],
            upstream_path_bus_key=r['path_bus_key'],pending_queue_and_taps='Sealed raw CSV same role/node/slot/native_seconds'))
    table('MAY01_VOLTAGE_EVENT_CALENDAR_AND_PHASE.csv',rows)
    put('MAY01_NATIVE_CALENDAR_CONTRACT.json',dict(axis=axis,Actual_native_origin_AEST=axis['issue_AEST'],
        Planning_native_origin_AEST=axis['begin_AEST'],physical_seconds_are_not_solver_iterations=True,
        rows=len(rows),calendar_events=record(OUT/'MAY01_VOLTAGE_EVENT_CALENDAR_AND_PHASE.csv')))

if __name__=='__main__':run()
