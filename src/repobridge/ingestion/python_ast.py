"""L1 ingestion for Python: parse a repository into ``ProgramEntity`` and ``GraphEdge`` records.

What is extracted (all ``provenance = static``):

- Entities: modules, classes, functions, methods and tests, each with its span and fingerprint.
- ``CONTAINS``: module -> class/function, class -> method, function -> nested function.
- ``IMPORTS``: module -> module. Modules outside the repo become ``unresolved:<name>``.
- ``INHERITS``: class -> base class, when the base is defined in the repo.
- ``CALLS``: resolved through module imports (absolute, relative, aliased, re-exported), nested
  scopes, constructors (``Cls()`` -> ``Cls.__init__``), and ``self``/``cls``/``super()`` method
  lookup along in-repo base classes. Calls the analysis cannot pin down (callable parameters,
  methods on local values, external libraries) are kept as ``unresolved:<as written>`` with a
  ``reason``. Calls to Python builtins are skipped and only counted.
- ``TESTS``: test -> non-test entity that the test calls directly.

Intra-procedural def-use is not stored as edges. ``graph/slicing.py`` computes it on demand.
"""

import ast
import builtins
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repobridge.core import ids
from repobridge.core.schemas import (
    EntityKind,
    GraphEdge,
    ProgramEntity,
    Provenance,
    Relation,
    Span,
)

SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "site-packages",
        "_upstream",
    }
)
BUILTINS = frozenset(dir(builtins))
_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass
class IndexResult:
    snapshot: str
    root: str
    entities: list[ProgramEntity]
    edges: list[GraphEdge]
    skipped: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


# ============================================================================ discovery


def _module_name(rel: Path) -> str | None:
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if parts and all(p.isidentifier() for p in parts):
        return ".".join(parts)
    return None


def discover_modules(root: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    """Return (repo-relative path, module name) for every Python file, plus skipped files."""
    src = root / "src"
    src_layout = src.is_dir() and any(
        (src / d / "__init__.py").exists() for d in os.listdir(src) if (src / d).is_dir()
    )
    found, skipped = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            rel = (Path(dirpath) / fn).relative_to(root)
            mod_rel = rel.relative_to("src") if src_layout and rel.parts[0] == "src" else rel
            name = _module_name(mod_rel)
            if name is None:
                skipped.append(f"{rel.as_posix()}: not an importable module name")
            else:
                found.append((rel, name))
    return found, skipped


# ============================================================================ per-module model


@dataclass
class _Def:
    qualname: str
    kind: EntityKind
    node: ast.AST
    parent: str
    span: Span


@dataclass
class _Module:
    name: str
    path: str
    source: str
    tree: ast.Module
    is_package: bool
    defs: list[_Def] = field(default_factory=list)
    top: dict[str, str] = field(default_factory=dict)  # top-level name -> qualname
    imports: dict[str, str] = field(default_factory=dict)  # bound name -> dotted target
    import_stmts: list[tuple[str, int]] = field(default_factory=list)  # (target, line)
    star: list[str] = field(default_factory=list)
    module_vars: set[str] = field(default_factory=set)
    node_qualname: dict[int, str] = field(default_factory=dict)  # id(def node) -> qualname

    @property
    def package(self) -> str:
        return self.name if self.is_package else self.name.rpartition(".")[0]

    @property
    def is_test_module(self) -> bool:
        last = self.name.rsplit(".", 1)[-1]
        parts = self.name.split(".")
        return last.startswith("test_") or last.endswith("_test") or "tests" in parts[:-1]


def _span(node: ast.AST, n_lines: int) -> Span:
    decos = [d.lineno for d in getattr(node, "decorator_list", [])]
    start = min([node.lineno, *decos])
    end = max(getattr(node, "end_lineno", None) or start, start)
    return Span(start, min(end, max(n_lines, start)))


def _child_stmts(body: list[ast.stmt]):
    """Statements in a block, descending into compound statements but not into defs."""
    for stmt in body:
        yield stmt
        if isinstance(stmt, _DEFS):
            continue
        for name in ("body", "orelse", "finalbody"):
            yield from _child_stmts(getattr(stmt, name, []) or [])
        for handler in getattr(stmt, "handlers", []) or []:
            yield from _child_stmts(handler.body)
        for case in getattr(stmt, "cases", []) or []:
            yield from _child_stmts(case.body)


def _collect_defs(mod: _Module, n_lines: int) -> None:
    seen: set[str] = {mod.name}

    def visit(body: list[ast.stmt], prefix: str, in_class: str | None) -> None:
        for stmt in _child_stmts(body):
            if not isinstance(stmt, _DEFS):
                continue
            qn = f"{prefix}.{stmt.name}"
            if qn in seen:  # redefinition (e.g. property setter): keep the first
                mod.node_qualname[id(stmt)] = qn
                visit(stmt.body, qn, qn if isinstance(stmt, ast.ClassDef) else None)
                continue
            seen.add(qn)
            if isinstance(stmt, ast.ClassDef):
                kind = EntityKind.CLASS
            elif in_class is not None:
                cls_name = in_class.rsplit(".", 1)[-1]
                is_test = (
                    mod.is_test_module
                    and cls_name.startswith("Test")
                    and stmt.name.startswith("test")
                )
                kind = EntityKind.TEST if is_test else EntityKind.METHOD
            else:
                is_test = mod.is_test_module and stmt.name.startswith("test")
                kind = EntityKind.TEST if is_test else EntityKind.FUNCTION
            mod.defs.append(_Def(qn, kind, stmt, prefix, _span(stmt, n_lines)))
            mod.node_qualname[id(stmt)] = qn
            if prefix == mod.name:
                mod.top[stmt.name] = qn
            visit(stmt.body, qn, qn if isinstance(stmt, ast.ClassDef) else None)

    visit(mod.tree.body, mod.name, None)


def _resolve_relative(mod: _Module, module: str | None, level: int) -> str:
    if level == 0:
        return module or ""
    base = mod.package.split(".") if mod.package else []
    base = base[: len(base) - (level - 1)] if level > 1 else base
    return ".".join([*base, module] if module else base)


def _collect_imports(mod: _Module) -> None:
    for node in ast.walk(mod.tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    mod.imports[a.asname] = a.name
                else:
                    head = a.name.split(".")[0]
                    mod.imports.setdefault(head, head)
                mod.import_stmts.append((a.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative(mod, node.module, node.level)
            for a in node.names:
                if a.name == "*":
                    mod.star.append(base)
                    mod.import_stmts.append((base, node.lineno))
                    continue
                target = f"{base}.{a.name}" if base else a.name
                mod.imports[a.asname or a.name] = target
                mod.import_stmts.append((target, node.lineno))
    for stmt in _child_stmts(mod.tree.body):
        if isinstance(stmt, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        mod.module_vars.add(n.id)
    mod.module_vars -= set(mod.top)


# ============================================================================ repository model


class _Repo:
    def __init__(self, modules: list[_Module]) -> None:
        self.modules = {m.name: m for m in modules}
        self.defs: dict[str, _Def] = {d.qualname: d for m in modules for d in m.defs}
        self.module_of: dict[str, _Module] = {d.qualname: m for m in modules for d in m.defs}
        self.methods: dict[str, dict[str, str]] = {}
        for d in self.defs.values():
            parent = self.defs.get(d.parent)
            if parent is not None and parent.kind is EntityKind.CLASS:
                self.methods.setdefault(d.parent, {})[d.qualname.rsplit(".", 1)[-1]] = d.qualname
        self.bases: dict[str, list[str]] = {}

    def known(self, qn: str) -> bool:
        return qn in self.defs or qn in self.modules

    def resolve_dotted(self, dotted: str, depth: int = 0) -> str | None:
        """Resolve an absolute dotted name to a repo qualname, following re-exports."""
        if self.known(dotted):
            return dotted
        if depth > 6:
            return None
        parts = dotted.split(".")
        for i in range(len(parts) - 1, 0, -1):
            prefix = ".".join(parts[:i])
            mod = self.modules.get(prefix)
            if mod is None:
                continue
            first, rest = parts[i], parts[i + 1 :]
            if first in mod.imports:
                return self.resolve_dotted(".".join([mod.imports[first], *rest]), depth + 1)
            for star in mod.star:
                hit = self.resolve_dotted(".".join([star, first, *rest]), depth + 1)
                if hit:
                    return hit
            return None
        return None

    def mro(self, cls: str) -> list[str]:
        order, queue = [], [cls]
        while queue:
            c = queue.pop(0)
            if c in order:
                continue
            order.append(c)
            queue.extend(self.bases.get(c, []))
        return order

    def find_method(self, cls: str, name: str, skip_self: bool = False) -> str | None:
        for c in self.mro(cls)[1 if skip_self else 0 :]:
            hit = self.methods.get(c, {}).get(name)
            if hit:
                return hit
        return None

    def constructor(self, cls: str) -> str:
        return self.find_method(cls, "__init__") or cls


# ============================================================================ call resolution

_RESOLVED, _DYNAMIC, _EXTERNAL, _BUILTIN, _UNKNOWN = (
    "resolved",
    "dynamic",
    "external",
    "builtin",
    "unknown",
)


@dataclass
class _Scope:
    defs: dict[str, str]
    vars: set[str]


def _render(expr: ast.AST) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return f"{_render(expr.value)}.{expr.attr}"
    if isinstance(expr, ast.Call):
        return f"{_render(expr.func)}()"
    if isinstance(expr, ast.Subscript):
        return f"{_render(expr.value)}[]"
    return "<expr>"


def _dotted_parts(expr: ast.AST) -> list[str] | None:
    parts = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if isinstance(expr, ast.Name):
        return [expr.id, *reversed(parts)]
    return None


def _function_scope(mod: _Module, node: ast.AST) -> _Scope:
    a = node.args
    params = {x.arg for x in [*a.posonlyargs, *a.args, *a.kwonlyargs]}
    params |= {x.arg for x in (a.vararg, a.kwarg) if x is not None}
    defs, stored, declared_global = {}, set(), set()
    for stmt in _child_stmts(node.body):
        if isinstance(stmt, _DEFS):
            defs[stmt.name] = mod.node_qualname.get(id(stmt), "")
            continue
        if isinstance(stmt, ast.Global | ast.Nonlocal):
            declared_global |= set(stmt.names)
        for n in _walk_no_defs(stmt):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                stored.add(n.id)
    return _Scope(defs=defs, vars=(params | stored) - declared_global - set(defs))


def _walk_no_defs(node: ast.AST):
    """ast.walk that does not enter nested function or class bodies."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(c for c in ast.iter_child_nodes(n) if not isinstance(c, _DEFS))


class _CallCollector:
    def __init__(self, repo: _Repo, mod: _Module, emit) -> None:
        self.repo, self.mod, self.emit = repo, mod, emit
        self.builtin_calls = 0

    # ----------------------------------------------------------------- name resolution
    def resolve_name(self, name: str, scopes: list[_Scope]) -> tuple[str, str]:
        for sc in scopes:
            if name in sc.defs and sc.defs[name]:
                return _RESOLVED, sc.defs[name]
            if name in sc.vars:
                return _DYNAMIC, name
        mod = self.mod
        if name in mod.top:
            return _RESOLVED, mod.top[name]
        if name in mod.imports:
            target = mod.imports[name]
            hit = self.repo.resolve_dotted(target)
            return (_RESOLVED, hit) if hit else (_EXTERNAL, target)
        if name in mod.module_vars:
            return _DYNAMIC, name
        for star in mod.star:
            hit = self.repo.resolve_dotted(f"{star}.{name}")
            if hit:
                return _RESOLVED, hit
        if name in BUILTINS:
            return _BUILTIN, name
        return _UNKNOWN, name

    def resolve_call(
        self, func: ast.AST, scopes: list[_Scope], cls: str | None, self_name: str | None
    ) -> tuple[str, str, dict[str, Any]]:
        written = _render(func)
        # super().method()
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Call)
            and isinstance(func.value.func, ast.Name)
            and func.value.func.id == "super"
            and cls
        ):
            hit = self.repo.find_method(cls, func.attr, skip_self=True)
            return (_RESOLVED, hit, {}) if hit else (_UNKNOWN, written, {})
        parts = _dotted_parts(func)
        if parts is None:
            return _DYNAMIC, written, {}
        head, rest = parts[0], parts[1:]
        if self_name and head == self_name and cls:
            if len(rest) == 1:
                hit = self.repo.find_method(cls, rest[0])
                if hit:
                    return _RESOLVED, hit, {}
            return _DYNAMIC, written, {}
        status, target = self.resolve_name(head, scopes)
        if status == _RESOLVED:
            qn = self.repo.resolve_dotted(".".join([target, *rest])) if rest else target
            if qn is None:
                return _UNKNOWN, written, {}
            d = self.repo.defs.get(qn)
            if d is not None and d.kind is EntityKind.CLASS:
                return _RESOLVED, self.repo.constructor(qn), {"via": "constructor"}
            return _RESOLVED, qn, {}
        if status == _EXTERNAL:
            return _EXTERNAL, written, {}
        if status == _BUILTIN:
            return (_BUILTIN, written, {}) if not rest else (_DYNAMIC, written, {})
        return status, written, {}

    # ----------------------------------------------------------------- traversal
    def run(self) -> None:
        self._block(self.mod.tree.body, self.mod.name, [], None, None)

    def _block(self, stmts, owner, scopes, cls, self_name) -> None:
        for s in stmts:
            self._node(s, owner, scopes, cls, self_name)

    def _node(self, node, owner, scopes, cls, self_name) -> None:
        if isinstance(node, _FUNCS):
            self._function(node, owner, scopes, cls, self_name, is_method=False)
        elif isinstance(node, ast.ClassDef):
            self._class(node, owner, scopes, cls, self_name)
        elif isinstance(node, ast.expr):
            self._expr(node, owner, scopes, cls, self_name)
        else:
            for c in ast.iter_child_nodes(node):
                self._node(c, owner, scopes, cls, self_name)

    def _function(self, node, owner, scopes, cls, self_name, is_method) -> None:
        for e in [
            *node.decorator_list,
            *node.args.defaults,
            *[d for d in node.args.kw_defaults if d is not None],
        ]:
            self._expr(e, owner, scopes, cls, self_name)
        qn = self.mod.node_qualname[id(node)]
        if is_method:
            static = any(_render(d) == "staticmethod" for d in node.decorator_list)
            first = (node.args.posonlyargs + node.args.args)[:1]
            self_name = None if static or not first else first[0].arg
        self._block(node.body, qn, [_function_scope(self.mod, node), *scopes], cls, self_name)

    def _class(self, node, owner, scopes, cls, self_name) -> None:
        for e in [*node.decorator_list, *node.bases, *[k.value for k in node.keywords]]:
            self._expr(e, owner, scopes, cls, self_name)
        qn = self.mod.node_qualname[id(node)]
        for stmt in node.body:
            if isinstance(stmt, _FUNCS):
                self._function(stmt, qn, scopes, qn, None, is_method=True)
            else:
                self._node(stmt, qn, scopes, None, None)

    def _expr(self, node, owner, scopes, cls, self_name) -> None:
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                status, target, attrs = self.resolve_call(n.func, scopes, cls, self_name)
                if status == _BUILTIN:
                    self.builtin_calls += 1
                elif status == _RESOLVED:
                    self.emit(owner, target, n.lineno, None, attrs)
                else:
                    self.emit(owner, target, n.lineno, status, attrs)


# ============================================================================ entry point


def index_repository(root: str | Path, snapshot: str) -> IndexResult:
    """Parse every Python module under ``root`` into contract records for ``snapshot``."""
    root = Path(root).resolve()
    files, skipped = discover_modules(root)
    modules: list[_Module] = []
    for rel, name in files:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text, filename=rel.as_posix())
        except SyntaxError as exc:
            skipped.append(f"{rel.as_posix()}: syntax error at line {exc.lineno}")
            continue
        mod = _Module(
            name=name,
            path=rel.as_posix(),
            source=text,
            tree=tree,
            is_package=rel.name == "__init__.py",
        )
        _collect_defs(mod, len(text.splitlines()))
        _collect_imports(mod)
        modules.append(mod)
    # a module name can come from two files (e.g. src/ and a top-level copy): keep the first
    unique: dict[str, _Module] = {}
    for m in modules:
        if m.name in unique:
            skipped.append(f"{m.path}: duplicate module name {m.name}")
        else:
            unique[m.name] = m
    repo = _Repo(list(unique.values()))

    entities: list[ProgramEntity] = []
    for mod in repo.modules.values():
        lines = mod.source.splitlines()
        entities.append(
            ProgramEntity(
                entity_id=ids.entity_id(mod.name, snapshot),
                snapshot=snapshot,
                kind=EntityKind.MODULE,
                qualified_name=mod.name,
                path=mod.path,
                span=Span(1, max(len(lines), 1)),
                fingerprint=ids.fingerprint(mod.source),
            )
        )
        for d in mod.defs:
            src = "\n".join(lines[d.span.start_line - 1 : d.span.end_line])
            entities.append(
                ProgramEntity(
                    entity_id=ids.entity_id(d.qualname, snapshot),
                    snapshot=snapshot,
                    kind=d.kind,
                    qualified_name=d.qualname,
                    path=mod.path,
                    span=d.span,
                    fingerprint=ids.fingerprint(src),
                )
            )

    edges: dict[tuple[str, str, Relation], dict[str, Any]] = {}

    def add(
        src_qn: str,
        dst: str,
        relation: Relation,
        line: int | None,
        unresolved_reason: str | None = None,
        attrs: dict | None = None,
    ) -> None:
        src = ids.entity_id(src_qn, snapshot)
        dst_id = ids.UNRESOLVED_PREFIX + dst if unresolved_reason else ids.entity_id(dst, snapshot)
        if dst_id == src and relation is not Relation.CALLS:
            return
        entry = edges.setdefault((src, dst_id, relation), {"lines": [], **(attrs or {})})
        if unresolved_reason:
            entry["reason"] = unresolved_reason
        if line is not None and line not in entry["lines"]:
            entry["lines"].append(line)

    # CONTAINS and INHERITS
    for mod in repo.modules.values():
        for d in mod.defs:
            add(d.parent, d.qualname, Relation.CONTAINS, None)
    collectors = {m.name: _CallCollector(repo, m, None) for m in repo.modules.values()}
    for mod in repo.modules.values():
        for d in mod.defs:
            if d.kind is not EntityKind.CLASS:
                continue
            bases = []
            for b in d.node.bases:
                parts = _dotted_parts(b)
                if not parts:
                    continue
                status, target = collectors[mod.name].resolve_name(parts[0], [])
                if status != _RESOLVED:
                    continue
                qn = repo.resolve_dotted(".".join([target, *parts[1:]])) if parts[1:] else target
                if qn and repo.defs.get(qn) and repo.defs[qn].kind is EntityKind.CLASS:
                    bases.append(qn)
                    add(d.qualname, qn, Relation.INHERITS, b.lineno)
            repo.bases[d.qualname] = bases

    # IMPORTS
    for mod in repo.modules.values():
        for target, line in mod.import_stmts:
            hit = target if target in repo.modules else None
            if hit is None and target.rpartition(".")[0] in repo.modules:
                hit = target.rpartition(".")[0]
            if hit is None:
                hit = next((p for p in _prefixes(target) if p in repo.modules), None)
            if hit == mod.name:
                continue
            if hit:
                add(mod.name, hit, Relation.IMPORTS, line)
            else:
                add(mod.name, target, Relation.IMPORTS, line, unresolved_reason=_EXTERNAL)

    # CALLS
    builtin_calls = 0
    for mod in repo.modules.values():
        col = collectors[mod.name]

        def emit(owner, target, line, reason, attrs):
            add(owner, target, Relation.CALLS, line, unresolved_reason=reason, attrs=attrs)

        col.emit = emit
        col.run()
        builtin_calls += col.builtin_calls

    # TESTS: test -> what it calls directly
    kinds = {e.entity_id: e.kind for e in entities}
    for (src, dst, rel), _attrs in list(edges.items()):
        if (
            rel is Relation.CALLS
            and kinds.get(src) is EntityKind.TEST
            and dst in kinds
            and kinds[dst] is not EntityKind.TEST
        ):
            edges.setdefault((src, dst, Relation.TESTS), {"via": "direct_call"})

    edge_records = []
    for (src, dst, rel), attrs in sorted(
        edges.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1])
    ):
        resolved = not dst.startswith(ids.UNRESOLVED_PREFIX)
        if "lines" in attrs:
            attrs = {**attrs, "lines": sorted(attrs["lines"])}
            if not attrs["lines"]:
                del attrs["lines"]
        edge_records.append(
            GraphEdge(
                edge_id=ids.new_id("EDGE", seed=f"{snapshot}|{src}|{rel}|{dst}"),
                src=src,
                dst=dst,
                relation=rel,
                resolved=resolved,
                provenance=Provenance.STATIC,
                snapshot=snapshot,
                attrs=attrs,
            )
        )

    stats: dict[str, Any] = {
        "files": len(files),
        "modules": len(repo.modules),
        "entities": len(entities),
        "edges": len(edge_records),
        "builtin_calls_skipped": builtin_calls,
        "unresolved_edges": sum(not e.resolved for e in edge_records),
    }
    for k in EntityKind:
        stats[f"kind.{k.value}"] = sum(e.kind is k for e in entities)
    for r in Relation:
        n = sum(e.relation is r for e in edge_records)
        if n:
            stats[f"relation.{r.value}"] = n
    return IndexResult(
        snapshot=snapshot,
        root=str(root),
        entities=entities,
        edges=edge_records,
        skipped=skipped,
        stats=stats,
    )


def _prefixes(dotted: str) -> list[str]:
    parts = dotted.split(".")
    return [".".join(parts[:i]) for i in range(len(parts), 0, -1)]
