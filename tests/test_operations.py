"""The operations the preamble describes, performed by the package that describes them.

Before this module `render` told an agent to search the store, read an entry,
keep a proposal or retire one — and none of those were things this package
offered a way to do. Every host defined the same vocabulary, validated it, and
dispatched it to methods that already existed. Measured on one: a hundred and
five lines of schema and forty-eight of dispatch before any of its own policy.

So these tests are written the way a new host would use it, with nothing from
any particular application in them.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from amem import Store, execute, parse_operation
from amem.candidates import MemoryCandidate
from amem.operations import (
    OPERATION_NAMES,
    AddOp,
    AffirmOp,
    RetireOp,
    SearchOp,
    UnknownOperation,
)


def _store() -> Store:
    return Store(Path(tempfile.mkdtemp()))


def _run(store: Store, payload: dict[str, object]):
    return execute(store, parse_operation(payload))


class TestAHostNeedsNothingElse:
    """A round trip using only what the package exports."""

    def test_a_fact_can_be_stored_and_found_again(self) -> None:
        store = _store()

        _run(
            store,
            {"op": "add", "kind": "project", "content": "报告在 output/reports/", "key": "r/d"},
        )
        result = _run(store, {"op": "search", "query": "报告在哪个目录"})

        assert [h.handle for h in result.hits] == ["r/d"]

    def test_an_entry_can_be_read_in_full_by_handle(self) -> None:
        store = _store()
        _run(store, {"op": "add", "kind": "project", "content": "a long fact", "key": "p/one"})

        result = _run(store, {"op": "get", "handle": "p/one"})

        assert result.found
        assert result.entry is not None
        assert result.entry.content == "a long fact"

    def test_asking_about_something_absent_is_an_answer_not_an_error(self) -> None:
        """An agent that learns the store has nothing has learned something."""
        result = _run(_store(), {"op": "get", "handle": "nothing/here"})

        assert result.found is False
        assert result.entry is None

    def test_list_returns_the_three_kinds_of_thing_a_store_holds(self) -> None:
        store = _store()
        store.add("project", "a fact", key="p/one")
        store.suggest([MemoryCandidate(kind="project", content="a guess")])

        result = _run(store, {"op": "list"})

        assert len(result.entries) == 1
        assert len(result.candidates) == 1


class TestTheApprovalGateSurvivesTheOperationLayer:
    """The one property this package claims over every alternative.

    Exposing operations is where it would be lost: a `promote` that could be
    reached without a decision, or an `add` that quietly took proposals.
    """

    def test_a_proposal_is_not_stored_by_listing_it(self) -> None:
        store = _store()
        store.suggest([MemoryCandidate(kind="project", content="a guess")])

        _run(store, {"op": "list"})

        assert store.entries() == []

    def test_promote_is_the_only_operation_that_stores_a_proposal(self) -> None:
        store = _store()
        store.suggest([MemoryCandidate(kind="project", content="a guess")])
        candidate = store.pending()[0]

        assert store.entries() == []
        result = _run(store, {"op": "promote", "id": candidate.id})

        assert result.entry is not None
        assert [e.content for e in store.entries()] == ["a guess"]

    def test_dismiss_loses_nothing_because_nothing_was_stored(self) -> None:
        store = _store()
        store.suggest([MemoryCandidate(kind="project", content="a guess")])

        assert _run(store, {"op": "dismiss", "id": store.pending()[0].id}).found
        assert store.pending() == []
        assert store.entries() == []


class TestWhichOperationsChangeTheStore:
    """`writes` is on the operation so a host gating writes cannot fall behind.

    A host keeping its own list of which verbs to ask about has to update it
    every time this package gains one, and the failure is silent: the new verb
    goes through ungated.
    """

    @pytest.mark.parametrize("name", OPERATION_NAMES)
    def test_every_operation_says_whether_it_writes(self, name: str) -> None:
        sample: dict[str, dict[str, object]] = {
            "search": {"query": "x"},
            "get": {"handle": "h"},
            "list": {},
            "add": {"kind": "project", "content": "x"},
            "promote": {"id": "i"},
            "dismiss": {"id": "i"},
            "update": {"handle": "h", "content": "x"},
            "retire": {"handle": "h"},
            "restore": {"handle": "h"},
            "affirm": {"handle": "h"},
            "consolidate": {"content": "x", "replacing": ["h"]},
            "delete": {"handle": "h"},
        }
        operation = parse_operation({"op": name, **sample[name]})

        assert isinstance(operation.writes, bool)
        assert operation.describe()

    def test_reading_does_not_count_as_writing(self) -> None:
        assert SearchOp(op="search", query="x").writes is False

    def test_storing_does(self) -> None:
        assert AddOp(op="add", kind="project", content="x").writes is True
        assert RetireOp(op="retire", handle="h").writes is True

    def test_affirming_does_not(self) -> None:
        """It stores no fact and removes none — it records that a question was
        answered, and asking permission to store the user's own answer is a
        loop with nothing at the end of it."""
        assert AffirmOp(op="affirm", handle="h").writes is False


class TestBadInput:
    def test_an_operation_that_does_not_exist_is_named_as_such(self) -> None:
        with pytest.raises(UnknownOperation):
            parse_operation({"op": "teleport"})

    def test_a_known_operation_missing_its_argument_is_rejected(self) -> None:
        with pytest.raises(UnknownOperation):
            parse_operation({"op": "get"})

    def test_the_error_is_catchable_without_importing_pydantic(self) -> None:
        """A host should be able to tell "the agent asked for something that
        does not exist" from its own bugs using only what this package exports."""
        assert issubclass(UnknownOperation, ValueError)


class TestConsolidatingThroughTheLayer:
    def test_it_keeps_one_entry_and_retires_the_others(self) -> None:
        store = _store()
        a = store.add("feedback", "Read the README first.").entry
        b = store.add("feedback", "Verify the date with `date`.").entry

        result = _run(
            store,
            {
                "op": "consolidate",
                "content": "Read the README, then verify the date with `date`.",
                "replacing": [a.id, b.id],
            },
        )

        assert result.found
        live = [e for e in store.entries() if e.retired_at is None]
        assert [e.content for e in live] == ["Read the README, then verify the date with `date`."]

    def test_an_unresolvable_handle_changes_nothing(self) -> None:
        store = _store()
        store.add("feedback", "Read the README first.")

        result = _run(store, {"op": "consolidate", "content": "x", "replacing": ["0" * 32]})

        assert result.found is False
        assert [e.content for e in store.entries()] == ["Read the README first."]


class TestTheErrorIsWrittenForWhoeverReadsIt:
    """The message usually goes back to the agent that sent the payload.

    So it is an instruction as much as a diagnosis. Pydantic's own text names
    the union and all twelve members of it — accurate, and not something to
    hand a model as guidance.
    """

    def test_an_unknown_name_lists_the_real_ones(self) -> None:
        with pytest.raises(UnknownOperation) as caught:
            parse_operation({"op": "teleport"})

        message = str(caught.value)
        assert "teleport" in message
        assert "search" in message and "retire" in message
        assert "validation error" not in message
        assert "tagged-union" not in message

    def test_a_missing_argument_says_which(self) -> None:
        with pytest.raises(UnknownOperation) as caught:
            parse_operation({"op": "get"})

        assert "'get' needs handle" in str(caught.value)

    def test_a_payload_that_is_not_an_operation_at_all_still_helps(self) -> None:
        with pytest.raises(UnknownOperation) as caught:
            parse_operation({"query": "no op key here"})

        assert "Available:" in str(caught.value)
