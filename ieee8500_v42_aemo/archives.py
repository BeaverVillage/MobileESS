"""Retain full thermal/voltage arrays and focused exact phasor evidence.

Phasors are retained for all conductors/ends of the daily top20 lines and all
their endpoint nodes plus daily voltage extrema. No hard-constraint axis is
removed; full complex phasors on other elements are not a required archive.
"""
import numpy as np
from .common import *

CORE_KEYS=('line_amps','line_rho','node_voltage_pu','transformer_amps',
           'transformer_current_rho','transformer_winding_nameplate_kva_rho')


def save_arrays(folder,packed,axes):
    folder=Path(folder)
    groups={}
    for i,r in enumerate(axes['lines']):
        if r['objective_included']:groups.setdefault(r['element'],[]).append(i)
    names=sorted(groups,key=lambda n:(-float(packed['line_rho'][:,groups[n]].max()),n))[:20]
    li=np.array([i for i,r in enumerate(axes['lines']) if r['element'] in names])
    records=read(PR193/'ORIGINAL_FEEDER_INVENTORY.json')['lines']
    buses={b.split('.')[0].lower() for r in records if r['element'] in names for b in r['buses']}
    extremes=set(np.argmin(packed['node_voltage_pu'],axis=1))|set(np.argmax(packed['node_voltage_pu'],axis=1))
    ni=np.array([i for i,node in enumerate(axes['nodes']) if i in extremes or node.rsplit('.',1)[0].lower() in buses])
    np.savez_compressed(folder/'PHASOR_FORENSICS.npz',line_indices=li,node_indices=ni,
        line_complex_A=packed['line_complex_A'][:,li],line_complex_kVA=packed['line_complex_kVA'][:,li],
        node_complex_V=packed['node_complex_V'][:,ni])
    np.savez_compressed(folder/'AC_96.npz',**{k:packed[k] for k in CORE_KEYS})
    return dict(full_original_hard_constraint_axes_preserved=True,
        focused_complex_phasor_lines=names,focus=receipt(folder/'PHASOR_FORENSICS.npz'))


def compact_existing():
    records=[]
    for folder in sorted((REPORT/'ac').iterdir()):
        path=folder/'AC_96.npz'
        if not path.exists():continue
        with np.load(path) as z:
            if 'line_complex_A' not in z.files:continue
            packed={k:z[k] for k in z.files}
        old=receipt(path);record=save_arrays(folder,packed,read(folder/'AC_AXES.json'))
        doc=read(folder/'RECEIPT.json');doc['AC_arrays']=receipt(path);doc['phasor_archive']=record
        write(folder/'RECEIPT.json',doc)
        records.append(dict(stage=folder.name,prior_full_complex_archive=old,new_archive=doc['AC_arrays'],**record))
    if records:
        write(REPORT/'ARCHIVE_COMPACTION.json',dict(records=records,
            scope='archive representation only; all thermal/voltage metrics and retained phasors unchanged',
            full_complex_arrays_outside_focus_omitted=True))
        run=read(REPORT/'RUN_RECEIPT.json')
        for key,value in run.items():
            if isinstance(value,dict) and value.get('stage'):
                run[key]=read(REPORT/'ac'/value['stage']/'RECEIPT.json')
            elif key=='policies':run[key]=[read(REPORT/'ac'/v['stage']/'RECEIPT.json') for v in value]
        write(REPORT/'RUN_RECEIPT.json',run)
        regression=read(REPORT/'STATIC_PR193_REGRESSION.json')
        regression['case']=read(REPORT/'ac/STATIC_PR193_P0/RECEIPT.json')
        write(REPORT/'STATIC_PR193_REGRESSION.json',regression)


if __name__=='__main__':compact_existing()
