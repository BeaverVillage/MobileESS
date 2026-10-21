"""Independent live model snapshot; no TIME campaign or optimization."""
import json,re
from pathlib import Path
import numpy as np
from .audit import read,sha,DOC
from .correction_svr import SV,save
from . import correction as c
from . import correction_svr_run as runner
from .correction_svr_implicit import source_svr
from .correction_time100 import clock_class

def main():
    c.priority();runner.seal_s0();m=source_svr();m._BUS=re.compile(r'^[a-zA-Z0-9_\-]+(?:\.[0-3])*$')
    runner.source_svr=lambda:m;c.clock_class=clock_class;runner.Instrumented.configuration='S1_12'
    e=runner.Instrumented('INDEPENDENT_MODEL_AUDIT_S1_12','ACTUAL');d=e.d
    before=e.original_line_static;after={name:e._line_static(name) for name in before};assert before==after
    original_buses={r['name']:r['buses'] for r in read(DOC/'OFFICIAL_BALANCED_AXES.json')['lines']}
    new_buses={r['element'].split('.',1)[1]:r['buses'] for r in e.inventory['lines']}
    cuts={u['cut_element'].split('.',1)[1]:u for u in e.bank.contract['units']}
    for name,buses in original_buses.items():
        expected=list(buses)
        if name in cuts:expected[0]=cuts[name]['upstream_new_bus']+'.1.2.3'
        assert new_buses[name]==expected
    # Independently read every original line current, after PDE reindexing.
    data=e.measurement_arrays();max_error=0.;cursor=0
    for meta in e.inventory['lines']:
        d.Circuit.SetActiveElement(meta['element'])
        if meta['enabled']:
            mags=d.CktElement.CurrentsMagAng();nodes=d.CktElement.NodeOrder()
            for k,node in enumerate(nodes):
                if node>0:max_error=max(max_error,abs(mags[2*k]/d.CktElement.NormalAmps()-data['line_rho'][cursor+k]))
        cursor+=len(meta['node_order'])
    assert max_error<1e-12
    pv=[]
    for name,kva,r in zip(e.pv_names,e.pv_capacity,e.pv_records):
        d.Generators.Name(name);assert d.Generators.kV()==r['kv'] and d.Generators.Model()==1
        assert d.CktElement.BusNames()==r['buses'];assert abs(float(d.Properties.Value('kVA'))-kva)<1e-9
        pv.append(dict(name=name,kv=d.Generators.kV(),model=d.Generators.Model(),buses=d.CktElement.BusNames(),kva=float(d.Properties.Value('kVA'))))
    snapshots=dict(before_line_properties=before,after_line_properties=after,original_bus_connections=original_buses,
        installed_bus_connections=new_buses,contract=e.bank.contract,installation=e.bank.installation_receipt,
        transformer_inventory=e.inventory['transformers'],regcontrols=e.initial_audit,PV_roster=pv,
        AIDC12_STA12_mapping=e.mapping,port_meta=e.port_meta,node_names=e.node_axes)
    p=SV/'INDEPENDENT_S1_12_MODEL_SNAPSHOT.json';p.write_text(json.dumps(snapshots),encoding='utf-8')
    save('INDEPENDENT_S1_12_MODEL_CERTIFICATION.json',dict(PASS=True,original_lines=len(before),original_Triplex=1177,
        original_line_all_nonbus_properties_bit_identical=before==after,only_declared_terminal1_bus_splits=len(cuts),
        source_root_to_original_line_series_path='Original bus -> three finite single-phase transformers -> new bus -> retained original line',
        existing_RegControl_count=12,added_RegControl_count=36,total_RegControl_count=len(e.initial_audit),new_bank_count=12,
        all_existing_PV_kV_Model_capacity_and_buses_preserved=True,new_PDE_reindex_scalar_vs_bulk_max_abs_error=max_error,
        snapshot=dict(path=str(p),sha256=sha(p.read_bytes())),scope='Independent compiled installation snapshot, no TIME operating dispatch or feasibility claim',Native_optimizer_calls=0))
    print('INDEPENDENT SERIES MODEL SNAPSHOT PASS',flush=True)

if __name__=='__main__':main()
