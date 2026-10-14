"""Equivalent signed original rows with bounded vectorized kVA checks.

The strict E0 implementation and all physical authorities remain unchanged.
This research-only subclass changes computation order across independent
transformer branches, retaining the same expressions and violation order.
"""
import math
from copy import deepcopy
from collections import OrderedDict
import numpy as np
from .sensitivity_policy import OriginalGridPacket


class ExperimentalGridPacket(OriginalGridPacket):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._rated=[]
        for coefficient in self.coefficients:
            indices=np.array([i for i,r in enumerate(coefficient.transformer_ratings) if r is not None],dtype=int)
            limits=np.array([float(coefficient.transformer_ratings[i])*math.cos(math.pi/16) for i in indices])
            self._rated.append((indices,limits))
        self._batch_tables=None
        self._slot_cache=OrderedDict()
        self.slot_cache_hits=0
        self.slot_cache_misses=0
        self.slot_cache_enabled=True

    def _tables(self):
        if self._batch_tables is None:
            names=('voltage_constant','voltage_matrix','flow_p_constant','flow_p_matrix',
                'flow_q_constant','flow_q_matrix','current_constant','current_matrix','anchor')
            tables={name:np.stack([np.asarray(getattr(c,name),float) for c in self.coefficients]) for name in names}
            tables['kva_limit']=np.array([[np.nan if r is None else float(r)*math.cos(math.pi/16)
                for r in c.transformer_ratings] for c in self.coefficients])
            tables['correction']=np.stack(self.correction);tables['bias']=np.stack(self.bias)
            tables['ap']=np.stack(self.ap)
            tables['aidc_columns']=np.array([self.control_names.index('aidc_load_kw['+s+']') for s in self.sites])
            for value in tables.values():value.flags.writeable=False
            self._batch_tables=tables
        return self._batch_tables

    def evaluate(self,gpu_delta,*,remaining_slot=0,scenario_gpu=None):
        """Batch identical original rows; exact original peak and near guards.

        Einsum may change last-bit summation. Any row near an original hard
        boundary is rechecked through the exact original scalar path. The
        maximizing slot is also recomputed there; ratings/tolerances do not
        change. No cache survives a different complete numeric input.
        """
        from .sensitivity_policy import _array
        a=_array(gpu_delta,(96,len(self.sites)))
        if not 0<=remaining_slot<96:raise ValueError('REMAINING_GRID_HORIZON_REQUIRED')
        stress=np.zeros_like(a) if scenario_gpu is None else _array(scenario_gpu,a.shape)
        stress_key=stress.tobytes();key=(remaining_slot,stress_key,a.tobytes())
        if key in self.cache:
            self.cache_hits+=1;return deepcopy(self.cache[key])
        if stress_key not in self.scenario_cache:
            self.scenario_cache[stress_key]=[self._at_slot(t,stress[t]) for t in range(96)]
            if len(self.scenario_cache)>4:self.scenario_cache.pop(next(iter(self.scenario_cache)))
        base=self.scenario_cache[stress_key]
        peaks=np.array([r[0] for r in base]);by_slot={t:r[1] for t,r in enumerate(base)}
        slots=np.flatnonzero(np.any(a!=0,axis=1));slots=slots[slots>=remaining_slot]
        if len(slots):
            z=self._tables();control=self.controls[slots].copy()
            control[:,z['aidc_columns']]+=(a[slots]+stress[slots])*self.p_slope[slots]
            voltage=z['voltage_constant'][slots]+np.einsum('tkn,tk->tn',z['voltage_matrix'][slots],control)
            p=z['flow_p_constant'][slots]+np.einsum('tbk,tk->tb',z['flow_p_matrix'][slots],control)
            q=z['flow_q_constant'][slots]+np.einsum('tbk,tk->tb',z['flow_q_matrix'][slots],control)
            faces=p[:,:,None]*self.cos+q[:,:,None]*self.sin
            correction=np.einsum('tbk,tk->tb',z['correction'][slots],control-z['anchor'][slots])+z['bias'][slots]
            line=faces/z['ap'][slots,:,None]+correction[:,:,None]
            line_peak=np.maximum(0.,np.max(line[:,self.line_indices,:],axis=(1,2)))
            current=z['current_constant'][slots]+np.einsum('tkb,tk->tb',z['current_matrix'][slots],control)
            kva_peak=np.max(faces,axis=2);limits=z['kva_limit'][slots]
            # Only computation paths change, never the original 1e-9 guards.
            near=(np.any(np.abs(voltage-self.voltage_lower)<1e-7,axis=1)|
                np.any(np.abs(voltage-self.voltage_upper)<1e-7,axis=1)|
                (np.abs(line_peak-1)<1e-7)|
                np.any(np.abs(current[:,self.transformer_indices]-1)<1e-7,axis=1)|
                np.any(np.abs(kva_peak-limits)<1e-7,axis=1))
            for n,t in enumerate(slots):
                t=int(t)
                if near[n]:
                    peaks[t],by_slot[t]=self._at_slot(t,a[t]+stress[t]);continue
                violations=[]
                if np.any(voltage[n]<self.voltage_lower-1e-9) or np.any(voltage[n]>self.voltage_upper+1e-9):
                    violations.append(dict(slot=t,reason='ORIGINAL_PLANNING_VOLTAGE'))
                if line_peak[n]>1+1e-9:violations.append(dict(slot=t,reason='ORIGINAL_LINE_CURRENT'))
                if len(self.transformer_indices) and np.any(current[n,self.transformer_indices]>1+1e-9):
                    violations.append(dict(slot=t,reason='ORIGINAL_ALL_TRANSFORMER_CURRENT'))
                violations.extend(dict(slot=t,reason='ORIGINAL_TRANSFORMER_KVA',branch=self.branch_names[i])
                    for i in np.flatnonzero(kva_peak[n]>limits[n]+1e-9))
                peaks[t]=line_peak[n];by_slot[t]=violations
            # Recompute all numerical near-ties with the literal original
            # expression so the scalar objective used in ranking is exact.
            peak=float(np.max(peaks[remaining_slot:]));top=np.flatnonzero(peaks>=peak-1e-10)
            for t in top[top>=remaining_slot]:
                peaks[t],by_slot[int(t)]=self._at_slot(int(t),a[t]+stress[t])
        violations=[r for t in range(remaining_slot,96) for r in by_slot[t]]
        result=dict(peak_score=float(np.max(peaks[remaining_slot:])),hard_feasible=not violations,
            violations=violations,remaining_slots=96-remaining_slot,per_slot_peak=peaks[remaining_slot:].tolist(),
            affine_approximation_only=True,Fresh_AC_PASS_claimed=False)
        self.evaluation_calls+=1;self.cache[key]=result
        if len(self.cache)>256:self.cache.pop(next(iter(self.cache)))
        return deepcopy(result)

    def _at_slot(self,t,gpu_delta):
        # All response tables and authority are frozen per packet, as required
        # by the existing full-profile cache. Retain complete numeric input;
        # no rounding, tolerance change or approximation enters this key.
        delta=np.asarray(gpu_delta)
        if not getattr(self,'slot_cache_enabled',True):
            return self._at_slot_uncached(t,delta)
        key=(int(t),delta.dtype.str,delta.shape,delta.tobytes())
        cache=self.__dict__.setdefault('_slot_cache',OrderedDict())
        if key in cache:
            self.slot_cache_hits=getattr(self,'slot_cache_hits',0)+1
            cache.move_to_end(key)
            return deepcopy(cache[key])
        self.slot_cache_misses=getattr(self,'slot_cache_misses',0)+1
        result=self._at_slot_uncached(t,delta)
        cache[key]=deepcopy(result)
        if len(cache)>1024:cache.popitem(last=False)
        return result

    def _at_slot_uncached(self,t,gpu_delta):
        t=int(t)
        c=self.coefficients[t];control=self.controls[t].copy()
        for j,s in enumerate(self.sites):
            control[self.control_names.index('aidc_load_kw['+s+']')]+=gpu_delta[j]*self.p_slope[t,j]
        voltage=c.voltage_constant+c.voltage_matrix.T@control
        p=c.flow_p_constant+c.flow_p_matrix@control
        q=c.flow_q_constant+c.flow_q_matrix@control
        line=(p[:,None]*self.cos+q[:,None]*self.sin)/self.ap[t][:,None]
        line+=((self.correction[t]@(control-c.anchor))+self.bias[t])[:,None]
        line_peak=max(0.,float(np.max(line[self.line_indices])))
        violations=[]
        if np.any(voltage<self.voltage_lower-1e-9) or np.any(voltage>self.voltage_upper+1e-9):
            violations.append(dict(slot=t,reason='ORIGINAL_PLANNING_VOLTAGE'))
        if line_peak>1+1e-9:violations.append(dict(slot=t,reason='ORIGINAL_LINE_CURRENT'))
        current=c.current_constant+c.current_matrix.T@control
        if len(self.transformer_indices) and np.any(current[self.transformer_indices]>1+1e-9):
            violations.append(dict(slot=t,reason='ORIGINAL_ALL_TRANSFORMER_CURRENT'))
        indices,limits=self._rated[t]
        if len(indices):
            faces=p[indices,None]*self.cos+q[indices,None]*self.sin
            failed=indices[np.max(faces,axis=1)>limits+1e-9]
            violations.extend(dict(slot=t,reason='ORIGINAL_TRANSFORMER_KVA',branch=self.branch_names[i]) for i in failed)
        return line_peak,violations
