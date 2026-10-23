"""PR236 complete-static preparation. Historical May01 evidence is read-only."""
from pathlib import Path
import csv, hashlib, json, time
from .may01_common import ROOT, DOC, RUNTIME, SOURCE, INITIAL, read, record, relocated
from .prestart import resources, digest

BASE='b58d35b95aa1b0322883bf7498a328b52f23e0ec'
OUT=DOC/'static_complete'
RUN=RUNTIME/'static_complete'
HISTORY=DOC/'may01'
HIST_RUN=RUNTIME/'may01'

def put(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return value

def table(name,rows):
    rows=list(rows);assert rows
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader();w.writerows(rows)

def init():
    OUT.mkdir(exist_ok=True);RUN.mkdir(exist_ok=True)
    p=OUT/'TASK_DIRECTIVE_KO.md'
    if not p.exists():
        p.write_bytes(Path('C:/Users/kjw39/.codex/attachments/1aa5609c-2727-4833-97a6-cffaa55e7343/붙여넣은 텍스트.txt').read_bytes())
    return resources()

def guard(start,wall=7200):
    # October23 human steering: RAM is informational, including preparation.
    if time.perf_counter()-start>wall:raise TimeoutError('STATIC_PREPARATION_WALL_LIMIT')
