import os
import subprocess
import tempfile
import unittest
from unittest.mock import call, patch

from src.security.git_ops import GitOps


def _init_repo(path: str) -> None:
    """Helper: initialise a minimal git repo with one commit."""
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True, capture_output=True)
    readme = os.path.join(path, "README.md")
    with open(readme, "w", encoding="utf-8") as f:
        f.write("init\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


class TestGitOpsCheckpoint(unittest.TestCase):
    def test_checkpoint_runs_git_add_and_commit(self):
        with patch("src.security.git_ops.subprocess.run") as mock_run, \
             patch("builtins.print") as mock_print:
            ops = GitOps(repo_path="/fake/repo")
            ops.checkpoint("test checkpoint")

            self.assertEqual(mock_run.call_count, 2)
            add_call_args = mock_run.call_args_list[0][0][0]
            self.assertEqual(add_call_args[:2], ["git", "add"])

            commit_call_args = mock_run.call_args_list[1][0][0]
            self.assertEqual(commit_call_args[:2], ["git", "commit"])
            self.assertIn("test checkpoint", commit_call_args[3])

            mock_print.assert_called_once_with("💾 Точка сохранения создана.")

    def test_checkpoint_default_message(self):
        with patch("src.security.git_ops.subprocess.run") as mock_run, \
             patch("builtins.print"):
            ops = GitOps()
            ops.checkpoint()
            commit_args = mock_run.call_args_list[1][0][0]
            self.assertIn("Auto-evolution checkpoint", commit_args[3])

    def test_checkpoint_handles_exception(self):
        with patch("src.security.git_ops.subprocess.run", side_effect=FileNotFoundError("git not found")), \
             patch("builtins.print") as mock_print:
            ops = GitOps()
            ops.checkpoint()
            msg = mock_print.call_args[0][0]
            self.assertIn("⚠️ Git не настроен:", msg)

    def test_checkpoint_integration(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            ops = GitOps(repo_path=repo)

            new_file = os.path.join(repo, "evolution.txt")
            with open(new_file, "w", encoding="utf-8") as f:
                f.write("new state\n")

            with patch("builtins.print"):
                ops.checkpoint("integration test")

            result = subprocess.run(
                ["git", "log", "--oneline"],
                cwd=repo, capture_output=True, text=True, check=True,
            )
            self.assertIn("integration test", result.stdout)


class TestGitOpsRollback(unittest.TestCase):
    def test_rollback_runs_git_checkout(self):
        with patch("src.security.git_ops.subprocess.run") as mock_run, \
             patch("builtins.print") as mock_print:
            ops = GitOps(repo_path="/fake/repo")
            ops.rollback()

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertEqual(args, ["git", "checkout", "."])

            mock_print.assert_called_once()
            self.assertIn("🚨", mock_print.call_args[0][0])

    def test_rollback_uses_repo_path(self):
        with patch("src.security.git_ops.subprocess.run") as mock_run, \
             patch("builtins.print"):
            ops = GitOps(repo_path="/my/project")
            ops.rollback()
            _, kwargs = mock_run.call_args
            self.assertEqual(kwargs["cwd"], "/my/project")

    def test_rollback_integration(self):
        with tempfile.TemporaryDirectory() as repo:
            _init_repo(repo)
            ops = GitOps(repo_path=repo)

            tracked = os.path.join(repo, "README.md")
            with open(tracked, encoding="utf-8") as fh:
                original = fh.read()
            with open(tracked, "w", encoding="utf-8") as f:
                f.write("modified\n")

            with patch("builtins.print"):
                ops.rollback()

            with open(tracked, encoding="utf-8") as fh:
                restored = fh.read()
            self.assertEqual(restored, original)


class TestGitOpsInit(unittest.TestCase):
    def test_default_repo_path(self):
        ops = GitOps()
        self.assertEqual(ops.repo_path, ".")

    def test_custom_repo_path(self):
        ops = GitOps(repo_path="/some/path")
        self.assertEqual(ops.repo_path, "/some/path")
