"""Sequential stage machine, atomic immutable receipts, fail-closed resume."""
import json,os,uuid,copy
from pathlib import Path
from .authority import authority_sha,SCIENTIFIC,digest,file_sha,canonical
from .plan import build_plan
from .firewall import PlanningReads
from .state import validate_state,freeze_state

def atomic(path,value,immutable=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('xb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
    try:
        if immutable:os.link(temp,path) # Exclusive atomic publication; never overwrite.
        else:os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()

class CampaignEngine:
    def __init__(self,root,*,source_hashes,plan=None,mode='DRY_RUN'):
        if mode not in ('DRY_RUN','SYNTHETIC'):raise PermissionError('PRODUCTION_EXECUTION_DISABLED_IN_THIS_TASK')
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.plan=plan or build_plan();self.nodes={n['id']:n for n in self.plan['nodes']};self.mode=mode
        if mode=='SYNTHETIC' and len(self.plan['days'])>2:raise PermissionError('BOUNDED_FIXTURE_MAX_TWO_DAYS')
        self.identity=dict(authority_sha256=authority_sha(),scientific_contract_sha256=digest(SCIENTIFIC),source_hashes=source_hashes,plan_sha256=digest(self.plan),mode=mode)
        self.path=self.root/'STAGE_LEDGER.json';self.active_stage=None;self.lock=None;self.read_audits=[]
        if self.path.exists():
            ledger=json.loads(self.path.read_text(encoding='utf8'))
            if ledger['identity']!=self.identity:raise ValueError('RESUME_AUTHORITY_SOURCE_OR_CONTRACT_MISMATCH')
            self.ledger=ledger
            if set(ledger['stages'])!=set(self.nodes) or any(row.get('status') not in ('PENDING','RUNNING','ACCEPTED','FAILED') for row in ledger['stages'].values()):raise ValueError('RESUME_STAGE_SCHEMA_MISMATCH')
            pending_seen=False
            for node in self.plan['nodes']:
                status=ledger['stages'][node['id']]['status']
                if status!='ACCEPTED':pending_seen=True
                elif pending_seen:raise ValueError('RESUME_ACCEPTED_STAGES_MUST_BE_CAUSAL_PREFIX')
            for sid,row in ledger['stages'].items():
                if row['status']=='ACCEPTED':self.accepted(sid)
            if any(row['status'] in ('RUNNING','FAILED') for row in ledger['stages'].values()):raise ValueError('PARTIAL_OR_FAILED_RUN_RESUME_FORBIDDEN')
        else:
            self.ledger=dict(identity=self.identity,stages={sid:dict(status='PENDING') for sid in self.nodes});atomic(self.path,self.ledger)
    def accepted(self,sid):
        row=self.ledger['stages'][sid]
        if row['status']!='ACCEPTED':raise ValueError('DEPENDENCY_NOT_ACCEPTED:'+sid)
        path=self.root/row['freeze_path']
        if not path.resolve().is_relative_to(self.root.resolve()):raise ValueError('FREEZE_OUTSIDE_LEDGER_ROOT')
        if file_sha(path)!=row['freeze_sha256']:raise ValueError('IMMUTABLE_FREEZE_SHA_MISMATCH')
        payload=json.loads(path.read_text(encoding='utf8'))
        if payload['identity']!=self.identity or not payload['validated'] or not payload['complete']:raise ValueError('UNVALIDATED_OR_INCOMPLETE_RESUME')
        if payload['stage']!=sid:raise ValueError('FREEZE_STAGE_IDENTITY_MISMATCH')
        self.validate_data(self.nodes[sid],payload['data'])
        return payload
    def day_sources(self,node):
        sources=self.identity['source_hashes']
        return sources.get(node['day'],sources)
    def validate_data(self,node,data):
        if node['planning']:
            audit=data.get('certificate',{})
            if not all(audit.get(k) is True for k in ('scientifically_accepted','NUMERICAL_AUDIT_PASS','PHYSICAL_AUDIT_PASS')):raise ValueError('PLANNING_SCIENTIFIC_ACCEPTANCE_REQUIRED')
            state=data['Planning_state']
        elif node['stage']=='PLANNING_FREEZE':
            state=data['state']
            if data['state_sha256']!=digest(state):raise ValueError('PLANNING_STATE_SHA_MISMATCH')
        else:
            if node['stage']=='ACTUAL' and data.get('Actual_complete') is not True:raise ValueError('INCOMPLETE_ACTUAL')
            if node['stage']=='FRESH_AC' and data.get('Fresh_AC_complete') is not True:raise ValueError('INCOMPLETE_FRESH_AC')
            return
        validate_state(state)
        if state['authority_sha256']!=self.identity['authority_sha256'] or state['D1_source_hashes']!=self.day_sources(node):raise ValueError('PLANNING_CAUSAL_AUTHORITY_MISMATCH')
    def next_stage(self):
        for node in self.plan['nodes']:
            status=self.ledger['stages'][node['id']]['status']
            if status in ('FAILED','RUNNING'):raise ValueError('SCIENTIFIC_FAILURE_OR_PARTIAL_STATE_STOP')
            if status=='PENDING':return node
        return None
    def begin(self,sid):
        if self.mode!='SYNTHETIC':raise PermissionError('PRODUCTION_EXECUTION_DISABLED_IN_THIS_TASK')
        if self.active_stage is not None:raise RuntimeError('ONE_STAGE_WORKER_ONLY')
        expected=self.next_stage()
        if expected is None or expected['id']!=sid:raise ValueError('CAMPAIGN_ORDER_VIOLATION')
        for dependency in self.nodes[sid]['required_accepted_freezes']:self.accepted(dependency)
        self.lock=(self.root/'SINGLE_WORKER_LEASE').open('x',encoding='utf8');self.lock.write(sid);self.lock.flush()
        self.active_stage=sid;self.ledger['stages'][sid]=dict(status='RUNNING');atomic(self.path,self.ledger)
    def finish(self,sid,data,*,validated,complete=True):
        if self.active_stage!=sid or self.ledger['stages'][sid]['status']!='RUNNING':raise ValueError('STAGE_NOT_RUNNING')
        if not validated or not complete:self.fail(sid,'UNVALIDATED_OR_INCOMPLETE');raise ValueError('ACCEPTANCE_GATE_FAILED')
        node=self.nodes[sid]
        try:self.validate_data(node,data)
        except BaseException as error:self.fail(sid,str(error));raise
        relative=Path('freezes')/(digest(sid)+'.json')
        payload=dict(stage=sid,identity=self.identity,validated=True,complete=True,producer_phase='PLANNING' if node['planning'] or node['stage']=='PLANNING_FREEZE' else node['stage'],data=data,synthetic_only=True)
        atomic(self.root/relative,payload,immutable=True)
        self.ledger['stages'][sid]=dict(status='ACCEPTED',freeze_path=relative.as_posix(),freeze_sha256=file_sha(self.root/relative));atomic(self.path,self.ledger);self._release()
    def fail(self,sid,reason):
        self.ledger['stages'][sid]=dict(status='FAILED',reason=reason);atomic(self.path,self.ledger);self._release()
    def _release(self):
        if self.lock:self.lock.close();self.lock=None
        lease=self.root/'SINGLE_WORKER_LEASE'
        if lease.exists():lease.unlink()
        self.active_stage=None
    def planning_entries(self,sid,external):
        node=self.nodes[sid];entries=list(external)
        kinds=[entry['kind'] for entry in external]
        if node['planning'] and (len(kinds)!=3 or set(kinds)!={'D1_SOURCE','FORECAST','RUNTIME_CC4'}):raise PermissionError('EXACT_D1_FORECAST_CC4_WHITELIST_REQUIRED')
        for entry in external:
            if entry['kind'] not in node['allowed_input_kinds'] or self.day_sources(node).get(entry['key'])!=entry['sha256']:raise PermissionError('UNREGISTERED_PLANNING_SOURCE')
        for dep in node['Planning_dependencies']:
            receipt=self.accepted(dep)
            if receipt['producer_phase']!='PLANNING':raise PermissionError('ACTUAL_DEPENDENCY_FOR_PLANNING')
            row=self.ledger['stages'][dep]
            entries.append(dict(key=dep,path=str(self.root/row['freeze_path']),sha256=row['freeze_sha256'],kind='PREVIOUS_PLANNING_FREEZE' if '/PLANNING_FREEZE' in dep else 'CURRENT_PLANNING_FREEZE',producer_phase='PLANNING'))
        return entries
    def synthetic_stage(self,sid,handler,*,entries,issue_time):
        self.begin(sid);node=self.nodes[sid]
        try:
            if node['planning'] or node['stage']=='PLANNING_FREEZE':
                guard=PlanningReads(self.planning_entries(sid,entries),issue_time=issue_time)
                with guard:data=handler(node,guard.loaded,dict(predecessor_accepted=True))
                self.read_audits.append(dict(stage=sid,**guard.receipt))
                if node['planning']:
                    state=data['Planning_state'];d1=guard.loaded['D1']
                    if state['population_sha256']!=d1['population_sha256'] or set(state['aidc']['decisions'])!=set(d1['initial_AIDC']['decisions']):raise ValueError('COMMON_PHYSICAL_POPULATION_DRIFT')
                    transfer=handoff(node,{dep:guard.loaded[dep] for dep in node['Planning_dependencies']})
                    for key,value in (transfer['fixed_counterpart'] or {}).items():
                        if state[key.lower()]!=value:raise ValueError('FIXED_COUNTERPART_CHANGED')
                    if node['arm'] in ('B0','B2') and state['aidc']!=d1['initial_AIDC']:raise ValueError('AIDC_GRID_FLEXIBILITY_OFF')
                    if node['arm'] in ('B0','B1') and state['mess']!=d1['initial_MESS']:raise ValueError('MESS_OFF')
            else:data=handler(node,{},dict(predecessor_accepted=True))
            self.finish(sid,data,validated=True,complete=True)
        except BaseException as error:
            if self.active_stage==sid:self.fail(sid,str(error))
            raise
    def production_execute(self,*args,**kwargs):raise PermissionError('MAY_PRODUCTION_NOT_AUTHORIZED_THIS_TASK')

def handoff(node,planning_payloads):
    """Only declared Planning payloads; Actual/Fresh completion stays outside."""
    expected=set(node['Planning_dependencies'])
    if set(planning_payloads)!=expected:raise PermissionError('UNDECLARED_OR_ACTUAL_LOOP_SEED')
    if any(p.get('producer_phase')!='PLANNING' or p.get('validated') is not True or p.get('complete') is not True for p in planning_payloads.values()):raise PermissionError('UNVALIDATED_OR_ACTUAL_HANDOFF')
    states={sid:(payload['data'].get('state') or payload['data'].get('Planning_state')) for sid,payload in planning_payloads.items()}
    for state in states.values():validate_state(state)
    fixed=None;warm=None
    if node['stage']=='A1' and node['loop'] and node['loop']>1:
        previous=next(iter(states.values()));fixed=dict(MESS=previous['mess']);warm=dict(AIDC_candidate=previous['aidc'],validated=True,AIDC_fixed=False)
    elif node['stage']=='M1' and node['loop']:fixed=dict(AIDC=next(iter(states.values()))['aidc'])
    elif node['stage']=='A2':fixed=dict(MESS=next(iter(states.values()))['mess'])
    elif node['stage']=='M2':
        a2=next(s for sid,s in states.items() if sid.endswith('/A2'));m1=next(s for sid,s in states.items() if sid.endswith('/M1'))
        fixed=dict(AIDC=a2['aidc']);warm=dict(MESS_candidate=m1['mess'],validated=True,route_fixed=False)
    return copy.deepcopy(dict(fixed_counterpart=fixed,warm_start=warm,free_decisions=node.get('free_decisions',[]),Actual_values_included=False))

def final_planning_state(node,loaded):
    """Assemble final A2/M2 using only declared, accepted Planning receipts."""
    payloads={sid:loaded[sid] for sid in node['Planning_dependencies']}
    if any(p['producer_phase']!='PLANNING' or not p['validated'] or not p['complete'] for p in payloads.values()):raise PermissionError('FINAL_FREEZE_PLANNING_ONLY')
    if node['group'].startswith('B3_'):
        a2=next(p['data']['Planning_state'] for sid,p in payloads.items() if sid.endswith('/A2'))
        m2=next(p['data']['Planning_state'] for sid,p in payloads.items() if sid.endswith('/M2'))
        state=copy.deepcopy(m2);state['aidc']=copy.deepcopy(a2['aidc'])
        if any(a2[k]!=m2[k] for k in ('authority_sha256','D1_source_hashes','population_sha256')):raise ValueError('FINAL_POPULATION_OR_AUTHORITY_DRIFT')
    else:state=next(iter(payloads.values()))['data']['Planning_state']
    return freeze_state(state,group=node['group'],day=node['day'])
