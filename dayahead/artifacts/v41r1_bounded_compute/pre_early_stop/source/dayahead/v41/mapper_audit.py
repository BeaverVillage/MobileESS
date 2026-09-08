"""Independent native-load group readback after the corrected mapping call."""
from contextlib import contextmanager
import math
import pandas as pd
from dayahead.paper_analysis.storage import write_json
from dayahead.v40e.mapping import NativeAllocation, TOLERANCE
from .persistence import table
from .preflight import record
from .reserve import require


@contextmanager
def observe(output, day, stage):
    original=NativeAllocation.apply; rows=[]; sampled=set(); invocations=0
    def applied(self, odd, background, slot):
        nonlocal invocations
        result=original(self,odd,background,slot); invocations+=1
        # Native targets are fixed for each daily slot in the coefficient
        # generator. All control perturbations change AIDC/MESS only.
        if slot not in sampled:
            active=str(odd.CktElement.Name()); previous_load=str(odd.Loads.Name())
            actual={}; members={}; source={str(r['load_name']).lower():r for r in self.loads}
            try:
                for name,r in source.items():
                    odd.Loads.Name(name)
                    require(str(odd.Loads.Name()).lower()==name,'MAPPER_NATIVE_LOAD_MISSING')
                    p,q=float(odd.Loads.kW()),float(odd.Loads.kvar())
                    for phase in r['phases']:
                        key=(str(r['bus']).lower(),'ABC'[phase-1])
                        actual.setdefault(key,[[],[]]); members.setdefault(key,[])
                        actual[key][0].append(p/len(r['phases'])); actual[key][1].append(q/len(r['phases']))
                        members[key].append(name)
            finally:
                odd.Loads.Name(previous_load); odd.Circuit.SetActiveElement(active)
            for key in sorted(actual):
                p,q=map(math.fsum,actual[key]); ep=float(background.gross_p_kw_96[slot].get(key,0)); eq=float(background.gross_q_kvar_96[slot].get(key,0))
                rows.append(dict(target_day=day,stage=stage,slot=int(slot),bus=key[0],phase=key[1],
                    native_members=','.join(sorted(members[key])),native_load_count=len(members[key]),
                    shared_bus_phase=len(members[key])>1,target_P_kW=ep,target_Q_kvar=eq,readback_P_kW=p,readback_Q_kvar=q,
                    P_error_kW=p-ep,Q_error_kvar=q-eq,duplication_detected=p-ep>TOLERANCE or q-eq>TOLERANCE))
            sampled.add(slot)
        return result
    NativeAllocation.apply=applied
    try:
        yield
    finally:
        NativeAllocation.apply=original
        if rows:
            frame=pd.DataFrame(rows); source=table(output/'NATIVE_BUS_PHASE_96.parquet',frame)
            complete=sampled==set(range(96)); maxp=float(frame.P_error_kW.abs().max()); maxq=float(frame.Q_error_kvar.abs().max())
            status='PASS' if complete and max(maxp,maxq)<=TOLERANCE and not frame.duplication_detected.any() else 'FAIL'
            write_json(output/'MAPPER_AUDIT.json',dict(status=status,target_day=day,stage=stage,
                corrected_mapper=record(NativeAllocation.apply.__code__.co_filename),
                observed_corrected_native_apply_calls=invocations,slots=len(sampled),
                native_group_count=int(frame[['bus','phase']].drop_duplicates().shape[0]),
                shared_group_count=int(frame[frame.shared_bus_phase][['bus','phase']].drop_duplicates().shape[0]),
                duplicated_group_slots=int(frame.duplication_detected.sum()),P_max_error_kW=maxp,Q_max_error_kvar=maxq,
                tolerance=TOLERANCE,rows=source,readback_source='OpenDSS Loads.kW/kvar after corrected application, per native listed phase',
                original_native_duplication_branch_receives_empty_load_list=True))
            require(status=='PASS','INDEPENDENT_NATIVE_LOAD_DUPLICATION_OR_CONSERVATION_FAILURE')
        else:
            raise ValueError('CORRECTED_MAPPER_NEVER_EXECUTED')
