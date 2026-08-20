"""One object over the files, so a caller needs to know about none of them.

The pieces underneath are deliberately separate — a store, an index, a
candidate queue, a recap log — because each is testable alone and the store is
a text file somebody may want to read. This is the layer that spares an
application from assembling them, and it is where one rule is enforced that the
pieces cannot enforce for themselves:

    suggest() queues.   keep() commits.

Nothing else writes to persistent memory. An extractor can propose all day; a
proposal becomes a memory when the application has asked a person and been told
yes. That is the whole reason `keep` exists as a separate call rather than as a
flag on `suggest`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from amem.candidates import CANDIDATES_FILENAME, CandidateFile, MemoryCandidate
from amem.entry import MemoryEntry, MemoryKind
from amem.recent import RECENT_FILENAME, SessionSummary, read_recent_summaries
from amem.search import MemorySearchIndex, SearchHit
from amem.storage import (
    PERSISTENT_FILENAME,
    UpsertResult,
    delete_entry,
    read_entries,
    resolve_handle,
    set_affirmed,
    set_retired,
    stamp_relevance,
    update_entry,
    upsert_entry,
)

#: The index is a cache. Losing it costs a rebuild and nothing else, which is
#: what lets the store stay a file someone can edit by hand.
INDEX_FILENAME = "search.db"


class Store:
    """Persistent memory rooted at a directory.

    Creates nothing until something is written, so pointing at an empty or
    absent directory is a valid empty store rather than an error.
    """

    def __init__(self, directory: Path | str) -> None:
        # expanduser because the obvious call is Store("~/.myagent/memory"), and
        # Path does not expand it: without this the store lands in a directory
        # literally named "~" beside wherever the process happened to start.
        self.directory = Path(directory).expanduser()
        self.path = self.directory / PERSISTENT_FILENAME
        self._candidates = CandidateFile(self.directory / CANDIDATES_FILENAME)
        self._index = MemorySearchIndex(self.directory / INDEX_FILENAME, self.path)

    # ---- reading -------------------------------------------------------

    def entries(self) -> list[MemoryEntry]:
        """Everything stored, oldest first. Includes retired entries."""
        return read_entries(self.path)

    def recent(self, limit: int = 5) -> list[SessionSummary]:
        return read_recent_summaries(self.directory / RECENT_FILENAME, limit=limit)

    def pending(self) -> list[MemoryCandidate]:
        """Proposals awaiting a decision. Not memory yet."""
        return self._candidates.read()

    def search(self, query: str, *, limit: int = 8) -> list[SearchHit]:
        return self._index.search(query, self.entries(), limit=limit)

    def get(self, handle: str) -> MemoryEntry | None:
        """One entry by `key`, full id, or unambiguous id prefix."""
        return resolve_handle(self.entries(), handle)

    # ---- proposing -----------------------------------------------------

    def suggest(self, candidates: Sequence[MemoryCandidate]) -> int:
        """Queue proposals. Returns how many were new."""
        return self._candidates.add(candidates)

    def keep(self, candidate_id: str) -> UpsertResult | None:
        """Approve a proposal into memory. The only path from queue to store."""
        candidate = self._candidates.take(candidate_id)
        if candidate is None:
            return None
        return upsert_entry(
            self.path,
            MemoryEntry(
                kind=candidate.kind,
                scope="persistent",
                content=candidate.content,
                key=candidate.key,
            ),
        )

    def dismiss(self, candidate_id: str) -> bool:
        return self._candidates.take(candidate_id) is not None

    # ---- writing -------------------------------------------------------

    def add(self, kind: MemoryKind, content: str, *, key: str | None = None) -> UpsertResult:
        """Write directly, for a fact the user stated outright.

        Bypasses the queue because there is nothing to approve: the user said
        it. Anything a model *inferred* goes through `suggest`.
        """
        return upsert_entry(
            self.path,
            MemoryEntry(kind=kind, scope="persistent", content=content, key=key),
        )

    def update(self, handle: str, content: str) -> MemoryEntry | None:
        return update_entry(self.path, handle, content)

    def retire(self, handle: str) -> MemoryEntry | None:
        """Stop injecting an entry without losing it. Reversible."""
        return set_retired(self.path, handle, retired=True)

    def restore(self, handle: str) -> MemoryEntry | None:
        return set_retired(self.path, handle, retired=False)

    def affirm(self, handle: str) -> MemoryEntry | None:
        """Record that this entry was raised and kept.

        The answer :func:`find_superseded` had no way to record. Saying "both
        of these still hold" used to leave no trace, so the same pair came back
        the next session and the one after — a prompt that asks for attention
        and ignores the answer teaches people to stop giving it.
        """
        return set_affirmed(self.path, handle)

    def consolidate(
        self, content: str, replacing: Sequence[str], *, key: str | None = None
    ) -> UpsertResult | None:
        """Replace several entries with one that keeps what all of them said.

        The usual answer when entries look superseded, and the one that had no
        support here: retiring the older entry is right only when the newer one
        subsumes it, and a later instruction more often *adds* to an earlier one
        than replaces it. On a real store the newest of three generations had
        quietly dropped three requirements the older two carried; retiring on
        that advice would have removed them with nothing to show it happened.

        Written first and retired second, and never the reverse: interrupted
        after the write leaves a duplicate, which is visible and costs a line to
        fix. Interrupted after a retirement would leave the requirements gone
        with nothing left holding them.

        Returns ``None`` without writing anything if a handle does not resolve,
        since consolidating onto the wrong set is worse than not consolidating.
        """
        entries = self.entries()
        targets = [resolve_handle(entries, h) for h in replacing]
        if any(t is None for t in targets):
            return None

        kinds = {t.kind for t in targets if t is not None}
        result = upsert_entry(
            self.path,
            MemoryEntry(
                kind=kinds.pop() if len(kinds) == 1 else "feedback",
                scope="persistent",
                content=content,
                key=key,
            ),
            dedup=False,
        )
        for target in targets:
            if target is not None and target.id != result.entry.id:
                set_retired(self.path, target.id, retired=True)
        return result

    def delete(self, handle: str) -> bool:
        """For an entry that was wrong. Use `retire` for one that is merely over."""
        return delete_entry(self.path, handle)

    def note_topics(self, conversation: str, *, now: float | None = None) -> int:
        """Record which entries this conversation was about.

        Feeds the dormancy ranking, which asks what to review rather than what
        to remove. Cheap enough to call wherever a session ends.
        """
        import time as _time

        return stamp_relevance(self.path, conversation, now=now or _time.time())
