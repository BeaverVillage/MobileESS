"""Route the existing corrective driver to new SVR11 Current AC authority."""
from pathlib import Path
from types import SimpleNamespace
import ast
import inspect
import textwrap
from .common import ROOT,read,record,verify,NotReady
from functools import partial
from .svr11_hardware import HARDWARE
from .svr11_ac import SVR11CurrentAC


def certificate(path):
    if path is None or not Path(path).is_file():raise NotReady('SVR11_NEW_CURRENT_AC_CERTIFICATE_REQUIRED')
    c=read(path)
    if (not c.get('PASS') or c['hardware']!=record(HARDWARE/'HARDWARE.json')
            or c.get('source_7reg_certificate_reused') is not False or c.get('RegControl_count')!=40
            or c.get('Native_TIME_prefix_verified') is not True):
        raise PermissionError('SVR11_CURRENT_AC_SOURCE_HARDWARE_CERTIFICATE_DRIFT')
    verify(c['sources']+[c['hardware'],c['real_prefix_evidence']])
    return c


def corrective_driver(original_run,shared,bindings,day_start):
    import v43_corrective.compare as original
    tree=ast.parse(textwrap.dedent(inspect.getsource(original_run)));gate=[0];day=[0]
    class Route(ast.NodeTransformer):
        def visit_If(self,node):
            if ast.unparse(node.test)=="ac_mode == 'FAST'":
                gate[0]+=1
                return ast.Expr(ast.Call(ast.Name('_svr11_certificate',ast.Load()),[ast.Name('ac_certification',ast.Load())],[]))
            return self.generic_visit(node)
        def visit_Constant(self,node):
            if node.value==1746021600.:
                node.value=day_start;day[0]+=1
            elif node.value=='REAL_V43_R1_FLEX30_CORRECTIVE':node.value='REAL_V44_SVR11_R1_FLEX30_CORRECTIVE'
            return node
    tree=Route().visit(tree);ast.fix_missing_locations(tree)
    if gate!=[1] or day!=[1]:raise ValueError('V43_CORRECTIVE_SVR11_ADAPTER_BOUNDARY_DRIFT')
    cls=partial(SVR11CurrentAC,arm=bindings.arm)
    ns=dict(original_run.__globals__,original=shared,CorrectiveBinding=lambda *a,**kw:bindings,
        CertifiedPrefixAC=SVR11CurrentAC,FullPrefixReferenceAC=SVR11CurrentAC,ShadowCertifiedPrefixAC=SVR11CurrentAC,
        _svr11_certificate=certificate)
    # Constructor routing keeps the real class available for isinstance receipts.
    class Routed(SVR11CurrentAC):
        def __init__(self,*a,**kw):super().__init__(*a,arm=bindings.arm,**kw)
    ns.update(CertifiedPrefixAC=Routed,FullPrefixReferenceAC=Routed,ShadowCertifiedPrefixAC=Routed)
    exec(compile(tree,original.__file__,'exec'),ns)
    return ns['run']
