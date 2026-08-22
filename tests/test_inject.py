"""What an agent is told before anyone speaks.

`render` is one of the three calls the README puts in front of a reader, and
until this file it was the least tested thing in the package — the paths that
run when the store outgrows its budget had no coverage at all. Those are the
paths that matter most: a standing instruction that stops arriving is a
standing instruction that stops being followed, and the only defence is that
the preamble says it cut something. An untested "say that you cut" is a
silence waiting to happen.
"""

from __future__ import annotations

import time

from carryover.candidates import MemoryCandidate
from carryover.consolidate import (
    BEHAVIOURAL_BUDGET_CHARS,
    PRESSURE_ACT_AT,
    PRESSURE_WARN_AT,
)
from carryover.entry import MemoryEntry
from carryover.inject import DEFAULT_ACTIONS, Actions, render
from carryover.recent import SessionSummary


def _entry(kind: str, content: str, *, key: str | None = None, **kw) -> MemoryEntry:
    return MemoryEntry(kind=kind, scope="persistent", content=content, key=key, **kw)


class TestTheTwoKindsArriveDifferently:
    """The split is the whole architecture, so it is asserted on the output."""

    def test_behavioural_memory_is_stated_in_full(self) -> None:
        rule = "Never put function names in the external docs."

        out = render([_entry("feedback", rule)], [])

        assert rule in out, "a rule nobody will think to search for has to be present"

    def test_lookup_memory_is_a_line_not_the_whole_entry(self) -> None:
        body = (
            "The daily report lives in output/reports/daily/ and is written from the SOP, "
            "which lists three scans that must run before anything is written down."
        )

        out = render([_entry("project", body, key="reports/daily")], [])

        assert "reports/daily" in out, "the handle has to be there to be fetchable"
        assert body not in out, "carrying every lookup entry in full is the cost being avoided"
        assert "…" in out, "a cut entry has to show that it was cut"

    def test_an_empty_store_renders_nothing_to_pay_for(self) -> None:
        assert render([], []) == ""


class TestRetiring:
    def test_a_retired_entry_stops_arriving(self) -> None:
        out = render([_entry("feedback", "an old rule", retired_at=time.time())], [])

        assert "an old rule" not in out

    def test_and_the_preamble_says_one_was_retired(self) -> None:
        """An agent told a rule last week and not this week should see it was deliberate."""
        out = render(
            [
                _entry("feedback", "a live rule"),
                _entry("feedback", "an old rule", retired_at=time.time()),
            ],
            [],
        )

        assert "retired" in out
        assert "no longer in force" in out


class TestWhenTheStoreOutgrowsTheBudget:
    """The failure this package exists to make visible.

    Past the ceiling the oldest entries simply stop arriving, and absent
    instructions read as instructions that were never given. Consolidation is
    the fix; saying so is what turns a silent loss into a visible one.
    """

    def _overflowing(self, n: int = 60) -> list[MemoryEntry]:
        """Distinct rules, not one rule repeated.

        Padding them identically made every entry look like a restatement of
        the next, so the preamble filled with supersession advisories quoting
        the very entries this is checking are absent. A degenerate fixture
        tests the wrong thing twice.
        """
        return [
            _entry("feedback", f"Standing rule {i}: never {'ab cd ef gh ij kl mn op' * 12} {i}.")
            for i in range(n)
        ]

    def _behavioural_section(self, out: str) -> str:
        return out.split("## Persistent memory")[1].split("\n## ")[0]

    def test_it_says_how_many_did_not_fit(self) -> None:
        out = render(self._overflowing(), [])

        assert "not shown here" in out
        assert "past what this section holds" in out

    def test_it_points_at_the_way_to_reach_them(self) -> None:
        """Telling someone something is missing without saying how to get it is worse."""
        out = render(self._overflowing(), [])

        assert "search" in out

    def test_the_section_stays_within_a_sane_size(self) -> None:
        """Sixty paragraph-length rules is 18,000 characters of behavioural memory."""
        out = render(self._overflowing(), [])

        assert len(out) < 12_000, "the budget is not being applied at all"

    def test_the_newest_rules_are_the_ones_kept(self) -> None:
        """Dropping the newest would silently revert the most recent correction."""
        section = self._behavioural_section(render(self._overflowing(), []))

        assert "Standing rule 59:" in section
        assert "Standing rule 0:" not in section


class TestTheIndexDoesNotOverstateItself:
    """A reader who believes the list is complete concludes the rest was never recorded."""

    def test_a_complete_index_is_introduced_as_one(self) -> None:
        out = render([_entry("project", "a fact", key=f"ns/f{i}") for i in range(3)], [])

        assert "(index)" in out
        assert " of " not in out.split("## Recorded facts")[1].splitlines()[0]

    def test_a_truncated_index_says_so_in_its_heading(self) -> None:
        entries = [_entry("project", "a fact " + "y" * 200, key=f"ns/f{i}") for i in range(400)]

        out = render(entries, [])

        heading = out.split("## Recorded facts")[1].splitlines()[0]
        assert " of 400" in heading, "the heading has to admit it is a slice"
        assert "not listed" in out


class TestPending:
    def test_a_proposal_is_shown_as_awaiting_a_decision(self) -> None:
        out = render(
            [],
            [],
            [MemoryCandidate(kind="feedback", content="Do not force-push to main.")],
        )

        assert "Do not force-push to main." in out

    def test_a_proposal_is_not_presented_as_something_already_kept(self) -> None:
        """The approval rule is only real if the preamble does not blur it."""
        out = render(
            [_entry("feedback", "A rule that was approved.")],
            [],
            [MemoryCandidate(kind="feedback", content="A fact merely noticed.")],
        )

        approved = out.index("A rule that was approved.")
        noticed = out.index("A fact merely noticed.")
        assert approved < noticed, "kept memory and proposals are different sections"


class TestRecentSessions:
    def test_a_summary_reaches_the_preamble(self) -> None:
        out = render(
            [],
            [
                SessionSummary(
                    session_id="s1",
                    trigger="session_end",
                    summary="Fixed the packaging duplicate.",
                )
            ],
        )

        assert "Fixed the packaging duplicate." in out


class TestTheAdvisoryEscalates:
    """A suggestion nobody is ever obliged to raise is a suggestion nobody raises.

    Measured on a real store: 83% of budget for weeks, a concrete list of
    superseded pairs in every session's opening context with the handles and
    the command spelled out, and the subject never once raised. "When it fits"
    never fits — which is this project's own thesis reappearing inside the
    mechanism meant to act on it.
    """

    def _store(self, fraction: float) -> list[MemoryEntry]:
        """Behavioural entries filling *fraction* of the budget, two of them a pair."""
        target = int(BEHAVIOURAL_BUDGET_CHARS * fraction)
        pair = [
            _entry("feedback", "截至 2026-03-04，上报失败采用固定间隔重试。"),
            _entry("feedback", "截至 2026-04-02，上报失败已改为指数退避，不再使用固定间隔重试。"),
        ]
        used = sum(len(e.render()) + 1 for e in pair)
        filler = []
        i = 0
        while used < target:
            e = _entry("feedback", f"Standing rule {i}: never {'ab cd ef gh ij kl' * 10} {i}.")
            filler.append(e)
            used += len(e.render()) + 1
            i += 1
        return pair + filler

    def test_below_the_warn_line_nothing_is_raised_at_all(self) -> None:
        """Under the ceiling the pair costs nothing and pruning is busywork."""
        out = render(self._store(0.4), [])

        assert "Possibly superseded" not in out

    def test_between_the_lines_it_is_raised_when_it_fits(self) -> None:
        out = render(self._store(PRESSURE_WARN_AT + 0.01), [])

        assert "Possibly superseded" in out
        assert "when it fits" in out
        assert "before this conversation ends" not in out

    def test_past_the_act_line_it_has_to_be_raised_this_conversation(self) -> None:
        out = render(self._store(PRESSURE_ACT_AT + 0.01), [])

        assert "Possibly superseded" in out
        assert "before this conversation ends" in out
        assert "when it fits" not in out, "the soft wording is what was measured doing nothing"

    def test_the_two_lines_leave_room_to_mention_it_first(self) -> None:
        """Escalating at the same moment the list appears is one warning, not two."""
        assert PRESSURE_WARN_AT < PRESSURE_ACT_AT < 1.0


class TestTheAdvisoryWarnsAgainstTheWrongFix:
    """Retiring the older entry is not always the right move, and often is not.

    On a real store the newest of three generations of one rule had dropped
    three requirements the older two carried — read the README first, take the
    date from `date` rather than the context, verify after writing. Retiring on
    the advisory's word would have removed all three silently, which is exactly
    what the entry being retired was written to prevent.
    """

    def _crowded_pair(self) -> list[MemoryEntry]:
        pair = [
            _entry("feedback", "截至 2026-03-04，上报失败采用固定间隔重试。"),
            _entry("feedback", "截至 2026-04-02，上报失败已改为指数退避，不再使用固定间隔重试。"),
        ]
        used = sum(len(e.render()) + 1 for e in pair)
        i = 0
        while used < BEHAVIOURAL_BUDGET_CHARS * (PRESSURE_ACT_AT + 0.01):
            e = _entry("feedback", f"Standing rule {i}: never {'ab cd ef gh ij kl' * 10} {i}.")
            pair.append(e)
            used += len(e.render()) + 1
            i += 1
        return pair

    def test_it_says_to_read_both_entries_first(self) -> None:
        out = render(self._crowded_pair(), [])

        assert "Read both entries" in out

    def test_it_names_merging_as_the_alternative(self) -> None:
        out = render(self._crowded_pair(), [])

        assert "merged entry" in out
        assert "keeps every requirement" in out

    def test_it_still_refuses_bulk_retirement(self) -> None:
        out = render(self._crowded_pair(), [])

        assert "Never retire in bulk" in out


class TestTheHostNamesItsOwnActions:
    """The preamble tells an agent what to call, so it has to name something real.

    The wording named one particular application's tool — `Memory(operation=...)`
    — which was correct there and silently wrong everywhere else: another host's
    agent was being told to call something that does not exist, in a section
    otherwise written to be trusted.
    """

    def _crowded_with_everything(self) -> list[MemoryEntry]:
        pair = [
            _entry("feedback", "截至 2026-03-04，上报失败采用固定间隔重试。"),
            _entry("feedback", "截至 2026-04-02，上报失败已改为指数退避，不再使用固定间隔重试。"),
            _entry("project", "The daily report lives in output/reports/daily/.", key="r/d"),
            _entry("feedback", "an old rule", retired_at=time.time()),
        ]
        used = sum(len(e.render()) + 1 for e in pair)
        i = 0
        while used < BEHAVIOURAL_BUDGET_CHARS * (PRESSURE_ACT_AT + 0.01):
            e = _entry("feedback", f"Standing rule {i}: never {'ab cd ef gh ij kl' * 10} {i}.")
            pair.append(e)
            used += len(e.render()) + 1
            i += 1
        return pair

    def test_no_particular_application_is_named_by_default(self) -> None:
        out = render(
            self._crowded_with_everything(),
            [],
            [MemoryCandidate(kind="project", content="a guessed fact")],
        )

        assert "Memory(operation=" not in out, "that is one host's tool, not this library's"

    def test_every_action_the_host_supplies_is_used(self) -> None:
        """A host that overrides one and not another would otherwise get a mix."""
        spoken = Actions(
            search="SEARCH-VERB",
            get="GET-VERB",
            promote="PROMOTE-VERB",
            dismiss="DISMISS-VERB",
            retire="RETIRE-VERB",
            affirm="AFFIRM-VERB",
        )

        out = render(
            self._crowded_with_everything(),
            [],
            [MemoryCandidate(kind="project", content="a guessed fact")],
            actions=spoken,
        )

        for verb in (
            "SEARCH-VERB",
            "GET-VERB",
            "PROMOTE-VERB",
            "DISMISS-VERB",
            "RETIRE-VERB",
            "AFFIRM-VERB",
        ):
            assert verb in out, f"{verb} was not used anywhere"

    def test_every_default_is_an_operation_this_package_performs(self) -> None:
        """The point of the defaults: a host that passes them through `execute`
        needs no override, so a default naming something unexecutable would put
        the package back where it started — describing what it cannot do."""
        import re
        from dataclasses import fields

        from carryover.operations import OPERATION_NAMES

        spelled = " ".join(getattr(DEFAULT_ACTIONS, f.name) for f in fields(DEFAULT_ACTIONS))
        named = set(re.findall(r'"op":\s*"(\w+)"', spelled))

        assert named, "the defaults name no operation at all"
        assert named <= set(OPERATION_NAMES), sorted(named - set(OPERATION_NAMES))

    def test_a_default_action_round_trips_through_the_parser(self) -> None:
        """Named is not enough — the shape has to validate."""
        from carryover.operations import GetOp, parse_operation

        assert isinstance(parse_operation({"op": "get", "handle": "p/one"}), GetOp)
