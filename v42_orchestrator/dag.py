"""Reuse frozen scientific stage metadata, replacing only scheduling edges."""
import copy
import json
from datetime import date
from pathlib import Path

from v42_campaign.authority import GROUPS, MAIN, CONVERGENCE, digest, file_sha
from v42_campaign.plan import planning_stages, stage_id
from .config import Config, BASE_SHA

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / 'docs/v42_m1_cutpass_loop_campaign/MAY_CAMPAIGN_DRY_RUN_PLAN.json'


def load_dates(path=AUTHORITY):
    frozen = json.loads(Path(path).read_text(encoding='utf8'))
    days = frozen['days']
    parsed = [date.fromisoformat(day) for day in days]
    if (len(days) != 31 or len(set(days)) != 31 or parsed != sorted(parsed)
            or len({d.year for d in parsed}) != 1 or any(d.month != 5 for d in parsed)
            or [d.day for d in parsed] != list(range(1, 32))):
        raise ValueError("Frozen authority must contain exactly 31 ordered unique May dates")
    return tuple(days)


def build_dag(config=Config(), *, fixture_days=None):
    authoritative = load_dates()
    days = authoritative if fixture_days is None else tuple(fixture_days)
    if not days or len(set(days)) != len(days) or days != tuple(d for d in authoritative if d in days):
        raise ValueError("Synthetic fixtures must be an ordered subset of frozen authority")
    frozen = json.loads(AUTHORITY.read_text(encoding='utf8'))
    templates = {n['id']: n for n in frozen['nodes']}
    nodes = []
    previous_group = None
    for group in GROUPS:
        barrier = ([stage_id(previous_group, d, 'VALIDATION_FREEZE') for d in days]
                   if previous_group else [])
        if group == 'B3_L2':
            barrier = ['MAIN_MAY_CAMPAIGN_COMPLETE']
        for day in days:
            previous = None
            for stage in (*planning_stages(group), 'PLANNING_FREEZE', 'ACTUAL', 'FRESH_AC', 'VALIDATION_FREEZE'):
                node = copy.deepcopy(templates[stage_id(group, day, stage)])
                control = [previous] if previous else barrier[:]
                planning = list(node['Planning_dependencies'])
                if stage == 'PLANNING_FREEZE':
                    planning = [stage_id(group, day, s) for s in
                                (('A2', 'M2') if group.startswith('B3_') else planning_stages(group))]
                if stage in ('FRESH_AC', 'VALIDATION_FREEZE'):
                    control += [stage_id(group, day, 'PLANNING_FREEZE'), stage_id(group, day, 'ACTUAL')]
                node.update(control_dependencies=control, Planning_dependencies=planning,
                            required_pass=list(dict.fromkeys(control + planning)),
                            worker_class='coordinator' if not node['arm'] else f"{node['arm']}_DAY",
                            resource_slots=config.slots(node), execution_status='NOT_RUN')
                # Remove legacy sequential-all-days scheduler fields.
                for key in ('predecessor', 'required_accepted_freezes', 'output_freeze'):
                    node.pop(key, None)
                parts = [node['arm']] + ([f"L{node['loop']}"] if node['loop'] else []) + [day, stage]
                node['artifact_destination'] = '/'.join(['campaign', *parts])
                nodes.append(node)
                previous = node['id']
        if group == 'B3_L1':
            gate = copy.deepcopy(templates['MAIN_MAY_CAMPAIGN_COMPLETE'])
            required = [stage_id(g, d, 'VALIDATION_FREEZE') for g in MAIN for d in days]
            gate.update(control_dependencies=required, required_pass=required,
                        resource_slots=0, worker_class='coordinator',
                        artifact_destination='campaign/MAIN_MAY_CAMPAIGN_COMPLETE')
            for key in ('predecessor', 'required_accepted_freezes', 'output_freeze'):
                gate.pop(key, None)
            nodes.append(gate)
        previous_group = group
    plan = dict(days=list(days), nodes=nodes, main_order=list(MAIN), convergence_order=list(CONVERGENCE),
                scientific_sha=digest(dict(base=BASE_SHA, frozen_scientific_sha=frozen['authority_sha256'])),
                date_source=str(AUTHORITY.relative_to(ROOT)), date_source_sha=file_sha(AUTHORITY),
                synthetic_fixture=fixture_days is not None, production_executed=False)
    validate_dag(plan)
    return plan


def validate_dag(plan):
    seen = set()
    for node in plan['nodes']:
        if node['id'] in seen or not set(node['required_pass']) <= seen:
            raise ValueError("Duplicate, missing, or non-topological dependency")
        if node['planning'] or node['stage'] == 'PLANNING_FREEZE':
            for sid in node['Planning_dependencies']:
                source = next(n for n in plan['nodes'] if n['id'] == sid)
                if not (source['planning'] or source['stage'] == 'PLANNING_FREEZE'):
                    raise PermissionError("Actual must never feed Planning")
        seen.add(node['id'])


def select_results(results, *, convergence=False):
    """Main paper gets B3 L1 only; convergence study stores L2-L4 separately."""
    groups = CONVERGENCE if convergence else MAIN
    if any(group not in results for group in groups):
        raise ValueError('Incomplete result authority')
    return {group: copy.deepcopy(results[group]) for group in groups}


def planning_inputs(node, payloads):
    expected = set(node['Planning_dependencies'])
    if set(payloads) != expected:
        raise PermissionError("Undeclared/Actual Planning input")
    if any(p.get('producer_phase') != 'PLANNING' for p in payloads.values()):
        raise PermissionError("Actual/Fresh AC provenance cannot seed Planning")
    return copy.deepcopy(payloads)
