"""Original-source loader and extension-only write routing for V41R4.

Scientific code retains its original logical __file__ for manifest checks. Missing
historical paths resolve to byte-verified copies. New files are always routed
under the extension. This module does not run optimization or use Actual states.
"""
import builtins
import hashlib
import contextlib
import importlib.abc
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).parent
ORIGINAL=Path(r'C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance')
PR=Path(r'D:\ChatGPT\Mobile ESS 2\v41r4_final_results_pr')
WRITE_ROOTS=tuple(os.path.normcase(os.path.abspath(str(p))) for p in (ROOT,ROOT.resolve()))
OLD_OPEN=builtins.open;OLD_IO_OPEN=io.open;OLD_STAT=os.stat;OLD_MKDIR=os.mkdir
OLD_OS_OPEN=os.open;OLD_REPLACE=os.replace;OLD_RENAME=os.rename;OLD_UNLINK=os.unlink
OLD_RESOLVE=Path.resolve
ALIASES={};READS=set();WRITES=set();ACTIVE=None;LINEAGE_EXCEPTIONS=set()
FORBIDDEN_SENSITIVITY_NAMES=('v40e_corrected_april_full_bus_phase_sensitivity.parquet','v40e_corrected_april_local_sensitivity.parquet')


def norm(p):
    return os.path.normcase(os.path.abspath(os.fsdecode(p)))


def exists(p):
    try:OLD_STAT(p);return True
    except (FileNotFoundError,NotADirectoryError):return False


def seed_aliases():
    with OLD_OPEN(ROOT/'AUTHORITY_LOCK.json',encoding='utf-8') as f:lock=json.load(f)
    for s in lock['original_source_snapshot']:
        ALIASES[norm(s['original_path'])]=Path(s['resolved_path'])
    for s in lock['resolved_dependency_references']:
        ALIASES[norm(s['original_reference'])]=Path(s['resolved_path'])
        ALIASES[norm(str(s['original_reference']).replace('D:\\codex_mobileess_workspace','C:\\codex_mobileess_workspace'))]=Path(s['resolved_path'])
    extra=ROOT/'authority_recovery/ADDITIONAL_EXACT_ALIASES.json'
    if exists(extra):
        with OLD_OPEN(extra,encoding='utf-8') as f:entries=json.load(f)
        for s in entries:
            with OLD_OPEN(s['resolved_path'],'rb') as f:data=f.read()
            if len(data)!=s['bytes'] or hashlib.sha256(data).hexdigest()!=s['sha256']:
                raise RuntimeError('EXACT_GATE_DEPENDENCY_CHANGED:'+s['resolved_path'])
            ALIASES[norm(s['original_path'])]=Path(s['resolved_path'])
    recovery=ROOT/'CONTEXT_DEPENDENCY_RECOVERY.json'
    if exists(recovery):
        with OLD_OPEN(recovery,encoding='utf-8') as f:recovered=json.load(f)
        for s in recovered['matched']:
            with OLD_OPEN(s['resolved_path'],'rb') as f:data=f.read()
            if len(data)!=s['bytes'] or hashlib.sha256(data).hexdigest()!=s['sha256']:
                raise RuntimeError('RECOVERED_DEPENDENCY_CHANGED:'+s['resolved_path'])
            ALIASES[norm(s['original_path'])]=Path(s['resolved_path'])
    regenerated=ROOT/'april_regeneration/REGENERATION_VERIFICATION.json'
    if exists(regenerated):
        with OLD_OPEN(regenerated,encoding='utf-8') as f:verified=json.load(f)
        for s in verified['files']:
            if not s['exact_sha_match']:continue
            with OLD_OPEN(s['regenerated_path'],'rb') as f:data=f.read()
            if len(data)!=s['expected_bytes'] or hashlib.sha256(data).hexdigest()!=s['expected_sha256']:
                raise RuntimeError('EXACT_REGENERATION_CHANGED:'+s['regenerated_path'])
            ALIASES[norm(s['original_path'])]=Path(s['regenerated_path'])


def read_path(p):
    if isinstance(p,int):return p
    text=os.fsdecode(p);key=norm(text)
    if ACTIVE and any(t in key for t in ('\\production_v1\\','\\production_v2_full_round\\','\\production_v3_after_fast_wiring\\','\\diagnostic_may31_warm_start\\','\\diagnostic_stopped_attempt_01\\','\\diagnostic_stopped_attempt_02\\','\\diagnostic_stopped_attempt_03_attached_launch\\')):
        raise RuntimeError('SUPERSEDED_DIAGNOSTIC_INPUT_FORBIDDEN:'+text)
    if ACTIVE and os.environ.get('B3_2R_FAST_WIRING')!='1' and '\\corrected_model_diagnostic\\' in key:
        raise RuntimeError('CORRECTED_DIAGNOSTIC_RESULT_NOT_PRODUCTION_INPUT:'+text)
    if ACTIVE and os.environ.get('B3_2R_FAST_WIRING')!='1' and '\\fast_wiring_preflight_v1\\' in key and Path(key).name!='fast_wiring_gate.json':
        raise RuntimeError('FAST_DIAGNOSTIC_RESULT_PRODUCTION_INPUT_FORBIDDEN:'+text)
    if ACTIVE and Path(key).name in FORBIDDEN_SENSITIVITY_NAMES:
        raise RuntimeError('DIAGNOSTIC_SENSITIVITY_PRODUCTION_READ_FORBIDDEN:'+text)
    if any(t in key for t in ('resited','resiting')):raise RuntimeError('FORBIDDEN_RESITED_INPUT:'+text)
    if ACTIVE=='DA' and not key.endswith(('.py','.pyc','.pyd','.dll')):
        if any(t in key for t in ('\\actual_inputs\\','\\common_inputs\\','\\replays\\','\\actual\\')):
            raise RuntimeError('ACTUAL_STATE_READ_BEFORE_DA_FREEZE:'+text)
    mapped=ALIASES.get(key)
    if mapped is not None:return mapped
    if exists(text):return text
    # D: migration preserves old logical names in scientific receipts.
    if '\\chatgpt\\mobile ess 2\\' in key:
        suffix=key.split('\\chatgpt\\mobile ess 2\\',1)[1]
        candidate=Path(r'D:\ChatGPT\Mobile ESS 2')/suffix
        if exists(candidate):return candidate
    if '\\dayahead\\' in key:
        candidate=PR/'dayahead'/key.split('\\dayahead\\',1)[1]
        if exists(candidate):return candidate
    if key.startswith(norm(ORIGINAL)+os.sep):
        candidate=PR/key[len(norm(ORIGINAL))+1:]
        if exists(candidate):return candidate
    return text


def write_path(p):
    if isinstance(p,int):return p
    text=os.fsdecode(p);key=norm(text)
    if key in ('nul',norm('NUL')):return text
    if any(key==r or key.startswith(r+os.sep) for r in WRITE_ROOTS):
        WRITES.add(text);return text
    # Legacy code may persist derived input/readback diagnostics. Isolate them.
    drive,tail=os.path.splitdrive(key)
    target=Path(os.environ.get('ABLATION_CASE_ROOT',str(ROOT)))/'s'/hashlib.sha256(os.path.dirname(key).encode()).hexdigest()[:12]/os.path.basename(key)
    WRITES.add(str(target));return str(target)


def install(phase='DA'):
    global ACTIVE
    if ACTIVE is not None:
        ACTIVE=phase;return ROOT
    ACTIVE=phase;sys.dont_write_bytecode=True;seed_aliases()
    def resolve_new_output(p,strict=False):
        absolute=os.path.abspath(os.fsdecode(p));key=norm(absolute)
        for root in WRITE_ROOTS:
            if key==root or key.startswith(root+os.sep):
                if strict:OLD_STAT(p)
                if root==norm(Path('D:/c5')):return Path(absolute)
                return ROOT/absolute[len(root):].lstrip('\\/')
        return OLD_RESOLVE(p,strict=strict)
    # Windows canonicalization prefers an old Unicode OneDrive junction alias.
    # Native Gurobi cannot open that spelling. Keep new output resolves on D:;
    # all original logical source/input paths retain their original resolution.
    Path.resolve=resolve_new_output
    def opened(original,p,mode='r',*args,**kw):
        target=write_path(p) if any(c in mode for c in 'wax+') else read_path(p)
        if not any(c in mode for c in 'wax+') and not isinstance(target,int):READS.add((os.fsdecode(p),os.fsdecode(target)))
        if not isinstance(target,int) and any(c in mode for c in 'wax+'):
            Path(target).parent.mkdir(parents=True,exist_ok=True)
        return original(target,mode,*args,**kw)
    builtins.open=lambda p,mode='r',*args,**kw:opened(OLD_OPEN,p,mode,*args,**kw)
    io.open=lambda p,mode='r',*args,**kw:opened(OLD_IO_OPEN,p,mode,*args,**kw)
    def stat(p,*args,**kw):return OLD_STAT(read_path(p),*args,**kw)
    os.stat=stat
    def mkdir(p,*args,**kw):
        if exists(p):return OLD_MKDIR(p,*args,**kw)
        target=write_path(p)
        if norm(target)!=norm(p):Path(target).parent.mkdir(parents=True,exist_ok=True)
        return OLD_MKDIR(target,*args,**kw)
    os.mkdir=mkdir
    def osopen(p,flags,*args,**kw):
        writing=bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        target=write_path(p) if writing else read_path(p)
        if writing:Path(target).parent.mkdir(parents=True,exist_ok=True)
        return OLD_OS_OPEN(target,flags,*args,**kw)
    os.open=osopen
    os.replace=lambda src,dst,*args,**kw:OLD_REPLACE(write_path(src),write_path(dst),*args,**kw)
    os.rename=lambda src,dst,*args,**kw:OLD_RENAME(write_path(src),write_path(dst),*args,**kw)
    os.unlink=lambda p,*args,**kw:OLD_UNLINK(write_path(p),*args,**kw)
    sys.meta_path.insert(0,SourceFinder())
    tmp=Path(os.environ.get('ABLATION_CASE_ROOT',str(ROOT)))/'tmp';tmp.mkdir(exist_ok=True);tempfile.tempdir=str(tmp)
    os.environ['TEMP']=os.environ['TMP']=str(tmp)
    return ROOT


class SourceLoader(importlib.abc.SourceLoader):
    def __init__(self,logical,physical):self.logical=logical;self.physical=physical
    def get_filename(self,fullname):return str(self.logical)
    def get_data(self,path):
        with OLD_OPEN(self.physical,'rb') as f:return f.read()
    def set_data(self,path,data):pass


class SourceFinder(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        relative=Path(*fullname.split('.'))
        for suffix,package in ((relative/'__init__.py',True),(relative.with_suffix('.py'),False)):
            physical=ROOT/'original_source'/suffix
            if not exists(physical):physical=PR/suffix
            if not exists(physical):continue
            logical=physical if physical.is_relative_to(ROOT/'original_source') else ORIGINAL/suffix
            ALIASES[norm(logical)]=physical
            loader=SourceLoader(logical,physical)
            return importlib.util.spec_from_file_location(fullname,logical,loader=loader,
                submodule_search_locations=[str(logical.parent)] if package else None)
        return None


def save_audit(path):
    Path(path).write_text(json.dumps(dict(phase=ACTIVE,write_paths=sorted(WRITES),legacy_outputs_redirected=True,
        source_aliases={k:str(v) for k,v in ALIASES.items()},Actual_input_exclusion_enabled=ACTIVE=='DA',
        read_paths=sorted(READS),documented_missing_historical_leaves=sorted(LINEAGE_EXCEPTIONS),
        regenerated_sensitivity_production_usage=sum(Path(p).name.lower() in FORBIDDEN_SENSITIVITY_NAMES for _,p in READS)),indent=2),encoding='utf-8')
