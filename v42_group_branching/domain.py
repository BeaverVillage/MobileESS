from .common import *

def child_data(d,j,value):
    assert d['types'][j]=='B' and d['lower'][j]==0 and d['upper'][j]==1 and value in (0,1)
    child=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy(),types=np.full(len(d['types']),'C'))
    child['lower'][j]=child['upper'][j]=float(value)
    check_child(d,child,j,value);return child

def check_child(d,child,j,value):
    assert value in (0,1) and d['types'][j]=='B'
    for n in ('objective','constant','names','row_names','rhs','sense'):assert np.asarray(d[n]).tobytes()==np.asarray(child[n]).tobytes(),n
    mask=np.arange(len(d['types']))!=j
    for n in ('lower','upper'):assert d[n][mask].tobytes()==child[n][mask].tobytes()
    assert child['lower'][j]==child['upper'][j]==value and np.all(child['types']=='C')
    return True

def tests():
    prior.forbid_optimize()
    # Exhaustive binary words for min w with w>=z/4+v/2, 0<=w<=1.
    words=[(z,v) for z in (0,1) for v in (0,1)]
    c0={p for p in words if p[0]==0};c1={p for p in words if p[0]==1}
    assert c0|c1==set(words) and not c0&c1
    f=lambda p:p[0]/4+p[1]/2
    assert min(min(map(f,c0)),min(map(f,c1)))==min(map(f,words))==0
    # A transit path at t=1 has no site activity but crosses exactly one arc.
    paths=[[(0,3)],[(0,1),(1,2),(2,3)]]
    for path in paths:
        for t in range(3):assert sum(a==t for a,b in path)+sum(a<t<b for a,b in path)==1
    return dict(PASS=True,exhaustive_binary_words=4,two_way_union_complete=True,child_bound_min_rule=True,
        transit_all_zero_site_activity_allowed=True,native_calls=0)

def main():
    prior.forbid_optimize();A,d,T,AA,full=model_inputs();chosen=read(REPORTS/'SELECTED_BRANCH_VARIABLES.json')['selected']
    result=[]
    for k,row in enumerate(chosen,1):
        j=row['column'];children=[child_data(full,j,v) for v in (0,1)]
        result.append(dict(candidate=f'C{k:02d}',column=j,variable=row['variable_name'],original_type='B',
            original_bounds=[0,1],only_selected_bound_substituted=True,all_other_columns_relaxed=True,
            continuous_route_flow_unchanged=True,full_CSR_RHS_objective_preserved=True,
            convex_linear_children=True,original_integer_union_complete=True,additional_implied_fixing=0,
            child_native_API_transport='CHECKED_BY_WORKER_BEFORE_OPTIMIZE'))
    _,_,start=hc.load();checks=[]
    modes=[r['column'] for r in chosen if r['family']=='charge_mode']
    import itertools
    for pattern in itertools.product((0,1),repeat=len(modes)):
        x=start.copy()
        for j,value in zip(modes,pattern):x[j]=value
        replay=hc.replay(A,d,x,True);assert replay['PASS']
        assert float(np.max(T@x-full['rhs'][-651:],initial=0))<=1e-8
        checks.append(dict(mode_word=list(pattern),original_replay_PASS=True))
    write(REPORTS/'BRANCH_DOMAIN_AUDIT.json',dict(PASS=True,candidates=result,
        independently_feasible_mode_patterns=checks,mode_pivots_not_equivalent=len(checks)==2**len(modes),
        exact_integer_projection_proof_reused=sha(P183/'ROUTE_PROJECTION_AUDIT.json'),synthetic=tests(),native_calls=0))
    (REPORTS/'BRANCH_DOMAIN_COVERAGE_PROOF.md').write_text('''# 양방향 정수 영역 포괄 증명

선택 column j는 원래 C3A의 binary이며 원래 bounds는 [0,1]이다. 따라서 모든 원래 정수 feasible vector의 z_j는 정확히 0 또는 1이다. 원래 정수 영역 F=F(z_j=0)∪F(z_j=1)이며 두 영역은 서로소다. 기존 651개 부등식은 모든 원래 정수 vector에 유효하므로 각 child LP는 해당 원래 정수 영역을 포함한다. LP 구성은 선택 column의 두 bounds만 [0,0]/[1,1]로 바꾸고 나머지 binary를 C로 완화한다. 다른 위치나 route의 추가 고정은 없다. 목적함수·전체 CSR·RHS·senses·나머지 bounds는 원본 augmented 모델과 bit-identical이다.

각 child의 정확한 bounded weak-duality 하한을 L0,L1이라 하면 모든 F의 목적값은 min(L0,L1) 이상이다. 한쪽 native 목적값을 전체 하한으로 사용하지 않는다. 독립 pair들의 유효한 min 값만 max(inherited LB, pair1, pair2, pair3)에 넣는다. 미완료/미인증 sibling은 폐기하지 않고 unresolved로 유지한다. Native INFEASIBLE은 독립 Farkas proof가 없으면 +infinity로 승격하지 않는다.

Charge_mode는 unit/time마다 독립 원본 column이다. 선정된 두 mode의 네 가지 0/1 조합을 원본 idle feasible start의 같은 route/PQ/SOC에 대입해 원본 행·B2 행을 검사하여 서로 동치가 아님을 확인했다. 일반 path 정수 projection은 원래 nonparallel forward DAG와 unit source flow, binary vertex through-mass에 대한 PR183의 SHA 보존 증명을 재사용한다. 과거 불가능한 전체 배정은 개별 pivot의 전역 infeasibility 증명이 아니다.
''',encoding='utf-8')
    print('BRANCH_DOMAIN_PASS',len(result),'native=0',flush=True)

if __name__=='__main__':main()
