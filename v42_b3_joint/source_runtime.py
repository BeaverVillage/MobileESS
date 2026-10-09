"""Guarded source API registry and shared real-stage execution interfaces.

Source functions are reused with isolated lexical/AST routing, never patched in
the B1/B2 process or files. The production permit remains closed in this version.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
import ast
import hashlib
import importlib
import json
import re

from .contracts import Authority, AIDCDecision, MESSDecision, StageRequest, canonical, digest, require, require_sha
from .policy import parameters, require_production_authorization

_current = ContextVar("v42_b3_real_source_context", default=None)
_native = ContextVar("v42_b3_ledgered_native_model", default=None)


def source_input_identity(folder):
    """Canonical identity for the original two source-owned input packets."""
    folder = Path(folder).resolve()
    receipts = {}
    documents = {}
    for name in ("NATIVE_INPUT.json", "WINDOWS.json"):
        path = folder / name
        require(path.is_file(), "ORIGINAL_INPUT_PACKET_REQUIRED")
        raw = path.read_bytes()
        receipts[name] = hashlib.sha256(raw).hexdigest()
        documents[name] = json.loads(raw.decode("utf-8-sig"))
    return {"input_sha": digest(receipts), "receipts": receipts,
            "bundle": documents["NATIVE_INPUT.json"], "windows": documents["WINDOWS.json"],
            "basis": "ORIGINAL_NATIVE_INPUT_AND_WINDOWS_BYTES_SHA256"}


def jsonable(value):
    if value is None or type(value) in (bool, int, float, str):
        return value
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return jsonable(value.tolist())
    if isinstance(value, SimpleNamespace):
        return jsonable(vars(value))
    raise ValueError("SOURCE_PACKET_SERIALIZABLE_STATE_REQUIRED:" + type(value).__name__)


@dataclass(frozen=True)
class RealStageContext:
    request: StageRequest
    input_folder: Path
    output: Path
    original_bundle_json: str
    source_registry: object
    grid_authority: object
    source_packets: dict
    producer_source_sha: str
    run_id: str

    def __post_init__(self):
        require(isinstance(self.request, StageRequest), "REAL_STAGE_REQUEST_REQUIRED")
        object.__setattr__(self, "input_folder", Path(self.input_folder).resolve())
        object.__setattr__(self, "output", Path(self.output).resolve())
        object.__setattr__(self, "original_bundle_json", canonical(json.loads(self.original_bundle_json)))
        require_sha(self.producer_source_sha)
        require(isinstance(self.run_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.run_id), "B3_RUN_ID_REQUIRED")
        self.verify_identity()

    @property
    def original_bundle(self):
        return json.loads(self.original_bundle_json)

    def verify_identity(self):
        bundle = self.original_bundle
        require(bundle.get("day") == self.request.authority.day, "SOURCE_BUNDLE_DAY_DRIFT")
        require(self.producer_source_sha == self.request.authority.source_sha, "SOURCE_PRODUCER_SHA_DRIFT")
        require(self.input_folder != self.output and not self.input_folder.is_relative_to(self.output)
                and not self.output.is_relative_to(self.input_folder), "B3_SOURCE_INPUT_OUTPUT_SEPARATION_REQUIRED")
        active = Path("D:/MobileESS_v42").resolve()
        require(not self.output.is_relative_to(active), "B1_B2_OUTPUT_WRITE_FORBIDDEN")
        registry = self.source_registry
        if not isinstance(registry, FakeSourceRegistry):
            workspace = Path(__file__).resolve().parents[1]
            require(self.output.is_relative_to(workspace / "runtime" / "b3"), "ISOLATED_B3_RUNTIME_OUTPUT_REQUIRED")
        require(isinstance(self.source_packets, dict), "SOURCE_HANDOFF_PACKETS_REQUIRED")
        return True

    @property
    def identity(self):
        return {"stage": self.request.stage, "day": self.request.authority.day, "arm": "B3",
                "run_id": self.run_id, "authority_sha": self.request.authority.sha,
                "input_sha": self.request.authority.input_sha, "request_sha": self.request.request_sha,
                "fixed_input_sha": self.request.fixed_input_sha, "source_sha": self.producer_source_sha}


class SourceRegistry:
    evidence_kind = "SOURCE"

    def __init__(self, root=None, source_manifest=None):
        self.root = Path(root or Path(__file__).resolve().parents[1]).resolve()
        self.source_manifest = dict(source_manifest or {})
        self.audit = []

    def admit(self, context, action):
        context.verify_identity()
        require(context.source_registry is self, "SOURCE_REGISTRY_CONTEXT_DRIFT")
        require_production_authorization("B3_SOURCE_" + action)
        inputs = source_input_identity(context.input_folder)
        require(inputs["bundle"] == context.original_bundle
                and inputs["input_sha"] == context.request.authority.input_sha,
                "SOURCE_ORIGINAL_BUNDLE_OR_INPUT_AUTHORITY_SHA_DRIFT")

    def _path(self, module):
        require(isinstance(module, str) and re.fullmatch(r"v42_[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*", module), "PINNED_SOURCE_MODULE_NAME_REQUIRED")
        path = self.root.joinpath(*module.split(".")).with_suffix(".py").resolve()
        if not path.exists():
            path = self.root.joinpath(*module.split("."), "__init__.py").resolve()
        require(path.is_relative_to(self.root), "SOURCE_REGISTRY_PATH_ESCAPE")
        return path

    def resolve(self, module):
        context = _current.get()
        require(context is not None, "B3_SOURCE_EXECUTION_SCOPE_REQUIRED")
        self.admit(context, "IMPORT")
        path = self._path(module)
        relative = path.relative_to(self.root).as_posix()
        expected = self.source_manifest.get(relative)
        require_sha(expected)
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        require(observed == expected, "B3_ORIGINAL_SOURCE_SHA_DRIFT:" + relative)
        resolved = importlib.import_module(module)
        require(Path(resolved.__file__).resolve() == path, "B3_SOURCE_IMPORTED_FROM_OTHER_CHECKOUT")
        from .source_guard import route_resolved_module
        route_resolved_module(resolved)
        self.audit.append({"action": "RESOLVE", "module": module, "source_sha": observed, "evidence_kind": self.evidence_kind})
        return resolved

    @staticmethod
    def module_name(path):
        return path.removesuffix(".py").replace("/", ".").replace("\\", ".")

    def callable(self, file, symbol):
        module = self.resolve(self.module_name(file))
        target = module
        for part in symbol.split("."):
            target = getattr(target, part)
        require(callable(target), "SOURCE_CALLABLE_REQUIRED")
        return target

    def rebind(self, module_name, symbol, *, globals=None, literal_replacements=None,
               attribute_replacements=None, import_replacements=None, expression_replacements=None):
        """Compile one original function, preserving its arithmetic/algorithm.

        String stage/arm/schema literals, dotted stage enums, lexical globals
        and inline API imports are the only routing inputs. Numeric constants
        cannot be altered. The transformation is audited by source/AST SHA.
        """
        module = self.resolve(module_name)
        path = self._path(module_name)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        definition = tree
        for part in symbol.split("."):
            matches = [node for node in definition.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == part]
            require(len(matches) == 1, "SOURCE_REBIND_DEFINITION_REQUIRED:" + symbol)
            definition = matches[0]
        require(isinstance(definition, ast.FunctionDef), "SOURCE_REBIND_FUNCTION_REQUIRED")
        before = ast.dump(definition, include_attributes=False)
        literals = dict(literal_replacements or {})
        attributes = dict(attribute_replacements or {})
        imports = dict(import_replacements or {})
        expressions = dict(expression_replacements or {})
        require(all(type(k) is str and type(v) is str for k, v in literals.items()), "NUMERIC_SCIENTIFIC_REWRITE_FORBIDDEN")
        for replacement in attributes.values():
            require(re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", replacement), "SOURCE_STAGE_ENUM_REPLACEMENT_REQUIRED")
        for original, replacement in expressions.items():
            require(original in {"120 * 96", "keyword:sites:24"}, "SOURCE_FEEDER_METADATA_ROUTE_NOT_ALLOWED")
            require(re.fullmatch(r"_b3_[A-Za-z_]\w*", replacement), "SOURCE_FEEDER_DERIVED_COUNT_NAME_REQUIRED")
        class Router(ast.NodeTransformer):
            def visit_BinOp(self, node):
                name = ast.unparse(node)
                if name in expressions:
                    return ast.copy_location(ast.Name(expressions[name], ast.Load()), node)
                return self.generic_visit(node)
            def visit_keyword(self, node):
                if node.arg == "sites" and isinstance(node.value, ast.Constant) and node.value.value == 24 and "keyword:sites:24" in expressions:
                    node.value = ast.copy_location(ast.Name(expressions["keyword:sites:24"], ast.Load()), node.value)
                return self.generic_visit(node)
            def visit_Constant(self, node):
                if type(node.value) is str and node.value in literals:
                    return ast.copy_location(ast.Constant(literals[node.value]), node)
                return node
            def visit_Attribute(self, node):
                name = ast.unparse(node)
                if name in attributes:
                    return ast.copy_location(ast.parse(attributes[name], mode="eval").body, node)
                return self.generic_visit(node)
            def visit_ImportFrom(self, node):
                assignments, remaining = [], []
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name in imports:
                        assignments.append(ast.copy_location(ast.Assign([ast.Name(name, ast.Store())],
                            ast.Subscript(ast.Name("_b3_imports", ast.Load()), ast.Constant(name), ast.Load())), node))
                    else:
                        remaining.append(alias)
                if remaining:
                    assignments.append(ast.copy_location(ast.ImportFrom(node.module, remaining, node.level), node))
                return assignments
            def visit_Import(self, node):
                assignments, remaining = [], []
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    if name in imports:
                        assignments.append(ast.copy_location(ast.Assign([ast.Name(name, ast.Store())],
                            ast.Subscript(ast.Name("_b3_imports", ast.Load()), ast.Constant(name), ast.Load())), node))
                    else:
                        remaining.append(alias)
                if remaining:
                    assignments.append(ast.copy_location(ast.Import(remaining), node))
                return assignments
        definition = Router().visit(definition)
        definition.decorator_list = []
        routed = ast.fix_missing_locations(ast.Module([definition], type_ignores=[]))
        namespace = dict(vars(module))
        namespace.update(globals or {})
        namespace["_b3_imports"] = imports
        exec(compile(routed, str(path) + ":B3_ROUTED", "exec"), namespace)
        self.audit.append({"action": "REBIND", "module": module_name, "symbol": symbol,
                           "source_sha": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "original_AST_sha": digest(before), "routed_AST_sha": digest(ast.dump(definition, include_attributes=False)),
                           "literal_replacements": literals, "attribute_replacements": attributes,
                           "global_routes": sorted(globals or {}), "inline_import_routes": sorted(imports),
                           "feeder_metadata_routes": expressions,
                           "numeric_scientific_constants_changed": False, "evidence_kind": self.evidence_kind})
        return namespace[definition.name]

    @contextmanager
    def execution_scope(self, context):
        self.admit(context, "EXECUTE")
        token = _current.set(context)
        try:
            if self.evidence_kind == "SOURCE":
                from .source_guard import compatibility_scope
                with compatibility_scope(context):
                    yield context
            else:
                yield context
        finally:
            _current.reset(token)

    @contextmanager
    def native_scope(self, model, component="P1", track=None):
        context = _current.get()
        require(context is not None, "B3_NATIVE_SOURCE_SCOPE_REQUIRED")
        self.admit(context, "NATIVE")
        require(component in {"P1", "ORIGINAL_P1", "PHASE_I", "INTEGER_CONTROL", "NODE_LP", "LOCAL_PRICING",
                              "FEASIBILITY_LP", "FEASIBILITY_MIP", "LP_DUAL", "UB", "PRICING", "RMP"}, "B3_P2_FORBIDDEN")
        allowed = track is None or (str(track).startswith("A") if context.request.stage.startswith("A")
                                   else str(track).startswith("M") or track in {"UB", "LB", "PRICING", "RMP"})
        require(allowed, "B3_NATIVE_TRACK_DRIFT")
        token = _native.set((context, model, component))
        try:
            yield
        finally:
            _native.reset(token)

    def guard(self, model):
        context = _current.get()
        require(context is not None, "B3_NATIVE_MODEL_CONTEXT_REQUIRED")
        self.admit(context, "NATIVE_GUARD")
        scope = _native.get()
        require(scope is not None and scope[0] is context and scope[1] is model,
                "B3_LEDGERED_NATIVE_MODEL_SCOPE_REQUIRED")
        require(type(model.Params.Threads) is int and model.Params.Threads == 1, "B3_NATIVE_THREADS_ONE_REQUIRED")


class FakeSourceRegistry(SourceRegistry):
    """Explicit test double registry. Real modules are never imported here."""
    evidence_kind = "FAKE_SOURCE_TEST"

    def __init__(self, modules=None, root=None):
        super().__init__(root)
        self.modules = dict(modules or {})
        require(all(getattr(module, "__b3_fake__", False) is True for module in self.modules.values()), "MARKED_FAKE_SOURCE_MODULES_ONLY")

    def admit(self, context, action):
        context.verify_identity()
        require(context.source_registry is self, "SOURCE_REGISTRY_CONTEXT_DRIFT")

    def resolve(self, module):
        require(module in self.modules, "UNREGISTERED_FAKE_SOURCE_MODULE:" + module)
        target = self.modules[module]
        require(getattr(target, "__b3_fake__", False) is True, "REAL_MODULE_IN_FAKE_REGISTRY_FORBIDDEN")
        self.audit.append({"action": "RESOLVE", "module": module, "evidence_kind": self.evidence_kind})
        return target

    def rebind(self, module_name, symbol, **routing):
        module = self.resolve(module_name)
        target = module
        for part in symbol.split("."):
            target = getattr(target, part)
        factory = getattr(module, "__b3_rebind__", None)
        require(factory is not None, "FAKE_SOURCE_REBIND_FACTORY_REQUIRED")
        result = factory(symbol, target, routing)
        self.audit.append({"action": "REBIND", "module": module_name, "symbol": symbol, "evidence_kind": self.evidence_kind,
                           "global_routes": sorted(routing.get("globals") or {}), "inline_import_routes": sorted(routing.get("import_replacements") or {})})
        return result


@dataclass(frozen=True)
class SourceStageOutput:
    request: StageRequest
    source_result: dict
    aidc: AIDCDecision
    mess: MESSDecision | None
    model_sha: str
    physical_evidence: dict
    global_evidence: dict
    source_packet: dict
    ledger_receipt: str
    evidence_kind: str = "SOURCE"

    def __post_init__(self):
        require_sha(self.model_sha)
        require(isinstance(self.aidc, AIDCDecision) and (self.mess is None or isinstance(self.mess, MESSDecision)), "SOURCE_TYPED_DECISIONS_REQUIRED")
        require(self.evidence_kind in ("SOURCE", "FAKE_SOURCE_TEST"), "SOURCE_EVIDENCE_KIND_REQUIRED")
        object.__setattr__(self, "ledger_receipt", canonical(json.loads(self.ledger_receipt)))
        for name in ("source_result", "physical_evidence", "global_evidence", "source_packet"):
            object.__setattr__(self, name, json.loads(canonical(jsonable(getattr(self, name)))))
        object.__setattr__(self, "_content_sha", self.sha)

    @property
    def decision_sha(self):
        return digest({"aidc": self.aidc.to_dict(), "mess": self.mess.to_dict() if self.mess else None})

    @property
    def identity(self):
        return {"stage": self.request.stage, "authority_sha": self.request.authority.sha,
                "fixed_input_sha": self.request.fixed_input_sha, "request_sha": self.request.request_sha,
                "decision_sha": self.decision_sha, "original_model_sha": self.model_sha}

    @property
    def sha(self):
        current = digest({**self.identity, "source_result": jsonable(self.source_result),
                       "physical": jsonable(self.physical_evidence), "global": jsonable(self.global_evidence),
                       "ledger": json.loads(self.ledger_receipt), "evidence_kind": self.evidence_kind,
                       "source_packet": jsonable(self.source_packet)})
        require(not hasattr(self, "_content_sha") or self._content_sha == current,
                "SEALED_SOURCE_OUTPUT_CONTENT_DRIFT")
        return current
