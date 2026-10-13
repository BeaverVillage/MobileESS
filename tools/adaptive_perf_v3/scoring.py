"""Heuristic signed minimax service with backward terminal-SOC lookahead."""
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_compact_joint.scoring import AdaptiveMinimax

class LookaheadMinimax(AdaptiveMinimax):
    def path_vector(self,u,path):
        key=(u,tuple(path))
        if key in self.path_cache:return self.path_cache[key][0]
        ui=self.units.index(u);battery=self.case.graph[3];dt=battery.dt_hours
        connected=np.full(96,-1,dtype=int);travel=np.zeros(96)
        for k in path:
            arc=self.case.graph[2][k]
            if arc[-1] is None:connected[arc[1]]=self.site_id[arc[0]]
            else:travel[arc[1]]=float(arc[-1].energy_kwh)
        required=np.full(97,battery.minimum);required[-1]=battery.terminal
        for t in range(95,-1,-1):
            capacity=battery.p_limit*dt*battery.eta_charge if connected[t]>=0 else 0.
            required[t]=max(battery.minimum,required[t+1]+travel[t]-capacity)
        out=np.zeros(self.m);rebound=np.zeros(self.m);soc=battery.initial;unresolved=0.;spent=0.
        if not hasattr(self,'slot_indices'):
            self.slot_indices=[np.flatnonzero(self.times==t) for t in range(96)]
            rewards=np.zeros((4,24,96))
            for t,indices in enumerate(self.slot_indices):
                if len(indices):rewards[:,:,t]=np.maximum(0.,(-self.coeff[:,:,indices,1]*battery.eta_discharge/dt).max(axis=-1))
            maxima=np.maximum.accumulate(rewards[:,:,::-1],axis=-1)[:,:,::-1]
            self.future_energy_price=np.zeros((4,24,96));self.future_energy_price[:,:,:95]=.30*maxima[:,:,1:]
        support=getattr(self,'base_support',np.zeros((4,self.m)))
        reference_all=self.base+support.sum(axis=0)-support[ui]
        for t in range(96):
            soc-=travel[t];spent+=travel[t];unresolved+=max(0.,battery.minimum-soc)
            site=connected[t]
            if site<0:continue
            active=self.slot_indices[t]
            if not len(active):continue
            charge_cap=min(battery.p_limit,max(0.,battery.maximum-soc)/(dt*battery.eta_charge))
            discharge_cap=min(battery.p_limit,max(0.,soc-max(battery.minimum,required[t+1]))*battery.eta_discharge/dt)
            minimum_charge=max(0.,required[t+1]-soc)/(dt*battery.eta_charge)
            energy_price=self.future_energy_price[ui,site,t];reference=reference_all[active]
            vertex_p=self.vertices[:,0];qv=self.vertices[:,1]
            pv=np.where(vertex_p>=0,np.minimum(vertex_p,discharge_cap),-np.minimum(-vertex_p,charge_cap))
            valid=np.ones(len(pv),dtype=bool)
            if minimum_charge>0:valid=(vertex_p<0)&(np.minimum(-vertex_p,charge_cap)+1e-9>=minimum_charge)
            if not valid.any():unresolved+=minimum_charge*dt*battery.eta_charge;continue
            service_matrix=(np.maximum(0.,-pv)[:,None]*self.coeff[ui,site,active,0]+np.maximum(0.,pv)[:,None]*self.coeff[ui,site,active,1]+qv[:,None]*self.coeff[ui,site,active,2])
            energies=np.where(pv>=0,pv*dt/battery.eta_discharge,pv*dt*battery.eta_charge)
            scores=(reference[None,:]+service_matrix).max(axis=1)+energy_price*energies;scores[~valid]=np.inf
            index=int(np.argmin(scores));p=float(pv[index]);q=float(qv[index]);service=service_matrix[index];energy=float(energies[index])
            soc-=energy;out[active]=service
            if p>=0:spent+=energy
            else:rebound[active]=np.maximum(0.,self.coeff[ui,site,active,0]*(-p))
        unresolved+=max(0.,battery.terminal-soc)
        # Charging is already in the signed service vector. Record its risk
        # separately without adding it twice to the minimax prediction.
        self.path_cache[key]=(out,np.zeros(self.m),unresolved,spent)
        if not hasattr(self,'lookahead_diagnostics'):self.lookahead_diagnostics={}
        self.lookahead_diagnostics[key]=dict(terminal_SOC=soc,terminal_recovery_shortfall=max(0.,battery.terminal-soc),
            conservative_required_SOC=required.tolist(),remaining_connected_slots=int(np.count_nonzero(connected>=0)),
            travel_energy=float(travel.sum()),charge_rebound=rebound.tolist(),heuristic_only=True,no_physical_feasibility_pruning=True)
        return out
