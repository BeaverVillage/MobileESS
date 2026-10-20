"""Serial preparation and seven independent Actual/Fresh processes."""
from importlib import import_module

# Legacy packages re-export their parent's names. Load each real submodule
# explicitly so a cached parent ``operations`` attribute cannot select r036
# when the requested dependency is r037.
for _revision in range(29,38):
    _package=import_module(f'v44_recovery_r{_revision:03d}')
    _module=import_module(f'v44_recovery_r{_revision:03d}.operations')
    _package.operations=_module
