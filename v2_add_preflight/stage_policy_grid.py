"""IEEE8500 electrical packet for the unmodified signed Actual policy.

The source policy still ranks the same signed 16-face loading objective and
calls its current-AC guard. Independent P/Q derivatives are folded by the
original PF contract. All original voltages, both line terminals, every
transformer winding/current and all24 port limits remain physical guards.
"""
import copy,math
from types import SimpleNamespace
import numpy as np
from .stage_common import *
from v42_native.contracts import digest
from .stage_a_grid import PF
from v43_actual.vendor.sensitivity_policy import OriginalGridPacket

def collapse(J):return np.r_[J[:12]+PF*J[12:24],J[24:]]

class Carrier:
    """Immutable lazy parent-line score view; full security remains in packet."""
    def __init__(self,owner,t):self.owner=owner;self.t=t
    def __deepcopy__(self,memo):return self
    def __getattr__(self,key):
        data=self.owner._source(self.t);p=self.owner.parent;anchor=np.r_[data['anchor'][:12],np.zeros(48)]
        static=dict(slot=self.t,control_names=self.owner.control_names,branch_names=self.owner.branch_names,
            coefficient_sha256=self.owner.sources[self.t]['sha256'],anchor=anchor,
            branch_limits=np.asarray(self.owner.axes['line_phase_kVA'])[p],transformer_ratings=tuple(None for _ in p))
        if key in static:return static[key]
        pairs={'voltage':('v',None),'flow_p':('lp',p),'flow_q':('lq',p),'current':('line',p)}
        for stem,(name,idx) in pairs.items():
            y=data[name] if idx is None else data[name][idx]
            J=collapse(data[name+'_J']);J=J if idx is None else J[:,idx]
            if key==stem+'_constant':return y-J.T@anchor
            if key==stem+'_matrix':return J.T if stem in ('flow_p','flow_q') else J
        raise AttributeError(key)

class GridPacket(OriginalGridPacket):
    def __init__(self,*,arrays,power,swing,capacities,aidc_plan,mess,bindings,begin_seconds,rack_compatibility):
        from v43_actual.vendor.sensitivity_policy import REQUIRED_BINDINGS
        if any(not bindings.get(k) for k in REQUIRED_BINDINGS):raise ValueError('COMPLETE_SENSITIVITY_POLICY_ANCHORS_REQUIRED')
        self.axes=read(OUT/'SOURCE_YY_GRID_AXES.json');self.parent=np.flatnonzero(self.axes['parent_mask']);self.security=np.flatnonzero(self.axes['security_mask'])
        self.sources=read(OUT/'SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json')['records']
        self._cached_slot=None;self._cached_data=None
        self.bindings=copy.deepcopy(bindings);self.begin_seconds=float(begin_seconds);self.sites=tuple(sorted(capacities))
        assert self.sites==tuple(f'AIDC{i:02d}' for i in range(1,13)) and sum(capacities.values())==780
        self.capacities=dict(capacities);self.rack_compatibility=copy.deepcopy(rack_compatibility)
        assert set(self.rack_compatibility)==set(self.sites)
        assert all(limits and all(math.isfinite(float(v)) and v>0 for v in limits) for limits in self.rack_compatibility.values())
        self.aidc_plan=copy.deepcopy(aidc_plan);self.pf=.95;self.q_per_p=PF;self.swing_kw=float(swing)
        self.control_names=tuple([f'aidc_load_kw[{s}]' for s in self.sites]+[f'mess_p_kw[{s}{i:02d}]' for s in ('IDC','STA') for i in range(1,13)]+[f'mess_q_kvar[{s}{i:02d}]' for s in ('IDC','STA') for i in range(1,13)])
        self.branch_names=tuple(self.axes['line'][j]['element']+'::'+self.axes['line'][j]['physical_phase'] for j in self.parent)
        self.coefficients=tuple(Carrier(self,t) for t in range(96));self.controls=np.zeros((96,60))
        p=np.asarray(arrays['PCC_P_kw']);q=np.asarray(arrays['PCC_Q_kvar']);assert p.shape==q.shape==(96,12) and np.max(abs(q-PF*p))<1e-8
        self.controls[:,:12]=p;services=[f'{s}{i:02d}' for s in ('IDC','STA') for i in range(1,13)]
        for j,s in enumerate(services):
            self.controls[:,12+j]=mess['P_by_site'][s];self.controls[:,36+j]=mess['Q_by_site'][s]
        assert np.isfinite(self.controls).all() and digest({k:v for k,v in mess.items() if k!='plan_sha'})==mess['plan_sha']
        assert mess['plan_sha']==bindings['mess_anchor']
        self.response_sources=sorted({r['sha256'] for r in self.sources})
        if bindings['response_sha'] not in (digest(self.response_sources),record(OUT/'SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json')['sha256']):
            raise ValueError('ELECTRICAL_RESPONSE_ANCHOR_DRIFT')
        self.p_slope=np.array([[power[s,t].slope*swing for s in self.sites] for t in range(96)])
        assert np.min(self.p_slope)>0
        self.line_indices=np.arange(len(self.parent));self.transformer_indices=np.array([],dtype=int)
        self.voltage_lower=.95**2;self.voltage_upper=1.05**2
        self.cos=np.cos(2*np.pi*np.arange(16)/16);self.sin=np.sin(2*np.pi*np.arange(16)/16)
        self.ap=[];self.correction=[];self.bias=[]
        for t,c in enumerate(self.coefficients):
            ap=c.branch_limits*math.cos(math.pi/16);a=self._source(t)
            raw=(a['lp'][self.parent,None]*self.cos+a['lq'][self.parent,None]*self.sin)/ap[:,None];active=raw.argmax(axis=1)
            grad=(self.cos[active,None]*c.flow_p_matrix+self.sin[active,None]*c.flow_q_matrix)/ap[:,None]
            self.ap.append(ap);self.correction.append(c.current_matrix.T-grad);self.bias.append(a['line'][self.parent]-raw.max(axis=1))
        self.known_gpu=np.asarray(arrays['known_gpu']).copy();assert self.known_gpu.shape==(96,12)
        self.cache={};self.scenario_cache={};self.evaluation_calls=0;self.cache_hits=0
        self.authority=dict(schema='IEEE8500_SOURCE_YY_FULL_PHYSICAL_SIGNED_PACKET',
            hardware=record(OUT/'SOURCE_YY_HARDWARE_FREEZE.json'),grid=record(OUT/'SOURCE_YY_IEEE8500_GRID_COEFFICIENT_CERTIFICATION.json'),
            original_lines=3703,Triplex=1177,parent_line_cells=len(self.parent),all_terminal_current_cells=len(self.security),
            transformer_current_cells=len(self.axes['transformer_current']),transformer_winding_cells=len(self.axes['transformer_winding']),
            original_source_policy_algorithm_unchanged=True,PF_folded_independent_Q=True,
            transformer_and_port_checks='Separate full native axes in _at_slot; never omitted from the physical guard',
            rack_source='EXACT_ORIGINAL_SOURCE_MAP',mess_plan_sha=mess['plan_sha'])
    def _source(self,t):
        if self._cached_slot!=t:
            path=RUN/'coefficients'/f'{t:02d}.npz';expected=self.sources[t]
            if record(path)['sha256']!=expected['sha256']:raise ValueError('CURRENT_SIGNED_GRID_SOURCE_DRIFT')
            with np.load(path) as z:data={k:z[k] for k in z.files}
            for value in data.values():value.setflags(write=False)
            self._cached_slot=t;self._cached_data=data
        return self._cached_data
    def _at_slot(self,t,gpu_delta):
        t=int(t);a=self._source(t);p=self.controls[t,:12]+np.asarray(gpu_delta)*self.p_slope[t]
        delta=np.r_[p-a['anchor'][:12],PF*p-a['anchor'][12:24],self.controls[t,12:]]
        y=lambda key:a[key]+a[key+'_J'].T@delta
        v=y('v');current=y('line');tc=y('tc');tp=y('tp');tq=y('tq');lp=y('lp')[self.parent];lq=y('lq')[self.parent]
        control=np.r_[p,self.controls[t,12:]]
        faces=(lp[:,None]*self.cos+lq[:,None]*self.sin)/self.ap[t][:,None]
        faces+=(self.correction[t]@(control-self.coefficients[t].anchor)+self.bias[t])[:,None]
        peak=max(0.,float(faces.max()));bad=[]
        if np.min(v)<self.voltage_lower-1e-9 or np.max(v)>self.voltage_upper+1e-9:bad.append(dict(slot=t,reason='ORIGINAL_PLANNING_VOLTAGE'))
        if peak>1+1e-9 or current[self.security].max()>1+1e-9:bad.append(dict(slot=t,reason='ORIGINAL_ALL_TERMINAL_LINE_CURRENT'))
        if tc.max()>1+1e-9:bad.append(dict(slot=t,reason='ORIGINAL_ALL_TRANSFORMER_CURRENT'))
        tx=tp[:,None]*self.cos+tq[:,None]*self.sin
        if np.any(tx>np.asarray(self.axes['tx_kVA'])[:,None]*math.cos(math.pi/16)+1e-9):bad.append(dict(slot=t,reason='ORIGINAL_ALL_TRANSFORMER_KVA'))
        port=np.array([i for i,r in enumerate(self.axes['transformer_current']) if r['winding']==2 and r['element'].lower().startswith(('transformer.high_mv_sta','transformer.full_mobile_idc'))])
        portfaces=self.controls[t,12:36,None]*self.cos+self.controls[t,36:60,None]*self.sin
        if np.any(tc[port]>.8+1e-9) or np.any(portfaces>600*math.cos(math.pi/16)+1e-9):bad.append(dict(slot=t,reason='ORIGINAL_MOBILE_PORT_RATING'))
        return peak,bad
