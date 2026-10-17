"""SHA-pinned in-place reuse, without copying a historical case/result tree.

Whole runtime algorithms have no import-time case IO. The older oracle and
verifier are reduced to exact reusable definitions, excluding historical
paths, case/bound globals, CLI entrypoints and sys.path changes.
"""
import ast
import importlib.abc
import importlib.util
from pathlib import Path
import sys
import types

from v43.common import PR231,DOC,ROOT,read,record,verify_records,atomic

PREFIX='v44.reuse'
WHOLE={name:PR231/'v42_integration'/(name+'.py') for name in (
    'preparation_profile','table_v_memory','m_engine','m_adaptive','m_candidates','table_v_k48','table_v_global_control')}
SLICES={
    'tools.critical_grid_cg.oracle':(PR231/'tools/critical_grid_cg/oracle.py',
        ('FAMILIES','QUOTAS','EPS','require','canonical_sha','upward','row_sha','float_sum_error','Geometry','metadata')),
    'tools.critical_grid_cg.verify':(PR231/'tools/critical_grid_cg/verify.py',
        ('FAMILIES','PHYSICAL','require','dyadic','upward','axis','canonical_data','digests','original_row_sha','Geometry')),
    'tools.time_decomposed_lb.grid':(PR231/'tools/time_decomposed_lb/grid.py',
        ('FAMILIES','PHYSICAL','require','canonical_sha','_row_sha','_upward','SelectiveAuthority')),
    'v42_ultracompact.current_verify':(PR231/'v42_ultracompact/current_verify.py',
        ('_rational','family','vec','physical_pcs_authority')),
}
MANIFEST=ROOT/'docs/v44/V43_MESS_REUSE_SOURCE_MANIFEST.json'


def _selected(path,names):
    source=path.read_text(encoding='utf-8-sig');lines=source.splitlines(keepends=True)
    nodes={};imports=[]
    for node in ast.parse(source).body:
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            imports.append(''.join(lines[node.lineno-1:node.end_lineno]))
        elif isinstance(node,(ast.FunctionDef,ast.ClassDef)):
            nodes[node.name]=node
        elif isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name):nodes[target.id]=node
    bodies=[];spans=[]
    for name in names:
        node=nodes[name]
        first=min([node.lineno]+[d.lineno for d in getattr(node,'decorator_list',[])])
        bodies.append(''.join(lines[first-1:node.end_lineno]))
        spans.append(dict(symbol=name,first_line=first,last_line=node.end_lineno))
    return '\n'.join(imports+bodies),spans


def pin():
    rows=[]
    for name,path in WHOLE.items():rows.append(dict(module=PREFIX+'.'+name,source=record(path),scope='WHOLE_RUNTIME_ONLY'))
    for name,(path,names) in SLICES.items():
        _,spans=_selected(path,names)
        rows.append(dict(module=name,source=record(path),scope='EXACT_DEFINITION_SLICE',definitions=spans))
    rows += [dict(module=name,source=record(ROOT/path),scope='UNCHANGED_PR189_PHYSICAL_VALIDATOR_OR_CASE_BUILDER') for name,path in (
        ('original_m_case','v42_may_campaign_native90/m_model.py'),
        ('original_full_validator','v42_m1_research/check_ub.py'),
        ('original_mess_physics','v42_native/mess.py'))]
    payload=dict(schema='V43_IN_PLACE_MESS_SOURCE_REUSE_V1',sources=rows,
        copied_algorithm_files=0,allowed_execution_dates=['2025-05-01'],
        historical_case_or_result_globals_loaded=False,old_FULL_seed_activated=False,
        permitted_adaptations=['canonical digest helper only','May01-only date guard',
            'V43 atomic IO for status/artifacts','V43 source/case identity instead of D0 labels',
            'separately bound original-stage budgets; no numerical-policy changes'])
    if MANIFEST.exists() and read(MANIFEST)!=payload:
        raise ValueError('PINNED_MESS_LIBRARY_SOURCE_DRIFT')
    atomic(MANIFEST,payload)
    return payload


def _package(name):
    if name not in sys.modules:
        module=types.ModuleType(name);module.__path__=[];sys.modules[name]=module
        if '.' in name:
            parent,field=name.rsplit('.',1)
            if parent in sys.modules:setattr(sys.modules[parent],field,module)
    return sys.modules[name]


def current_identity(case):
    from v42_native.contracts import digest
    from v42_m1_hybrid.blocks import matrix_sha
    from v42_may_campaign_native90.m_model import _domain_sha
    i=case.identity
    if digest(i)!=case.case_sha or i.get('schema')!='V44_DATED_FIXED_AIDC_MESS_CASE_V1':
        raise ValueError('V43_MESS_EXPLICIT_CURRENT_CASE_REQUIRED')
    from v44.config import DAYS
    if i['day'] not in DAYS or case.bundle['day']!=i['day'] or i['stage'] not in ('M1','M2'):
        raise ValueError('V43_MAY01_MESS_STAGE_ONLY')
    actual=dict(matrix_sha=matrix_sha(case.original_A),domain_sha=_domain_sha(case.original_d))
    if actual['matrix_sha']!=i['original_matrix_sha'] or actual['domain_sha']!=i['original_domain_sha']:
        raise ValueError('V43_ORIGINAL_FULL_MATH_BYTES_DRIFT')
    for name in ('source_sha','parent_case_sha','aidc_anchor'):
        value=i[name]
        if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('V43_MESS_COMPLETE_BINDING_REQUIRED:'+name)
    return dict(day=i['day'],stage_case_sha=case.case_sha,source_sha=i['source_sha'],
        parent_case_sha=i['parent_case_sha'],arm=i['arm'],stage=i['stage'],aidc_anchor=i['aidc_anchor'],**actual)


class _SourceLoader(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def __init__(self,payload):
        self.records={r['module']:r for r in payload['sources']}

    def find_spec(self,fullname,path=None,target=None):
        if fullname in self.records and (fullname.startswith(PREFIX+'.') or fullname in SLICES):
            return importlib.util.spec_from_loader(fullname,self)
        return None

    def create_module(self,spec):return None

    def exec_module(self,module):
        name=module.__name__;row=self.records[name]
        verify_records([row['source']]);path=Path(row['source']['path'])
        module.__file__=str(path);module.__package__=name.rsplit('.',1)[0]
        source=_selected(path,SLICES[name][1])[0] if name in SLICES else path.read_bytes()
        exec(compile(source,str(path),'exec'),module.__dict__)
        module._v43_source_pin=row['source']
        if name in SLICES:
            forbidden=('SAVED','COEFFICIENTS','SOURCE','CASE','CERT','UB','LB_OLD','ROOT','OUT')
            if any(key in module.__dict__ for key in forbidden):
                raise ValueError('HISTORICAL_MESS_GLOBAL_LOADED')
        if name==PREFIX+'.table_v_k48':
            module.identity=current_identity
            original_metadata=module._coefficient_metadata
            def metadata(case):
                return case._v43_coefficient_metadata if hasattr(case,'_v43_coefficient_metadata') else original_metadata(case)
            module._coefficient_metadata=metadata
        if name==PREFIX+'.table_v_global_control':
            # The original proof math is retained; only the source namespace
            # field changes. A fake D0 identity is never attached to V43.
            import inspect,textwrap
            body=textwrap.dedent(inspect.getsource(module.mess_upper))
            old="case.identity.get('D0_source_sha')"
            if body.count(old)!=1:raise ValueError('M_GLOBAL_SOURCE_BINDING_SHAPE_DRIFT')
            exec(compile(body.replace(old,"case.identity.get('source_sha')"),str(path),'exec'),module.__dict__)
        if name.startswith(PREFIX+'.') and hasattr(module,'_write'):
            def write(path,value):
                # Keep the original Fraction/dataclass/NumPy serializer; only
                # unique-temp/locking/replace IO belongs to the V43 writer.
                from v44.reuse.m_engine import _json_value
                atomic(path,_json_value(value))
            module._write=write


def load():
    payload=read(MANIFEST)
    payload=dict(payload,sources=[dict(r,module=r['module'].replace('v43_mess.reuse.',PREFIX+'.',1))
        if r['module'].startswith('v43_mess.reuse.') else r for r in payload['sources']])
    verify_records([r['source'] for r in payload['sources']])
    _package(PREFIX)
    _package('tools')
    for name in ('tools.critical_grid_cg','tools.time_decomposed_lb'):_package(name)
    for name in SLICES:
        if name in sys.modules and getattr(sys.modules[name],'_v43_source_pin',None) is None:
            raise RuntimeError('PRELOADED_UNSCOPED_MESS_ORACLE:'+name)
    if not any(isinstance(f,_SourceLoader) for f in sys.meta_path):sys.meta_path.insert(0,_SourceLoader(payload))
    digest_module=_package(PREFIX+'.a_engine')
    from v42_native.contracts import digest
    digest_module.digest=digest
    dates=_package(PREFIX+'.table_v_dates')
    from v44.config import require_day
    dates.require_day=require_day
    gap=_package(PREFIX+'.table_v_gap_contract');gap.MESS_GLOBAL_GAP_TARGET=.03
    authority=_package(PREFIX+'.table_v_mess')
    from v44.budget import require_budget
    authority.require_real_budget=require_budget
    modules={name:__import__(PREFIX+'.'+name,fromlist=['*']) for name in WHOLE}
    return modules


def dependency_smoke():
    """Exercise lazy Beam dependencies before spending any K48 Native budget."""
    import importlib
    grid=importlib.import_module('tools.time_decomposed_lb.grid')
    pcs=importlib.import_module('v42_ultracompact.current_verify')
    checksum=grid._row_sha(0,'V43_DEPENDENCY_CANARY','<',1.,[(0,1.)])
    if len(checksum)!=64 or not callable(pcs.physical_pcs_authority):
        raise ValueError('M_RUNTIME_DEPENDENCY_CANARY_FAILED')
    return dict(PASS=True,row_hash=checksum,PCS_dependency=pcs._v43_source_pin,Native_calls=0)


if __name__=='__main__':
    pin()
    print('PINNED_IN_PLACE_MESS_LIBRARIES',list(load()))
