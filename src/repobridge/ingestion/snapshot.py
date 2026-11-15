"""Work out the snapshot (commit SHA, plus a dirty marker) for a directory inside a git repo."""

import subprocess
from pathlib import Path

from repobridge.core import ids


class SnapshotError(RuntimeError):
    """The directory is not in a git repository with at least one commit."""


def _git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SnapshotError(f"git {' '.join(args)} failed in {root}: {exc}") from exc
    return out.stdout


def git_snapshot(root: str | Path) -> str:
    """Snapshot for ``root``: HEAD's SHA, marked dirty if files under ``root`` changed."""
    root = Path(root)
    sha = _git(root, "rev-parse", "HEAD").strip()
    status = _git(root, "status", "--porcelain", "--", ".")
    if not status.strip():
        return ids.make_snapshot(sha)
    diff = _git(root, "diff", "HEAD", "--", ".")
    return ids.make_snapshot(sha, dirty_diff=status + diff)
