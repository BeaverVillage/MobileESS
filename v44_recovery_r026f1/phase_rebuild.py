"""Stage-local exact input caches; native solves and full point replays remain live."""
from collections import OrderedDict
from contextlib import contextmanager, ExitStack
from functools import wraps
from pathlib import Path
from time import perf_counter
from types import FunctionType
from unittest.mock import patch
import hashlib, inspect, pickle, textwrap


def encoded(value):
    return pickle.dumps(value, protocol=5)


def key(value):
    return hashlib.sha256(encoded(value)).digest()


def content_key(value):
    """Hash acyclic proof values independently of Python object sharing."""
    digest=hashlib.sha256()
    class Sink:
        def write(self,raw):digest.update(raw);return memoryview(raw).nbytes
    serializer=pickle.Pickler(Sink(),protocol=5)
    serializer.fast=True
    serializer.dump(value)
    return digest.digest()


class ExactCache:
    """Own serialized values so consumers cannot mutate an admitted cache entry."""
    def __init__(self, limit):
        self.limit=limit;self.size=0;self.values=OrderedDict();self.hits=0;self.misses=0
        self.original_seconds=0.;self.lookup_seconds=0.;self.evictions=0

    def call(self, identity, compute):
        start=perf_counter()
        if identity in self.values:
            self.hits+=1;raw=self.values.pop(identity);self.values[identity]=raw
            value=pickle.loads(raw);self.lookup_seconds+=perf_counter()-start;return value
        self.misses+=1;t=perf_counter();value=compute();self.original_seconds+=perf_counter()-t
        raw=encoded(value)
        if len(raw)<=self.limit:
            while self.size+len(raw)>self.limit:
                _,old=self.values.popitem(last=False);self.size-=len(old);self.evictions+=1
            self.values[identity]=raw;self.size+=len(raw)
        self.lookup_seconds+=perf_counter()-start
        return value

    def report(self):
        return dict(hits=self.hits,misses=self.misses,entries=len(self.values),bytes=self.size,
                    limit=self.limit,evictions=self.evictions,original_seconds=self.original_seconds,
                    total_seconds=self.lookup_seconds)



class Rebuild:
    def __init__(self):
        from v42_a_stage_compact_rowgen import assembly
        from v42_a_stage_phase1 import backend
        self.context=None;self.builds=0;self.wall_seconds=0.;self.ledger_rebuilds=0
        self.blocks=ExactCache(512*1024*1024);self.proofs=ExactCache(32*1024*1024)
        self.original_block=backend.native_block;self.original_verify=assembly.verify
        from .sparse_couplings import CouplingParts,compile_reference
        self.assemble=compile_reference(backend.assemble_original,self.native_block)

        ns=dict(vars(assembly),assemble_original=self.assemble,native_block=self.native_block,verify=self.verify,CouplingParts=CouplingParts)
        self.build_original=assembly.build
        # Only the O(classes * columns) index is transformed. Exact local proof
        # reuse below removes repeated expensive Fraction signature construction.
        source=textwrap.dedent(inspect.getsource(assembly.build))
        old="    ids={k:sorted(j for j,v in rowned.items() if v==k) for k in data[7]['classes']}"
        new="    ids={k:[] for k in data[7]['classes']}\n    for j,k in rowned.items():ids[k].append(j)\n    for cols in ids.values():cols.sort()\n    indexed_units=defaultdict(list)\n    member_class={u:k for k,us in data[7]['classes'].items() for u in us}\n    for unit in rdesc['units']:indexed_units[member_class[unit['uid']]].append(unit)"
        assert source.count(old)==1,'R026F1_BUILD_COLUMN_INDEX_SOURCE_DRIFT'
        source=source.replace(old,new)
        old="        runits=[shift(u,-first) for u in rdesc['units'] if u['uid'] in members]"
        assert source.count(old)==1,'R026F1_BUILD_UNIT_INDEX_SOURCE_DRIFT'
        source=source.replace(old,"        runits=[shift(u,-first) for u in indexed_units[key]]")
        from .sparse_couplings import compact_source
        source=compact_source(source)
        exec(compile(source,__file__+'.build.generated','exec'),ns)
        self.compiled=ns['build']

    def native_block(self,data,class_id,graph,coupling_axes,*,averaged=True):
        if self.context is None:raise RuntimeError('R026F1_BLOCK_OUTSIDE_REBUILD')
        identity=(self.context,class_id,bool(averaged),key((graph,tuple(coupling_axes))))
        return self.blocks.call(identity,lambda:self.original_block(data,class_id,graph,coupling_axes,averaged=averaged))

    def verify(self,*args):
        # Hash every byte of all proof inputs on every call, including descriptor
        # expressions, sparse indices/data, boxes, row senses/RHS and cardinality.
        return self.proofs.call(content_key(args),lambda:self.original_verify(*args))

    def update_graph(self,data,domains,class_id,graph):
        graphs=dict(data[5])
        for member in data[7]['classes'][class_id]:graphs[member]=graph
        return (*data[:5],graphs,data[6],data[7]),None

    def build(self,base,grows,n,axes,data,domains,ledger,candidates):
        from v42_a_stage_domain_v2.active import _ledger
        start=perf_counter();previous=self.context
        # Full static data bytes are checked once per rebuild; graph bytes are
        # checked separately for each class. No cross-stage/date cache exists.
        self.context=key((data[:5],data[6:]))
        try:
            if ledger is None:
                ledger=_ledger(data,domains,{k:{} for k in data[7]['classes']});self.ledger_rebuilds+=1
            return self.compiled(base,grows,n,axes,data,domains,ledger,candidates)
        finally:self.context=previous;self.builds+=1;self.wall_seconds+=perf_counter()-start

    def report(self):
        return dict(builds=self.builds,wall_seconds=self.wall_seconds,ledger_rebuilds=self.ledger_rebuilds,
                    native_blocks=self.blocks.report(),exact_projection_proofs=self.proofs.report(),
                    native_solve_results_cached=False,raw_points_cached=False,full_point_replays_skipped=0,
                    axis_mapping='ONE_VECTOR_PER_REFERENCE_AND_COMPACT_BUILD',global_coupling_CSR='ONE_COMBINED_LOCAL_COUPLING_BLOCK_PER_BUILD',
                    cache_scope='ONE_A_STAGE',key_policy='FULL_STATIC_INPUT_BYTES_GRAPH_BYTES_FULL_PROJECTION_INPUT_BYTES')


@contextmanager
def stage_scope(request):
    from v44.common import atomic,now
    from v42_a_stage_compact_rowgen import assembly
    from v42_a_stage_canary import phase,prepare
    from v42_may_campaign_native90 import a_stage
    from .a2_continue import FrozenWeights
    from .phase_stability import StableNative,stabilized_phase,policy,observe,annotated_atomic
    from .row_generation import compile_phase,exact_phi
    from .phase_speed import compile_attribution,Profile
    from v42_a_stage_phase1 import core
    from v42_a_stage_early import progress
    from v42_a_stage_acceptance import native as acceptance_native
    import gurobipy as gp
    stable=(request.get('stage')=='A2' and request.get('arm') in ('B1','B3')) or (request.get('stage')=='A1' and request.get('arm')=='B1')
    row_generation=stable
    output=Path(request.get('output',Path(request['root'])/'OUTPUT'))
    profile=Profile(output)
    memo=Rebuild();original=assembly.build;original_group=a_stage.group
    def group(module,names,**routing):
        namespace=original_group(module,names,**routing)
        if module is phase:
            original_run=compile_phase(module.run,namespace) if row_generation else stabilized_phase(module.run,namespace) if stable else namespace['run']
            from .voltage_policy import ACTIVE
            conditional=ACTIVE.get() if request.get('stage')=='A2' else None
            if conditional is not None:
                from .conditional_voltage import compile_conditional
                original_run=compile_conditional(original_run,namespace,conditional)
            def run(native,state,day,certified_zero_point=None):
                frozen=FrozenWeights(state['reference'],state['grows'],None)
                if conditional is not None:conditional.frozen_weights=frozen
                namespace.update(elastic_master=frozen.elastic_master,restricted=frozen.restricted)
                if row_generation:
                    namespace['analyze']=compile_attribution(module.analyze)
                    if conditional is not None:
                        conditional.bind(state)
                        namespace['analyze']=conditional.wrap_analyze(namespace['analyze'])
                        namespace['targeted']=conditional.wrap_targeted(namespace['targeted'])
                    for name in ('analyze','targeted','full_pricing','build','expanded_point','inclusion_witness','compact_inverse','certified_separate','elastic_master'):
                        namespace[name]=profile.wrap(name,namespace[name])
                from .phase_limit import phase_scope
                with phase_scope(native,output) as limited:
                    return original_run(StableNative(limited) if stable else limited,state,day,certified_zero_point)
            namespace['run']=run
        return namespace
    with ExitStack() as stack:
        stack.enter_context(profile)
        for module in (assembly,phase,prepare):
            if getattr(module,'build',None) is original:stack.enter_context(patch.object(module,'build',memo.build))
        stack.enter_context(patch.object(phase,'update_graph',memo.update_graph))
        stack.enter_context(patch.object(a_stage,'group',group))
        if stable:
            stack.enter_context(patch.object(acceptance_native,'apply_policy',policy(acceptance_native.apply_policy)))
            stack.enter_context(patch.object(acceptance_native,'atomic',annotated_atomic(acceptance_native.atomic)))
            stack.enter_context(patch.object(gp.Model,'optimize',observe(gp.Model.optimize)))
        if row_generation:
            stack.enter_context(patch.object(core,'phase_objective',exact_phi))
            stack.enter_context(patch.object(progress,'phase_objective',exact_phi))
        try:yield memo
        finally:
            output=Path(request.get('output',Path(request['root'])/'OUTPUT'))
            if output.exists():atomic(output/'R026F1_PHASE_REBUILD_PROFILE.json',dict(UTC=now(),**memo.report()))


@contextmanager
def install():
    from v44 import worker
    original=worker.a_stage
    @wraps(original)
    def routed(request,*args,**kwargs):
        if request.get('arm') in ('B0','B1','B3'):
            with stage_scope(request):return original(request,*args,**kwargs)
        return original(request,*args,**kwargs)
    with patch.object(worker,'a_stage',routed):yield
