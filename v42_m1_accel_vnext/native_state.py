"""Read-only, PID-bound live-call evidence; an import is never a conflict.

py-spy uses nonblocking snapshots without locals. Unknown/idle engine mappings
are recorded but do not block. A live Python call site for a native solver,
with the same PID creation time before/after sampling, is required.
"""
from .common import *
import ast
import shutil
import subprocess
import time
import psutil

NATIVE_CALLS = {'optimize', 'presolve', 'Solve', 'SolveSnap', 'SolveDirect', 'SolveNoControl', 'SolvePFlow', 'SolvePlusControl'}


def call_witness(frame, source):
    """The currently executing line must be the solver call, not its import."""
    line = frame['line']
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            api_call=node.func.attr.startswith(('Solution_Solve','ctx_Solution_Solve'))
            native_call=node.func.attr in NATIVE_CALLS or api_call
            if native_call and node.lineno <= line <= node.end_lineno:
                if api_call:
                    filename=frame.get('filename','').replace('\\','/').lower()
                    package=any(p in filename for p in ['/site-packages/opendssdirect/','/site-packages/dss/'])
                    receiver=node.func.value
                    ffi= isinstance(receiver,ast.Attribute) and receiver.attr=='_lib'
                    if not (package and ffi):continue
                if isinstance(node.func.value, ast.Call) and isinstance(node.func.value.func, ast.Name) and node.func.value.func.id == 'super':
                    # A Python wrapper is real native evidence only when its
                    # enclosing class provably subclasses this imported gp.Model.
                    aliases = {n.targets[0].id for n in ast.walk(tree)
                        if isinstance(n, ast.Assign) and len(n.targets)==1
                        and isinstance(n.targets[0], ast.Name)
                        and isinstance(n.value, ast.Attribute) and n.value.attr=='Model'
                        and isinstance(n.value.value, ast.Name)
                        and any(isinstance(i, ast.Import) and any(a.name=='gurobipy' and (a.asname or a.name)==n.value.value.id for a in i.names) for i in ast.walk(tree))}
                    proven = any(isinstance(c, ast.ClassDef) and c.lineno <= line <= c.end_lineno
                        and any(isinstance(b, ast.Name) and b.id in aliases for b in c.bases) for c in ast.walk(tree))
                    if not proven:
                        continue
                return dict(call=node.func.attr, line=line,
                            statement=ast.get_source_segment(source, node),
                            source_SHA=hashlib.sha256(source.encode()).hexdigest())
    return None


def classify(row, stacks, source_reader):
    result = dict(row, classification='NATIVE_MAPPING_WITHOUT_LIVE_SOLVE_PROOF',
                  optimize_state='UNCONFIRMED', live_call_proofs=[])
    if not row.get('native_maps'):
        result.update(classification='NO_NATIVE_ENGINE_MAPPED', optimize_state='NOT_OBSERVED')
        return result
    for thread in stacks:
        if thread.get('pid') != row['pid']:
            continue
        frames = thread.get('frames', [])
        # A Python mock implementation is not evidence of a native call.
        if any('unittest' in f.get('filename', '').lower() and
               'mock' in f.get('filename', '').lower() for f in frames):
            continue
        for index,frame in enumerate(frames):
            # A custom Python scheduler's optimize() remains Python execution,
            # even if its caller has an engine mapping. Do not infer a C call.
            if any(f.get('name') in NATIVE_CALLS for f in frames[:index]):
                continue
            try:
                proof = call_witness(frame, source_reader(frame['filename']))
            except (OSError, SyntaxError, UnicodeError, KeyError, TypeError):
                continue
            if proof:
                result['live_call_proofs'].append(dict(proof, filename=frame['filename'],
                    function=frame['name'], thread_id=thread['thread_id'],
                    sample_pid=thread['pid']))
    if result['live_call_proofs']:
        result.update(classification='CONFIRMED_FOREIGN_NATIVE_SOLVE',
                      optimize_state='IN_NATIVE_CALL_OR_ITS_CALLBACK')
    return result


def inspect_live(excluded=()):
    rows = []; blocked = []; skip = {os.getpid(), *excluded}
    spy = shutil.which('py-spy')
    for p in psutil.process_iter(['pid', 'ppid', 'name', 'create_time']):
        if p.pid in skip or not any(s in (p.info['name'] or '').lower()
                                   for s in ('python', 'gurobi', 'opendss', 'pytest')):
            continue
        try:
            before = p.create_time()
            maps = sorted({x.path for x in p.memory_maps(grouped=True)
                if any(s in x.path.lower() for s in ('gurobi', 'opendss', 'dss_capi'))})
            row = dict(p.info, native_maps=maps, RSS=p.memory_info().rss,
                       observed_epoch=time.time(), observer='nonblocking py-spy + source call site')
            stacks = []; error = None
            if maps and spy and 'python' in (p.info['name'] or '').lower():
                probe = subprocess.run([spy, 'dump', '--pid', str(p.pid), '--nonblocking', '--json'],
                    capture_output=True, text=True, encoding='utf8', errors='replace', timeout=2,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if probe.returncode == 0:
                    stacks = json.loads(probe.stdout)
                else:
                    error = probe.stderr[:500]
            elif maps:
                error = 'LIVE_STACK_UNAVAILABLE; mapping alone does not block'
            after = psutil.Process(p.pid).create_time()
            if after != before:
                continue  # PID reuse cannot authorize a conflict.
            observed = classify(row, stacks,
                lambda name: Path(name).read_text(encoding='utf-8-sig'))
            observed.update(PID_identity_rechecked=True, stack_error=error)
            rows.append(observed)
            if observed['classification'] == 'CONFIRMED_FOREIGN_NATIVE_SOLVE':
                blocked.append(observed)
        except psutil.NoSuchProcess:
            continue
        except (psutil.AccessDenied, subprocess.TimeoutExpired, ValueError, OSError) as e:
            rows.append(dict(p.info, classification='UNCONFIRMED_OBSERVATION_ERROR',
                             optimize_state='UNCONFIRMED', error=repr(e)))
    return rows, blocked
