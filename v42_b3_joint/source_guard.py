"""Scoped compatibility for original backstop and B3 execution identities.

This runs only in the isolated B3 process after source admission. Original
functions and imported aliases are restored on exit, including exceptions.
No B1/B2 context, manifest or process is entered or modified.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import RLock
import sys

from .contracts import require

_active = ContextVar("b3_source_guard_aliases", default=None)
_lock = RLock()


class SourceGuardAliases:
    def __init__(self, context, module):
        self.context, self.registry, self.module = context, context.source_registry, module
        self.saved = []
        self.keys = set()
        self.original = {name: getattr(module, name) for name in
            ("require_action_authorized", "guard_model_optimize", "tag_model_for_day")}
        self.replacements = {"require_action_authorized": self.authorize,
                             "guard_model_optimize": self.registry.guard,
                             "tag_model_for_day": self.tag}

    def authorize(self, authority, action="OPTIMIZE", *, require_day=True):
        require(action in {"OPTIMIZE", "P1", "A1", "M1", "A2", "M2", "PHASE_I",
            "FEASIBILITY_LP", "FEASIBILITY_MIP", "PLANNING_FREEZE", "ACTUAL", "FRESH_AC"},
            "B3_P2_OR_UNKNOWN_SOURCE_ACTION_FORBIDDEN")
        day = self.module.day_from_authority(authority)
        require(day == self.context.request.authority.day or day is None and not require_day,
                "B3_SOURCE_GUARD_AUTHORITY_DAY_DRIFT")
        self.registry.admit(self.context, "ORIGINAL_GUARD_" + action)
        return self.context.request.authority.day

    def tag(self, model, authority, *, require_day=True):
        self.authorize(authority, "OPTIMIZE", require_day=require_day)
        old = getattr(model, "_v42_a_stage_day", None)
        day = self.context.request.authority.day
        require(old is None or old == day, "B3_SOURCE_MODEL_DATE_DRIFT")
        model._v42_a_stage_day = day
        return model

    def route(self, module):
        namespace = vars(module)
        for key, value in list(namespace.items()):
            for name, original in self.original.items():
                if value is original or value is self.replacements[name]:
                    identity = (id(namespace), key)
                    if identity not in self.keys:
                        self.saved.append((namespace, key, original))
                        self.keys.add(identity)
                    namespace[key] = self.replacements[name]

    def restore(self):
        for namespace, key, original in reversed(self.saved):
            namespace[key] = original
        require(all(namespace[key] is original for namespace, key, original in self.saved),
                "B3_SOURCE_GUARD_RESTORATION_FAILED")


def route_resolved_module(module):
    current = _active.get()
    if current is not None:
        current.route(module)
        # Transitive imports may copy an already-routed export. Save those
        # aliases too so the next stage/date cannot retain this context.
        for name, loaded in list(sys.modules.items()):
            if name.startswith("v42_") and not name.startswith("v42_b3_joint") and loaded is not None:
                current.route(loaded)


@contextmanager
def compatibility_scope(context):
    current = _active.get()
    if current is not None:
        require(current.context is context, "B3_GUARD_NESTED_CONTEXT_DRIFT")
        yield
        return
    registry = context.source_registry
    registry.admit(context, "SOURCE_GUARD_ROUTING")
    with _lock:
        module = registry.resolve("v42_a_stage_domain_v2.execution")
        aliases = SourceGuardAliases(context, module)
        token = _active.set(aliases)
        try:
            for name, loaded in list(sys.modules.items()):
                if name.startswith("v42_") and not name.startswith("v42_b3_joint") and loaded is not None:
                    aliases.route(loaded)
            aliases.route(module)
            yield
        finally:
            route_resolved_module(module)
            aliases.restore()
            _active.reset(token)
