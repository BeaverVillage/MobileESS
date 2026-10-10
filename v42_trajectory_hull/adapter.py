"""Stage-local bridge for selected legacy CG admission and stabilization mechanics."""
from fractions import Fraction as F
from hashlib import sha256
from types import FunctionType
import json
import numpy as np
from . import legacy_mechanics as legacy
from .case import file_sha
from .budget import write
from v42_m1_research.check_ub import matrix_replay, vector_sha


def axis_sha(axis):
    return sha256(np.asarray(axis,dtype='<i8').tobytes()).hexdigest()


def exact_price(point, price):
    return sum((F(q)*F(float(point[int(j)])) for j,q in price.items()),F(0))


def strict_admission(block,point,axis):
    if not np.array_equal(axis,block.original_columns):
        raise ValueError('COLUMN_ORIGINAL_AXIS_DRIFT')
    replay=matrix_replay(block.A,block.d,point)
    replay['PASS']=bool(replay['PASS'] and replay['integer_pattern_exact'] and replay['exact_binary_0_1'])
    return replay


class BlockAdapter:
    def __init__(self,case,block,source_rows):
        self.block=block;self.unit=block.unit;self.columns=block.original_columns
        self.d=block.d;self.B=case.A[source_rows][:,self.columns].tocsr()
        self.true_price={};self.eta=F(0)

    def validate(self,x,integer):
        return strict_admission(self.block,x,self.columns)

    def column(self,x):
        return self.B@x,float(self.d['objective']@x),vector_sha(x)

    def exact_coupling(self,x,a):
        exact={};error=0.
        for i in np.flatnonzero(abs(self.B)@abs(x)):
            lo,hi=self.B.indptr[i:i+2]
            value=sum((F(float(v))*F(float(x[j])) for j,v in
                       zip(self.B.indices[lo:hi],self.B.data[lo:hi])),F(0))
            if value:exact[int(i)]=value
            error=max(error,abs(float(value-F(float(a[i])))))
        return exact,error


class Pool:
    def __init__(self,adapter,catalog):
        self.adapter=adapter;self.catalog=catalog
    def add(self,m,x,a,c,key):
        owner=self.adapter;block=owner.blocks[m]
        # The unchanged legacy method has already saved its source packet.
        file=owner.output/'columns'/('COLUMN_%06d_%s.npz'%(owner.column_id-1,block.unit))
        with np.load(file,allow_pickle=False) as z:data=dict(z)
        data.update(point=x,original_columns=block.columns)
        np.savez_compressed(file,**data)
        self.catalog[block.unit].append(dict(path=str(file),sha256=file_sha(file),
            admission=block.validate(x,True),point_sha=key,case_sha=owner.case.case_sha,
            variable_axis_sha=axis_sha(block.columns),feasibility='NUMERICAL_ONLY'))


class CGAdapter:
    """Original legacy add/smooth methods run against current axes and authority."""
    def __init__(self,case,decomp,source_rows,catalog,output):
        self.case=case;self.decomp=decomp;self.output=output;self.source_rows=source_rows
        expected=np.sort(np.concatenate((decomp.nonunit_block.original_rows,decomp.coupling_rows)))
        if not np.array_equal(source_rows,expected):raise ValueError('MASTER_ORIGINAL_ROW_AXIS_DRIFT')
        (output/'columns').mkdir(parents=True,exist_ok=True)
        self.blocks=[BlockAdapter(case,b,source_rows) for b in decomp.units.values()]
        self.master=Pool(self,catalog);self.persistent_selected=False
        self.seen=[{vector_sha(case.point[b.columns])} for b in self.blocks]
        for k,b in enumerate(self.blocks):
            for item in catalog[b.unit]:
                if file_sha(item['path'])!=item['sha256']:raise ValueError('CHECKPOINT_COLUMN_BYTE_DRIFT')
                with np.load(item['path'],allow_pickle=False) as z:
                    strict=strict_admission(b.block,z['point'],z['original_columns'])
                    if not strict['PASS']:raise ValueError('CHECKPOINT_COLUMN_DOMAIN_FAIL')
                    self.seen[k].add(vector_sha(z['point']))
        self.columns=[];self.column_id=0;self.current_round=0
        self.smooth_weight=.30;self.smooth_pi=self.smooth_conv=None
        self.last_true_pi=None;self.smoothing_rows=[]
        def rc(block,x,pi,alpha):
            # Old M1 +/-1 coefficient shortcut is intentionally not imported.
            return exact_price(x,block.true_price)-F(float(alpha))
        env=dict(legacy.__dict__,OUT=output,ROOT=output.parents[2],EPS=1e-8,
                 DISCOVERY_RC=0.,exact_rc=rc,next_smoothing_weight=legacy.next_smoothing_weight)
        self._add=FunctionType(legacy.add.__code__,env)
        self._smooth=FunctionType(legacy.smooth_snapshot.__code__,env)

    def bind_true_prices(self,prices,eta):
        for b in self.blocks:
            b.true_price={str(j):str(q) for j,q in prices.exact_objectives[b.unit].items()}
            b.eta=F(eta[b.unit])

    def smooth(self,pi,eta):
        key=sha256(pi.tobytes()+eta.tobytes()).hexdigest()
        self._smooth(self,(pi,eta,key,''))
        return self.smooth_pi.copy(),self.smooth_conv.copy()

    def admit(self,m,path):
        block=self.blocks[m]
        with np.load(path,allow_pickle=False) as z:
            x=z['point'];axis=z['original_columns']
        replay=strict_admission(block.block,x,axis)
        true_rc=exact_price(x,block.true_price)-block.eta;key=vector_sha(x)
        info=dict(unit=block.unit,path=str(path),point_sha=key,local=replay,
                  exact_true_RC=str(true_rc),true_RC=float(true_rc),duplicate=key in self.seen[m],
                  axis_sha=axis_sha(axis),feasibility='NUMERICAL_ONLY_NOT_EXACT_MEMBERSHIP')
        projected=block.B@x
        comparisons=[('ORIGINAL_UB_SEED',self.case.point[block.columns])]
        for item in self.master.catalog[block.unit]:
            with np.load(item['path'],allow_pickle=False) as cached:
                previous=cached['point']
            digest=vector_sha(previous)
            if 'point_sha' in item and item['point_sha']!=digest:
                raise ValueError('CACHED_COLUMN_POINT_SHA_DRIFT')
            comparisons.append((digest,previous))
        info['grid_projection_comparisons']=[dict(point_sha=digest,
             max_abs_difference=float(np.max(abs(projected-block.B@previous),initial=0.)),
             numerical_similarity_only=True) for digest,previous in comparisons]
        info['projection_pruning_authority']=False
        if not replay['PASS'] or true_rc>=0 or info['duplicate']:
            info['added']=False;return info
        alias=self.output/('CANDIDATE_%d_%d.npz'%(self.current_round,m))
        np.savez_compressed(alias,x=x,axis=axis)
        record=dict(type='DISCOVERY',valid_negative=True,rc_inc=float(true_rc),unit=m,
                    point_file=str(alias),full_original_local=replay,call=self.current_round,
                    native_status='STORED_OR_NATIVE_DISCOVERY',round=self.current_round)
        # Absolute point_file is accepted by pathlib's OUT / absolute operation.
        info['added']=self._add(self,record,np.array([]),
                                np.array([float(b.eta) for b in self.blocks]))
        return info


def checkpoint(adapter,budget,path,case_identity,dual_file):
    catalog=adapter.master.catalog
    payload=dict(case_identity=case_identity,source_rows_sha=axis_sha(adapter.source_rows),
        variable_axes={b.unit:axis_sha(b.columns) for b in adapter.blocks},catalog=catalog,
        dual_file=str(dual_file),dual_sha=file_sha(dual_file),round=adapter.current_round,
        calls=budget.calls,measured_native_seconds=budget.used,smooth_weight=adapter.smooth_weight,
        smooth_file=str(adapter.output/adapter.smooth_file),
        smooth_sha=file_sha(adapter.output/adapter.smooth_file))
    write(path,payload)


def validate_checkpoint(path,case_identity,decomp):
    from .case import read
    cp=read(path)
    if cp['case_identity']!=case_identity:raise ValueError('CHECKPOINT_CASE_MATRIX_DOMAIN_DRIFT')
    if file_sha(cp['dual_file'])!=cp['dual_sha']:raise ValueError('CHECKPOINT_DUAL_DRIFT')
    if file_sha(cp['smooth_file'])!=cp['smooth_sha']:raise ValueError('CHECKPOINT_SMOOTH_DRIFT')
    if sum(c['Runtime'] for c in cp['calls'])!=cp['measured_native_seconds']:
        raise ValueError('CHECKPOINT_NATIVE_BUDGET_DRIFT')
    expected=np.sort(np.concatenate((decomp.nonunit_block.original_rows,decomp.coupling_rows)))
    if cp['source_rows_sha']!=axis_sha(expected):raise ValueError('CHECKPOINT_ROW_AXIS_DRIFT')
    for u,b in decomp.units.items():
        if cp['variable_axes'][u]!=axis_sha(b.original_columns):raise ValueError('CHECKPOINT_AXIS_DRIFT')
        for item in cp['catalog'][u]:
            if file_sha(item['path'])!=item['sha256']:raise ValueError('CHECKPOINT_COLUMN_DRIFT')
    return cp
