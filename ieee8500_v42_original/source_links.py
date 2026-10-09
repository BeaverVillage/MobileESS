"""Original entry points, resolved only after the IEEE8500 hold gate.

These bindings prepare call paths; they do not establish grid integration or
authorize calls. B3's independent original production gate remains unchanged.
"""
from importlib import import_module
from .hold import require_execution_approval

SOURCE_HEADS = {
    'PR198': 'b34feffdcf11e076378f63e2aab05d9ea2f2014b',
    'PR191': '40b6f94dcd80e470f93c73b7479fdd2d9d91c3f2',
    'PR189': '625bbcb8b9a54a00c1660c26d96f7737c2f75457',
    'PR199': '23c3643681e38c8b3cf16f2d02686a78c4570cc7',
}

ENTRY_POINTS = {
    'B1_A': ('v42_may_build_v6.a_stage', 'run'),
    'B2_V19': ('v42_b2_seed_recovery_v19.m_stage', 'run'),
    'V19_INITIALIZATION': ('v42_b2_seed_recovery_v19.initialization', 'initialize'),
    'M_FULL_COMPACT_C3A': ('v42_may_campaign_native90.m_model', 'build_case'),
    'M_NATIVE': ('v42_native.mess', 'solve'),
    'A_NATIVE': ('v42_native.aidc', 'solve'),
    'ADAPTIVE': ('v42_m1_anytime.core', 'schedule_choice'),
    'PRICING': ('v42_m1_hybrid.pricing', 'run_pricing'),
    'RMP': ('v42_m1_hybrid.dw', 'run'),
    'STRICT_UB': ('v42_m1_research.check_ub', 'validate_candidate'),
    'EXACT_LB': ('v42_m1_research.check_lb', 'check_rational_dual_certificate'),
    'B3_A_BRIDGE': ('v42_b3_joint.a_source', 'ASourceBridge'),
    'B3_M_BRIDGE': ('v42_b3_joint.m_source', 'MSourceBridge'),
}


def call_original(component, *args, **kwargs):
    # The gate is first, even before component validation or scientific imports.
    require_execution_approval('ORIGINAL_CALL:' + str(component))
    module, symbol = ENTRY_POINTS[component]
    return getattr(import_module(module), symbol)(*args, **kwargs)
