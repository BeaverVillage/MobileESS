"""Current canonical measurement API, separate from immutable event archives.

The archival CorrectedPhysical reducer retained the all-event safety envelope.
Consumers requiring r043 slot objectives must use this class or the equivalent
saved-event projection. No new optimization/integration is enabled here.
"""
import numpy as np
from .correction import CorrectedPhysical

class CanonicalTimePhysical(CorrectedPhysical):
    def measure(self,role,t,beta,**kwargs):
        result=super().measure(role,t,beta,**kwargs)
        if self.mode!='TIME':return result
        row=self.event_rows[-1].copy();arrays=self.event_arrays[-1];state=self.event_states[-1]
        row['measurement_scope']='V44_CANONICAL_SETTLED_SLOT'
        row['all_event_security_PASS']=all(r['physics_PASS'] for r in self.event_rows)
        row['event_envelope_rho']=max(r['rho_global'] for r in self.event_rows)
        row['event_envelope_Vmin']=min(r['Vmin'] for r in self.event_rows)
        row['event_envelope_Vmax']=max(r['Vmax'] for r in self.event_rows)
        # The clock advanced to its end-boundary without solving. Circuit
        # readbacks still represent exactly the final native solved state.
        ports=[]
        for meta in self.port_meta:
            self.d.Circuit.SetActiveElement(self.pccs[meta['site']]['element'])
            current=np.asarray(self.d.CktElement.Currents()).reshape(-1,2)
            amps=np.linalg.norm(current,axis=1);pq=np.asarray(self.d.CktElement.Powers()).reshape(-1,2).sum(0)
            ports.append(dict(site=meta['site'],P_kw=float(pq[0]),Q_kvar=float(pq[1]),current_max_A=float(amps.max()),
                current_loading=float(amps.max()/meta['interface_current_A']),apparent_kva=float(np.linalg.norm(pq)),interface_loading=float(np.linalg.norm(pq)/600)))
        return row,arrays,state,ports
