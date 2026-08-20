"""Amem — cross-session memory for coding agents.

The shape of a working setup:

    from amem import Store, render, propose

    store = Store(memory_dir)

    # Opening a conversation: what the agent is told before anyone speaks.
    preamble = render(store.entries(), store.recent(), store.pending())

    # Closing one: what it noticed, for a person to approve.
    for candidate in await propose(complete, transcript, session_id=session.id):
        store.suggest(candidate)

    # Answering "where does X live": what it can look up on demand.
    hits = store.search("deployment path")

`complete` is yours — see `amem.extract.Completer`. Nothing here imports a
model client, and nothing reaches persistent memory that a user did not
approve: `suggest` queues, `keep` commits.
"""

from importlib.metadata import PackageNotFoundError, version

from amem.candidates import MemoryCandidate
from amem.check import Finding, report
from amem.consolidate import (
    BEHAVIOURAL_BUDGET_CHARS,
    PRESSURE_ACT_AT,
    PRESSURE_WARN_AT,
    find_dormant,
    find_superseded,
    pressure,
)
from amem.entry import (
    BEHAVIOURAL_KINDS,
    LOOKUP_KINDS,
    MemoryEntry,
    MemoryKind,
    MemoryScope,
)
from amem.extract import Completer, propose
from amem.inject import Actions, render
from amem.operations import (
    Operation,
    OperationResult,
    UnknownOperation,
    execute,
    parse_operation,
)
from amem.recent import SessionSummary
from amem.search import MemorySearchIndex, SearchHit
from amem.storage import AmbiguousHandleError, UpsertResult
from amem.store import Store
from amem.text import fold_text

__all__ = [
    "BEHAVIOURAL_BUDGET_CHARS",
    "BEHAVIOURAL_KINDS",
    "LOOKUP_KINDS",
    "PRESSURE_ACT_AT",
    "PRESSURE_WARN_AT",
    "Actions",
    "AmbiguousHandleError",
    "Completer",
    "Finding",
    "MemoryCandidate",
    "MemoryEntry",
    "MemoryKind",
    "MemoryScope",
    "MemorySearchIndex",
    "Operation",
    "OperationResult",
    "SearchHit",
    "SessionSummary",
    "Store",
    "UnknownOperation",
    "UpsertResult",
    "execute",
    "find_dormant",
    "find_superseded",
    "fold_text",
    "parse_operation",
    "pressure",
    "propose",
    "render",
    "report",
]

try:
    __version__ = version("amem")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0.0.0.dev0"
