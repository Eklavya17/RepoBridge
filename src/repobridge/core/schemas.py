"""Data contracts v1 (docs/contracts.md). Frozen in Stage A.

Every top-level record is an immutable dataclass with a versioned ``SCHEMA`` tag, strict JSON
round-tripping (``to_dict``/``from_dict``/``to_json``/``from_json``) and field-level validation
on construction. Rules that span several records live in ``repobridge.core.rules``.

Changing a field after Stage A requires a ``core/*`` PR, a schema version bump and an ADR.
"""

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from repobridge.core import ids
from repobridge.core.serialization import Contract, ContractError, Record

# =========================================================================== enums


class Status(StrEnum):
    """Status lattice: proposed -> checked -> observed -> reproduced -> regression_checked,
    or refuted (terminal). Moving back to ``proposed`` happens only through invalidation."""

    PROPOSED = "proposed"
    CHECKED = "checked"
    OBSERVED = "observed"
    REPRODUCED = "reproduced"
    REGRESSION_CHECKED = "regression_checked"
    REFUTED = "refuted"

    @property
    def rank(self) -> int:
        return _STATUS_ORDER.index(self) if self is not Status.REFUTED else -1

    def can_become(self, new: "Status") -> bool:
        if self is Status.REFUTED:
            return False
        if new is Status.REFUTED:
            return True
        return new.rank > self.rank

    def at_least(self, other: "Status") -> bool:
        return self is not Status.REFUTED and self.rank >= other.rank


_STATUS_ORDER = (
    Status.PROPOSED,
    Status.CHECKED,
    Status.OBSERVED,
    Status.REPRODUCED,
    Status.REGRESSION_CHECKED,
)


class Provenance(StrEnum):
    STATIC = "static"
    OBSERVED = "observed"
    LLM_INFERRED = "llm_inferred"


class EntityKind(StrEnum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    TEST = "test"
    VARIABLE = "variable"  # fields, globals and locks (concurrency overlay)


class Relation(StrEnum):
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    INHERITS = "INHERITS"
    DEF_USE = "DEF_USE"
    TESTS = "TESTS"
    ACCESSES = "ACCESSES"
    GUARDED_BY = "GUARDED_BY"


class LedgerSection(StrEnum):
    POSTMORTEM = "postmortem"
    STRATEGY = "strategy"
    PLAN = "plan"
    EXECUTION = "execution"


class QuestionKind(StrEnum):
    SLOT_PROPERTY = "slot_property"  # debugging / vulnerabilities
    COST_PROPERTY = "cost_property"  # optimization
    ACCESS_PROPERTY = "access_property"  # concurrency


class Confidence(StrEnum):
    """Ranking aid only. Never evidence."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Fidelity(StrEnum):
    FULL = "full"
    SIGNATURE = "signature"
    SUMMARY = "summary"
    REFERENCE = "reference"


class ItemRole(StrEnum):
    ANCHOR = "anchor"
    ESSENTIAL = "essential"
    SUPPORTING = "supporting"
    TEST = "test"
    CONSTRAINT = "constraint"


class HintOutcome(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    UNUSED = "unused"
    CONTRADICTED = "contradicted"


class LessonKind(StrEnum):
    REFUTED_HYPOTHESIS = "refuted_hypothesis"
    REJECTED_PATCH = "rejected_patch"


# =========================================================================== helpers

_SLOT = re.compile(r"^(return|self|(param|field|global):[A-Za-z_][A-Za-z0-9_.]*)$")
_SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
MAX_DIGEST_CHARS = 160


def _req_id(value: str, prefix: str, name: str) -> None:
    if not ids.is_record_id(value, prefix):
        raise ContractError(f"{name} must look like '{prefix}-<token>', got {value!r}")


def _req_entity(value: str, name: str) -> None:
    if not ids.is_entity_id(value):
        raise ContractError(
            f"{name} must be an entity ID like 'py:pkg.mod.func@<rev>', got {value!r}"
        )


def _req_snapshot(value: str) -> None:
    if not ids.is_snapshot(value):
        raise ContractError(
            f"snapshot must be a 40-hex SHA (optionally '+dirty:<12 hex>'), got {value!r}"
        )


def _req_text(value: str, name: str) -> None:
    if not value.strip():
        raise ContractError(f"{name} must not be empty")


def _req_ref(value: str, name: str) -> None:
    """A reference to any record or entity."""
    if not (ids.is_record_id(value) or ids.is_entity_id(value)):
        raise ContractError(f"{name}: {value!r} is neither a record ID nor an entity ID")


def _no_ghosts(refs: tuple[str, ...], name: str) -> None:
    ghosts = [r for r in refs if ids.id_prefix(r) == "GH"]
    if ghosts:
        raise ContractError(
            f"{name} may not depend on ghost hints {ghosts}: hints are never evidence"
        )


def _req_slot(value: str) -> None:
    if not _SLOT.match(value):
        raise ContractError(
            f"slot must be 'return', 'self', 'param:<name>', 'field:<name>' or "
            f"'global:<name>', got {value!r}"
        )


# =========================================================================== value objects


@dataclass(frozen=True)
class Span(Record):
    """Inclusive 1-based line range."""

    start_line: int
    end_line: int

    def _validate(self) -> None:
        if not 1 <= self.start_line <= self.end_line:
            raise ContractError(f"invalid span {self.start_line}-{self.end_line}")


@dataclass(frozen=True)
class Question(Record):
    """One atomic question: one entity, one slot, one property."""

    kind: QuestionKind
    entity: str
    slot: str
    property: str

    def _validate(self) -> None:
        _req_entity(self.entity, "question.entity")
        _req_slot(self.slot)
        if not _SNAKE.match(self.property):
            raise ContractError(f"property must be snake_case, got {self.property!r}")


@dataclass(frozen=True)
class Budget(Record):
    input_tokens: int
    output_tokens: int

    def _validate(self) -> None:
        if self.input_tokens <= 0 or self.output_tokens <= 0:
            raise ContractError("budget token counts must be positive")


@dataclass(frozen=True)
class Claim(Record):
    """A property of one entity slot, optionally under a structured condition."""

    entity: str
    slot: str
    property: str
    condition: dict[str, Any] | None = None

    def _validate(self) -> None:
        _req_entity(self.entity, "claim.entity")
        _req_slot(self.slot)
        if not _SNAKE.match(self.property):
            raise ContractError(f"property must be snake_case, got {self.property!r}")


@dataclass(frozen=True)
class BundleItem(Record):
    ref: str
    fidelity: Fidelity
    role: ItemRole
    tokens: int

    def _validate(self) -> None:
        _req_ref(self.ref, "bundle item ref")
        if self.tokens < 0:
            raise ContractError("bundle item tokens must be >= 0")


@dataclass(frozen=True)
class StrategyStats(Record):
    n: int = 0
    localized_rate: float = 0.0
    mean_tokens: float = 0.0
    mean_steps: float = 0.0

    def _validate(self) -> None:
        if self.n < 0 or self.mean_tokens < 0 or self.mean_steps < 0:
            raise ContractError("strategy stats must be non-negative")
        if not 0.0 <= self.localized_rate <= 1.0:
            raise ContractError("localized_rate must be in [0, 1]")


# =========================================================================== contracts


@dataclass(frozen=True)
class ProgramEntity(Contract):
    """A program element at one repository snapshot."""

    SCHEMA = "repobridge.program_entity/v1"

    entity_id: str
    snapshot: str
    kind: EntityKind
    qualified_name: str
    path: str
    span: Span
    fingerprint: str

    def _validate(self) -> None:
        _req_snapshot(self.snapshot)
        _req_entity(self.entity_id, "entity_id")
        _lang, qname, rev = ids.parse_entity_id(self.entity_id)
        if qname != self.qualified_name:
            raise ContractError(
                f"entity_id names {qname!r} but qualified_name is {self.qualified_name!r}"
            )
        if rev != ids.rev_tag(self.snapshot):
            raise ContractError(f"entity_id revision {rev!r} does not match snapshot")
        if not ids.is_fingerprint(self.fingerprint):
            raise ContractError(f"fingerprint must be 16 hex characters, got {self.fingerprint!r}")
        if self.path.startswith("/") or "\\" in self.path:
            raise ContractError(
                f"path must be repo-relative with '/' separators, got {self.path!r}"
            )


@dataclass(frozen=True)
class GraphEdge(Contract):
    """A directed relation between entities. Unresolved calls/imports point at
    ``unresolved:<name>`` instead of guessing a target."""

    SCHEMA = "repobridge.graph_edge/v1"

    edge_id: str
    src: str
    dst: str
    relation: Relation
    resolved: bool
    provenance: Provenance
    snapshot: str
    attrs: dict[str, Any] = field(default_factory=dict)

    def _validate(self) -> None:
        _req_id(self.edge_id, "EDGE", "edge_id")
        _req_snapshot(self.snapshot)
        _req_entity(self.src, "src")
        if ids.parse_entity_id(self.src)[2] != ids.rev_tag(self.snapshot):
            raise ContractError("src revision does not match snapshot")
        if self.resolved:
            _req_entity(self.dst, "dst")
        else:
            if self.relation not in (Relation.CALLS, Relation.IMPORTS):
                raise ContractError("only CALLS and IMPORTS edges may be unresolved")
            if not self.dst.startswith(ids.UNRESOLVED_PREFIX):
                raise ContractError(
                    f"unresolved dst must start with {ids.UNRESOLVED_PREFIX!r}, got {self.dst!r}"
                )


@dataclass(frozen=True)
class Evidence(Contract):
    """An artifact (span, trace, profile, test result, ...) stored once and passed by ID."""

    SCHEMA = "repobridge.evidence/v1"

    evidence_id: str
    task_id: str
    entity_ids: tuple[str, ...]
    artifact_ref: str
    digest: str
    producer: str
    status: Status
    snapshot: str
    depends_on: tuple[str, ...] = ()

    def _validate(self) -> None:
        _req_id(self.evidence_id, "EV", "evidence_id")
        _req_id(self.task_id, "TASK", "task_id")
        _req_snapshot(self.snapshot)
        for e in self.entity_ids:
            _req_entity(e, "entity_ids")
        _req_text(self.artifact_ref, "artifact_ref")
        _req_text(self.producer, "producer")
        _req_text(self.digest, "digest")
        if "\n" in self.digest or len(self.digest) > MAX_DIGEST_CHARS:
            raise ContractError(f"digest must be one line of at most {MAX_DIGEST_CHARS} chars")
        for r in self.depends_on:
            _req_ref(r, "depends_on")
        _no_ghosts(self.depends_on, "evidence")

    def with_status(self, new: Status) -> "Evidence":
        if not self.status.can_become(new):
            raise ContractError(f"status cannot move from {self.status} to {new}")
        return dataclasses.replace(self, status=new)


@dataclass(frozen=True)
class LedgerEvent(Contract):
    """One append-only entry in an investigation ledger."""

    SCHEMA = "repobridge.ledger_event/v1"

    event_id: str
    investigation_id: str
    section: LedgerSection
    type: str
    producer: str
    ts: str
    refs: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)

    def _validate(self) -> None:
        _req_id(self.event_id, "LE", "event_id")
        _req_id(self.investigation_id, "INV", "investigation_id")
        if not _SNAKE.match(self.type):
            raise ContractError(f"type must be snake_case, got {self.type!r}")
        _req_text(self.producer, "producer")
        for r in self.refs:
            _req_ref(r, "refs")
        try:
            parsed = datetime.fromisoformat(self.ts)
        except ValueError:
            raise ContractError(f"ts must be ISO 8601, got {self.ts!r}") from None
        if parsed.tzinfo is None:
            raise ContractError("ts must include a timezone (use UTC)")


@dataclass(frozen=True)
class ScoutRequest(Contract):
    """A work order: one question, a budget, and a reference to its context bundle."""

    SCHEMA = "repobridge.scout_request/v1"

    order_id: str
    investigation_id: str
    question: Question
    budget: Budget
    bundle_ref: str
    anchors: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    permitted_tools: tuple[str, ...] = ()
    answer_schema: str = "repobridge.scout_finding/v1"

    def _validate(self) -> None:
        _req_id(self.order_id, "WO", "order_id")
        _req_id(self.investigation_id, "INV", "investigation_id")
        _req_id(self.bundle_ref, "CB", "bundle_ref")
        for a in self.anchors:
            _req_entity(a, "anchors")
        for a in self.assumptions:
            _req_ref(a, "assumptions")
        _no_ghosts(self.assumptions, "assumptions")


@dataclass(frozen=True)
class ScoutFinding(Contract):
    """A scout's answer: a claim with citations, plus follow-up questions it needs."""

    SCHEMA = "repobridge.scout_finding/v1"

    finding_id: str
    order_id: str
    claim: Claim
    cites: tuple[str, ...]
    confidence: Confidence
    status: Status = Status.PROPOSED
    needs: tuple[Question, ...] = ()

    def _validate(self) -> None:
        _req_id(self.finding_id, "FND", "finding_id")
        _req_id(self.order_id, "WO", "order_id")
        if not self.cites:
            raise ContractError("a finding must cite at least one item from its bundle")
        for c in self.cites:
            _req_ref(c, "cites")
        _no_ghosts(self.cites, "cites")


@dataclass(frozen=True)
class ContextBundle(Contract):
    """The ordered, budgeted context handed to one scout."""

    SCHEMA = "repobridge.context_bundle/v1"

    bundle_id: str
    order_id: str
    token_budget: int
    snapshot: str
    items: tuple[BundleItem, ...]
    excluded: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    missing_requirements: tuple[str, ...] = ()

    def _validate(self) -> None:
        _req_id(self.bundle_id, "CB", "bundle_id")
        _req_id(self.order_id, "WO", "order_id")
        _req_snapshot(self.snapshot)
        if self.token_budget <= 0:
            raise ContractError("token_budget must be positive")
        used = sum(i.tokens for i in self.items)
        if used > self.token_budget:
            raise ContractError(f"items use {used} tokens, over the budget of {self.token_budget}")
        refs = [i.ref for i in self.items]
        if len(refs) != len(set(refs)):
            raise ContractError("bundle items must have unique refs")
        overlap = set(refs) & set(self.excluded)
        if overlap:
            raise ContractError(f"refs both included and excluded: {sorted(overlap)}")
        _no_ghosts(tuple(refs), "bundle items")

    @property
    def item_refs(self) -> frozenset[str]:
        return frozenset(i.ref for i in self.items)

    @property
    def tokens_used(self) -> int:
        return sum(i.tokens for i in self.items)


@dataclass(frozen=True)
class Summary(Contract):
    """A reusable, revision-scoped contract for one (entity, slot, property).

    ``fingerprints`` maps every source entity the summary relies on (including ``entity``
    itself) to its fingerprint when the summary was made; any change invalidates it."""

    SCHEMA = "repobridge.summary/v1"

    summary_id: str
    entity: str
    slot: str
    property: str
    status: Status
    fingerprints: dict[str, str]
    conditions: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()

    def _validate(self) -> None:
        _req_id(self.summary_id, "SUM", "summary_id")
        _req_entity(self.entity, "entity")
        _req_slot(self.slot)
        if not _SNAKE.match(self.property):
            raise ContractError(f"property must be snake_case, got {self.property!r}")
        if self.entity not in self.fingerprints:
            raise ContractError("fingerprints must include the summary's own entity")
        for e, fp in self.fingerprints.items():
            _req_entity(e, "fingerprints key")
            if not ids.is_fingerprint(fp):
                raise ContractError(f"bad fingerprint for {e}: {fp!r}")
        for r in self.depends_on:
            _req_ref(r, "depends_on")
        _no_ghosts(self.depends_on, "summary")

    def with_status(self, new: Status) -> "Summary":
        if not self.status.can_become(new):
            raise ContractError(f"status cannot move from {self.status} to {new}")
        return dataclasses.replace(self, status=new)


@dataclass(frozen=True)
class StrategyEdge(Contract):
    """Strategy memory: in a situation like this, this tool sequence worked this well."""

    SCHEMA = "repobridge.strategy_edge/v1"

    strategy_id: str
    situation_sig: str
    strategy: tuple[str, ...]
    stats: StrategyStats = field(default_factory=StrategyStats)

    def _validate(self) -> None:
        _req_id(self.strategy_id, "STR", "strategy_id")
        if self.situation_sig.count("/") != 2:
            raise ContractError("situation_sig must be '<area>/<anchor_kind>/<symptom_class>'")
        if not self.strategy:
            raise ContractError("strategy must name at least one tool")


@dataclass(frozen=True)
class GhostHint(Contract):
    """An unverified strategy transferred from a past investigation. Plan-only, never evidence."""

    SCHEMA = "repobridge.ghost_hint/v1"

    hint_id: str
    source_investigation: str
    situation_sig: str
    strategy_id: str
    ephemeral: bool = True
    outcome: HintOutcome = HintOutcome.PENDING

    def _validate(self) -> None:
        _req_id(self.hint_id, "GH", "hint_id")
        _req_id(self.source_investigation, "INV", "source_investigation")
        _req_id(self.strategy_id, "STR", "strategy_id")
        if not self.ephemeral:
            raise ContractError(
                "ghost hints are always ephemeral; promote a confirmed hint to a "
                "StrategyEdge instead"
            )


@dataclass(frozen=True)
class Lesson(Contract):
    """A refuted hypothesis or rejected patch, so later agents do not repeat it."""

    SCHEMA = "repobridge.lesson/v1"

    lesson_id: str
    kind: LessonKind
    reason: str
    applies_when: str
    refs: tuple[str, ...] = ()

    def _validate(self) -> None:
        _req_id(self.lesson_id, "LSN", "lesson_id")
        _req_text(self.reason, "reason")
        _req_text(self.applies_when, "applies_when")
        for r in self.refs:
            _req_ref(r, "refs")


# =========================================================================== registry

CONTRACTS: tuple[type[Contract], ...] = (
    ProgramEntity,
    GraphEdge,
    Evidence,
    LedgerEvent,
    ScoutRequest,
    ScoutFinding,
    ContextBundle,
    Summary,
    StrategyEdge,
    GhostHint,
    Lesson,
)
REGISTRY: dict[str, type[Contract]] = {c.SCHEMA: c for c in CONTRACTS}


def load(data: dict[str, Any]) -> Contract:
    """Decode any contract by its ``schema`` tag."""
    schema = data.get("schema") if isinstance(data, dict) else None
    if schema not in REGISTRY:
        raise ContractError(f"unknown schema {schema!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[schema].from_dict(data)
