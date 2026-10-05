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

NATIVE_CALLS = {'optimize', 'presolve', 'Solve', 'SolveSnap'}


def call_witness(frame, source):
    """The currently executing line must be the solver call, not its import."""
    line = frame['line']
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in NATIVE_CALLS and node.lineno <= line <= node.end_lineno:
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
