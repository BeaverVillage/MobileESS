"""One required SVR11 coefficient/thermal authority for every V44 Arm."""
from contextlib import contextmanager,ExitStack
from functools import wraps
from pathlib import Path
from unittest.mock import patch
import ast
import inspect
import textwrap
from .common import read,record,verify,NotReady
from .svr11_hardware import HARDWARE,scope
from .svr11_forecast import INPUTS


def ready(day):
    path=INPUTS/day/'SVR11_INPUT_READY.json'
    if not path.is_file():raise NotReady('NEW_SVR11_FORECAST_COEFFICIENTS_REQUIRED:'+day)
    proof=read(path);verify([proof[k] for k in ('model','input','windows','hardware','original')])
    h=read(HARDWARE/'HARDWARE.json');cert=read(proof['model']['path'])
    if (proof['hardware']!=record(HARDWARE/'HARDWARE.json') or cert['scenario_SHA']!=h['scenario_SHA']
            or cert.get('model_version')!='V42_SVR11_LDC_INTERVAL_ELECTRICAL_CERTIFICATE_V2'
            or cert['Actual_inputs_read']!=0 or not cert['model_regenerated']):
        raise PermissionError('SVR11_OLD_HARDWARE_OR_COEFFICIENTS_FORBIDDEN')
    return proof


def _fresh_a_builder(original):
    # The old May01 shortcut contains frozen grid/coupling matrices. Rebuild
    # them using the same producer as other dates, preserving domain rules.
    tree=ast.parse(textwrap.dedent(inspect.getsource(original)));count=0
    class Fresh(ast.NodeTransformer):
        def visit_If(self,node):
            nonlocal count
            if ast.unparse(node.test)=="bundle['day'] == '2025-05-01'":
                node.test=ast.Constant(False);count+=1
            return self.generic_visit(node)
    tree=Fresh().visit(tree);ast.fix_missing_locations(tree)
    if count!=1:raise ValueError('SVR11_MAY01_STATIC_GRID_SHORTCUT_BOUNDARY_DRIFT')
    ns=dict(original.__globals__);exec(compile(tree,original.__code__.co_filename,'exec'),ns)
    return ns[original.__name__]


@contextmanager
def grid_scope(day):
    proof=ready(day)
    with scope():
        from v42_svr11.model import load_coefficients,verify_coefficients
        cert=read(proof['model']['path']);coeff=load_coefficients(cert,day);verify_coefficients(cert,day,coeff)
        import v42_pr134_b1.native as binder
        import v42_temporal.native as temporal
        import v42_may01.prepare as original
        import v42_thermal.authority as thermal
        import v42_thermal.measurement as measurement
        import v42_may_campaign_native90.bindings as dated_checks
        def coefficients(_module,certificate,requested_day):
            if requested_day!=day or certificate.get('output',{}).get('sha256')!=cert['output']['sha256']:
                raise PermissionError('SVR11_EXACT_DATED_COEFFICIENT_BINDING_REQUIRED')
            return coeff
        def checked_coefficients(requested_day,certificate,values):
            if requested_day!=day or certificate.get('output')!=cert['output']:
                raise PermissionError('SVR11_DATED_COEFFICIENT_CHECK_DRIFT')
            proof=verify_coefficients(certificate,day,values)
            return dict(proof,transformer_phase_current_rows_per_slot=153,
                all_unchanged_source_coefficient_arrays_bit_exact=True,
                original_NormalAmps_denominator_binding_bit_exact=True,
                transformer_current_authority_SHA=values[0].transformer_current_authority_sha256,
                electrical_outputs=certificate['outputs'])
        with ExitStack() as stack:
            stack.enter_context(patch.object(measurement,'current_authority',thermal.current_authority))
            stack.enter_context(patch.object(binder,'original_coefficients_for_day',coefficients))
            stack.enter_context(patch.object(binder,'build_static',_fresh_a_builder(binder.build_static)))
            stack.enter_context(patch.object(dated_checks,'check_coefficients',checked_coefficients))
            # Existing bind() subsequently assigns these to its own exact dated
            # coefficient object. No old native constructor may read 7-reg NPZ.
            stack.enter_context(patch.object(original,'native_coefficients',lambda c:coefficients(original,c,day)))
            stack.enter_context(patch.object(temporal,'native_coefficients',lambda c:coefficients(original,c,day)))
            yield proof


def stage_scope(function):
    @wraps(function)
    def run(*args,**kwargs):
        item=args[0];day=item if isinstance(item,str) else item['day']
        with grid_scope(day):return function(*args,**kwargs)
    return run
