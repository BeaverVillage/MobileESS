"""Bindings to the unmodified IEEE123 compiler and original physical backend."""
def original_bindings():
    from v42_regcontrol import authority
    from v42_regcontrol.runner import background
    from v42_may_campaign_native90.operations import isolated_compile
    from v42_may_campaign_native90.preflight import native_zero
    authority.source()
    from dayahead.v28r2 import opendss_backend as backend, opendss_mapping as mapping
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from v42_regcontrol.common import CODE
    return authority,background,isolated_compile,native_zero,backend,mapping,FrozenTrajectory,CODE
