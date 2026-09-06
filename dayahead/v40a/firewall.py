"""Fail closed on outcome-file reads while the Planning stages are active."""
from __future__ import annotations
import os
from pathlib import Path
import re
import sys

_active=False
_day=None
_installed=False
_violations=[]


def check_read(path, mode='r', flags=0):
    if not _active or not isinstance(path,(str,bytes,os.PathLike)):return
    value=os.fsdecode(path).replace('\\','/').lower()
    read_access=mode is None and (flags & (os.O_WRONLY|os.O_RDWR))!=os.O_WRONLY
    if not (('r' in str(mode)) or '+' in str(mode) or read_access):return
    suffix=Path(value).suffix
    if suffix in ('.py','.pyc','.pyd','.dll','.exe'):return
    basename=Path(value).name
    denied=bool(re.search(r'(^|[/_])(actual|fresh)([/_.]|$)',value))
    dates=re.findall(r'2025-\d{2}-\d{2}',value)
    if _day and _day.startswith('2025-04-') and any(d>_day for d in dates):denied=True
    if denied:
        _violations.append(value)
        raise PermissionError('V40A_PLANNING_DATA_FIREWALL:'+value)


def _audit(event,args):
    if event=='open':check_read(*args[:3])


def activate(day):
    global _installed,_active,_day
    if not _installed:sys.addaudithook(_audit);_installed=True
    _day=day;_active=True


def deactivate():
    global _active
    _active=False


def status():return {'active':_active,'day':_day,'blocked_reads':list(_violations),'Actual_reads_allowed_inside_loop':0,'Fresh_reads_allowed_inside_loop':0}
