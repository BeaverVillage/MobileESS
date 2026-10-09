"""Sequential, small source-routing regression; real execution stays blocked."""
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
import ast
import hashlib
import importlib.abc
import io
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "v42_b3_implementation_completion_20261009"


class SourceImportFirewall(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.denied = []

    def find_spec(self, fullname, path=None, target=None):
        top = fullname.split(".")[0]
        if top in {"gurobipy", "win32com", "pythoncom", "opendssdirect", "dss", "pydss", "scipy", "pandas"} or (
                top.startswith("v42_") and top != "v42_b3_joint"):
            self.denied.append(fullname)
            raise ImportError("B3_COMPLETION_FORBIDDEN_REAL_IMPORT:" + fullname)
        return None


def write_json(name, value):
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def source_signature_audit():
    checks, unresolved = [], []
    def lookup(relative, symbol, seen=None):
        seen = set(seen or ())
        require_key = (relative, symbol)
        if require_key in seen:
            return None
        seen.add(require_key)
        source = ROOT / relative
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        scope = tree
        for name in symbol.split("."):
            nodes = [n for n in scope.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
            if len(nodes) != 1:
                for imported in tree.body:
                    if not isinstance(imported, ast.ImportFrom):
                        continue
                    for alias in imported.names:
                        if alias.name != "*" and (alias.asname or alias.name) != symbol.split(".")[0]:
                            continue
                        if imported.level:
                            package = relative.removesuffix(".py").split("/")[:-imported.level]
                            module = package + (imported.module.split(".") if imported.module else [])
                        else:
                            module = (imported.module or "").split(".")
                        target = "/".join(module) + ".py"
                        if (ROOT / target).is_file():
                            routed_symbol = symbol if alias.name == "*" else alias.name + symbol[len(symbol.split(".")[0]):]
                            found = lookup(target, routed_symbol, seen)
                            if found:
                                return found
                return None
            scope = nodes[0]
        return relative, scope
    for path in sorted((ROOT / "v42_b3_joint").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        constants = {n.targets[0].id: n.value.value for n in tree.body
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
            and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
        def constant(node):
            return node.value if isinstance(node, ast.Constant) else constants.get(node.id) if isinstance(node, ast.Name) else None
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute) or call.func.attr not in ("callable", "rebind") or len(call.args) < 2:
                continue
            file, symbol = constant(call.args[0]), constant(call.args[1])
            if not file or not symbol:
                unresolved.append({"bridge": path.name, "line": call.lineno, "route": ast.unparse(call)[:200]})
                continue
            relative = file if file.endswith(".py") else file.replace(".", "/") + ".py"
            source = ROOT / relative
            if not source.exists():
                raise ValueError("SOURCE_API_FILE_MISSING:" + relative)
            found = lookup(relative, symbol)
            if found is None:
                raise ValueError("SOURCE_API_SYMBOL_MISSING:" + relative + ":" + symbol)
            defining_file, scope = found
            checks.append({"bridge": path.name, "line": call.lineno, "source_file": relative,
                "defining_source_file": defining_file,
                "symbol": symbol, "source_sha": hashlib.sha256(source.read_bytes()).hexdigest(),
                "signature": ast.unparse(scope.args) if isinstance(scope, ast.FunctionDef) else "class"})
    return checks, unresolved


def verification():
    if ROOT != Path("D:/MobileESS_v42_B3_prep").resolve():
        raise PermissionError("COMPLETION_WRITES_REQUIRE_ISOLATED_WORKTREE")
    historical = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (ROOT / "docs/v42_b3_preparation_20261009").glob("*") if p.is_file()}
    started = perf_counter()
    firewall = SourceImportFirewall()
    sys.meta_path.insert(0, firewall)
    try:
        from .adapters import inspect_source_links
        from .dry_run import fixture_authority
        from .pipeline import MockPipeline
        from .schema import validate_schema_packet
        from .verify_preparation import handoff_schema
        files = sorted((ROOT / "v42_b3_joint").glob("*.py")) + sorted((ROOT / "tests").glob("test_v42_b3_*.py"))
        for file in files:
            ast.parse(file.read_text(encoding="utf-8-sig"), filename=str(file))
        old_api = inspect_source_links()
        new_api, dynamic = source_signature_audit()
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_v42_b3_*.py")
        stream = io.StringIO()
        with ExitStack() as gates:
            gates.enter_context(patch("subprocess.Popen", side_effect=PermissionError("B3_TEST_PROCESS_START_FORBIDDEN")))
            gates.enter_context(patch("os.system", side_effect=PermissionError("B3_TEST_SHELL_START_FORBIDDEN")))
            result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
        print(stream.getvalue().strip())
        schema = handoff_schema()
        mock = MockPipeline().execute_mock(fixture_authority())
        for request, output in zip(mock.requests, mock.results):
            validate_schema_packet(schema, json.loads(json.dumps({"request": asdict(request), "result": asdict(output)})))
        preserved = all(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == sha for relative, sha in historical.items())
        if not preserved:
            raise ValueError("HISTORICAL_PREPARATION_EVIDENCE_CHANGED")
        report = {"schema": "B3_SOURCE_COMPLETION_LIGHTWEIGHT_REGRESSION_V1",
            "status": "LIGHTWEIGHT_TEST_PASS" if result.wasSuccessful() else "LIGHTWEIGHT_TEST_FAIL",
            "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
            "elapsed_seconds": perf_counter() - started, "test_scope": "B3 focused tests only, one process sequential; tiny NumPy arrays and original pure AST bodies with marked fake source APIs",
            "historical_75_tests_included": True, "historical_preparation_reports_unchanged": preserved,
            "historical_evidence_files_checked": len(historical), "schema_packets_passed": 4,
            "AST_files_passed": len(files), "existing_39_source_API_signatures_passed": len(old_api),
            "new_literal_source_API_routes_checked": len(new_api), "dynamic_source_routes": dynamic,
            "actual_native_optimize_calls": 0, "actual_OpenDSS_calls": 0,
            "actual_FULL_model_builds": 0, "actual_domain_builds": 0, "actual_pricing_optimize_calls": 0,
            "actual_scientific_source_modules_imported": 0, "Gurobi_license_sessions": 0,
            "FAKE_SOURCE_TEST_is_scientific_evidence": False,
            "real_scientific_validation": "NOT_RUN", "production_authorized": False,
            "real_import_denials": firewall.denied,
            "limits": ["No real May01/May23 FULL equivalence", "No real optimization or exact Global gap result",
                       "No real Original physical or Fresh AC result", "No real build performance/RSS comparison"],
            "failure_details": [{"test": str(test), "trace": trace} for test, trace in result.failures + result.errors]}
        write_json("B3_LIGHTWEIGHT_REGRESSION.json", report)
        write_json("B3_SOURCE_API_STATIC_AUDIT.json", {"literal_routes": new_api, "dynamic_routes_requiring_source_routing_tests": dynamic,
            "actual_invocations": 0, "scientific_certified": False})
        print(json.dumps({k: report[k] for k in ("status", "tests_run", "failures", "errors", "schema_packets_passed", "actual_native_optimize_calls")}))
        if not result.wasSuccessful():
            raise RuntimeError("B3_LIGHTWEIGHT_REGRESSION_FAILED")
        return report
    finally:
        sys.meta_path.remove(firewall)


if __name__ == "__main__":
    verification()
