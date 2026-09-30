"""Explicit Linux path plumbing for byte-preserved historical Windows inputs.

Enabled only when MOBILEESS_PATH_MAP is set by the canonical launcher.
Unmapped drive paths fail closed; no Windows mounts are accessed at runtime.
"""
import os,json,pathlib,builtins
_config=os.environ.get('MOBILEESS_PATH_MAP')
if _config:
    with open(_config,encoding='utf8') as _f:_map=json.load(_f)
    def _translate(value):
        if not isinstance(value,(str,bytes,os.PathLike)):return value
        text=os.fsdecode(value).replace('\\','/')
        if text in _map:return _map[text]
        if len(text)>2 and text[1:3]==':/':
            if text in _map:return _map[text]
            # Descendant package directories are derived only from exact files.
            candidates={dest[:-(len(key)-len(text))] for key,dest in _map.items() if key.startswith(text.rstrip('/')+'/')}
            if len(candidates)==1:return next(iter(candidates))
            raise FileNotFoundError('UNMAPPED_HISTORICAL_WINDOWS_PATH:'+text)
        return value
    _new=pathlib.Path.__new__
    def _path_new(cls,*args,**kwargs):
        if args and isinstance(args[0],(str,bytes,os.PathLike)):
            first=os.fsdecode(args[0]).replace('\\','/')
            if first in _map and len(args)==1:return _new(cls,_map[first],**kwargs)
            if len(first)>2 and first[1:3]==':/':
                return _new(cls,_translate('/'.join([first.rstrip('/')]+[os.fsdecode(x).strip('/') for x in args[1:]])),**kwargs)
        return _new(cls,*args,**kwargs)
    pathlib.Path.__new__=staticmethod(_path_new)
    # Python 3.12 initializes _raw_paths in __init__, after __new__.
    _init=pathlib.Path.__init__
    def _path_init(self,*args,**kwargs):
        if args and isinstance(args[0],(str,bytes,os.PathLike)):
            first=os.fsdecode(args[0]).replace('\\','/')
            if first in _map and len(args)==1:args=(_map[first],)
            elif len(first)>2 and first[1:3]==':/':
                args=(_translate('/'.join([first.rstrip('/')]+[os.fsdecode(x).strip('/') for x in args[1:]])),)
        return _init(self,*args,**kwargs)
    pathlib.Path.__init__=_path_init
    _open=builtins.open
    def _mapped_open(file,*args,**kwargs):return _open(_translate(file),*args,**kwargs)
    builtins.open=_mapped_open
    # np.load and pandas use builtins.open for manifest string paths.
