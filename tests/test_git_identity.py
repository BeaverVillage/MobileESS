from pathlib import Path

from pfr.git_identity import windows_gitdir_to_wsl_path


def test_windows_gitdir_translation_for_wsl_mount() -> None:
    assert windows_gitdir_to_wsl_path(
        r"C:\Users\example\repo\.git\worktrees\experiment"
    ) == Path("/mnt/c/Users/example/repo/.git/worktrees/experiment")


def test_non_windows_gitdir_is_not_translated() -> None:
    assert windows_gitdir_to_wsl_path("../repo/.git/worktrees/experiment") is None
