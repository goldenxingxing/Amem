"""Finding what a newer instruction has replaced — and refusing to act on it.

Behavioural memory is injected unasked and the budget holds about a hundred and
twenty entries, so a store that only grows eventually drops the oldest without
saying so. Consolidation is the intended way out. What it must not become is a
threshold that retires instructions on its own: being wrong costs a rule the
user is relying on, silently, while being cautious costs a line of context.
"""

from __future__ import annotations

import pytest

from amem.consolidate import (
    MAX_PROPOSALS,
    SUPERSEDED_RATIO,
    find_dormant,
    find_superseded,
    mark_relevant,
    pressure,
)
from amem.entry import MemoryEntry


def _entry(kind: str, content: str, *, retired: bool = False) -> MemoryEntry:
    entry = MemoryEntry(kind=kind, scope="persistent", content=content)  # type: ignore[arg-type]
    if retired:
        entry.retired_at = 1_700_000_000.0
    return entry


class TestFindingSupersession:
    def test_a_restatement_of_the_same_rule_is_paired(self) -> None:
        entries = [
            _entry("feedback", "Never force-push to the main branch."),
            _entry("feedback", "Never force-push to the main branch, use --force-with-lease."),
        ]

        found = find_superseded(entries)

        assert len(found) == 1
        assert found[0].older is entries[0]
        assert found[0].newer is entries[1]

    def test_two_rules_about_different_things_are_not_paired(self) -> None:
        entries = [
            _entry("feedback", "Never force-push to the main branch."),
            _entry("feedback", "Write commit messages in the imperative mood."),
        ]

        assert find_superseded(entries) == []

    def test_the_newer_entry_is_the_survivor(self) -> None:
        """Order in the file is chronological, so position decides which is which."""
        entries = [
            _entry("feedback", "Deploy from the release branch only."),
            _entry("feedback", "Deploy from the release branch only, after CI is green."),
        ]

        assert find_superseded(entries)[0].newer.content.endswith("after CI is green.")

    def test_project_facts_are_left_alone(self) -> None:
        """A stale project fact costs a wrong lookup; a stale rule gets followed."""
        entries = [
            _entry("project", "The API base path is /v1."),
            _entry("project", "The API base path is /v1 for all public routes."),
        ]

        assert find_superseded(entries) == []

    def test_a_retired_entry_is_not_proposed_again(self) -> None:
        entries = [
            _entry("feedback", "Never force-push to the main branch.", retired=True),
            _entry("feedback", "Never force-push to the main branch, use --force-with-lease."),
        ]

        assert find_superseded(entries) == []

    def test_a_contradicting_pair_is_never_paired(self) -> None:
        """The guard that matters most: identical wording, opposite meaning.

        Character similarity cannot see the difference, and merging these would
        silently invert an instruction.
        """
        entries = [
            _entry("feedback", "Always run the migration before deploying."),
            _entry("feedback", "Never run the migration before deploying."),
        ]

        assert find_superseded(entries) == []

    def test_a_precise_rule_is_not_displaced_by_a_vague_one(self) -> None:
        """A merge discards the older text, so the dangerous direction is losing detail."""
        entries = [
            _entry(
                "feedback",
                "Never force-push to main; on shared branches use --force-with-lease "
                "and tell the channel first.",
            ),
            _entry("feedback", "Never force-push."),
        ]

        assert find_superseded(entries) == []

    def test_the_list_is_short_enough_to_read(self) -> None:
        """A long list gets approved wholesale, which is what this design prevents."""
        entries = [
            _entry("feedback", f"Rule {i}: keep the changelog entry under one line.")
            for i in range(40)
        ]

        assert len(find_superseded(entries)) <= MAX_PROPOSALS

    def test_the_floor_sits_below_the_merge_threshold(self) -> None:
        """Entries similar enough to merge outright never reach this code."""
        from amem.dedup import AUTO_MERGE_RATIO

        assert SUPERSEDED_RATIO < AUTO_MERGE_RATIO


class TestPressure:
    def test_it_reports_what_did_not_fit(self) -> None:
        entries = [_entry("feedback", "x" * 200) for _ in range(50)]

        fit, held = pressure(entries, budget_chars=1_000)

        assert held == 50
        assert 0 < fit < 50

    def test_a_store_within_budget_reports_no_pressure(self) -> None:
        entries = [_entry("feedback", "Keep commits small.")]

        assert pressure(entries, budget_chars=8_000) == (1, 1)

    def test_retired_entries_do_not_count_against_the_budget(self) -> None:
        """Retiring is how the ceiling is relieved, so it has to show up here."""
        entries = [_entry("feedback", "x" * 200, retired=True) for _ in range(50)]
        entries.append(_entry("feedback", "Keep commits small."))

        assert pressure(entries, budget_chars=8_000) == (1, 1)


class TestTheThresholdSeparatesRealCases:
    """The number was measured, so the measurements are kept.

    Token-level similarity scores markedly lower than the character-level
    scores the merge thresholds were tuned against, so a threshold carried over
    from there silently rejects every real pair — which is how this was first
    written.
    """

    def _score(self, a: str, b: str) -> float:
        from amem.consolidate import _similarity
        from amem.dedup import normalize_content

        return _similarity(normalize_content(a), normalize_content(b))

    def test_restatements_land_above_it(self) -> None:
        pairs = [
            (
                "Deploy from the release branch only.",
                "Deploy from the release branch only, after CI is green.",
            ),
            ("日报要简洁。", "日报要简洁，聚焦产出而不是过程。"),
            ("文档里不要出现代码函数名。", "文档里不要出现代码函数名，只保留功能化描述。"),
        ]

        for older, newer in pairs:
            assert self._score(older, newer) >= SUPERSEDED_RATIO, older

    def test_unrelated_rules_land_below_it(self) -> None:
        pairs = [
            (
                "Never force-push to the main branch.",
                "Write commit messages in the imperative mood.",
            ),
            ("文档里不要出现代码函数名。", "日报需要包含工作内容理解部分。"),
            ("Keep commits small.", "Keep the changelog under 80 characters."),
        ]

        for older, newer in pairs:
            assert self._score(older, newer) < SUPERSEDED_RATIO, older

    def test_chinese_is_compared_meaningfully(self) -> None:
        """Splitting on whitespace makes a Chinese rule one token and every score 0 or 1."""
        from amem.consolidate import _tokens

        assert len(_tokens("日报要简洁")) == 5

    def test_the_comparison_stays_cheap_on_a_large_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """This runs over every pair on the way into a session.

        Character-level comparison of sixty four-hundred-character entries took
        twenty seconds of a session's opening context.

        Asserted on how the pairs are compared rather than on a stopwatch. The
        wall-clock version of this had three times' headroom against a limit a
        sibling test overran by two and a half on a Windows CI runner, so it was
        going to fail for the machine rather than for the code. Doubling the
        length of every entry must not change how many comparisons happen.
        """
        from amem import consolidate

        def comparisons_at(length: int) -> int:
            calls = 0
            real = consolidate._similarity

            def counting(a: str, b: str) -> float:
                nonlocal calls
                calls += 1
                return real(a, b)

            entries = [_entry("feedback", f"rule number {i} " + "x" * length) for i in range(60)]
            monkeypatch.setattr(consolidate, "_similarity", counting)
            find_superseded(entries)
            monkeypatch.setattr(consolidate, "_similarity", real)
            return calls

        assert comparisons_at(400) > 0, "nothing was compared at all"
        assert comparisons_at(800) == comparisons_at(400), (
            "the number of comparisons follows entry length, which is what "
            "character-level similarity does"
        )


class TestDormancy:
    """Ranking what to ask about, on evidence that a rule cannot destroy itself by working.

    The obvious signal — was this rule used — is unavailable and worse than
    unavailable. A rule is obeyed by *not* doing something, so a prohibition
    honoured for a year looks exactly like one nobody remembers. Scoring on
    compliance would retire the entries least safe to lose, first.

    What is observable is whether the subject came up at all.
    """

    def _aged(self, kind: str, content: str, *, days_quiet: float) -> MemoryEntry:
        import time

        entry = _entry(kind, content)
        entry.created_at = entry.last_relevant_at = time.time() - days_quiet * 86_400
        return entry

    def test_a_rule_whose_subject_came_up_is_stamped(self) -> None:
        import time

        entries = [_entry("feedback", "Never force-push to the main branch.")]

        touched = mark_relevant(
            entries, "I rebased and had to force-push the branch again", now=time.time()
        )

        assert touched == entries
        assert entries[0].last_relevant_at is not None

    def test_an_unrelated_conversation_does_not_stamp(self) -> None:
        import time

        entries = [_entry("feedback", "Never force-push to the main branch.")]

        assert (
            mark_relevant(entries, "let's talk about the invoice template", now=time.time()) == []
        )

    def test_one_word_in_common_is_not_a_topic(self) -> None:
        """Otherwise every rule is stamped by every conversation and none is ever quiet."""
        import time

        entries = [_entry("feedback", "Never force-push to the main branch.")]

        assert mark_relevant(entries, "the main course was good", now=time.time()) == []

    def test_a_prohibition_that_was_obeyed_is_still_quiet_only_when_its_subject_is(
        self,
    ) -> None:
        """The failure mode this whole design avoids, asserted directly.

        Obeying "never force-push" produces no force-push in the transcript.
        What keeps the rule alive is that branches were discussed at all.
        """
        import time

        rule = self._aged("feedback", "Never force-push to the main branch.", days_quiet=200)

        mark_relevant([rule], "merged the branch into main after review", now=time.time())

        assert find_dormant([rule], now=time.time()) == []

    def test_a_rule_nobody_has_touched_is_proposed(self) -> None:
        import time

        old = self._aged("feedback", "Keep the invoice template in landscape.", days_quiet=200)
        fresh = self._aged("feedback", "Never force-push to main.", days_quiet=1)

        dormant = find_dormant([old, fresh], now=time.time())

        assert [e.content for e in dormant] == [old.content]

    def test_project_facts_are_left_alone(self) -> None:
        import time

        stale = self._aged("project", "The API base path is /v1.", days_quiet=400)

        assert find_dormant([stale], now=time.time()) == []

    def test_a_retired_entry_is_not_proposed_again(self) -> None:
        import time

        gone = self._aged("feedback", "Keep the invoice template in landscape.", days_quiet=400)
        gone.retired_at = 1_700_000_000.0

        assert find_dormant([gone], now=time.time()) == []

    def test_a_store_written_before_any_stamping_ages_in(self) -> None:
        """Everything unstamped must not read as dormant on the first run."""
        import time

        entry = _entry("feedback", "Keep the invoice template in landscape.")

        assert find_dormant([entry], now=time.time()) == []


class TestTheShapesRealEntriesActuallyHave:
    """Calibrated on one-sentence rules, this found nothing in a real store.

    Live data: eleven behavioural entries, of which three were versions of one
    daily-report procedure at 850–1,040 characters each. Sequence similarity
    put the clearest pair at 0.198 against a 0.50 floor, and the numeric guard
    vetoed it anyway because one version numbers its steps. The detector
    reported zero while a quarter of the budget sat in duplicates.
    """

    def _procedure(self, variant: str) -> str:
        return (
            f"{variant} daily report SOP. Canonical file: "
            "/Users/x/output/reports/daily/SOP.md. Before writing, scan the "
            "session directory for the day's sessions, read the first user "
            "message and the closing summary of each, and summarise the work. "
            "Also scan the code projects for commits and deliverables produced "
            "that day, and cross-check both against the deliverables index so "
            "nothing is missed. Report the absolute path when done."
        )

    def test_two_versions_of_one_procedure_are_paired(self) -> None:
        older = _entry("feedback", self._procedure("Daily report location and writing"))
        newer = _entry(
            "feedback",
            self._procedure("Updated")
            + " Steps (1) read the SOP (2) scan sessions (3) scan code projects.",
        )

        found = find_superseded([older, newer])

        assert len(found) == 1, "long procedures share vocabulary, not wording"
        assert found[0].older is older

    def test_differing_numbers_are_reported_rather_than_vetoed(self) -> None:
        """`dedup.may_merge` vetoes on this, and must: it merges destructively.

        A proposal is read by the user, so the asymmetry runs the other way —
        a wrong veto hides a real duplicate forever, a wrong proposal costs one
        line to decline.
        """
        older = _entry("feedback", self._procedure("Daily report"))
        newer = _entry("feedback", self._procedure("Updated") + " See §4.0 and §5.1.")

        found = find_superseded([older, newer])

        assert found, "a step number must not be able to hide a duplicate"
        assert found[0].numbers_differ
        assert "numbers differ" in found[0].render()

    def test_an_inversion_is_still_refused(self) -> None:
        """Relaxing the numeric veto must not relax the one about meaning."""
        older = _entry("feedback", "Always run the migration before deploying to staging.")
        newer = _entry("feedback", "Never run the migration before deploying to staging.")

        assert find_superseded([older, newer]) == []

    def test_a_shorter_rewrite_is_still_refused(self) -> None:
        older = _entry("feedback", self._procedure("Daily report"))
        newer = _entry("feedback", "Write daily reports.")

        assert find_superseded([older, newer]) == []


class TestAnnouncedReplacement:
    """A newer entry that says it replaces something is stating the relationship.

    Similarity can only guess at it, and guessed badly: on an incremental
    corpus where six facts were revised, similarity paired none of them — the
    revisions are terse and share little wording with the originals they
    replace. The wording that announces the replacement is the evidence, and it
    was being thrown away.
    """

    def test_a_revision_is_paired_on_what_it_says_not_what_it_resembles(self) -> None:
        older = _entry("feedback", "截至 2026-03-04，上报失败采用固定间隔重试。")
        newer = _entry(
            "feedback",
            "截至 2026-04-02，上报失败已改为指数退避，不再使用固定间隔重试。",
        )

        found = find_superseded([older, newer])

        assert len(found) == 1
        assert found[0].older is older

    def test_the_announcement_does_not_trip_the_negation_guard(self) -> None:
        """The two collide by construction, and the guard was winning.

        A replacement is usually announced by negating what it replaces —
        "改用 EWMA，不再维护 48 小时窗口" — which the negation guard reads as an
        inversion. Two of three real revisions were lost to exactly this.
        """
        older = _entry("feedback", "采样率估计使用 48 小时滚动窗口，用 deque 存 576 个采样点。")
        newer = _entry(
            "feedback",
            "2026-05-06 起，采样率改用 EWMA，alpha=1/288，不再维护 48 小时窗口。",
        )

        assert find_superseded([older, newer]), "「不再」在这里是公告，不是反转"

    def test_a_genuine_inversion_is_still_refused(self) -> None:
        """The guard has to keep working where it was actually needed.

        This pair announces nothing — no "改为", no "replaced by" — so the
        negation stays visible and still refuses it.
        """
        older = _entry("feedback", "Always run the migration before deploying.")
        newer = _entry("feedback", "Never run the migration before deploying.")

        assert find_superseded([older, newer]) == []

    def test_announcing_a_change_to_something_else_is_not_enough(self) -> None:
        """Otherwise every revision retires whatever happens to be oldest."""
        older = _entry("feedback", "Keep the changelog entry under one line.")
        newer = _entry("feedback", "端口已从 5494 改为 8721，不再使用旧端口。")

        assert find_superseded([older, newer]) == []


class TestAnAnswerCanBeRecorded:
    """ "Both of these still hold" had nowhere to go.

    find_superseded recomputes from scratch, so a pair the user declined came
    back the next session and the one after. That is worse than the silence it
    replaced: a prompt that asks for attention and ignores the answer teaches
    people to withhold it, and the escalated wording asks every session.
    """

    def _pair(self) -> tuple[MemoryEntry, MemoryEntry]:
        older = _entry("feedback", "截至 2026-03-04，上报失败采用固定间隔重试。")
        newer = _entry(
            "feedback",
            "截至 2026-04-02，上报失败已改为指数退避，不再使用固定间隔重试。",
        )
        newer.created_at = older.created_at + 86_400
        return older, newer

    def test_a_pair_is_offered_before_anyone_answers(self) -> None:
        older, newer = self._pair()

        assert len(find_superseded([older, newer])) == 1

    def test_affirming_the_older_one_settles_it(self) -> None:
        older, newer = self._pair()
        older.affirmed_at = newer.created_at + 1

        assert find_superseded([older, newer]) == []

    def test_a_later_entry_reopens_the_question(self) -> None:
        """Affirming answered the store as it stood, not every store after it."""
        older, newer = self._pair()
        older.affirmed_at = newer.created_at + 1
        newest = _entry(
            "feedback",
            "截至 2026-06-01，上报失败改为一次性放弃，不再使用固定间隔重试。",
        )
        newest.created_at = older.affirmed_at + 86_400

        found = find_superseded([older, newer, newest])

        # Among the results rather than first: the newest also supersedes the
        # middle one, and that pair scores higher. What matters is that the
        # affirmed entry is back on the list at all.
        assert older in [s.older for s in found], (
            "an entry written after the answer is a question nobody asked"
        )

    def test_affirming_does_not_retire_or_hide_anything(self) -> None:
        """It records an answer. It is not a soft delete."""
        older, newer = self._pair()
        older.affirmed_at = newer.created_at + 1

        assert older.retired_at is None
        assert older.is_behavioural
