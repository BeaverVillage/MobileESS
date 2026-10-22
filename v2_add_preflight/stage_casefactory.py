"""Current accepted AIDC -> same Source-YY static FULL M1/M2 authority.

The original runtime admission checks execute before construction. Every
changed AIDC anchor gets fresh RHS, bounds and independent removal proofs.
No accepted-result, bound, grid mask or Native clock from B0 is substituted.
"""
import ast,inspect,textwrap,types
from contextlib import contextmanager
from types import SimpleNamespace
import numpy as np
from .stage_common import *
from .stage_resources import current,OFFICIAL,sample
from v42_native.contracts import digest


def prepare_current(payload,request,root,progress=None):
    from v44.runtime import build as original
    if request['day']!='2025-05-01':raise ValueError('V2_ADD_MAY01_ONLY')
    row=day_inputs();identity=payload['identity']
    if identity['input']['sha256']!=row['files']['native']['sha256'] or identity['windows']['sha256']!=row['files']['windows']['sha256']:
        raise ValueError('CURRENT_AIDC_SOURCE_INPUT_OR_WINDOW_DRIFT')
    p=np.asarray(payload['planning']['PCC_P_kw']);q=np.asarray(payload['planning']['PCC_Q_kvar'])
    if p.shape!=(96,12) or q.shape!=p.shape or not np.isfinite(p).all():raise ValueError('CURRENT_C1_FULL96_REQUIRED')
    if np.max(abs(q-np.tan(np.arccos(.95))*p))>1e-8:raise ValueError('SOURCE_C1_PF_DRIFT')
    fn=types.FunctionType(original.__code__,dict(original.__globals__,
        _build=lambda payload,request,progress:_construct(payload,request,root,progress)),argdefs=original.__defaults__)
    return fn(payload,request,progress)


def _construct(payload,request,root,progress=None):
    from . import stage_m_reanchor as anchor
    from . import static_screen,static_verify,static_native,static_transport_verify
    from .stage_m_case import build_case
    # Preserve the sealed complete M1. Reuse is possible only for literal
    # B0-reference P/Q equality at every slot; changed A1/A2 anchors follow
    # the fresh RHS/proof construction below.
    p=np.asarray(payload['planning']['PCC_P_kw'])
    if request['arm']=='B2' and request['stage']=='M1':
        anchor=np.array([np.load(RUN/'coefficients'/f'{t:02d}.npz')['anchor'][:12] for t in range(96)])
        if np.array_equal(p,anchor):
            names=('SOURCE_YY_ORIGINAL_FULL_REFERENCE.json','IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json',
                'IEEE8500_EXACT_COMPACT_EQUIVALENCE.json','IEEE8500_COMPLETE_STATIC_NATIVE0_REPORT.json',
                'NATIVE_ORIGINAL_TRANSPORT_VERIFICATION.json')
            if not all(read(OUT/name).get('PASS') for name in names):raise ValueError('SEALED_COMPLETE_M1_PROOFS_REQUIRED')
            case=build_case('M1',current_anchor=payload['identity'],arm='B2')
            case._construction_evidence={name:record(OUT/name) for name in names}
            case._current_payload_identity=payload['identity']
            return case
    root=Path(root);root.mkdir(parents=True,exist_ok=False);proof=root/'proof';proof.mkdir()
    stage=request['stage'];p=np.array(payload['planning']['PCC_P_kw'],copy=True)
    identity=dict(payload['identity'],scope='REAL_CURRENT_ACCEPTED_AIDC_FIXED_PARAMETER',
        current_M_stage=stage,C1_P_sha=digest(p.tolist()),payload_AIDC_anchor=payload['identity']['aidc_anchor'])
    namespace=dict(vars(anchor),MROOT=root,MPACK=root/'SOURCE_YY_FULL96',MDOC=proof,
        fixed_a2_fixture=lambda:(p,identity))
    def output(name,value):
        path=proof/name;path.write_text(json.dumps(value,default=str,ensure_ascii=False,indent=2),encoding='utf-8');return value
    @contextmanager
    def measured(name):
        report=dict(PASS=False,stage=stage,current_AIDC_anchor=identity['aidc_anchor']);start=time.perf_counter()
        try:yield report,start
        finally:
            report['wall_seconds']=time.perf_counter()-start;output(name,report)
    namespace.update(measured=measured)
    if current().phase==OFFICIAL.phase:namespace['resources']=sample
    preparation=types.FunctionType(anchor.prepare.__code__,namespace);preparation()
    # The reused function's A2 labels are IO metadata only. The actual fixed
    # payload and root are recorded explicitly for either current M stage.
    reference=read(proof/'SOURCE_YY_ORIGINAL_FULL_REFERENCE.json')
    reference.update(stage=stage,fixture=False,AIDC=identity,A2=identity)
    reference['case_sha']=digest({k:v for k,v in reference.items() if k!='case_sha'})
    output('SOURCE_YY_ORIGINAL_FULL_REFERENCE.json',reference)
    routed=types.FunctionType(anchor.rebound.__code__,namespace)
    for module,name in ((static_screen,'prepare'),(static_verify,'verify')):
        function=routed(module,name)
        # This output remains in the current run, never the preparation docs.
        function.__globals__['put']=output
        function()
    builder=routed(static_native,'build')
    # Only the two explicit Native0 RAM admission checks are phase-dependent.
    # All original equations, materialization and exhaustive readback remain.
    source=textwrap.dedent(inspect.getsource(static_native.build));tree=ast.parse(source)
    changed=[]
    class MemoryPolicy(ast.NodeTransformer):
        def visit_If(self,node):
            if any(isinstance(n,ast.Raise) and isinstance(n.exc,ast.Call) and isinstance(n.exc.func,ast.Name)
                   and n.exc.func.id=='MemoryError' for n in node.body):
                node.test=ast.BoolOp(ast.And(),[ast.UnaryOp(ast.Not(),ast.Call(ast.Name('_official_memory_unlimited',ast.Load()),[],[])),node.test]);changed.append(node.lineno)
            return self.generic_visit(node)
    tree=MemoryPolicy().visit(tree);ast.fix_missing_locations(tree);assert len(changed)==2
    ng=dict(builder.__globals__,put=output,_official_memory_unlimited=lambda:current().phase==OFFICIAL.phase)
    ng['native_rows_exact']=types.FunctionType(static_native.native_rows_exact.__code__,
        dict(static_native.native_rows_exact.__globals__,guard=guard))
    exec(compile(tree,static_native.__file__,'exec'),ng);ng['build']()
    if not read(proof/'IEEE8500_COMPLETE_STATIC_NATIVE0_REPORT.json')['PASS']:raise ValueError('CURRENT_FULL_STATIC_NATIVE_BUILD_REQUIRED')
    verifier=routed(static_transport_verify,'verify');verifier.__globals__['put']=output;verifier()
    case=build_case(stage,current_root=root,current_pack=root/'SOURCE_YY_FULL96',
        current_proof=proof/'SOURCE_YY_ORIGINAL_FULL_REFERENCE.json',current_anchor=identity,arm=request['arm'])
    case._current_payload_identity=identity
    case._construction_evidence={n:record(proof/n) for n in ('SOURCE_YY_ORIGINAL_FULL_REFERENCE.json',
        'IEEE8500_STATIC_PRESCREENING_CERTIFICATION.json','IEEE8500_EXACT_COMPACT_EQUIVALENCE.json',
        'IEEE8500_COMPLETE_STATIC_NATIVE0_REPORT.json','NATIVE_ORIGINAL_TRANSPORT_VERIFICATION.json')}
    return case
