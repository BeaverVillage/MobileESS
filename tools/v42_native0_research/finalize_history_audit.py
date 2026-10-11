"""Combine read-only primary PR/source history into the Source19 receipt."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
OUT=Path(r'D:\v42_multitime_audit_20261011')
REPO=Path(r'D:\v42_svr11_epoch18r_20261011')
ATTACHMENT=Path(r'C:\Users\kjw39\.codex\attachments\c67fcc1b-f7bf-49a5-b0b5-5ff665e5367e\붙여넣은 텍스트.txt')
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def record(path):return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))
def git(*args):return subprocess.check_output(['git',*args],cwd=REPO,text=True,encoding='utf-8').strip()
descriptions={
109:dict(candidate='Aggregate connected charge/discharge mode hull and per-arc energy-flow extension',
 code=[('v42_relaxation/strengthening.py',12,28)],
 finding='Local mode cuts and the energy-flow extension preserved integer physics but their historical material-gain gate failed; per-arc energy lifting increased solve cost. Fractional location/mode witnesses alone did not establish objective cause.',
 implication='Do not repeat aggregate mode rows or per-arc full-horizon energy lifting as the current objective experiment.'),
110:dict(candidate='Single-slot location-conditioned grid epigraph',
 code=[('v42_epigraph/oracle.py',24,41)],
 finding='O1 retained only non-transformer P1 line faces at one slot and dropped voltage, transformer and every other-time grid row. Complete conditional upper witnesses certified no useful epigraph coefficients under that weak oracle.',
 implication='This stopping proof does not reject current full-grid temporal coupling; a new candidate must keep current stored original grid authority and rebound.'),
111:dict(candidate='Seven-slot W7 state/pair epigraph and two-time route support',
 code=[('v42_window/grid.py',14,20),('v42_window/reachability.py',55,58)],
 finding='Only registered slots40–46 retained grid rows, allowing travel repayment outside the window; historical objective stress lay outside. Pure DAG-flow path decomposition already implied the supported two-time marginals. No useful epigraph row was installed.',
 implication='Do not transplant window40–46 or pure reachable-pair transport. Static current line/window selection must be independent of historical duals.'),
137:dict(candidate='Connected C/D aggregate cuts; route-state SOC envelopes; per-arc SOC flow',
 code=[('v42_strengthening/cuts.py',9,18),('v42_strengthening/envelopes.py',31,69),('v42_strengthening/envelopes.py',99,124),('v42_strengthening/flow.py',25,43)],
 finding='Aggregate C+D and exact route-state SOC envelopes had historical violations but no material objective gain. The SOC-flow EF added207928 continuous columns,443344 rows and2559730 NNZ; its full LP did not complete at its cap.',
 implication='Integer-only SOC envelope diagnostics are not LP-safe prescreening. Current Source18 deliberately adopted none; simple SOC sums remain LP implied.'),
167:dict(candidate='Connected-power and folded PCS-mode local hulls',
 code=[('docs/v42_m1_root_gap_attribution_20261007/folded_pcs_hull.py',51,69)],
 finding='Exact integer-state union PCS hulls added320 rows/17837NNZ in ten historical cut loops, with no material certified gain. Selective integrality did not isolate the cause; strict raw feasibility limitations were preserved.',
 implication='Per-stay integer-mode PCS support is a known local hull ingredient, not a new temporal proof. Any current direction-specific support must be freshly compared to actual fractional stay rows and connected to current thermal objective.'),
169:dict(candidate='Four-slot complete route/mode/PQ/SOC hull and controlled two-block extension',
 code=[('docs/v42_m1_gap_rootcause_20261007/trajectory_hull.py',65,90),('docs/v42_m1_gap_rootcause_20261007/mode_coordinate_audit.py',23,32)],
 finding='149817 mobility paths times16 mode words yielded2397072 local patterns. Boundary SOC remained free, so this was not the96-slot global hull. A separator could be removed by changing only an objective-zero mode coordinate with all P/Q/route/SOC coordinates fixed. Historical verified UB improvement also showed incumbent choice contributed to the gap.',
 implication='Do not enumerate complete local trajectories or infer LB impact from mode-coordinate separation. Preserve global terminal SOC and relocation/recharge alternatives.'),
182:dict(candidate='Fleet/window count Balas EF and Boolean-product RLT',
 code=[('docs/v42_m1_joint_formulation_20261008/formulations.py',49,53),('docs/v42_m1_joint_formulation_20261008/formulations.py',77,103)],
 finding='A added133254 columns/312931rows; B added225952columns/1001388rows. Both600s ROOT runs failed optimal completion/material certified improvement; incomplete points were not promoted to bounds.',
 implication='Both sizes greatly violate the new sparse256-row/0.5% NNZ scope. No full-size replay or EF copy is justified.'),
185:dict(candidate='Physical master closure, cumulative SOC substitution and route endpoint cuts',
 code=[('v42_physics_redesign/structure.py',33,73),('v42_physics_redesign/cumulative.py',3,61),('v42_physics_redesign/temporal.py',44,52)],
 finding='Pure physical master is weaker; restoring full original grid returns the original LP. Cumulative SOC is LP identical and predicts25937190 NNZ despite removing380SOC columns. All651 archived selected cuts are ARRIVAL_SOC_REACHABILITY, from795944 screened candidates.',
 implication='No651 transplantation or dense cumulative elimination. Endpoint energy implications omit joint interval service/PCS and may never affect the current critical objective.'),
186:dict(candidate='May12 A-stage activation/pricing rescue',code=[],
 finding='Artificial-free Phase-I witness activation and full-domain STAY/migration pricing address the A-stage P1 implementation, not MESS Multi-Time formulation.',
 implication='Relevant to preservation of legitimate actions, but supplies no M route/SOC strengthening.'),
187:dict(candidate='Validation of historical651 route/SOC cuts',code=[],
 finding='Historical B2_ROOT_NONMATERIAL. All651 rows satisfied, none active at tested thresholds; no certified valid-bound improvement. Historical native objective variation did not establish an improvement.',
 implication='Do not repeat the archived selected set or reuse its numerical results/points as current evidence.')}
recent=read(OUT/'PR185_187_RECENT_HISTORY_AUDIT.json')
primary=[]
for number,item in descriptions.items():
 if number<185:
  path=OUT/f'PR{number}_PRIMARY_HISTORY.json';meta=read(path)
  p=dict(pr=number,title=meta['title'],url=meta['url'],head=meta['headRefOid'],primary=record(path),
    body_read=True,primary_diff_reviewed=True,selected_diff_files=len(meta['primary_selected_file_diffs']))
 else:
  previous=next(x for x in recent['primary_sources'] if x['pr']==number)
  p=dict(pr=number,url=previous['url'],head=previous['head'],primary=record(OUT/previous['body_saved']),
    body_read=True,primary_diff_reviewed=True,diff_method=previous['diff_review'])
 p.update(item);p['source_evidence']=[]
 for name,start,end in item['code']:
  current=REPO/name
  evidence=dict(path=name,start=start,end=end,url=f"https://github.com/BeaverVillage/MobileESS/blob/{p['head']}/{name}#L{start}",
    current_path_exists=current.exists())
  if number==111:
   path=OUT/('PR111_'+Path(name).name+'.source.txt');method='GitHub Contents at exact PR head; local commit object absent, no fetch/mutation'
  elif number<185:
   path=OUT/(f'PR{number}_'+name.replace('/','__')+'.source.txt');method='Local git show at exact PR head'
  else:path=None;method='Recent independent agent local git show and primary diff'
  evidence['method']=method
  if path is not None:
   evidence['historical_source']=record(path)
   evidence['current_file_SHA']=sha(current) if current.exists() else None
   evidence['historical_file_identical_current']=current.exists() and sha(current)==sha(path)
  p['source_evidence'].append(evidence)
 primary.append(p)

theorem='If each per-stay relief-minus-energy term is bounded using existing fractional control/PCS rows, and travel/terminal/rebound energy uses a linear Lagrange combination of existing SOC equalities/bounds, whole-horizon additive DAG DP adds no LP strength. Set terminal potentials0 and p(v)=max_a(r_a+p(head(a))). Then r_a<=p(tail(a))-p(head(a)); multiplying by nonnegative route flows and summing telescopes to the source potential under existing flow conservation. Adding the per-stay and SOC row bounds proves the candidate for every existing fractional LP point.'
receipt=dict(schema='V42_SOURCE19_MULTITIME_PRIMARY_HISTORY_AUDIT_V1',UTC=datetime.now(timezone.utc).isoformat(),PASS=True,
 repository=str(REPO),base_git_head=git('rev-parse','HEAD'),base_execution_source_SHA='146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8',
 git_status=git('status','--porcelain=v1'),attachment=record(ATTACHMENT),attachment_read_entire=True,
 required_PRs=list(descriptions),primary_history=primary,recent_independent_audit=record(OUT/'PR185_187_RECENT_HISTORY_AUDIT.json'),
 current_baseline=dict(rows=715596,columns=354277,binaries=9322,nnz=7911369,Root_complete=False,
   completed_LP_point_available=False,current_native_LB_reported_by_parent=0.289400491085489,
   current_gap_percent_reported_by_parent=57.19266,
   interpretation='Current parent-reported bound/gap belongs only to fresh Phase18 repaired source. No historical bound or LP vector is used as current comparison.'),
 user_limits=dict(max_added_rows=256,max_added_NNZ_fraction=.005,max_added_NNZ_integer=39556,
   new_binaries=0,full_size_MILP_optimize_calls=0,full_size_repeated_LP_calls=0,
   full_size_LP_measurement_currently_authorized=False,reason='Latest Root failed completion at600s; user disallows meaningless120s comparison and repeat600s.'),
 current_source_differences=[
   'Current B2/B3 use fresh May01 Forecast/SVR11/grid/battery/route authority and exact Original->Compact->pre-C2 security->C2->C3A->Dense transport, not historical raw axes or frozen old root points.',
   'Dense response is an exact affine extension/projection and changes no LP or integer domain. Physical backward/SOC adoption is0; legitimate continuous route flow and binary node/mode variables remain.',
   'Current native MESS retains net-P PCS16, individual connected Pch/Pdis and binary-mode bounds, actual0.25-slot efficiency coefficients, whole travel debit atdepart+1, and original terminal SOC. Optional legacy strengthening hook defaultsNone and is not enabled by current constructor.',
   'The old research packages for PR137/167/169/182/185 are not current production wiring. PR109/110 source directories remain as legacy reference but their study oracles are not the current model.',
   'No completed current LP point exists; current fractional node/mode/route violations and objective-dual window cannot be inferred from old studies.'
 ],
 candidate_implications=dict(reject_pure_route_marginal=True,reject_SOC_sum_only=True,reject_651_copy=True,reject_large_EF=True,
   additive_DAG_energy_price_LP_implication_theorem=theorem,
   possible_nonredundant_ingredient='Only if exact integer-mode/connected PCS support is strictly smaller than the actual fractional stay relaxation, or another freshly proved integer temporal implication is used, can the bound strengthen LP. Integer-mode union support is already the PR167 local-hull family; objective-directed current coupling and new independent validity/redundancy checks are essential.',
   next_scope='One CURRENT stored thermal line and one interval, selected statically from current sensitivity and physical support, with whole96slot terminal/recharge/travel preserved. No old critical slot, LP point or cut selected set.',
   current_actual_violation='UNPROVEN_NO_COMPLETED_CURRENT_LP_POINT',current_LB_improvement='UNPROVEN',history_adoption='NONE'),
 operations=dict(Native_calls=0,model_builds=0,old_LP_point_ingestion=0,old_LB_values_reused_as_current=0,
   copied_651_cut_payload=0,full_path_enumerations=0,candidate_generation_or_adoption=0,
   source_edits=0,Git_mutations=0,campaign_HOLD=True,Supervisor_and_schedules_reenabled=False),
 conclusion='HISTORY_AUDIT_COMPLETE_MULTITIME_TIGHTENING_LB_UNPROVEN')
receipt['PASS']=not receipt['git_status'] and receipt['base_git_head']=='497609b46faa14ea7e32a9483a333ab32fd264ef'
path=OUT/'SOURCE19_MULTITIME_HISTORY_RECEIPT.json';path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
lines=['# Source19 Multi-Time primary history audit','',
 'Required history audit complete. Primary GitHub bodies/diffs for PR109–111/137/167/169/182/185–187 and exact-head source were reviewed. No repository mutation, Native, model build, archived LP-point read, cut transplant or candidate generation occurred. Current Root remains incomplete; full-size Multi-Time Native is0.','',
 '| PR | What failed or was redundant | Current implication |','|---|---|---|']
for p in primary:lines.append(f"| [{p['pr']}]({p['url']}) | {p['finding']} | {p['implication']} |")
lines+=['','The proposed whole-horizon DP/energy-price support must first be checked for LP implication:', '',theorem,'',
 receipt['candidate_implications']['possible_nonredundant_ingredient'],'',
 'Current source changes justify fresh static analysis, not reuse of old performance: exact Dense extension and Physical prescreen0 preserve the current LP; all current grid rows,0.25-slot energy coefficients, terminal SOC, recharge/relocation/Q actions remain. There is no completed current LP point, so actual violation and LB improvement are unproven.','',
 'Start only with one current stored thermal line and one interval. Maximum256 added rows,0 binaries, and39,556 added NNZ under the0.5% selected-matrix cap. No full-path enumeration, automatic cut loop, huge EF,651copy, Root600 rerun or full-size Native is authorized.','',
 f"Base HEAD `{receipt['base_git_head']}`; execution SHA `{receipt['base_execution_source_SHA']}`. Primary evidence and exact-head source/line references are recorded in `SOURCE19_MULTITIME_HISTORY_RECEIPT.json`. PR111 commit object is not in local Git; its exact-head primary GitHub Contents and file diffs were reviewed without fetching into the repository. Historical LB values are confined to original primary documents and are not used as current bounds.",'',
 'Final history-stage classification: `HISTORY_AUDIT_COMPLETE_MULTITIME_TIGHTENING_LB_UNPROVEN`. No tightening adopted; campaign HOLD.','']
path.with_suffix('.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
print(json.dumps(dict(PASS=receipt['PASS'],PRs=len(primary),path=str(path))))
