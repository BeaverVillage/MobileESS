"""Exact integer successive-shortest-path transportation (pure Python)."""
import heapq

def transport(supply,demand,edges):
    classes=sorted(supply);starts=sorted(demand);n=2+len(classes)+len(starts);S=0;T=n-1
    ids={key:i+1 for i,key in enumerate(classes)};times={key:1+len(classes)+i for i,key in enumerate(starts)}
    graph=[[] for _ in range(n)];refs={}
    def add(u,v,cap,cost):
        if type(cap) is not int or cap<0 or type(cost) is not int:raise ValueError('EXACT_INTEGER_FLOW_REQUIRED')
        a=[v,len(graph[v]),cap,cost];b=[u,len(graph[u]),0,-cost];graph[u].append(a);graph[v].append(b);return a
    total=sum(supply.values())
    if total!=sum(demand.values()):raise ValueError('BALANCED_TRANSPORT_REQUIRED')
    for key,mass in supply.items():add(S,ids[key],mass,0)
    for slot,mass in demand.items():add(times[slot],T,mass,0)
    for (key,slot),(cap,cost) in sorted(edges.items()):
        if cost<0:raise ValueError('INITIAL_COSTS_MUST_BE_NONNEGATIVE')
        refs[key,slot]=(add(ids[key],times[slot],cap,cost),cap,cost)
    sent=0;pot=[0]*n
    while sent<total:
        dist=[None]*n;prev=[None]*n;dist[S]=0;heap=[(0,S)]
        while heap:
            d,u=heapq.heappop(heap)
            if dist[u]!=d:continue
            for k,e in enumerate(graph[u]):
                v,rev,cap,cost=e
                if not cap:continue
                rc=cost+pot[u]-pot[v]
                if rc<0:raise ValueError('NEGATIVE_REDUCED_COST_IN_EXACT_FLOW')
                nd=d+rc
                if dist[v] is None or nd<dist[v]:dist[v]=nd;prev[v]=(u,k);heapq.heappush(heap,(nd,v))
        if dist[T] is None:raise ValueError('PRESERVED_OLD_ASSIGNMENT_NOT_IN_TRANSPORT_SUPPORT')
        for v,d in enumerate(dist):
            if d is not None:pot[v]+=d
        mass=total-sent;v=T
        while v!=S:
            u,k=prev[v];mass=min(mass,graph[u][k][2]);v=u
        v=T
        while v!=S:
            u,k=prev[v];e=graph[u][k];e[2]-=mass;graph[v][e[1]][2]+=mass;v=u
        sent+=mass
    flow={key:cap-e[2] for key,(e,cap,cost) in refs.items()};cost=sum(flow[key]*r[2] for key,r in refs.items())
    if any(sum(v for (c,t),v in flow.items() if c==key)!=mass for key,mass in supply.items()) or any(sum(v for (c,t),v in flow.items() if t==slot)!=mass for slot,mass in demand.items()):raise ValueError('EXACT_FLOW_MARGINALS_FAILED')
    return flow,cost
