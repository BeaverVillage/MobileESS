"""Compile-only differential projection of original V41R4 joint model.

Electrical rows are excluded, never replaced by a fictitious passing feeder.
This is a structural audit model, not an executable production optimizer.
"""
import ast,copy,inspect,hashlib,json,math,time
from collections import defaultdict
from pathlib import Path
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from frozen_binding import ROOT,HOME,save,read,record,option_reader
from dayahead.v40g import optimizer
from dayahead.v41r1 import feasible_seed

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(x):return hashlib.sha256(canonical(x)).hexdigest()
def expr(e):
    if isinstance(e,(int,float,np.number)):return dict(constant=float(e),terms=[])
    if isinstance(e,gp.Var):return dict(constant=0.,terms=[(e.VarName,1.)])
    d=defaultdict(float)
    for i in range(e.size()):d[e.getVar(i).VarName]+=float(e.getCoeff(i))
    return dict(constant=float(e.getConstant()),terms=sorted((k,v) for k,v in d.items() if v))

def export(model,ctx,scope):
    model.update();vs=model.getVars();names=model.getAttr('VarName',vs)
    modelvars=[(v.VarName,v.VType,float(v.LB),float(v.UB)) for v in vs if v.VarName!='rho_max']
    expressions=[scope['reserve_mean'],scope['migration'],scope['dev'],scope['tie']]
    objective=[expr(e) for e in expressions]
    matrix=model.getA().tocsr();constraints=model.getConstrs();linear=hashlib.sha256();wan=hashlib.sha256()
    for i,c in enumerate(constraints):
        a,b=matrix.indptr[i:i+2];terms=[(names[int(j)],float(v)) for j,v in zip(matrix.indices[a:b],matrix.data[a:b])]
        row=(c.ConstrName,c.Sense,float(c.RHS),terms);raw=canonical(row)+b'\n';linear.update(raw)
        if any(n.startswith(('WAN_','migration_','placement[')) for n,_ in terms):wan.update(raw)
    general=hashlib.sha256();types=defaultdict(int)
    for c in model.getGenConstrs():
        kind=c.GenConstrType;types[str(kind)]+=1
        if kind==GRB.GENCONSTR_PWL:
            a,b,x,y=model.getGenConstrPWL(c);v=[a.VarName,b.VarName,x,y]
        elif kind==GRB.GENCONSTR_MAX:
            result,args,constant=model.getGenConstrMax(c);v=[result.VarName,[a.VarName for a in args],constant]
        elif kind==GRB.GENCONSTR_INDICATOR:
            flag,value,expression,sense,rhs=model.getGenConstrIndicator(c);v=[flag.VarName,value,expr(expression),sense,rhs]
        else:raise AssertionError(('UNSUPPORTED_GENERAL_CONSTRAINT',kind))
        general.update(canonical([c.GenConstrName,kind,v])+b'\n')
    cohort=[dict(members=scope['groups'][key],frozen_P5_rank=scope['original_ranks'][key[:6]]) for key in scope['keys']]
    # Build the original no-optional-move seed's non-electrical fields only.
    # Original row_audit and job_audit are called, not optimize or AC.
    physical,power=feasible_seed.job_audit(ctx.jobs,ctx)
    assert physical['status']=='PASS'
    from dayahead.v41.reserve import diagnostics
    from dayahead.v41r1.migration import checkpoints
    fill={}
    for t in range(96):
        for k,s in enumerate(ctx.capacity.aidc_ids):fill[f'GPU[{t},{s}]']=power['gpu'][t,k];fill[f'PCC[{t},{s}]']=power['pcc'][t,k]
    reserve=diagnostics(ctx.v41_ml_snapshot,ctx.capacity,power['gpu'])
    for k,v in enumerate(reserve['xi_GPUh']):fill[f'V41_H4_shortfall_GPUh[{k}]']=v
    for row in ctx.reference:
        cp=checkpoints(row,ctx.elapsed)
        if cp:fill['WAN_ready_'+row['job_uid']]=max(26,cp[0])
        fill['WAN_selected_'+row['job_uid']]=0;fill['WAN_cursor_'+row['job_uid']]=26
    fill['rho_max']=0. # Excluded abstract electrical port; no physical P1 claim.
    seed=np.asarray(model.getAttr('Start',vs),dtype=float)
    for i,v in enumerate(vs):
        if v.VarName in fill:seed[i]=fill[v.VarName]
        elif v.VarName.startswith('migration_source['):seed[i]=0.
        assert math.isfinite(seed[i]) and abs(seed[i])<GRB.UNDEFINED,v.VarName
    seed_audit=feasible_seed.row_audit(model,seed);assert seed_audit['status']=='PASS',seed_audit
    snapshot=dict(variable_count=len(modelvars),linear_constraints=model.NumConstrs,general_constraints=model.NumGenConstrs,matrix_nonzeros=int(model.NumNZs),decision_variable_sha256=digest(modelvars),linear_rows_sha256=linear.hexdigest(),WAN_migration_linear_rows_sha256=wan.hexdigest(),general_rows_sha256=general.hexdigest(),general_types=dict(types),P2_P3_P4_P5_sha256=[digest(o) for o in objective],P5_cohort_rank_sha256=digest(cohort),cohort_count=len(cohort),candidate_counts=dict(scope['domain_counts']),seed_non_electrical_sha256=digest([(n,float(x)) for n,x in zip(names,seed) if n!='rho_max']),seed_audit=seed_audit,seed_physical_job_audit=physical,status='NON_ELECTRICAL_PROJECTION_PASS',grid_rows='EXCLUDED_AUTHORIZED_ELECTRICAL_DIFFERENCE',optimization_calls=0)
    save(ctx.audit_label+'/STRUCTURE.json',snapshot)
    save(ctx.audit_label+'/P2_P3_P4_P5.json',objective)
    save(ctx.audit_label+'/P5_COHORT_RANKS.json',cohort)
    save(ctx.audit_label+'/DECISION_VARIABLES.json',modelvars)
    np.savez_compressed(HOME/ctx.audit_label/'B0_REFERENCE_NON_ELECTRICAL_SEED.npz',names=np.asarray(names),values=seed)
    return snapshot

def compile_projection(ctx,label,source_override=None,namespace_override=None):
    source=source_override or inspect.getsource(optimizer.solve);tree=ast.parse(source);fn=tree.body[0]
    # Slice the exact source through the original P2 construction; exclude all
    # electrical assembly, seed export and optimization entry points.
    removed=[]
    def note(node,why):removed.append(dict(reason=why,source=ast.get_source_segment(source,node)))
    body=[]
    for node in fn.body:
        if isinstance(node,ast.Try):
            prefix=[]
            for n in node.body:
                if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='grid_rows' for x in ast.walk(n.targets[0])):
                    note(n,'AUTHORIZED_ELECTRICAL_DIFFERENCE');prefix+=ast.parse("rho=model.addVar(lb=0,ub=1,name='rho_max')").body;continue
                if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and n.value.func.attr=='setObjective':break
                prefix.append(n)
            prefix+=ast.parse('model.update()\nreturn audit_export(model,context,locals())').body
            node.body=prefix;node.handlers=[];node.orelse=[];body.append(node);break
        if isinstance(node,ast.FunctionDef) and node.name in ('evaluate','optimize','callback','solution_value'):
            note(node,'NONEXECUTED_ELECTRICAL_OR_SOLVE_HELPER');continue
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='before' for t in node.targets):note(node,'AUTHORIZED_ELECTRICAL_DIFFERENCE');continue
        if isinstance(node,ast.Assert) and 'before' in ast.unparse(node):note(node,'NO_ELECTRICAL_FEASIBILITY_CLAIM');continue
        if isinstance(node,ast.If) and "if bounded:"==ast.unparse(node).splitlines()[0] and 'CandidateManifest' in ast.unparse(node):
            note(node,'FROZEN_OPTIONS_ALREADY_BYTE_VERIFIED_NO_REGENERATION');continue
        # Gurobi cannot write to the resolved non-ASCII target of this junction.
        for call in ast.walk(node):
            if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=='resolve':call.func.attr='absolute'
        body.append(node)
    fn.body=body;ast.fix_missing_locations(tree)
    namespace=dict(optimizer.solve.__globals__,options=option_reader(ctx),audit_export=export)
    namespace.update(namespace_override or {})
    exec(compile(tree,str(HOME/'structural_projection.py')+'::original_model_projection','exec'),namespace)
    ctx.audit_label=label
    from v41r4_ieee8500_adapter import electrical_port_contract
    ports=tuple(r['control_name'] for r in electrical_port_contract()['control_axis'])
    ctx.coefficients=tuple(type('ElectricalControlPort',(),{'control_names':ports})() for _ in range(96))
    save(label+'/PROJECTION_REMOVALS.json',removed)
    save(label+'/PROJECTION_SOURCE_IDENTITY.json',dict(original=record(ROOT/'dayahead/v40g/optimizer.py'),projection_AST_sha256=hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),original_non_electrical_AST_preserved=True,scope='AUDIT_ONLY_NO_GRID_OR_OPTIMIZATION'))
    return namespace['solve'](ctx.reference,ctx.power['pcc'],ctx,HOME/label,build_only=True)
