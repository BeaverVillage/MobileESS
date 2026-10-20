"""Exact sparse assembly without one global-row CSR allocation per class."""
import inspect
import textwrap
import numpy as np
import scipy.sparse as sp


class CouplingParts:
    def __init__(self, prefix):
        self.prefix=prefix
        self.width=0
        self.data=[];self.rows=[];self.columns=[]

    def append(self, block, positions):
        coo=block.tocoo()
        self.data.append(coo.data)
        self.rows.append(positions[coo.row])
        self.columns.append(coo.col.astype(np.int64)+self.width)
        self.width+=block.shape[1]

    def matrix(self):
        if not self.data:return self.prefix.copy()
        coupling=sp.csr_matrix((np.concatenate(self.data),
            (np.concatenate(self.rows),np.concatenate(self.columns))),
            shape=(self.prefix.shape[0],self.width))
        return sp.hstack((self.prefix,coupling),format='csr')


def substitute(source, old, new, label):
    if source.count(old)!=1:raise RuntimeError('R029_ASSEMBLY_SOURCE_DRIFT:'+label)
    return source.replace(old,new)


def compile_reference(function, native_block):
    source=textwrap.dedent(inspect.getsource(function))
    source=substitute(source,
        "    global_parts=[base.matrix[grows,:global_variables].tocsr()]",
        "    global_parts=CouplingParts(base.matrix[grows,:global_variables].tocsr())\n"
        "    axis_positions=np.asarray([global_position[value] for value in axes.values()],dtype=np.int64)",
        'reference_axes')
    source=substitute(source,
        "        coo=B.tocoo()\n"
        "        expanded=sp.csr_matrix((coo.data,([global_position[list(axes.values())[i]] for i in coo.row],coo.col)),\n"
        "            shape=(len(grows),block.matrix.shape[1]))\n"
        "        global_parts.append(expanded)",
        "        global_parts.append(B,axis_positions)",'reference_coupling')
    source=substitute(source,"sp.hstack(global_parts,format='csr')","global_parts.matrix()",'reference_stack')
    namespace=dict(function.__globals__,native_block=native_block,CouplingParts=CouplingParts)
    exec(compile(source,__file__+'.reference.generated','exec'),namespace)
    return namespace[function.__name__]


def compact_source(source):
    source=substitute(source,"global_parts=[base.matrix[list(grows),:n].tocsr()]",
        "global_parts=CouplingParts(base.matrix[list(grows),:n].tocsr())",'compact_parts')
    source=substitute(source,"    for key,members in sorted(data[7]['classes'].items()):",
        "    axis_positions=np.asarray(tuple(axes.values()),dtype=np.int64)\n"
        "    for key,members in sorted(data[7]['classes'].items()):",'compact_axes')
    source=substitute(source,
        "global_parts.append(sp.csr_matrix((coo.data,([list(axes.values())[i] for i in coo.row],coo.col)),shape=(len(grows),snap.matrix.shape[1])))",
        "global_parts.append(B,axis_positions)",'compact_coupling')
    return substitute(source,"sp.hstack(global_parts,format='csr')","global_parts.matrix()",'compact_stack')
