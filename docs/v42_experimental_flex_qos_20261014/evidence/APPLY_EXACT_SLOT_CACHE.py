"""Apply only after the measured predecessor source has finished execution."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'v42_integration/experimental_grid.py'
source=p.read_text(encoding='utf8')
assert 'def _at_slot_uncached' not in source,'SLOT_CACHE_ALREADY_APPLIED'
source=source.replace('from copy import deepcopy','from copy import deepcopy\nfrom collections import OrderedDict')
source=source.replace('        self._batch_tables=None','        self._batch_tables=None\n        self._slot_cache=OrderedDict()\n        self.slot_cache_hits=0\n        self.slot_cache_misses=0\n        self.slot_cache_enabled=True',1)
source=source.replace('    def _at_slot(self,t,gpu_delta):','''    def _at_slot(self,t,gpu_delta):
        # All response tables and authority are frozen per packet, as required
        # by the existing full-profile cache. Retain complete numeric input;
        # no rounding, tolerance change or approximation enters this key.
        delta=np.asarray(gpu_delta)
        if not getattr(self,'slot_cache_enabled',True):
            return self._at_slot_uncached(t,delta)
        key=(int(t),delta.dtype.str,delta.shape,delta.tobytes())
        cache=self.__dict__.setdefault('_slot_cache',OrderedDict())
        if key in cache:
            self.slot_cache_hits=getattr(self,'slot_cache_hits',0)+1
            cache.move_to_end(key)
            return deepcopy(cache[key])
        self.slot_cache_misses=getattr(self,'slot_cache_misses',0)+1
        result=self._at_slot_uncached(t,delta)
        cache[key]=deepcopy(result)
        if len(cache)>1024:cache.popitem(last=False)
        return result

    def _at_slot_uncached(self,t,gpu_delta):''',1)
p.write_bytes(source.encode('utf8'))
print('EXACT_SLOT_CACHE_APPLIED')
