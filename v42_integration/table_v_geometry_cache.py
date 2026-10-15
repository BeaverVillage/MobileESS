"""Additive geometry cache routing; original physics and UID proofs are retained.

The native window receipt SHA proves lineage, while the validated numerical
window remains in the cache key. No scientific class or matrix is regrouped.
This module does not install itself into an executing/frozen production case.
"""
from dataclasses import asdict
from types import FunctionType

from . import a_engine
from v42_native.service import NativeServiceBoundary

VERSION = 'TABLE_V_GEOMETRY_NUMERICAL_WINDOW_CACHE_V1'


def _geometry_asdict(value):
    fields = asdict(value)
    if type(value) is NativeServiceBoundary:
        # The original authorized_geometry calls require() before constructing
        # its key. Keep every numerical field and the duration authority.
        fields.pop('window_authority_sha256')
    return fields


def _bind(function, **bindings):
    namespace = dict(function.__globals__, **bindings)
    routed = FunctionType(function.__code__, namespace, function.__name__,
                          function.__defaults__, function.__closure__)
    routed.__kwdefaults__ = function.__kwdefaults__
    return routed


# Function-local namespaces avoid changing the original module or an active
# worker's globals. The original hit path reseals each UID's domain SHA.
authorized_geometry = _bind(a_engine.authorized_geometry, asdict=_geometry_asdict)
authorized_data = _bind(a_engine.authorized_data, authorized_geometry=authorized_geometry)
