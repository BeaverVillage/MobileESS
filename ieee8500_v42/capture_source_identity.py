"""Capture inherited V42 and pinned Git PR provenance without importing it."""
from pathlib import Path
import json
import subprocess

from .integration import file_sha, digest


PR_REFS = {"191": "origin/pr-191", "192": "origin/pr-192"}
PR_FILES = {
    "191": ("v42_b3_joint/a_source.py", "v42_b3_joint/m_source.py",
            "v42_b3_joint/grid_binding.py", "v42_b3_joint/operations_bridge.py",
            "v42_b3_joint/policy.py", "v42_b3_joint/source_runtime.py",
            "v42_b3_joint/native_ledger.py", "v42_b3_joint/numerical_policy.py"),
    "192": ("v42_b2_build_optimization/builder.py", "v42_b2_build_optimization/source_port.py"),
}


def capture(root):
    root = Path(root).resolve()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])
    import hashlib
    files = {}
    for path in sorted(root.glob("v42*/*")):
        if path.is_file() and path.suffix in (".py", ".html"):
            files[path.relative_to(root).as_posix()] = file_sha(path)
    for path in sorted(root.glob("v42*.py")):
        files[path.name] = file_sha(path)
    prs = {}
    for number, ref in PR_REFS.items():
        sha = git("rev-parse", ref).decode().strip()
        prs[number] = {"git_sha": sha, "url": f"https://github.com/BeaverVillage/MobileESS/pull/{number}",
                       "files_from_git_object": {name: hashlib.sha256(git("show", f"{sha}:{name}")).hexdigest()
                                                  for name in PR_FILES[number]}}
    return {"schema": "IEEE8500_V42_READ_ONLY_SOURCE_PIN_V1",
            "v42_git_sha": git("rev-parse", "HEAD").decode().strip(),
            "base_git_sha": "de6f79cd2cd215f0ed657b99d24b9ac26980ddc1",
            "files": files, "source_content_sha": digest(files), "pr_references": prs,
            "byte_identity_basis": "CURRENT_INHERITED_WORKTREE_BYTES_NO_LINE_ENDING_REWRITE",
            "original_models_modified": False, "native_calls": 0, "full_model_builds": 0,
            "campaign_worker_scheduler_input_ledger_writes": 0}


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root / "docs/ieee8500_v42_single_case"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "V42_SOURCE_SHA_MANIFEST.json"
    if path.exists():
        raise FileExistsError("PINNED_SOURCE_MANIFEST_ALREADY_EXISTS")
    path.write_text(json.dumps(capture(root), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(path))


if __name__ == "__main__":
    main()
