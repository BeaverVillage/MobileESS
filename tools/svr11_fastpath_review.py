"""Normalize only the byte-reviewed detached input and terminal fast paths."""
import ast,hashlib
HELPERS={
 '_forecast_setter_schedule':'a4ec65d8a220a652053773b0a2b1dee9086a35a6b839fb6bbd7726a30c40a8e5',
 '_apply_forecast_schedule':'f95512c9f7fef992a912c25104b0d3b6d11285c3b46f7f64e703de7c524e13b4',
 '_terminal_layout':'e568e5a831dd24ac52f46e502e72170912adca2dea67a917e1cf04a16b19f06a',
 '_terminal_values':'663ae1219b406054f09515519c813e0f14edef1b21bff321c14237a08f9aec4a'}
def signature(node):return ast.dump(node,include_attributes=False)
def normalize_exact_forecast_fastpath(text):
 tree=ast.parse(text);helpers={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in HELPERS}
 if not helpers:return text
 if set(helpers)!=set(HELPERS) or any(hashlib.sha256(signature(n).encode()).hexdigest()!=HELPERS[k] for k,n in helpers.items()):raise ValueError('REUSE_UNREVIEWED_FASTPATH_HELPER')
 removed=["load_names=tuple(e.Loads.AllNames())", "generator_names=tuple(e.Generators.AllNames())", "terminal_axis=_terminal_layout(e,branches)", "setter_schedule=_forecast_setter_schedule(native,totals_by_slot,bg,p,ad,load_names,generator_names,original.PF_TAN)", "if tuple(e.Loads.AllNames())!=load_names or tuple(e.Generators.AllNames())!=generator_names:\n raise PermissionError('SVR11_FORECAST_SETTER_INVENTORY_DRIFT')"]
 replacements={signature(ast.parse("_apply_forecast_schedule(e,setter_schedule[t])").body[0]):ast.parse("_apply_forecast_native(e,native,totals_by_slot,t)\noriginal._set_slot(e,{**ad,'loads':[]},bg,p,t)").body,signature(ast.parse("a=_terminal_values(e,terminal_axis,len(branches))").body[0]):ast.parse("pq=[original._terminal_phase(e,b.branch_id,b.parent_bus,b.phase) for b in branches]\na=np.asarray(pq)").body}
 allowed={signature(ast.parse(s).body[0]) for s in removed};counts={s:0 for s in allowed|set(replacements)}
 class Reviewed(ast.NodeTransformer):
  def visit_FunctionDef(self,node):return None if node.name in HELPERS else self.generic_visit(node)
  def visit_Assign(self,node):return self.exact(node)
  def visit_Expr(self,node):return self.exact(node)
  def visit_If(self,node):return self.exact(node)
  def exact(self,node):
   s=signature(node)
   if s in allowed:counts[s]+=1;return None
   if s in replacements:counts[s]+=1;return replacements[s]
   return self.generic_visit(node)
 result=Reviewed().visit(tree)
 if any(v!=1 for v in counts.values()):raise ValueError('REUSE_UNREVIEWED_FASTPATH_WIRING')
 return ast.unparse(ast.fix_missing_locations(result))
