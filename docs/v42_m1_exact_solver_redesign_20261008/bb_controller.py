"""Solver-independent, deterministic exact-coverage best-bound controller.

Only a proof-validated oracle result can prune. Expanded nodes are represented
by BOTH children. Unresolved leaves remain OPEN and preserve their inherited LB.
"""
import hashlib,json,os
from fractions import Fraction
from pathlib import Path

def rational(x):return x if isinstance(x,Fraction) else Fraction(str(x))
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
def digest(x):return hashlib.sha256(canonical(x)).hexdigest()
def history_hash(history):return digest(sorted([int(j),int(v)] for j,v in history))

class ExactBB:
    VERSION=1
    def __init__(self,identity,lower,upper,incumbent):
        lower=str(rational(lower));upper=str(rational(upper));assert rational(lower)<=rational(upper)
        root=dict(id=0,parent=None,depth=0,branch_variable=None,branch_value=None,fixings=[],fixing_hash=history_hash([]),LB=lower,inherited_LB=lower,state='OPEN',processed=False,children=[],prune_reason=None)
        self.state=dict(version=self.VERSION,identity=identity,UB=upper,incumbent=incumbent,nodes={'0':root},next_id=1,processed=0,ledger=[],in_flight=None,pruning_tolerance='0')
    @classmethod
    def load(cls,path,identity):
        envelope=json.loads(Path(path).read_text(encoding='utf-8'));s=envelope['state']
        assert digest(s)==envelope['SHA256'],'CHECKPOINT_DIGEST_FAILURE'
        assert s['version']==cls.VERSION and s['identity']==identity,'CHECKPOINT_AUTHORITY_FAILURE'
        obj=cls.__new__(cls);obj.state=s;obj.audit();return obj
    def save(self,path):
        self.audit();path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
        data=dict(SHA256=digest(self.state),state=self.state)
        with tmp.open('w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    def select(self):
        eligible=[n for n in self.state['nodes'].values() if n['state']=='OPEN' and not n['processed']]
        return min(eligible,key=lambda n:(rational(n['LB']),n['depth'],n['id'])) if eligible else None
    def begin(self,node):
        assert self.state['in_flight'] in (None,node['id']);assert node['state']=='OPEN' and not node['processed'];self.state['in_flight']=node['id']
    def apply(self,node_id,result):
        s=self.state;n=s['nodes'][str(node_id)]
        assert s['in_flight']==node_id and not n['processed']
        assert result['fixing_hash']==n['fixing_hash'] and result['identity']==s['identity']
        assert result['proof_checked'], 'ORACLE_PROOF_VALIDATION_REQUIRED'
        status=result['LP_status'];cert=result.get('certified_LB');witness=result.get('witness')
        if witness is not None:
            assert witness['PASS'] and witness['full_original_replay_PASS'] and witness['raw_vector_unchanged']
            value=rational(witness['objective_exact'])
            if value<rational(s['UB']):s['UB']=str(value);s['incumbent']=witness
        if status=='OPTIMAL':
            assert cert is not None and result['optimal_LP_certificate_PASS'];n['LP_certified_LB']=str(rational(cert));n['LB']=str(max(rational(n['inherited_LB']),rational(cert)))
        if status=='INFEASIBLE' and result.get('exact_infeasibility_PASS'):
            n['state']='FATHOMED';n['prune_reason']='EXACT_LP_INFEASIBILITY'
        elif status=='OPTIMAL' and rational(n['LB'])>=rational(s['UB']):
            n['state']='FATHOMED';n['prune_reason']='INTEGER_REPLAY_PASS_AND_CERTIFIED_OPTIMUM' if witness is not None else 'CERTIFIED_LB_AT_LEAST_VALIDATED_UB'
        elif status=='OPTIMAL' and result.get('branch_variable') is not None:
            j=int(result['branch_variable']);assert j not in dict(n['fixings']);assert result['branch_is_original_binary']
            assert result['raw_fractional_branch_value'] not in (0,1)
            for v in (0,1):
                i=s['next_id'];s['next_id']+=1;fixings=n['fixings']+[[j,v]]
                child=dict(id=i,parent=n['id'],depth=n['depth']+1,branch_variable=j,branch_value=v,fixings=fixings,fixing_hash=history_hash(fixings),LB=n['LB'],inherited_LB=n['LB'],state='OPEN',processed=False,children=[],prune_reason=None)
                s['nodes'][str(i)]=child;n['children'].append(i)
            n['state']='EXPANDED';n['prune_reason']=None
        else:
            # No proof can silently remove this domain, including numerical or
            # integer-witness results that lack an exact node optimality proof.
            n['state']='OPEN';n['prune_reason']='UNRESOLVED_PROOF_RETAINED_OPEN'
        n['processed']=True;n['receipt']=result.get('receipt');n['result_digest']=digest(result)
        row=dict(result,node_id=node_id,parent=n['parent'],depth=n['depth'],node_branch_variable=n['branch_variable'],node_branch_value=n['branch_value'],effective_LB=n['LB'],state=n['state'],prune_reason=n['prune_reason'],children=n['children'].copy(),UB_after=s['UB'])
        s['ledger'].append(row);s['processed']+=1;s['in_flight']=None;self.audit();return row
    def audit(self):
        s=self.state;nodes=s['nodes'];assert int(s['next_id'])==len(nodes)
        assert set(nodes)=={str(i) for i in range(s['next_id'])}
        assert len(s['ledger'])==s['processed']==sum(n['processed'] for n in nodes.values())
        visited=set();open_ids=[];terminal_ids=[];expanded=0
        def visit(i):
            nonlocal expanded
            assert i not in visited;visited.add(i);n=nodes[str(i)]
            assert n['id']==i and n['fixing_hash']==history_hash(n['fixings'])
            assert len(dict(n['fixings']))==len(n['fixings']) and all(v in (0,1) for j,v in n['fixings'])
            assert rational(n['LB'])>=rational(n['inherited_LB'])
            if n['state']=='EXPANDED':
                expanded+=1;assert n['processed'] and len(n['children'])==2 and n['prune_reason'] is None
                children=[nodes[str(c)] for c in n['children']];assert {c['branch_value'] for c in children}=={0,1}
                assert len({c['branch_variable'] for c in children})==1
                for c in children:
                    assert c['parent']==i and c['depth']==n['depth']+1
                    assert c['fixings']==n['fixings']+[[c['branch_variable'],c['branch_value']]]
                    assert c['inherited_LB']==n['LB'];visit(c['id'])
            elif n['state']=='FATHOMED':
                assert n['processed'] and not n['children']
                assert n['prune_reason'] in ('EXACT_LP_INFEASIBILITY','CERTIFIED_LB_AT_LEAST_VALIDATED_UB','INTEGER_REPLAY_PASS_AND_CERTIFIED_OPTIMUM');terminal_ids.append(i)
                if n['prune_reason']!='EXACT_LP_INFEASIBILITY':assert rational(n['LB'])>=rational(s['UB'])
            else:
                assert n['state']=='OPEN' and not n['children'];open_ids.append(i)
                if n['processed']:assert n['prune_reason']=='UNRESOLVED_PROOF_RETAINED_OPEN'
        visit(0);assert len(visited)==len(nodes),'UNCOVERED_GENERATED_DOMAIN'
        if s['in_flight'] is not None:assert s['in_flight'] in open_ids
        lower=min((rational(nodes[str(i)]['LB']) for i in open_ids),default=rational(s['UB']))
        return dict(PASS=True,complete_root_partition=True,expanded_parents_have_both_children=True,generated=len(nodes),expanded=expanded,OPEN=open_ids,exactly_fathomed=terminal_ids,unresolved_OPEN=[i for i in open_ids if nodes[str(i)]['processed']],global_OPEN_min_LB_exact=str(lower),validated_UB_exact=s['UB'],global_gap=float((rational(s['UB'])-min(lower,rational(s['UB'])))/rational(s['UB'])) if rational(s['UB']) else 0,all_other_generated_leaves_exactly_fathomed=True,global_bound_authority='Complete binary partitions, exact terminal certificates, inherited valid bounds; min over ALL OPEN leaves including unsolved/unresolved/in-flight leaves')
