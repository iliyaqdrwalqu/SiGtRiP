"""
git_ops.py — GitOps: система «Бессмертия» и откатов.

checkpoint() — сохраняет текущее состояние системы через git commit.
rollback()   — откатывает рабочее дерево к последнему стабильному состоянию.
"""
import datetime
import subprocess


class GitOps:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def checkpoint(self, message: str = "Auto-evolution checkpoint") -> None:
        """Сохраняет текущее состояние системы."""
        try:
            subprocess.run(
                ["git", "add", "."],
                cwd=self.repo_path,
                check=False,
            )
            subprocess.run(
                ["git", "commit", "-m", f"{message} [{datetime.datetime.now(datetime.timezone.utc)}]"],
                cwd=self.repo_path,
                check=False,
            )
            print("💾 Точка сохранения создана.")
        except Exception as e:
            print(f"⚠️ Git не настроен: {e}")

    def rollback(self) -> None:
        """Откат системы при критической ошибке."""
        print("🚨 Критическая ошибка! Откат к последней стабильной версии...")
        subprocess.run(
            ["git", "checkout", "."],
            cwd=self.repo_path,
            check=False,
        )
