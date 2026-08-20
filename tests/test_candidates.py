"""The queue between noticing a fact and keeping it.

Extraction closes the gap where persistent memory held only what the agent
thought to record at the moment it came up. The queue is what keeps it from
also removing the person from the decision: a candidate is a proposal, and it
expires if nobody acts on it.
"""

from __future__ import annotations

import time
from pathlib import Path

from amem.candidates import (
    CANDIDATE_TTL_SECONDS,
    MAX_CANDIDATES,
    CandidateFile,
    MemoryCandidate,
)


def _file(tmp_path: Path) -> CandidateFile:
    return CandidateFile(tmp_path / "candidates.jsonl")


class TestQueue:
    def test_a_restatement_of_something_queued_is_not_queued_twice(self, tmp_path: Path) -> None:
        queue = _file(tmp_path)

        queue.add([MemoryCandidate(kind="project", content="the repo is at /x")])
        queue.add([MemoryCandidate(kind="project", content="  THE REPO IS AT /X  ")])

        assert len(queue.read()) == 1

    def test_the_queue_stays_small(self, tmp_path: Path) -> None:
        """A backlog nobody clears is noise in every future session."""
        queue = _file(tmp_path)

        queue.add([MemoryCandidate(kind="project", content=f"fact {i}") for i in range(40)])

        assert len(queue.read()) == MAX_CANDIDATES

    def test_a_proposal_nobody_acted_on_expires(self, tmp_path: Path) -> None:
        queue = _file(tmp_path)
        stale = MemoryCandidate(
            kind="project",
            content="old news",
            created_at=time.time() - CANDIDATE_TTL_SECONDS - 1,
        )

        queue.write([stale, MemoryCandidate(kind="project", content="current")])

        assert [c.content for c in queue.read()] == ["current"]

    def test_taking_one_leaves_the_rest(self, tmp_path: Path) -> None:
        queue = _file(tmp_path)
        queue.add(
            [
                MemoryCandidate(kind="project", content="a"),
                MemoryCandidate(kind="project", content="b"),
            ]
        )

        first = queue.read()[0]

        assert queue.take(first.id).content == "a"
        assert [c.content for c in queue.read()] == ["b"]
        assert queue.take(first.id) is None, "taking it twice is not taking it again"

    def test_a_corrupt_line_does_not_take_the_file_with_it(self, tmp_path: Path) -> None:
        queue = _file(tmp_path)

        queue.path.write_text('{"broken\nnot json at all\n', encoding="utf-8")

        assert queue.read() == []

    def test_a_missing_file_is_simply_empty(self, tmp_path: Path) -> None:
        assert _file(tmp_path).read() == []
