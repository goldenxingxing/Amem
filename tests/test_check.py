"""The self-check, which exists because every failure here is quiet.

A host that wires this up has no way to tell working from absent by watching:
extraction that finds nothing looks like a conversation with nothing worth
keeping, a search with no match looks like a store with no match, and a
preamble that was never rendered looks like an agent that did not need one.
None of them raise, deliberately.

So these tests are mostly about what the check is allowed to *claim*. Its worst
possible failure is reporting a guess as a finding.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import amem
from amem.__main__ import main
from amem.check import FAIL, OK, UNUSED, WARN, check_capability, check_evidence


def _store(**_: object) -> Path:
    return Path(tempfile.mkdtemp())


def _by_name(findings: list[amem.Finding]) -> dict[str, amem.Finding]:
    return {f.name: f for f in findings}


class TestCapability:
    def test_a_healthy_install_reports_no_failure(self) -> None:
        findings = check_capability()

        assert [f.name for f in findings if f.status == FAIL] == []

    def test_it_actually_round_trips_rather_than_asserting_imports(self) -> None:
        """A check that only imports things passes on a machine where nothing works."""
        retrieval = _by_name(check_capability())["retrieval"]

        assert retrieval.status == OK
        assert "found again" in retrieval.detail

    def test_it_checks_both_scripts(self) -> None:
        """CJK retrieval takes a different path from Latin, and only one used to work."""
        assert "both scripts" in _by_name(check_capability())["retrieval"].detail

    def test_it_touches_nothing_of_yours(self, tmp_path: Path) -> None:
        store = amem.Store(tmp_path)
        store.add("project", "a fact of mine", key="mine/one")
        before = store.path.read_text(encoding="utf-8")

        check_capability()

        assert store.path.read_text(encoding="utf-8") == before


class TestEvidence:
    def test_a_store_that_was_never_written_says_so(self) -> None:
        findings = _by_name(check_evidence(_store()))

        assert findings["store"].status == UNUSED
        assert "nothing approved yet" in findings["store"].detail
        assert str(_store()) not in findings["store"].detail  # its own path, not another

    def test_it_keeps_checking_past_an_empty_store(self, tmp_path: Path) -> None:
        """A newly wired host is often exactly here — extraction running, nothing
        approved yet — and stopping would hide the one line that says so."""
        store = amem.Store(tmp_path)
        store.suggest([amem.MemoryCandidate(kind="project", content="a guessed fact")])

        findings = _by_name(check_evidence(tmp_path))

        assert findings["store"].status == UNUSED
        assert findings["extraction"].status == OK, "the evidence that matters most here"

    def test_an_approved_memory_is_evidence_of_approval(self, tmp_path: Path) -> None:
        amem.Store(tmp_path).add("project", "报告写在 output/reports/", key="r/d")

        findings = _by_name(check_evidence(tmp_path))

        assert findings["store"].status == OK
        assert "project 1" in findings["store"].detail

    def test_a_queued_proposal_is_evidence_extraction_ran(self, tmp_path: Path) -> None:
        store = amem.Store(tmp_path)
        store.suggest([amem.MemoryCandidate(kind="project", content="a guessed fact")])

        findings = _by_name(check_evidence(tmp_path))

        assert findings["extraction"].status == OK
        assert "1 proposal" in findings["extraction"].detail

    def test_an_emptied_queue_still_counts_as_having_run(self, tmp_path: Path) -> None:
        """Approved, dismissed or expired — the file having existed is the evidence."""
        store = amem.Store(tmp_path)
        store.suggest([amem.MemoryCandidate(kind="project", content="a guessed fact")])
        store.dismiss(store.pending()[0].id)

        findings = _by_name(check_evidence(tmp_path))

        assert findings["extraction"].status == OK
        assert "empty" in findings["extraction"].detail


class TestItDoesNotGuess:
    """The one thing this must not do.

    "Nothing was found" and "nothing was called" produce identical stores, and
    reporting the second when it might be the first would be the same mistake
    this package spends its whole design avoiding.
    """

    def test_it_says_both_readings_when_nothing_was_queued(self, tmp_path: Path) -> None:
        amem.Store(tmp_path).add("project", "written directly", key="d/1")

        extraction = _by_name(check_evidence(tmp_path))["extraction"]

        assert extraction.status == UNUSED
        assert "Either nothing calls" in extraction.remedy
        assert "runs and finds nothing" in extraction.remedy

    def test_it_says_how_to_tell_them_apart(self, tmp_path: Path) -> None:
        """A remedy that names no experiment leaves the reader where they were."""
        extraction = _by_name(check_evidence(tmp_path))["extraction"]

        assert "DEBUG" in extraction.remedy

    def test_the_same_holds_for_topical_stamps(self, tmp_path: Path) -> None:
        amem.Store(tmp_path).add("feedback", "一条永远不会被提起的规则。")

        stamps = _by_name(check_evidence(tmp_path))["topical stamps"]

        assert stamps.status == UNUSED
        assert "Either nothing calls" in stamps.remedy

    def test_absence_is_never_reported_as_failure(self, tmp_path: Path) -> None:
        """Only you know whether a store is new or a host is broken."""
        amem.Store(tmp_path).add("project", "a fact")

        assert [f.name for f in check_evidence(tmp_path) if f.status == FAIL] == []


class TestTheLoudCases:
    """Where the check does know enough to raise its voice."""

    def _crowded(self, tmp_path: Path, count: int) -> Path:
        store = amem.Store(tmp_path)
        for i in range(count):
            store.add("feedback", f"Standing rule {i}: never {'ab cd ef gh ij kl' * 12} {i}.")
        return tmp_path

    def test_a_store_past_the_warn_line_says_so(self, tmp_path: Path) -> None:
        budget = _by_name(check_evidence(self._crowded(tmp_path, 24)))["budget"]

        assert budget.status in {WARN, FAIL}

    def test_a_store_dropping_entries_is_a_failure(self, tmp_path: Path) -> None:
        """Entries stop arriving and nothing in a session would say so."""
        budget = _by_name(check_evidence(self._crowded(tmp_path, 60)))["budget"]

        assert budget.status == FAIL
        assert "not reaching conversations" in budget.remedy

    def test_an_unanswered_supersession_is_raised(self, tmp_path: Path) -> None:
        store = amem.Store(tmp_path)
        older = store.add("feedback", "截至 2026-03-04，上报失败采用固定间隔重试。").entry
        newer = amem.MemoryEntry(
            kind="feedback",
            content="截至 2026-04-02，上报失败已改为指数退避，不再使用固定间隔重试。",
        )
        newer.created_at = older.created_at + 1
        from amem.storage import upsert_entry

        upsert_entry(store.path, newer, dedup=False)

        consolidation = _by_name(check_evidence(tmp_path))["consolidation"]

        assert consolidation.status == WARN
        assert "merge" in consolidation.remedy


class TestTheCommandLine:
    def test_it_runs_without_a_directory(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([]) == 0

        assert "Can this machine run it" in capsys.readouterr().out

    def test_it_accepts_the_check_word_a_reader_would_type(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        amem.Store(tmp_path).add("project", "a fact")

        assert main(["check", str(tmp_path)]) == 0

        assert "What has used the store" in capsys.readouterr().out

    def test_it_exits_nonzero_only_on_a_real_failure(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """A store nobody has used yet is not an error, and a CI job that treats
        it as one would be wrong on the first run of every install."""
        assert main([str(tmp_path)]) == 0
