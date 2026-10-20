"""Dated IO bindings. Existing AIDC/Actual mathematics is called unchanged."""
import ast
from copy import deepcopy
from pathlib import Path
from types import FunctionType,SimpleNamespace
import inspect
import textwrap
import numpy as np

from .common import ROOT,DOC,read,record,verify,atomic,digest,NotReady
from .config import axis,require_day
from v43_followup.physical_cache import load_current_date_physical_cache as _historical_cache_loader


def clone(function,**overrides):
    answer=FunctionType(function.__code__,dict(function.__globals__,**overrides),function.__name__,function.__defaults__,function.__closure__)
    answer.__kwdefaults__=function.__kwdefaults__;return answer


def day_inputs(day):
    require_day(day);row=next(r for r in read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')['days'] if r['day']==day)
    from .initial_states import READY_INPUT_STATES
    if row['status'] not in READY_INPUT_STATES:raise NotReady('INPUT_NOT_READY:'+day+':'+','.join(row['blockers']))
    verify(list(row['files'].values()))
    from .planning import check_native,REVISION
    check_native(read(row['files']['native']['path']))
    row=deepcopy(row);row['hardware_revision']=REVISION
    return row


def load_aidc(folder,day):
    doc=read(Path(folder)/'AIDC_REFERENCE.json');i=doc['identity']
    if i['day']!=require_day(day):raise ValueError('AIDC_REFERENCE_WRONG_DAY')
    verify(i['source']+[i[k] for k in ('input','windows','reference','physical')])
    native=read(i['input']['path'])
    with np.load(i['physical']['path'],allow_pickle=False) as z:arrays={k:z[k].copy() for k in z.files}
    return dict(bundle=native,planning=arrays,identity=i),doc


def accepted(folder,day):
    payload,doc=load_aidc(folder,day);i=doc['identity']
    freeze=dict(selected_jobs=doc['selected_jobs'],scientific_input={'NATIVE_INPUT.json':i['input'],'WINDOWS.json':i['windows']})
    certificate=dict(planning_freeze=record(Path(folder)/'AIDC_REFERENCE.json'),
        source_freeze=record(DOC/'SCIENTIFIC_FREEZE_MANIFEST.json'))
    return certificate,freeze,payload['bundle'],read(i['windows']['path']),payload['planning']


def export_a(result,request,folder,stage):
    """Same frozen commands/CC4 arrays exported by the existing A materializer."""
    if result.get('PASS') is not True or not 0<=result.get('certified_gap',1)<=.005:raise ValueError('INDEPENDENT_A_ACCEPTANCE_REQUIRED')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False);core=read(result['freeze']['path'])
    with np.load(result['planning']['path'],allow_pickle=False) as z:arrays={k:z[k].copy() for k in z.files}
    known=arrays['known_GPU'];anonymous=arrays['GPU']-known
    if anonymous.min() < -1e-7:raise ValueError('NEGATIVE_ANONYMOUS_GPU')
    arrays.update(known_gpu=known,cc4_served_gpu=np.maximum(anonymous,0.))
    np.savez_compressed(folder/'PLANNING_PHYSICAL.npz',**arrays);sites=list(map(str,arrays['sites']))
    aidc=dict(selected_jobs=core['selected_jobs'],
        CC4_service={str(tuple(map(int,k[6:-1].split(',')))):v for k,v in core['globals'].items() if k.startswith('CC4_x[')},
        CC4_carryout={k[13:-1]:v for k,v in core['globals'].items() if k.startswith('CC4_carryout[')},
        AIDC_P_by_site={s:arrays['PCC_P_kw'][:,j].tolist() for j,s in enumerate(sites)},
        AIDC_Q_by_site={s:arrays['PCC_Q_kvar'][:,j].tolist() for j,s in enumerate(sites)})
    native=read(Path(request['input_folder'])/'NATIVE_INPUT.json')
    identity=dict(day=request['day'],arm='B1' if stage=='A1' else 'B3',stage=stage,
        parent_case_sha=result['freeze']['sha256'],aidc_anchor=digest(aidc),source=request['sources'],
        source_sha=request['source_sha'],input=core['scientific_input']['NATIVE_INPUT.json'],
        windows=core['scientific_input']['WINDOWS.json'],reference=native['reference'],physical=record(folder/'PLANNING_PHYSICAL.npz'),
        parent_acceptance=result['freeze'],FULL_feasible=True,PASS=True,certified_gap=result['certified_gap'],
        global_gap=result['certified_gap'],independent_Global_LB_validated=True,finished_UTC=result['finished_UTC'],
        P2_calls=0,reused_exact_A1=stage=='A1',UB=result['UB'],LB=result['LB'])
    if stage=='A2':identity.update(fixed_M1_plan_sha=result['fixed_M1_plan_sha'],fixed_M1=request['M1_result'],
        M1_UB_LB_transferred=False)
    atomic(folder/'AIDC_REFERENCE.json',dict(identity=identity,**aidc));return folder


class ActualBinding:
    def __init__(self,arm,folder,mess,day):
        self.day=day;self.row=day_inputs(day);self.arm=arm;self.mess=mess;self.folder=Path(folder)
        payload,self.aidc=load_aidc(folder,day);self.arrays=payload['planning'];self.anchor=self.aidc['identity']['aidc_anchor']
        self.aidc['aidc_anchor']=self.anchor;self.freeze=record(self.folder/'AIDC_REFERENCE.json')
        self.bundle=Path(self.row['actual_bundle'])

    def prepare(self,output,*,private_service=True):
        from v43_actual import case
        from v43_actual.vendor.initial_state import verified_initial_sites
        from v43_actual.vendor.known_commands import compile_known_commands
        source=Path(self.row['files']['initial_running_authority']['path'])
        def initialize(output):
            native=read(self.aidc['identity']['input']['path']);plan=read(self.bundle/'PLANNING_INPUT_BUNDLE.json')
            # Generalize only the historical hardcoded population count. Full
            # roster, episode, compatibility and exact capacity replay remain.
            body=textwrap.dedent(inspect.getsource(verified_initial_sites))
            old=' or len(original)!=254'
            if body.count(old)!=1:raise ValueError('DAILY_INITIAL_COUNT_BOUNDARY_DRIFT')
            ns=dict(verified_initial_sites.__globals__);exec(compile(body.replace(old,''),verified_initial_sites.__code__.co_filename,'exec'),ns)
            return ns['verified_initial_sites'](source,native,plan),source
        provider=lambda:accepted(self.folder,self.day)
        args,identity=clone(case.prepare,accepted=provider,initialize=initialize,BUNDLE=self.bundle)(output,private_service=private_service)
        args['arm']=self.arm
        args['known_schedule']=compile_known_commands(self.aidc['selected_jobs'],slot_zero_seconds=args['begin'],
            gpu_by_uid={r['job_uid']:r['GPU_gang'] for r in provider()[2]['known_population']})
        identity.update(day=self.day,arm=self.arm,Final_AIDC_reference=self.freeze,
            initial_sites_assumption='SAME_DATE_EXISTING_AUTHORITY_ONLY',missing_initial_sites='DATED_AUTHORITY_ASSUMPTION',
            Known_commands_sha=digest(args['known_schedule']))
        atomic(Path(output)/'CASE_BINDINGS.json',identity);return args,identity

    def build(self,args,case,output):
        from v43_arms.actual import ArmBinding
        return clone(ArmBinding.build,accepted=lambda:accepted(self.folder,self.day),BUNDLE=self.bundle)(self,args,case,output)


def corrective_binding(arm,folder,mess,day):
    from v43_corrective.binding import CorrectiveBinding
    from .actual_policy import controller_class
    from .config import KNOWN_POLICY
    base=ActualBinding(arm,folder,mess,day)
    self=object.__new__(CorrectiveBinding);self.arm=arm;self.mess=mess;self.base=base
    self.known_window_policy=KNOWN_POLICY;self.controller_class=controller_class(arm,KNOWN_POLICY)
    tree=ast.parse(textwrap.dedent(inspect.getsource(CorrectiveBinding.prepare)))
    function=tree.body[0];kept=[]
    for statement in function.body:
        if isinstance(statement,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('source','target') for t in statement.targets):continue
        if isinstance(statement,ast.If) and ast.unparse(statement.test).startswith('source.exists()'):continue
        kept.append(statement)
    function.body=kept;descriptor=base.row['files']['request_descriptors']['path']
    class Route(ast.NodeTransformer):
        def visit_BinOp(self,node):
            if ast.unparse(node)=="ROOT / 'docs/v43/V43_R1_RECORDED_REQUEST_DESCRIPTOR_CACHE.json'":return ast.Constant(descriptor)
            return self.generic_visit(node)
        def visit_ImportFrom(self,node):
            if node.module=='known_window':return ast.ImportFrom(module='v44.actual_policy',names=[ast.alias('research_assumption','policy_assumption')],level=0)
            return node
    tree=Route().visit(tree);ast.fix_missing_locations(tree);ns=dict(CorrectiveBinding.prepare.__globals__)
    exec(compile(tree,CorrectiveBinding.prepare.__code__.co_filename,'exec'),ns)
    self.prepare=ns['prepare'].__get__(self,CorrectiveBinding)
    return self


def load_current_date_physical_cache(request,fresh_data,*,case_proof,original_loader,check=lambda:None,progress=None):
    """Use PR189's complete-domain verifier on an accepted same-date A1 cache."""
    proof=read(case_proof)
    if proof.get('schema')!='V44_ACCEPTED_A1_PHYSICAL_CACHE':
        return _historical_cache_loader(request,fresh_data,case_proof=case_proof,original_loader=original_loader,check=check,progress=progress)
    verify(proof['sources']+[proof['result'],proof['cache']]);parent=read(proof['result']['path'])
    if (proof['day']!=request['day'] or not parent.get('PASS') or not 0<=parent.get('certified_gap',1)<=.005):
        raise ValueError('DATED_A1_CACHE_ACCEPTANCE_REQUIRED')
    if any(record(Path(request['input_folder'])/name)['sha256']!=row['sha256'] for name,row in proof['inputs'].items()):
        raise ValueError('DATED_A1_CACHE_INPUT_DRIFT')
    return original_loader(request,fresh_data,check=check,progress=progress)
