"""Clone earlier systems listed in testing/prior_work/<area>/<system>/manifest.toml.

Clones go to testing/prior_work/_upstream/<area>/<system> (gitignored) and are checked out at
the pinned commit. Entries whose repo_url or commit is TODO are skipped.

    python scripts/fetch_prior_work.py --dry-run
    python scripts/fetch_prior_work.py --only fray
    python scripts/fetch_prior_work.py --area debugging
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "testing" / "prior_work"
UPSTREAM = PRIOR / "_upstream"


def load_manifests() -> list[tuple[Path, dict]]:
    out = []
    for path in sorted(PRIOR.glob("*/*/manifest.toml")):
        if path.parts[-3] == "_upstream":
            continue
        out.append((path, tomllib.loads(path.read_text(encoding="utf-8"))))
    return out


def git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def fetch(area: str, key: str, url: str, commit: str) -> None:
    dest = UPSTREAM / area / key
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        git("clone", "--filter=blob:none", "--no-checkout", url, str(dest))
    git("fetch", "--quiet", "origin", commit, cwd=dest)
    git("checkout", "--quiet", "--detach", commit, cwd=dest)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="list what would be fetched")
    ap.add_argument("--only", help="system folder name, e.g. repoaudit")
    ap.add_argument("--area", choices=["context", "debugging", "optimization", "concurrency"])
    args = ap.parse_args(argv)

    failures = 0
    for path, m in load_manifests():
        area, key = path.parts[-3], path.parts[-2]
        if (args.only and key != args.only) or (args.area and area != args.area):
            continue
        url, commit = m.get("repo_url", "TODO"), m.get("commit", "TODO")
        if "TODO" in (url, commit):
            print(f"SKIP   {area}/{key:<12} (repo_url/commit TODO)")
            continue
        print(f"FETCH  {area}/{key:<12} {url} @ {commit[:12]}")
        if args.dry_run:
            continue
        try:
            fetch(area, key, url, commit)
        except subprocess.CalledProcessError as exc:
            failures += 1
            print(f"ERROR  {area}/{key}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
