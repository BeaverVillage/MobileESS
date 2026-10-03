"""NormalAmps is the only transformer-current denominator; never synthesize it.

The scalar OpenDSS PDElement NormalAmps refers to the first winding. Every
oriented transformer parent in this frozen feeder must therefore be terminal 1.
kVA and line ratings remain independent authorities. No electrical setters.
"""
from functools import lru_cache
import hashlib,json,math
import numpy as np
from .common import *

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def checked_normal(value,name):
    try:value=float(value)
    except (ValueError,TypeError):raise ValueError('SOURCE_NORMALAMPS_ABSENT:'+name)
    if not math.isfinite(value) or value<=0:raise ValueError('SOURCE_NORMALAMPS_INVALID:'+name)
    return value

def compiled(odd,branches):
    rows=[];line=[]
    for b in branches:
        odd.Circuit.SetActiveElement(b.branch_id)
        if odd.CktElement.Name().lower()!=b.branch_id.lower():raise ValueError('COMPILED_BRANCH_IDENTITY')
        buses=[s.split('.')[0].lower() for s in odd.CktElement.BusNames()]
        terminal=buses.index(b.parent_bus.lower())
        if b.branch_id.startswith('line.'):
            odd.Lines.Name(b.branch_id.split('.',1)[1])
            line.append(dict(branch_phase=f'{b.branch_id}::{b.phase}',NormalAmps=float(odd.Lines.NormAmps()),EmergAmps=float(odd.Lines.EmergAmps())))
            continue
        if terminal!=0:raise ValueError('NORMALAMPS_FIRST_WINDING_AUTHORITY_REQUIRED:'+b.branch_id)
        normal=checked_normal(odd.Properties.Value('NormAmps'),b.branch_id)
        emerg=checked_normal(odd.Properties.Value('EmergAmps'),b.branch_id)
        normhkva=float(odd.Properties.Value('NormHkVA'));emerghkva=float(odd.Properties.Value('EmergHkVA'))
        odd.Transformers.Name(b.branch_id.split('.',1)[1]);odd.Transformers.Wdg(1)
        kv=float(odd.Transformers.kV());kva=float(odd.Transformers.kVA());phases=int(odd.CktElement.NumPhases())
        old=kva/(math.sqrt(3)*kv) if phases>=2 else kva/kv
        rows.append(dict(transformer=b.branch_id,phase=b.phase,branch_phase=f'{b.branch_id}::{b.phase}',
            parent_bus=b.parent_bus,child_bus=b.child_bus,parent_terminal=terminal+1,Phases=phases,
            kV=kv,kVA=kva,NormalAmps=normal,EmergAmps=emerg,NormHkVA=normhkva,EmergHkVA=emerghkva,
            old_denominator_A=old,old_denominator_source='winding kVA/(sqrt(3)*kV) for multiphase; kVA/kV for single phase',
            new_denominator_A=normal,difference_percent=100*(normal/old-1),
            new_denominator_source='compiled OpenDSS PDElement NormAmps, first winding',
            CTPrim_used=False,tap_used=False))
    if {r['transformer'] for r in rows}!={'transformer.'+n.lower() for n in odd.Transformers.AllNames()}:
        raise ValueError('ALL_COMPILED_TRANSFORMERS_REQUIRED')
    return rows,line

@lru_cache(None)
def current_authority():
    from v42_regcontrol.authority import source,compile_verified,assert_inventory
    import os
    m=source();odd,adapter,actual_controls=compile_verified()
    try:
        branches,topology=m['oriented_branches'](odd);actual,lines=compiled(odd,branches)
    finally:odd.Basic.ClearAll()
    from dayahead.run_planning_ac_voltage_forensic_v1 import _compile
    previous=Path.cwd()
    try:
        odd,_=_compile(m['assets'].master.parents[1],m['assets'].pcc.parents[3],'NATIVE')
        planning_controls=m['inventory'](odd);assert_inventory(planning_controls,initial=True)
        pb,_=m['oriented_branches'](odd);planning,plines=compiled(odd,pb)
    finally:
        odd.Basic.ClearAll();os.chdir(previous)
    if actual!=planning or lines!=plines or actual_controls!=planning_controls:
        raise ValueError('PLANNING_ACTUAL_COMPILED_THERMAL_AUTHORITY_MISMATCH')
    provenance=[record(resolve(r)) for r in m['audit']['static_source_graph']['files']]
    identity=dict(schema=SCHEMA,source_SHA256=[r['sha256'] for r in provenance],
        rows=actual,normalization='abs parent-terminal phase current_A / compiled NormalAmps',
        kVA_authority='unchanged winding nameplate',line_authority='unchanged Line NormAmps')
    return dict(rows=actual,lines=lines,Planning=planning,Actual=actual,
        transformer_current_authority_sha256=digest(identity),identity=identity,provenance=provenance,
        controls=actual_controls,topology=topology,PASS=True)

def denominators(names,*,old=False):
    a=current_authority();mapping={r['branch_phase'].lower():r['old_denominator_A' if old else 'NormalAmps'] for r in a['rows']}
    mapping.update({r['branch_phase'].lower():r['NormalAmps'] for r in a['lines']})
    try:return np.array([mapping[str(n).lower()] for n in names],float)
    except KeyError as e:raise ValueError('EXACT_CURRENT_BRANCH_AXIS_REQUIRED:'+str(e))

def require_certificate(receipt):
    expected=current_authority()['transformer_current_authority_sha256']
    if receipt.get('transformer_current_contract')!=SCHEMA or receipt.get('transformer_current_authority_sha256')!=expected:
        raise ValueError('SUPERSEDED_TRANSFORMER_CURRENT_CERTIFICATE')
    return True

def arm_contract(arm):
    if arm not in ('B0','B1','B2','B3'):raise ValueError('COMPARISON_ARM_REQUIRED')
    return dict(transformer_current_contract=SCHEMA,
        transformer_current_authority_sha256=current_authority()['transformer_current_authority_sha256'],
        transformer_current_limit='compiled source-backed OpenDSS NormalAmps',
        transformer_kVA_limit='unchanged source-backed winding kVA',line_rating_changed=False,
        voltage_band=[.95,1.05],CTPrim_thermal_authority=False)

def current_identity():
    return dict(transformer_current_contract=SCHEMA,
        transformer_current_authority_sha256=current_authority()['transformer_current_authority_sha256'])
