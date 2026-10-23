"""Lossless same-case Native MATRIX.npz reuse; raw vectors remain separate."""
from pathlib import Path
import os,hashlib
import numpy as np

class MatrixFiles:
    def __init__(self,root):self.root=Path(root).resolve();self.entries={};self.links=0;self.saved=0;self.fallbacks=0
    def wrap(self,original):
        def save(file,matrix,compressed=True):
            if not isinstance(file,(str,os.PathLike)):return original(file,matrix,compressed=compressed)
            path=Path(file)
            if path.name!='MATRIX.npz' or not path.resolve().is_relative_to(self.root) or matrix.format not in ('csr','csc'):
                return original(file,matrix,compressed=compressed)
            h=hashlib.sha256(repr((matrix.shape,matrix.format,type(matrix).__name__,bool(compressed))).encode())
            for a in (matrix.indptr,matrix.indices,matrix.data):
                h.update(repr((a.shape,a.dtype.str)).encode());h.update(memoryview(np.ascontiguousarray(a)).cast('B'))
            key=h.hexdigest();prior=self.entries.get(key)
            if path.exists() and path.stat().st_nlink>1:path.unlink()
            from .stage_common import record
            if prior and not path.exists():
                try:
                    source=Path(prior['path'])
                    if record(source)==prior:
                        path.parent.mkdir(parents=True,exist_ok=True);os.link(source,path)
                        self.links+=1;self.saved+=prior['bytes'];return
                except (OSError,ValueError):self.fallbacks+=1
            original(file,matrix,compressed=compressed);self.entries[key]=record(path)
        return save
    def report(self):
        return dict(scope='ONE_EXACT_CURRENT_A_CASE',linked_matrices=self.links,avoided_duplicate_bytes=self.saved,
            fallbacks=self.fallbacks,copy_on_write=True,lossless=True,all_raw_vectors_bounds_objectives_and_certificates_retained=True)
