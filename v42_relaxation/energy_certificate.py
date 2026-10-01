"""Independent interval energy cut certificate extracted from the IIS."""
from .diagnostics import *

def run():
    iis=read(OUT/'ROOT_ENERGY_DISAGGREGATION_IIS.json')
    v,_,_=solution();_,_,_,sites,initial,routes,b=inputs();arcs=topology(sites,routes)
    nodes=defaultdict(set)
    for row in iis.get('rows',[]):
        if row['name'].startswith('G_node['):
            unit,site,t=row['name'][7:-1].rsplit(',',2);nodes[unit].add((site,int(t)))
    certificates=[]
    for unit,group in nodes.items():
        outmass=inmass=rhs=0.;incoming_travel_loss=0.
        for k,(s,t,d,e,r) in enumerate(arcs):
            depart=(s,t) in group;arrive=(d,e) in group;x=v[f'arc[{unit},{k}]']
            if depart and not arrive:outmass+=x
            if arrive and not depart:inmass+=x
            if arrive:
                delta=-r.energy_kwh*x if r else b.dt_hours*(b.eta_charge*v[f'Pch[{unit},{s},{t}]']-v[f'Pdis[{unit},{s},{t}]']/b.eta_discharge)
                rhs+=delta
                if r:incoming_travel_loss-=delta
        lo=b.minimum*outmass-b.maximum*inmass
        hi=b.maximum*outmass-b.minimum*inmass
        violation=max(lo-rhs,rhs-hi,0.)
        certificates.append(dict(MESS=unit,nodes=sorted(group),out_boundary_mass=outmass,in_boundary_mass=inmass,
            sum_arrival_energy_changes_kWh=rhs,minimum_boundary_net_G_kWh=lo,maximum_boundary_net_G_kWh=hi,
            contradiction_margin_kWh=violation,incoming_travel_loss_kWh=incoming_travel_loss,
            certified=violation>TOL,
            derivation='Sum node conservation over listed nodes; internal G cancels. Boundary G bounds require minimum <= sum arrival changes <= maximum.'))
    dump('ROOT_ENERGY_INTERVAL_CERTIFICATE.json',dict(certificates=certificates,
        independent_arithmetic_certificate=any(c['certified'] for c in certificates),tolerance=TOL,
        source_sha256=sha(OUT/'BASE_ROOT_LP_SOLUTION.npz')))
    print('INDEPENDENT ENERGY CERTIFICATE',certificates,flush=True)

if __name__=='__main__':run()
