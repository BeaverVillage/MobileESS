"""Portable Git identity lookup for Windows worktrees executed through WSL."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from typing import Mapping, Optional, Sequence


_WINDOWS_ABSOLUTE = re.compile(r"^(?P<drive>[A-Za-z]):[\\/](?P<rest>.+)$")


def windows_gitdir_to_wsl_path(value: str) -> Optional[Path]:
    """Translate a standard WSL-mounted Windows Git path without mutating .git."""

    match = _WINDOWS_ABSOLUTE.fullmatch(value.strip())
    if match is None:
        return None
    rest = match.group("rest").replace("\\", "/")
    return Path("/mnt") / match.group("drive").lower() / rest


def git_subprocess_environment(repo: Path) -> Mapping[str, str]:
    environment = dict(os.environ)
    if environment.get("GIT_DIR") and environment.get("GIT_WORK_TREE"):
        return environment
    dot_git = repo.resolve() / ".git"
    if os.name != "posix" or not dot_git.is_file():
        return environment
    try:
        declaration = dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return environment
    prefix = "gitdir:"
    if not declaration.lower().startswith(prefix):
        return environment
    translated = windows_gitdir_to_wsl_path(declaration[len(prefix) :].strip())
    if translated is None or not translated.is_dir():
        return environment
    environment["GIT_DIR"] = str(translated)
    environment["GIT_WORK_TREE"] = str(repo.resolve())
    return environment


def run_git(repo: Path, args: Sequence[str]) -> str:
    process = subprocess.run(
        ("git", "-C", str(repo.resolve()), *args),
        check=True,
        capture_output=True,
        text=True,
        env=git_subprocess_environment(repo),
    )
    return process.stdout.strip()
