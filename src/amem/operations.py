"""The operations an agent can perform on a store, as data.

:func:`amem.render` tells an agent to search the store, read an entry in full,
keep or drop a proposal, retire an entry or affirm it. Until this module those
were things the preamble described and the package could not do: every host had
to define the same vocabulary, validate it, and dispatch it to methods that
already existed — measured at about a hundred and fifty lines before any of the
host's own policy.

So the vocabulary lives here, next to the text that describes it. A host wires
one function and keeps what is genuinely its own: whether to ask the user first,
how to render the result, what to log.

Operations are models rather than a function per verb because they arrive as
data — a tool call, a JSON line, a form — and validating them at the boundary is
the same reason :mod:`amem.entry` is a model. ``writes`` is on the operation
rather than left to the host to enumerate: a host gating writes should not have
to keep its own list in step with this one.

    op = parse_operation({"op": "search", "query": "where do reports live"})
    if op.writes and not await ask_the_user(op.describe()):
        return
    result = execute(store, op)
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from amem.candidates import MemoryCandidate
from amem.entry import MemoryEntry, MemoryKind
from amem.recent import SessionSummary
from amem.search import SearchHit
from amem.store import Store


class _Operation(BaseModel):
    """Shared behaviour. Not exported: hosts match on the concrete types."""

    @property
    def writes(self) -> bool:
        """Whether performing this changes the store.

        Read by hosts that ask before writing. On the operation rather than in
        a list the host maintains, so adding one here cannot leave a host
        silently letting it through ungated.
        """
        return False

    def describe(self) -> str:
        """One line, for asking a user whether to allow it."""
        return self.op  # type: ignore[attr-defined,no-any-return]


class SearchOp(_Operation):
    """Find entries whose text matches. Read-only."""

    op: Literal["search"]
    query: str
    limit: int = 8

    def describe(self) -> str:
        return f"Search memory for {self.query!r}"


class GetOp(_Operation):
    """Read one entry in full, having seen it summarised in the index."""

    op: Literal["get"]
    handle: str

    def describe(self) -> str:
        return f"Read memory entry {self.handle}"


class ListOp(_Operation):
    """Everything stored, including retired entries."""

    op: Literal["list"]

    def describe(self) -> str:
        return "List stored memory"


class AddOp(_Operation):
    """Write a fact the user stated outright.

    Bypasses the queue because there is nothing to approve — the user said it.
    Anything a model *inferred* goes through ``suggest`` and ``promote``.
    """

    op: Literal["add"]
    kind: MemoryKind
    content: str
    key: str | None = None

    @property
    def writes(self) -> bool:
        return True

    def describe(self) -> str:
        return f"Store a {self.kind} memory: {self.content[:60]}"


class PromoteOp(_Operation):
    """Keep a queued proposal. The only path from candidate to memory."""

    op: Literal["promote"]
    id: str

    @property
    def writes(self) -> bool:
        return True

    def describe(self) -> str:
        return f"Keep suggested memory {self.id}"


class DismissOp(_Operation):
    """Drop a queued proposal. Nothing was stored, so nothing is lost."""

    op: Literal["dismiss"]
    id: str

    def describe(self) -> str:
        return f"Discard suggested memory {self.id}"


class UpdateOp(_Operation):
    """Replace an entry's text, keeping its identity and its date."""

    op: Literal["update"]
    handle: str
    content: str

    @property
    def writes(self) -> bool:
        return True

    def describe(self) -> str:
        return f"Rewrite memory entry {self.handle}"


class RetireOp(_Operation):
    """Stop injecting an entry without losing it.

    For something that was right and no longer applies. The record stays and
    stays searchable; it only stops arriving in every conversation, which is
    the whole cost a stale behavioural entry imposes.
    """

    op: Literal["retire"]
    handle: str

    @property
    def writes(self) -> bool:
        return True

    def describe(self) -> str:
        return f"Retire memory entry {self.handle}"


class RestoreOp(_Operation):
    """Put a retired entry back into force."""

    op: Literal["restore"]
    handle: str

    @property
    def writes(self) -> bool:
        return True

    def describe(self) -> str:
        return f"Restore memory entry {self.handle}"


class AffirmOp(_Operation):
    """Record that an entry was raised and still holds.

    The answer to a supersession suggestion that is not "retire it", and more
    often the right one. Not a write in the sense the others are: it stores no
    fact and removes none, it records that a question was answered — which is
    why a host asking permission before writes should not ask before this one.
    """

    op: Literal["affirm"]
    handle: str

    def describe(self) -> str:
        return f"Record that memory entry {self.handle} still holds"


class ConsolidateOp(_Operation):
    """Replace several entries with one that keeps what all of them said."""

    op: Literal["consolidate"]
    content: str
    replacing: list[str]
    key: str | None = None

    @property
    def writes(self) -> bool:
        return True

    def describe(self) -> str:
        return f"Merge {len(self.replacing)} memory entries into one"


class DeleteOp(_Operation):
    """Remove an entry that was wrong. Use ``retire`` for one merely over."""

    op: Literal["delete"]
    handle: str

    @property
    def writes(self) -> bool:
        return True

    def describe(self) -> str:
        return f"Delete memory entry {self.handle}"


Operation = Annotated[
    Union[  # noqa: UP007 — pydantic reads the union at runtime
        SearchOp,
        GetOp,
        ListOp,
        AddOp,
        PromoteOp,
        DismissOp,
        UpdateOp,
        RetireOp,
        RestoreOp,
        AffirmOp,
        ConsolidateOp,
        DeleteOp,
    ],
    Field(discriminator="op"),
]

_ADAPTER: TypeAdapter[Operation] = TypeAdapter(Operation)

#: Every operation name, for a host building its own schema or its own prompt.
OPERATION_NAMES: tuple[str, ...] = (
    "search",
    "get",
    "list",
    "add",
    "promote",
    "dismiss",
    "update",
    "retire",
    "restore",
    "affirm",
    "consolidate",
    "delete",
)


class UnknownOperation(ValueError):
    """The payload did not describe an operation this package performs."""


def parse_operation(payload: object) -> Operation:
    """Validate an operation from whatever the host received.

    Raises :class:`UnknownOperation` rather than pydantic's error, so a host can
    tell "the agent asked for something that does not exist" apart from its own
    bugs without importing pydantic to catch it.
    """
    try:
        return _ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise UnknownOperation(_explain(payload, exc)) from exc


def _explain(payload: object, exc: ValidationError) -> str:
    """Say what is wrong in terms of the operation, not of the validator.

    This message usually goes back to the agent that sent the payload, so it is
    an instruction as much as a diagnosis. Pydantic's own text names the union
    and every member of it — accurate, and not something to hand to a model as
    guidance.
    """
    name = payload.get("op") if isinstance(payload, dict) else None
    if not isinstance(name, str) or name not in OPERATION_NAMES:
        listed = ", ".join(OPERATION_NAMES)
        return f"no operation named {name!r}. Available: {listed}"

    def field(error: object) -> str:
        # A discriminated union puts the tag first in `loc`, so the field this
        # is actually about is what follows it.
        path = [str(p) for p in error["loc"] if str(p) != name]  # type: ignore[index]
        return ".".join(path) or name

    missing = sorted(field(e) for e in exc.errors() if e["type"] == "missing")
    if missing:
        return f"{name!r} needs {', '.join(missing)}"
    wrong = "; ".join(f"{field(e)}: {e['msg']}" for e in exc.errors())
    return f"{name!r} was not usable — {wrong}"


class OperationResult(BaseModel):
    """What an operation produced.

    One shape for every operation, because a host renders results generically
    and matching on the request type to know which field to read is work each
    host would repeat. ``found`` is False where the handle or id did not
    resolve — an answer, not an error: an agent asking about something that is
    not there has learned something.
    """

    op: str
    found: bool = True
    hits: list[SearchHit] = Field(default_factory=list)
    entry: MemoryEntry | None = None
    entries: list[MemoryEntry] = Field(default_factory=list)
    candidates: list[MemoryCandidate] = Field(default_factory=list)
    recent: list[SessionSummary] = Field(default_factory=list)
    merged: bool = False
    replaced_content: str | None = None
    """What a merge overwrote, so a wrong one can be undone in the same turn."""

    advisories: list[tuple[str, str, float]] = Field(default_factory=list)
    """Near-misses the write did not act on. Reported rather than merged."""


def execute(store: Store, operation: Operation) -> OperationResult:
    """Perform *operation* against *store*.

    Does no asking. Whether the user is consulted first is the host's policy,
    and :attr:`_Operation.writes` is what it should consult — this package's own
    gate is the one that matters for what *enters* memory, and it is that a
    proposal only becomes an entry through ``promote``.
    """
    match operation:
        case SearchOp():
            return OperationResult(
                op="search", hits=store.search(operation.query, limit=operation.limit)
            )
        case GetOp():
            entry = store.get(operation.handle)
            return OperationResult(op="get", found=entry is not None, entry=entry)
        case ListOp():
            return OperationResult(
                op="list",
                entries=store.entries(),
                candidates=store.pending(),
                recent=store.recent(),
            )
        case AddOp():
            result = store.add(operation.kind, operation.content, key=operation.key)
            return OperationResult(
                op="add",
                entry=result.entry,
                merged=result.merged,
                replaced_content=result.replaced_content,
                advisories=list(result.advisories),
            )
        case PromoteOp():
            result = store.keep(operation.id)
            if result is None:
                return OperationResult(op="promote", found=False)
            return OperationResult(
                op="promote",
                entry=result.entry,
                merged=result.merged,
                replaced_content=result.replaced_content,
                advisories=list(result.advisories),
            )
        case DismissOp():
            return OperationResult(op="dismiss", found=store.dismiss(operation.id))
        case UpdateOp():
            entry = store.update(operation.handle, operation.content)
            return OperationResult(op="update", found=entry is not None, entry=entry)
        case RetireOp():
            entry = store.retire(operation.handle)
            return OperationResult(op="retire", found=entry is not None, entry=entry)
        case RestoreOp():
            entry = store.restore(operation.handle)
            return OperationResult(op="restore", found=entry is not None, entry=entry)
        case AffirmOp():
            entry = store.affirm(operation.handle)
            return OperationResult(op="affirm", found=entry is not None, entry=entry)
        case ConsolidateOp():
            result = store.consolidate(
                operation.content, replacing=operation.replacing, key=operation.key
            )
            if result is None:
                return OperationResult(op="consolidate", found=False)
            return OperationResult(op="consolidate", entry=result.entry)
        case DeleteOp():
            return OperationResult(op="delete", found=store.delete(operation.handle))
