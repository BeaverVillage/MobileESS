"""Deterministic synthetic tests only; never a native data/provider fallback."""
from .mess import Battery,RouteArc,solve as solve_mess
from .aidc import solve as solve_aidc
from .service import boundary
from .contracts import Deadline
from v42_job_capability import Job,Resources
from v42_native.voltage import PLANNING_LOWER_SQUARED, PLANNING_UPPER_SQUARED
import gurobipy as gp


def fixture():
    sites=('A','B');H=8
    battery=Battery(0,20,10,10,4,5,.95,.95)
    routes=(RouteArc('AB','A','B',2,3,3,.1,'a'*64),RouteArc('BA','B','A',6,7,7,.1,'a'*64))
    return sites,H,battery,routes


def mess_grid(model,p,q):
    rho=model.addVar(lb=0,ub=1,name='rho_max')
    for (site,t) in p:
        base=.9 if site=='B' and t>=4 else .7 if site=='A' and t<4 else .4
        model.addConstr(base-.02*p[site,t]-.01*q[site,t]<=rho,name='line_thermal')
        model.addConstr(.1+.01*p[site,t]<=1,name='transformer_current')
        model.addConstr(1+.001*q[site,t]>=PLANNING_LOWER_SQUARED,name='voltage_lower')
        model.addConstr(1+.001*q[site,t]<=PLANNING_UPPER_SQUARED,name='voltage_upper')
    return [('rho',rho),('reserve_shortfall',gp.LinExpr(0))]


def aidc_fixture():
    job=Job('job','PENDING',0,0,0,'A',6,4,qos='standby',initial_sites=('A','B'),
        checkpoint_authorized=True,duration_authority='EXPLICIT_TEST_SERVICE',standby_candidate_authorized=True)
    r=Resources({'A':8,'B':8},{'A':(8,),'B':(8,)},{('AB',t):640 for t in range(8)},
        {('A','B'):('AB',),('B','A'):('AB',)},8,80,{}, {}, {})
    b=boundary(job,(0,1),'a'*64,'b'*64,H=8)
    return {job.uid:job},{job.uid:b},r


def aidc_grid(model,gpu):
    rho=model.addVar(lb=0,ub=1,name='rho_max')
    for (s,t),v in gpu.items():model.addConstr(.2+.05*v<=rho,name='line_thermal')
    return [('rho',rho),('reserve_shortfall',gp.LinExpr(0))]


def worker(context,payload):
    stage=payload['stage'];deadline=Deadline(stage,min(20.,context.remaining));incumbent=payload.get('warm_start')
    if stage.startswith('A'):
        jobs,b,r=aidc_fixture();result,receipt=solve_aidc(stage,deadline,jobs,b,r,aidc_grid,incumbent,
            seconds_authority={u:j.service_slots*900 for u,j in jobs.items()},progress=context.progress)
    else:
        sites,H,b,routes=fixture();result,receipt=solve_mess(stage,deadline,sites,{'M':sites[0]},routes,b,H,mess_grid,incumbent,progress=context.progress)
    if result:context.publish(dict(**result,receipt=receipt,scope='SYNTHETIC_ONLY'))


def validator(candidate,payload):
    return {'PASS':candidate['scope']=='SYNTHETIC_ONLY' and candidate['physical_audit']['PASS']}
