"""Active original rows, exact full Phi, and semantic remapping after expansion.

This adapter reuses restricted(), certified_separate(), elastic_master(), and
the original inclusion/zero/replay proofs. It never promotes every row merely
because a number of rounds or a column expansion has occurred.
"""
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from time import perf_counter
import hashlib,inspect,linecache,textwrap
import numpy as np
from v44.common import atomic,now
from v42_a_stage_phase1.core import primal_replay,verify_zero


def exact_phi(master,point):
    """Identical rational sum, without constructing Fraction(0) for zero terms."""
    x=np.asarray(point)[master.original.matrix.shape[1]:]
    return sum((master.weights[int(j)]*Fraction(float(x[j])) for j in np.flatnonzero(x)),Fraction(0))


class IdentityCatalog:
    """Resolve only active rows; avoid 690k Python tuples and digest objects."""
    def __init__(self,state):
        self.state=state;self.count=len(state['grows']);self.atlas=state['atlas']
        self.resources={int(row):('RESOURCE',tuple(key)) for key,row in state['axes'].items()}
        self.reverse_resource={identity:row for row,identity in self.resources.items()}
        if len(self.reverse_resource)!=len(self.resources):raise ValueError('R028_DUPLICATE_RESOURCE_IDENTITY')
        self.nodes={str(node):i for i,node in enumerate(self.atlas.get('node_names',()))}
    def __len__(self):return self.count
    def __getitem__(self,row):
        if row in self.resources:return self.resources[row]
        family=str(self.atlas['rf_names'][self.atlas['rf'][row]])
        if family in ('voltage_lower','voltage_upper'):
            rows=self.atlas[family+'_rows'];position=int(np.searchsorted(rows,row))
            if position>=len(rows) or rows[position]!=row or not self.nodes:raise ValueError('R028_VOLTAGE_ORIGINAL_ROW_IDENTITY')
            slot,node=divmod(position,len(self.nodes))
            return (family,slot+24,str(self.atlas['node_names'][node]))
        return ('ORIGINAL_GLOBAL_ROW',family,int(self.state['grows'][row]))
    def resolve(self,identity):
        if identity[0]=='RESOURCE':row=self.reverse_resource[identity]
        elif identity[0] in ('voltage_lower','voltage_upper'):
            row=int(self.atlas[identity[0]+'_rows'][(identity[1]-24)*len(self.nodes)+self.nodes[identity[2]]])
        else:row=int(identity[2])
        if not 0<=row<self.count or self[row]!=identity:raise ValueError('R028_ACTIVE_SEMANTIC_ROW_UNMAPPED')
        return row


def row_identities(state):
    """Hash all original global-column bytes; resolve source identities lazily.

    G is the immutable selected-original-global prefix emitted by the existing
    assembler. A changed order/physics without a verified mapping fails closed.
    Resource/voltage identities additionally carry their site/slot/node axes.
    All new local rows are retained independently of old local numeric indices.
    """
    s=state['compact'];G=state['grows'];n=state['n'];atlas=state['atlas']
    if tuple(G)!=tuple(range(len(G))):raise ValueError('R028_ORIGINAL_GLOBAL_PREFIX_AUTHORITY_REQUIRED')
    if len(atlas['rf'])!=len(G):raise ValueError('R028_ORIGINAL_GLOBAL_FAMILY_AXIS')
    catalog=IdentityCatalog(state);prefix=s.matrix[:len(G),:n].tocsr();digest=hashlib.sha256()
    digest.update(repr((prefix.shape,tuple(map(str,atlas['rf_names'])),tuple(map(str,atlas.get('node_names',()))))).encode())
    for value in (prefix.indptr,prefix.indices,prefix.data,s.senses[:len(G)],s.rhs[:len(G)],s.lower[:n],s.upper[:n],s.vtypes[:n],atlas['rf'],
                  atlas.get('voltage_lower_rows',np.zeros(0)),atlas.get('voltage_upper_rows',np.zeros(0))):
        array=np.asarray(value);digest.update(str((array.shape,array.dtype.str)).encode());digest.update(array.tobytes())
    # Bind every resource's semantic identity to its exact original global
    # terms, including those resource rows not currently active in the LP.
    for identity,row in sorted(catalog.reverse_resource.items()):
        a,b=prefix.indptr[row:row+2];digest.update(repr(identity).encode())
        for array in (prefix.indices[a:b],prefix.data[a:b]):digest.update(array.tobytes())
        digest.update(repr((str(s.senses[row]),float(s.rhs[row]).hex())).encode())
    return catalog,digest.hexdigest()


class ActiveRows:
    def __init__(self,state,included,fullmaster):
        self.identities,self.authority=row_identities(state)
        self.state=state;self.full=fullmaster;self.included=set(map(int,included))
        self.included.update(range(len(state['grows']),state['compact'].matrix.shape[0]))
        self.batch=256;self.row_rounds=0;self.seed=None;self.previous_phi=None
        self._index_artificials()

    def _index_artificials(self):
        self.locations={};counts=defaultdict(int)
        for j,row in enumerate(self.full.artificial_rows):
            self.locations[row,counts[row]]=j;counts[row]+=1

    def prepare_native(self,native,master,rows):
        # The restricted row/artifical axes change. Re-admit a separately
        # projected, original-replayed feasible point for this exact snapshot.
        native.seed=None
        if self.seed is None:return
        n=self.state['compact'].matrix.shape[1];point=np.zeros(master.snapshot.matrix.shape[1]);point[:n]=self.seed[:n]
        counts=defaultdict(int)
        for j,row in enumerate(master.artificial_rows):
            source=rows[row];k=counts[source];counts[source]+=1
            point[n+j]=self.seed[n+self.locations[source,k]]
        native.admit_prior(master.snapshot,point)

    def evaluate(self,master,rows,raw,make_point):
        n=self.state['compact'].matrix.shape[1]
        # A separate lift constructs omitted-row residual artificials, then
        # copies every included artificial from raw X without clipping it.
        fullpoint=make_point(self.full,raw['X'][:n]);counts=defaultdict(int)
        for j,row in enumerate(master.artificial_rows):
            source=rows[row];k=counts[source];counts[source]+=1
            fullpoint[n+self.locations[source,k]]=raw['X'][n+j]
        replay=primal_replay(self.full.snapshot,fullpoint)
        if not replay['PASS']:raise ValueError('R028_FULL_ELASTIC_RAW_LIFT_REPLAY_FAILED')
        phi=exact_phi(self.full,fullpoint);contributions=defaultdict(Fraction)
        for j in np.flatnonzero(fullpoint[n:]):
            contributions[self.full.artificial_rows[int(j)]]+=self.full.weights[int(j)]*Fraction(float(fullpoint[n+j]))
        self.seed=fullpoint.copy()
        zero=verify_zero(self.full,fullpoint)
        return dict(Phi=phi,restricted_Phi=exact_phi(master,raw['X']),point=fullpoint,
                    contributions=contributions,zero=zero,full_elastic_replay=replay)

    def add_rows(self,separation,evaluation,folder):
        violated=set(separation['violated_rows'])-self.included
        positive={int(i) for i,v in evaluation['contributions'].items() if v>0 and i not in self.included}
        candidates=violated|positive
        if not candidates:return False
        phi=evaluation['Phi']
        if self.row_rounds and (self.previous_phi is None or phi>=self.previous_phi*Fraction(99,100)):
            self.batch=min(self.batch*2,16384)
        elif self.row_rounds and self.row_rounds%4==0:self.batch=min(self.batch*2,16384)
        self.previous_phi=phi;self.row_rounds+=1
        selected=sorted(candidates,key=lambda i:(i not in violated,-evaluation['contributions'].get(i,Fraction(0)),i))[:self.batch]
        if not selected:raise ValueError('R028_ROW_GENERATION_WITHOUT_PROGRESS')
        before=len(self.included);self.included.update(selected)
        atomic(Path(folder)/'R028_ROW_ADDITION.json',dict(UTC=now(),PASS=True,before=before,after=len(self.included),
            selected_rows=selected,selected_semantic_identities=[self.identities[i] for i in selected],
            omitted_violations=len(violated),omitted_positive_artificial_rows=len(positive),adaptive_batch=self.batch,
            exact_full_Phi=str(phi),restricted_Phi=str(evaluation['restricted_Phi']),
            all_omitted_original_rows_evaluated=True,forced_all_rows=False,duplicate_additions=0))
        return True

    def rebind(self,new,fullmaster,point,folder):
        identities,authority=row_identities(new)
        if authority!=self.authority:
            raise ValueError('R028_GLOBAL_SEMANTIC_OR_FIXED_PHYSICS_DRIFT')
        active={self.identities[i] for i in self.included if i<len(self.identities)}
        global_rows={identities.resolve(identity) for identity in active}
        hard=set(range(len(new['grows']),new['compact'].matrix.shape[0]))
        hard.update(new['axes'].values())
        old_columns=self.state['compact'].matrix.shape[1]
        self.state=new;self.full=fullmaster;self.identities=identities;self.authority=authority
        self.included=global_rows|hard;self.seed=np.asarray(point).copy();self._index_artificials()
        if not primal_replay(fullmaster.snapshot,self.seed)['PASS']:raise ValueError('R028_REBOUND_FULL_PRIOR_POINT_INVALID')
        atomic(Path(folder)/'R028_ACTIVE_ROW_MAPPING.json',dict(UTC=now(),PASS=True,
            active_global_rows_before=len(active),active_global_rows_after=len(global_rows),
            all_active_semantic_identities_preserved=True,original_global_coefficients_and_senses_RHS_exactly_preserved=True,
            new_global_support_coefficients_rechecked_by_full_prior_inclusion=True,
            all_new_local_hard_rows_retained=len(hard),active_rows=len(self.included),full_rows=new['compact'].matrix.shape[0],
            old_original_columns=old_columns,new_original_columns=new['compact'].matrix.shape[1],
            active_semantic_sha=hashlib.sha256(repr(sorted(active,key=repr)).encode()).hexdigest(),forced_all_rows=False))


def compile_phase(function,namespace):
    """Keep the original certified P1 body verbatim; adapt only Phase I routing."""
    source=textwrap.dedent(inspect.getsource(function))
    def replace(old,new):
        nonlocal source
        if source.count(old)!=1:raise ValueError('R028_PHASE_SOURCE_BOUNDARY_DRIFT:'+old[:90])
        source=source.replace(old,new)
    replace("    if certified_zero_point is not None:\n", "    rowgen=_R028ActiveRows(state,included,full);del full,p\n    if certified_zero_point is not None:\n")
    replace("        rec,raw=native.solve(master.snapshot,f,'PHASE_I')", "        rowgen.prepare_native(native,master,rows)\n        rec,raw=native.solve(master.snapshot,f,'PHASE_I')")
    replace("        x=raw['X'][:s.matrix.shape[1]];sep=certified_separate(s,x,included);Phi=phase_objective(master,raw['X'])", "        x=raw['X'][:s.matrix.shape[1]];sep=certified_separate(s,x,included)\n        evaluated=rowgen.evaluate(master,rows,raw,artificial_point);Phi=evaluated['Phi']")
    replace("        if not sep['PASS']:\n            included.update(sep['violated_rows'])\n            if len(phase_traces)>=POLICY['row_promotion_after']:included=set(range(s.matrix.shape[0]))\n            continue\n        allmaster=elastic_master(s,G);fullpoint=artificial_point(allmaster,x);zero=verify_zero(allmaster,fullpoint)", "        atomic(f/'R028_FULL_PHI.json',dict(PASS=True,exact_full_Phi=str(Phi),full_Phi=float(Phi),restricted_Phi=str(evaluated['restricted_Phi']),full_elastic_replay=evaluated['full_elastic_replay'],full_zero=evaluated['zero'],active_rows=len(included),full_rows=s.matrix.shape[0],original_columns=s.matrix.shape[1],artificial_columns=len(master.artificial_rows),omitted_rows_fully_scanned=True))\n        if (not sep['PASS'] or not evaluated['zero']['PASS']) and rowgen.add_rows(sep,evaluated,f):\n            included=set(rowgen.included);continue\n        if not sep['PASS']:raise ValueError('R028_UNADDED_OMITTED_ORIGINAL_VIOLATION')\n        allmaster=rowgen.full;fullpoint=evaluated['point'];zero=evaluated['zero']")
    replace("        ex=expanded_point(state,x);em=elastic_master(state['reference'],G);ep=artificial_point(em,ex)", "        ex=expanded_point(state,x);em=elastic_master(state['reference'],G);ep=np.r_[ex,fullpoint[s.matrix.shape[1]:]]\n        if not primal_replay(em.snapshot,ep)['PASS']:raise ValueError('R028_EXPANDED_ORIGINAL_FULL_RAW_LIFT_FAILED')")
    replace("        state=new;activation_round+=1;included=set(range(new['compact'].matrix.shape[0]))", "        rowgen.rebind(new,fullnew,included_point,f)\n        state=new;activation_round+=1;included=set(rowgen.included)")
    namespace.update(_R028ActiveRows=ActiveRows,phase_objective=exact_phi)
    filename=__file__+'.phase.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    exec(compile(source,filename,'exec'),namespace)
    return namespace['run']
