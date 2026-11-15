import importlib
import pkgutil
import tomllib
from pathlib import Path

import repobridge
from repobridge.core import schemas

ROOT = Path(__file__).resolve().parents[2]
AREAS = {"context", "debugging", "optimization", "concurrency"}
REQUIRED = {"name", "area", "paper", "repo_url", "commit", "license", "status"}


def test_all_modules_import():
    for mod in pkgutil.walk_packages(repobridge.__path__, "repobridge."):
        importlib.import_module(mod.name)


def test_contracts_declared():
    names = {c.__name__ for c in schemas.CONTRACTS}
    assert {"ProgramEntity", "GraphEdge", "Evidence", "ContextBundle", "GhostHint"} <= names


def test_prior_work_manifests_are_valid():
    manifests = sorted((ROOT / "testing" / "prior_work").glob("*/*/manifest.toml"))
    assert manifests, "no prior-work manifests found"
    for path in manifests:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        assert REQUIRED <= data.keys(), f"{path}: missing {REQUIRED - data.keys()}"
        assert data["area"] in AREAS and data["area"] == path.parent.parent.name, path
        if data["repo_url"] != "TODO":
            assert data["repo_url"].startswith("https://"), path
            assert data["commit"] == "TODO" or len(data["commit"]) == 40, path
