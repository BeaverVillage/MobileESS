"""Bind the exact frozen C1 implementation without changing its computation."""
import importlib
import importlib.util
import sys
from pathlib import Path

from v42_campaign.authority import file_sha


def bind_frozen_c1(spec):
    from v42_capacity.common import resolve
    from v42_regcontrol.authority import source
    source()
    target = resolve(spec['power']['C1_implementation']).resolve()
    expected = next(r for r in spec['frozen_sources'] if resolve(r).resolve() == target)
    if file_sha(target) != expected['sha256']:
        raise PermissionError('Frozen C1 source hash mismatch')
    name = 'dayahead.v28r2.c1_affine'
    previous = importlib.import_module(name)
    previous_path = Path(previous.__file__).resolve()
    # The grid package and C1 source have independent frozen path authorities.
    module_spec = importlib.util.spec_from_file_location(name, target)
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    module_spec.loader.exec_module(module)
    setattr(importlib.import_module('dayahead.v28r2'), 'c1_affine', module)
    if Path(module.__file__).resolve() != target:
        raise PermissionError('Frozen C1 exact path binding failed')
    return dict(exact_path=str(target), sha256=file_sha(target),
                prior_package_path=str(previous_path),
                prior_package_bytes_equal=file_sha(previous_path) == file_sha(target),
                scientific_source_modified=False)
