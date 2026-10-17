"""Same attribution arithmetic, batched sparse reads, and separated wall costs."""
from collections import defaultdict
from contextlib import contextmanager
from time import perf_counter
from pathlib import Path
import inspect,linecache,textwrap,threading,os
import psutil
import numpy as np
from v44.common import atomic,now
from .row_generation import exact_phi


def compile_attribution(function):
    source=textwrap.dedent(inspect.getsource(function))
    old="    for row,importance in signed_effect.items():\n        for j,key in enumerate(keys):"
    new="    axis_index={key:j for j,key in enumerate(keys)}\n    resource_ids=[j for j,key in enumerate(keys) if key[0] in ('GPU','RUNTIME')]\n    resource_cols=np.asarray([atlas['resource_variables'][j] for j in resource_ids],dtype=int)\n    resource_rows=np.asarray([axes[keys[j]] for j in resource_ids],dtype=int)\n    if np.any(resource_cols<0):raise ValueError('R024_RESOURCE_VARIABLE_AXIS')\n    bindings=np.asarray(A[resource_rows,resource_cols]).ravel()\n    values=A[list(signed_effect)][:,resource_cols].toarray()\n    cached_binding=dict(zip(resource_ids,map(float,bindings)))\n    for index,(row,importance) in enumerate(signed_effect.items()):\n        cached_row=dict(zip(resource_ids,map(float,values[index])))\n        for j,key in enumerate(keys):"
    if source.count(old)!=1:raise ValueError('R024_ATTRIBUTION_SOURCE_DRIFT')
    source=source.replace(old,new)
    source=source.replace("binding=float(A[resource_row,column])","binding=cached_binding[j]")
    source=source.replace("float(A[row,column])","cached_row[j]")
    source=source.replace("effect[keys.index(('GPU',site,t))]","effect[axis_index['GPU',site,t]]")
    filename=__file__+'.attribution.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    namespace=dict(function.__globals__,phase_objective=exact_phi)
    exec(compile(source,filename,'exec'),namespace)
    return namespace[function.__name__]


class Profile:
    def __init__(self,output):
        self.output=Path(output);self.costs=defaultdict(lambda:dict(calls=0,wall_seconds=0.));self.peak=0
        self.started=perf_counter();self.done=threading.Event();self.process=psutil.Process()
    def wrap(self,name,function):
        def timed(*args,**kwargs):
            start=perf_counter()
            try:return function(*args,**kwargs)
            finally:
                value=self.costs[name];value['calls']+=1;value['wall_seconds']+=perf_counter()-start
                self.save()
        return timed
    def save(self):
        self.peak=max(self.peak,self.process.memory_info().rss)
        atomic(self.output/'R024_PHASE_COMPONENT_PROFILE.json',dict(UTC=now(),wall_seconds=perf_counter()-self.started,
            peak_RSS_bytes=self.peak,component_costs=dict(self.costs),costs_may_be_nested=True,scaling_revision_applied=False))
    def sample(self):
        while not self.done.wait(.5):self.peak=max(self.peak,self.process.memory_info().rss)
    def __enter__(self):
        self.thread=threading.Thread(target=self.sample,daemon=True);self.thread.start();return self
    def __exit__(self,*args):self.done.set();self.thread.join(timeout=2);self.save()
