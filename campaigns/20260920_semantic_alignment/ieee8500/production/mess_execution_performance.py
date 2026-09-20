"""I/O-only adapters; preserve all coefficient values, rows and cache identities."""
import inspect, hashlib, json
from pathlib import Path
import full_electrical_rows

def single_pass_evaluator():
    source = inspect.getsource(full_electrical_rows.evaluate_grid)
    changes = {
        'rows=[];critical=None;bad=0': 'rows=[];critical=None;bad=0;coefficient_shas=[]',
        'for t,c in enumerate(coefficients):': 'for t,c in enumerate(coefficients):\n        coefficient_shas.append(c.coefficient_sha256)',
        'coefficient_SHAs=[c.coefficient_sha256 for c in coefficients]': 'coefficient_SHAs=coefficient_shas',
    }
    for old, new in changes.items():
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    namespace = dict(vars(full_electrical_rows))
    exec(compile(source, __file__ + '::single_pass_evaluate_grid', 'exec'), namespace)
    return namespace['evaluate_grid']

evaluate_grid = single_pass_evaluator()

def install_short_candidate_paths(root, save, read):
    from dayahead.v40h.candidate_cache import CandidateResultCache
    if getattr(CandidateResultCache, '_ieee8500_short_paths', False):
        return
    original = CandidateResultCache.__init__
    def init(self, cache_root, context):
        # Only the storage directory changes. Candidate, parent and execution
        # identities retain the original full SHA256 provenance checks.
        source_root = str(Path(cache_root).absolute())
        full_sha = hashlib.sha256(source_root.encode('utf-8')).hexdigest()
        short_root = Path(root) / 'cc' / full_sha[:20]
        marker = short_root / 'ROOT_IDENTITY.json'
        binding = dict(original_root=source_root, full_SHA256=full_sha)
        if marker.exists():
            assert read(marker) == binding, 'SHORT_CACHE_ROOT_COLLISION'
        else:
            save(marker, binding)
        original(self, short_root, context)
    CandidateResultCache.__init__ = init
    CandidateResultCache._ieee8500_short_paths = True
