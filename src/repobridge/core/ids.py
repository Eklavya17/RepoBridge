"""Identifiers, snapshots and fingerprints (docs/contracts.md, "Conventions").

- Record IDs are ``<PREFIX>-<token>``, e.g. ``EV-3f9a0c12ab45`` or a readable ``WO-0142``.
- Snapshots are a full 40-hex commit SHA, optionally ``+dirty:<12 hex>`` for a modified tree.
- Entity IDs are readable and revision-scoped: ``py:pkg.mod.func@<rev>``, where ``<rev>`` is the
  first 12 hex of the SHA, plus ``+<8 hex>`` of the dirty hash when the tree is dirty.
- Fingerprints hash an entity's source with whitespace normalised, so reformatting does not
  invalidate summaries but any token change does.
"""

import hashlib
import re
import uuid

RECORD_PREFIXES = frozenset(
    {
        "EDGE",  # GraphEdge
        "EV",  # Evidence
        "LE",  # LedgerEvent
        "WO",  # ScoutRequest (work order)
        "FND",  # ScoutFinding
        "CB",  # ContextBundle
        "SUM",  # Summary
        "STR",  # StrategyEdge
        "GH",  # GhostHint
        "LSN",  # Lesson
        "INV",  # investigation
        "TASK",  # benchmark / user task
    }
)
LANGUAGES = frozenset({"py", "java"})

_RECORD_ID = re.compile(r"^([A-Z]+)-[0-9A-Za-z][0-9A-Za-z_.#-]*$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SNAPSHOT = re.compile(r"^([0-9a-f]{40})(?:\+dirty:([0-9a-f]{12}))?$")
_QUALNAME = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
_ENTITY_ID = re.compile(rf"^([a-z]+):({_QUALNAME})@([0-9a-f]{{12}}(?:\+[0-9a-f]{{8}})?)$")
UNRESOLVED_PREFIX = "unresolved:"


def new_id(prefix: str, seed: str | None = None) -> str:
    """Return a new record ID. With ``seed`` the ID is deterministic (useful in tests)."""
    if prefix not in RECORD_PREFIXES:
        raise ValueError(f"unknown ID prefix {prefix!r}; expected one of {sorted(RECORD_PREFIXES)}")
    token = hashlib.sha256(seed.encode()).hexdigest()[:12] if seed else uuid.uuid4().hex[:12]
    return f"{prefix}-{token}"


def id_prefix(value: str) -> str | None:
    m = _RECORD_ID.match(value) if isinstance(value, str) else None
    return m.group(1) if m else None


def is_record_id(value: str, prefix: str | None = None) -> bool:
    p = id_prefix(value)
    return p in RECORD_PREFIXES and (prefix is None or p == prefix)


def make_snapshot(sha: str, dirty_diff: str | None = None) -> str:
    """Build a snapshot string from a commit SHA and, for a dirty tree, its diff text."""
    if not _SHA.match(sha):
        raise ValueError(f"commit SHA must be 40 lowercase hex characters, got {sha!r}")
    if dirty_diff is None:
        return sha
    return f"{sha}+dirty:{hashlib.sha256(dirty_diff.encode()).hexdigest()[:12]}"


def is_snapshot(value: str) -> bool:
    return isinstance(value, str) and bool(_SNAPSHOT.match(value))


def rev_tag(snapshot: str) -> str:
    """Short revision tag used inside entity IDs."""
    m = _SNAPSHOT.match(snapshot)
    if not m:
        raise ValueError(f"invalid snapshot {snapshot!r}")
    sha, dirty = m.groups()
    return sha[:12] if dirty is None else f"{sha[:12]}+{dirty[:8]}"


def entity_id(qualified_name: str, snapshot: str, language: str = "py") -> str:
    eid = f"{language}:{qualified_name}@{rev_tag(snapshot)}"
    if not is_entity_id(eid):
        raise ValueError(f"cannot build a valid entity ID from {qualified_name!r}")
    return eid


def parse_entity_id(value: str) -> tuple[str, str, str]:
    """Split an entity ID into (language, qualified_name, rev_tag)."""
    m = _ENTITY_ID.match(value) if isinstance(value, str) else None
    if not m or m.group(1) not in LANGUAGES:
        raise ValueError(f"invalid entity ID {value!r}; expected e.g. 'py:pkg.mod.func@<12 hex>'")
    return m.group(1), m.group(2), m.group(3)


def is_entity_id(value: str) -> bool:
    try:
        parse_entity_id(value)
    except ValueError:
        return False
    return True


def normalize_source(source: str) -> str:
    """Collapse runs of whitespace inside lines and drop blank lines."""
    lines = (" ".join(line.split()) for line in source.splitlines())
    return "\n".join(line for line in lines if line)


def fingerprint(source: str) -> str:
    """16-hex fingerprint of whitespace-normalised source."""
    return hashlib.sha256(normalize_source(source).encode()).hexdigest()[:16]


def is_fingerprint(value: str) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{16}", value))
