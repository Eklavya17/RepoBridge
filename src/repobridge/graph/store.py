"""SQLite store for the versioned repository graph.

Each record is stored as its contract JSON (the source of truth) next to a few indexed columns
used for lookups. Re-indexing a snapshot replaces it. Different snapshots live side by side.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from repobridge.core.schemas import EntityKind, GraphEdge, ProgramEntity, Relation
from repobridge.ingestion.python_ast import IndexResult

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot   TEXT PRIMARY KEY,
    root       TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    stats      TEXT NOT NULL,
    skipped    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
    entity_id      TEXT PRIMARY KEY,
    snapshot       TEXT NOT NULL,
    kind           TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    short_name     TEXT NOT NULL,
    path           TEXT NOT NULL,
    record         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_entities_qn ON entities (snapshot, qualified_name);
CREATE INDEX IF NOT EXISTS ix_entities_short ON entities (snapshot, short_name);
CREATE TABLE IF NOT EXISTS edges (
    edge_id  TEXT PRIMARY KEY,
    snapshot TEXT NOT NULL,
    src      TEXT NOT NULL,
    dst      TEXT NOT NULL,
    relation TEXT NOT NULL,
    resolved INTEGER NOT NULL,
    record   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_edges_src ON edges (src, relation);
CREATE INDEX IF NOT EXISTS ix_edges_dst ON edges (dst, relation);
"""


class GraphStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ writing
    def save(self, result: IndexResult) -> None:
        snap = result.snapshot
        with self.conn:
            self.conn.execute("DELETE FROM entities WHERE snapshot = ?", (snap,))
            self.conn.execute("DELETE FROM edges WHERE snapshot = ?", (snap,))
            self.conn.execute(
                "INSERT OR REPLACE INTO snapshots VALUES (?, ?, ?, ?, ?)",
                (
                    snap,
                    result.root,
                    datetime.now(UTC).isoformat(),
                    json.dumps(result.stats),
                    json.dumps(result.skipped),
                ),
            )
            self.conn.executemany(
                "INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        e.entity_id,
                        snap,
                        e.kind.value,
                        e.qualified_name,
                        e.qualified_name.rsplit(".", 1)[-1],
                        e.path,
                        e.to_json(),
                    )
                    for e in result.entities
                ],
            )
            self.conn.executemany(
                "INSERT INTO edges VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (g.edge_id, snap, g.src, g.dst, g.relation.value, int(g.resolved), g.to_json())
                    for g in result.edges
                ],
            )

    # ------------------------------------------------------------------ snapshots
    def snapshots(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT snapshot, root, indexed_at, stats, skipped FROM snapshots "
            "ORDER BY indexed_at DESC"
        ).fetchall()
        return [
            {
                "snapshot": s,
                "root": r,
                "indexed_at": t,
                "stats": json.loads(st),
                "skipped": json.loads(sk),
            }
            for s, r, t, st, sk in rows
        ]

    def latest_snapshot(self) -> str | None:
        snaps = self.snapshots()
        return snaps[0]["snapshot"] if snaps else None

    def snapshot_info(self, snapshot: str) -> dict[str, Any] | None:
        return next((s for s in self.snapshots() if s["snapshot"] == snapshot), None)

    # ------------------------------------------------------------------ entities
    def entity(self, entity_id: str) -> ProgramEntity | None:
        row = self.conn.execute(
            "SELECT record FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        return ProgramEntity.from_json(row[0]) if row else None

    def entities(self, snapshot: str, kind: EntityKind | None = None) -> list[ProgramEntity]:
        sql = "SELECT record FROM entities WHERE snapshot = ?"
        args: list[Any] = [snapshot]
        if kind is not None:
            sql += " AND kind = ?"
            args.append(kind.value)
        rows = self.conn.execute(sql + " ORDER BY qualified_name", args).fetchall()
        return [ProgramEntity.from_json(r[0]) for r in rows]

    def find(self, snapshot: str, name: str) -> list[ProgramEntity]:
        """Exact qualified name first; otherwise every entity whose name ends with ``name``."""
        rows = self.conn.execute(
            "SELECT record FROM entities WHERE snapshot = ? AND qualified_name = ?",
            (snapshot, name),
        ).fetchall()
        if not rows:
            short = name.rsplit(".", 1)[-1]
            rows = [
                r
                for r in self.conn.execute(
                    "SELECT record, qualified_name FROM entities WHERE snapshot = ? AND short_name = ? "
                    "ORDER BY qualified_name",
                    (snapshot, short),
                ).fetchall()
                if r[1] == name or r[1].endswith("." + name)
            ]
        return [ProgramEntity.from_json(r[0]) for r in rows]

    # ------------------------------------------------------------------ edges
    def _edges(
        self, column: str, value: str, relation: Relation | None, resolved: bool | None
    ) -> list[GraphEdge]:
        sql = f"SELECT record FROM edges WHERE {column} = ?"
        args: list[Any] = [value]
        if relation is not None:
            sql += " AND relation = ?"
            args.append(relation.value)
        if resolved is not None:
            sql += " AND resolved = ?"
            args.append(int(resolved))
        rows = self.conn.execute(sql + " ORDER BY src, dst", args).fetchall()
        return [GraphEdge.from_json(r[0]) for r in rows]

    def edges_from(
        self, src: str, relation: Relation | None = None, resolved: bool | None = None
    ) -> list[GraphEdge]:
        return self._edges("src", src, relation, resolved)

    def edges_to(
        self, dst: str, relation: Relation | None = None, resolved: bool | None = None
    ) -> list[GraphEdge]:
        return self._edges("dst", dst, relation, resolved)

    def edges(self, snapshot: str) -> list[GraphEdge]:
        rows = self.conn.execute(
            "SELECT record FROM edges WHERE snapshot = ? ORDER BY src, dst", (snapshot,)
        ).fetchall()
        return [GraphEdge.from_json(r[0]) for r in rows]
