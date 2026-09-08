"""Invert the frozen native load-to-bus/phase weight compilation once.

This changes no topology, native connection, rating, PV, AIDC, or MESS scale.
Missing native P/Q share authority is a hard error, never an equal-share fallback.
"""
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
import math
import sys

TOLERANCE = 1e-8


class AllocationError(RuntimeError):
    pass


@dataclass
class NativeAllocation:
    loads: list
    shares: dict

    @classmethod
    def from_adapter(cls, adapter):
        loads = adapter['loads']; groups = defaultdict(list); names=set()
        if not loads: raise AllocationError('NATIVE_SHARE_AUTHORITY_MISSING')
        for row in loads:
            name=str(row['load_name']).lower()
            if name in names: raise AllocationError('DUPLICATE_NATIVE_LOAD_AUTHORITY:'+name)
            names.add(name)
            phases=row['phases']
            if not phases or len(set(phases))!=len(phases) or any(p not in (1,2,3) for p in phases):
                raise AllocationError('INVALID_NATIVE_PHASE_AUTHORITY:'+name)
            for field in ('base_p_kw','base_q_kvar'):
                if field not in row or not math.isfinite(float(row[field])) or row[field]<0:
                    raise AllocationError('NATIVE_SHARE_AUTHORITY_MISSING_OR_INVALID:'+name+':'+field)
            for ph in phases:
                # The existing forward compiler uses base/n-listed-phases.
                groups[str(row['bus']).lower(),'ABC'[ph-1]].append((name,
                    Fraction(float(row['base_p_kw']))/len(phases),
                    Fraction(float(row['base_q_kvar']))/len(phases)))
        shares={}
        for key, rows in groups.items():
            totals=[sum((r[j] for r in rows),Fraction()) for j in (1,2)]
            shares[key]=[(r[0],r[1]/totals[0] if totals[0] else None,
                         r[2]/totals[1] if totals[1] else None) for r in rows]
        return cls(loads,shares)

    def allocate(self, p_targets, q_targets):
        totals={str(r['load_name']).lower():[0.,0.] for r in self.loads};parts=defaultdict(lambda:[[],[]]);ledger=[]
        for key in set(p_targets)|set(q_targets):
            if key not in self.shares and (abs(p_targets.get(key,0))>TOLERANCE or abs(q_targets.get(key,0))>TOLERANCE):
                raise AllocationError('NO_NATIVE_RECEIVER:'+str(key))
        for key, rows in self.shares.items():
            p=float(p_targets.get(key,0));q=float(q_targets.get(key,0))
            if not math.isfinite(p+q) or p<0 or q<0:raise AllocationError('INVALID_BACKGROUND_TARGET:'+str(key))
            for name, ps, qs in rows:
                if (ps is None and p!=0) or (qs is None and q!=0):raise AllocationError('ZERO_NATIVE_SHARE_AUTHORITY:'+str(key))
                ap=float(Fraction(p)*ps) if ps is not None else 0.
                aq=float(Fraction(q)*qs) if qs is not None else 0.
                parts[name][0].append(ap);parts[name][1].append(aq)
                ledger.append({'load_name':name,'bus':key[0],'phase':key[1],'target_P_kw':p,'target_Q_kvar':q,
                               'native_P_share':str(ps),'native_Q_share':str(qs),'allocated_P_kw':ap,'allocated_Q_kvar':aq})
        for name, (p,q) in parts.items():totals[name]=[math.fsum(p),math.fsum(q)]
        p_error=max((abs(math.fsum(r['allocated_P_kw'] for r in ledger if (r['bus'],r['phase'])==key)-p_targets.get(key,0)) for key in self.shares),default=0)
        q_error=max((abs(math.fsum(r['allocated_Q_kvar'] for r in ledger if (r['bus'],r['phase'])==key)-q_targets.get(key,0)) for key in self.shares),default=0)
        if max(p_error,q_error)>TOLERANCE:raise AllocationError('BUS_PHASE_CONSERVATION_FAIL')
        return totals,ledger,{'MAX_BUS_PHASE_P_CONSERVATION_ERROR_KW':p_error,'MAX_BUS_PHASE_Q_CONSERVATION_ERROR_KVAR':q_error,
                              'BACKGROUND_DUPLICATION_KW':0,'BUS65_DUPLICATION_KW':0,'BUS76_DUPLICATION_KW':0}

    def apply(self, odd, background, slot):
        from dayahead.v28r2.opendss_mapping import _set_load
        totals,ledger,audit=self.allocate(background.gross_p_kw_96[slot],background.gross_q_kvar_96[slot])
        for row in self.loads:
            name=str(row['load_name']);p,q=totals[name.lower()]
            _set_load(odd,name,p,q)
        return totals,ledger,audit

    def validate_native_engine(self, odd):
        records=[]
        for r in self.loads:
            odd.Loads.Name(r['load_name'])
            if odd.Loads.Name().lower()!=r['load_name'].lower():raise AllocationError('NATIVE_LOAD_NOT_FOUND')
            p=float(odd.Loads.kW());q=float(odd.Loads.kvar())
            odd.Circuit.SetActiveElement('Load.'+r['load_name']);bus=str(odd.CktElement.BusNames()[0]).lower()
            parts=bus.split('.');phases=[int(p) for p in parts[1:] if int(p)>0]
            if len(parts)==1:
                phases=list(range(1,int(odd.CktElement.NumPhases())+1))
            # Listed node order is frozen, including delta phase-pairs.
            if parts[0]!=r['bus'].lower() or phases!=list(r['phases']):raise AllocationError('NATIVE_BUS_PHASE_AUTHORITY_DRIFT:'+r['load_name'])
            if abs(p-r['base_p_kw'])>TOLERANCE or abs(q-r['base_q_kvar'])>TOLERANCE:raise AllocationError('NATIVE_PQ_AUTHORITY_DRIFT:'+r['load_name'])
            records.append({**r,'OpenDSS_native_P_kw':p,'OpenDSS_native_Q_kvar':q,'OpenDSS_bus':bus,
                            'OpenDSS_NumPhases':odd.CktElement.NumPhases(),'OpenDSS_delta':bool(odd.Loads.IsDelta()),'authority_verified':True})
        return records


@contextmanager
def corrected_mapping():
    """Process-local adapter injection; all original source files stay sealed.

    Import callers before entering so their function aliases are also replaced.
    The replacement runs only between slot application and SolveSnap, and no
    defective background values are ever assigned to the engine.
    """
    from dayahead.v28r2 import opendss_mapping as mapping
    from dayahead import run_v16_3_voltage_candidate as voltage
    from dayahead import run_v16_3_correction  # its _set_slot alias
    old_trajectory=mapping.apply_trajectory_slot;old_slot=voltage._set_slot;cache={}
    def allocation(adapter):
        key=id(adapter)
        if key not in cache:cache[key]=NativeAllocation.from_adapter(adapter)
        return cache[key]
    def trajectory(odd,adapter,context,frozen,slot):
        allocation(adapter).apply(odd,context.legacy_context[2],slot)
        return old_trajectory(odd,{**adapter,'loads':[]},context,frozen,slot)
    def anchor_slot(odd,adapter,background,plan,slot):
        allocation(adapter).apply(odd,background,slot)
        return old_slot(odd,{**adapter,'loads':[]},background,plan,slot)
    changes=[]
    for name,mod in list(sys.modules.items()):
        if not name.startswith('dayahead.') or mod is None:continue
        for attr,value in list(vars(mod).items()):
            if value is old_trajectory or value is old_slot:
                changes.append((mod,attr,value));setattr(mod,attr,trajectory if value is old_trajectory else anchor_slot)
    try:yield {'patched_aliases':[m.__name__+'.'+n for m,n,_ in changes]}
    finally:
        for mod,attr,value in reversed(changes):setattr(mod,attr,value)
