"""Long-path addressing for beam checkpoints; numerical/cache identities stay intact."""
from functools import wraps
import os
from pathlib import Path


def native_path(path):
    """Address the same Windows file using the extended-length namespace."""
    path = Path(path).absolute()
    value = str(path)
    if os.name != 'nt' or value.startswith('\\\\?\\'):
        return path
    if value.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + value[2:])
    return Path('\\\\?\\' + value)


def install_beam_paths(beam=None):
    """Cover B2/B3, every MESS/beam/K fallback, including temp files and renames.

    Only the filesystem address changes. In particular, do not normalize or
    shorten EXECUTION_CACHE_CONTEXT: its strings participate in cache identity.
    The original CACHE_ROOT is restored even if the solver raises an error.
    """
    if beam is None:
        from dayahead.tools import run_v35r3e_r1_beam as beam
    if os.name != 'nt' or getattr(beam._run_case, '_v40b_native_paths', False):
        return
    original = beam._run_case

    @wraps(original)
    def run_case(*args, **kwargs):
        saved = beam.CACHE_ROOT
        beam.CACHE_ROOT = native_path(Path.cwd() / saved)
        try:
            return original(*args, **kwargs)
        finally:
            beam.CACHE_ROOT = saved

    run_case._v40b_native_paths = True
    beam._run_case = run_case
