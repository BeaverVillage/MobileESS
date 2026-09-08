"""Regression for a WMI service PATH that cannot discover the launcher Git."""
import os
from pathlib import Path
import subprocess
import pytest
from dayahead.tools.v41_detached_launcher import git_executable, provision_git, worker_arguments
from dayahead.v41.preflight import ROOT


def test_service_path_without_git_is_provisioned_before_frozen_commit_check(monkeypatch):
    git=git_executable()
    expected=subprocess.check_output([git,'rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    monkeypatch.setenv('PATH','')
    assert provision_git(git)==git
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert actual==expected
    assert os.environ['PATH'].startswith(str(Path(git).parent))


def test_missing_relative_git_fails_before_any_worker(monkeypatch):
    monkeypatch.setenv('PATH','')
    with pytest.raises(ValueError,match='CHILD_GIT_NOT_ABSOLUTE_FILE'):
        provision_git('git.exe')


def test_worker_arguments_keep_kind_token_and_git_path_separate():
    args=worker_arguments('campaign','immutable-token','C:/Program Files/Git/cmd/git.exe')
    assert args[3]=='dayahead.tools.v41_detached_launcher'
    assert args[4:] == ['worker','--kind','campaign','--token','immutable-token',
                        '--git-executable','C:/Program Files/Git/cmd/git.exe']
