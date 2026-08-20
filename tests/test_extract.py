"""What extraction proposes, and how it fails when it fails.

These assertions came from an application that ran this prompt against real
sessions, and they stayed there when the code moved here — which meant the
prompt and the parser shipped in this package with no test of their own. The
findings they encode were expensive: one of them is the difference between
zero usable proposals per session and five.

The prompt is asserted on its *shape* rather than its wording. Wording is the
author's business; where the transcript sits, and whether the task is stated
after it, is what decides whether the model analyses the conversation or joins
it.
"""

from __future__ import annotations

import inspect

import pytest

from amem.extract import (
    EXTRACTION_PROMPT,
    MIN_CONVERSATION_CHARS,
    looks_like_refusal,
    parse_candidates,
    propose,
)


class TestParsing:
    def test_it_reads_an_array_out_of_a_chatty_reply(self) -> None:
        raw = 'Sure! [{"kind": "project", "content": "the repo is at /x", "key": "svc/repo"}] done'

        got = parse_candidates(raw, session_id="s1")

        assert [(c.kind, c.content, c.key) for c in got] == [
            ("project", "the repo is at /x", "svc/repo")
        ]

    def test_a_bad_row_is_dropped_without_taking_the_others(self) -> None:
        raw = """[
            {"kind": "bogus", "content": "wrong kind"},
            {"content": "no kind at all"},
            {"kind": "feedback", "content": "always check the date"},
            {"kind": "project", "content": "   "}
        ]"""

        assert [c.content for c in parse_candidates(raw, session_id="s")] == [
            "always check the date"
        ]

    def test_an_unusable_key_loses_the_key_not_the_fact(self) -> None:
        """A key that only fails on promotion turns an approval into an error."""
        raw = '[{"kind": "project", "content": "a fact", "key": "not a valid key!"}]'

        got = parse_candidates(raw, session_id="s")

        assert len(got) == 1
        assert got[0].key is None

    def test_nothing_qualifying_is_the_common_answer(self) -> None:
        assert parse_candidates("[]", session_id="s") == []
        assert parse_candidates("I could not find anything.", session_id="s") == []
        assert parse_candidates("", session_id="s") == []

    def test_a_flood_of_proposals_is_capped(self) -> None:
        raw = (
            "[" + ",".join(f'{{"kind": "project", "content": "fact {i}"}}' for i in range(50)) + "]"
        )

        assert len(parse_candidates(raw, session_id="s")) <= 5


class TestThePromptShape:
    """The transcript must sit *inside* the prompt, not after it.

    With the conversation appended last, the model treats its final turn as the
    live one and continues it instead of analysing it — against real sessions
    it replied to the transcript, or emitted the tool call the transcript was
    about to make, and returned no JSON at all. Measured over six sessions:
    zero usable proposals that way, four to five each once the transcript was
    closed and the task stated after it.
    """

    def test_the_conversation_is_embedded_and_the_task_stated_after_it(self) -> None:
        prompt = EXTRACTION_PROMPT.format(
            conversation="user: hello\nassistant: hi", today="2026-03-05"
        )

        assert "<transcript>\nuser: hello" in prompt
        assert prompt.index("</transcript>") < prompt.index("JSON array"), (
            "the instruction has to come after the transcript, or it is what gets continued"
        )
        assert not prompt.rstrip().endswith("hi")

    async def test_the_call_builds_the_prompt_rather_than_concatenating(self) -> None:
        """A stray `PROMPT + conversation` would pass every other test here.

        Asserted on what is sent rather than on the source: the prompt is a
        parameter now, and a test reading the function's text would pass while
        a host's own template was being concatenated.
        """
        assert "{conversation}" in EXTRACTION_PROMPT
        sent: list[str] = []

        async def complete(system: str, user: str) -> str:
            sent.append(user)
            return "[]"

        await propose(complete, "MARKER-BODY " * 40)

        assert sent
        assert sent[0].index("MARKER-BODY") < sent[0].index("JSON array"), (
            "the transcript has to sit inside the prompt, not after it"
        )
        assert not sent[0].rstrip().endswith("MARKER-BODY")


class TestTimeAnchoring:
    """A fact anchored to a moment has to say which moment.

    Measured on LoCoMo, where every question asks when something happened,
    extraction that produced only timeless traits scored 6.7% — but the more
    telling number came from real sessions: 28 facts extracted across six
    conversations, not one carrying a date. Entries do have a ``created_at``,
    and it answers a different question — when the fact was *recorded*, not
    when it was *true*.
    """

    def test_the_prompt_supplies_todays_date(self) -> None:
        """Without it, resolving "last Tuesday" means inventing a date."""
        assert "{today}" in EXTRACTION_PROMPT

        prompt = EXTRACTION_PROMPT.format(conversation="x", today="2026-03-05")

        assert "2026-03-05" in prompt

    def test_the_call_passes_a_real_date(self) -> None:
        source = inspect.getsource(propose)

        assert "today=" in source, "the placeholder is useless if nothing fills it"
        assert "strftime" in source

    def test_dating_does_not_reopen_the_door_to_the_work_log(self) -> None:
        """Asking for dates invites recording what happened, which is excluded.

        The prompt has to hold both at once, so both are asserted: the rule
        that a decision carries its date, and the rule that activity does not
        become a memory just because it can be dated.
        """
        assert "what was done" in EXTRACTION_PROMPT
        assert "not licence to record what happened" in EXTRACTION_PROMPT
        assert "a wrong date is worse than none" in EXTRACTION_PROMPT


class TestSilentFailureIsNotSilent:
    """ "Nothing worth keeping" and "the extractor is broken" are the same shape.

    Both end as zero candidates, and that is how a prompt that never once
    produced a usable proposal survived for the life of the feature: the
    failure looked exactly like the common, correct answer. The evidence that
    separates them is in the reply itself and costs nothing to keep.
    """

    def test_an_empty_array_is_a_refusal(self) -> None:
        assert looks_like_refusal("[]")
        assert looks_like_refusal("  [ ]  ")
        assert looks_like_refusal(""), "no reply proposed nothing either"

    def test_anything_else_that_parsed_to_nothing_is_a_fault(self) -> None:
        # What the model actually did when the transcript came last: it
        # continued the conversation instead of analysing it.
        assert not looks_like_refusal("Sure — I'll run the tests now.")
        assert not looks_like_refusal('<tool_calls><invoke name="bash">')
        assert not looks_like_refusal('[{"kind": "project", "content":')

    async def test_a_fault_is_reported_and_a_refusal_is_not(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        async def continued_the_conversation(system: str, user: str) -> str:
            return "Sure — I'll run the tests now."

        async def declined(system: str, user: str) -> str:
            return "[]"

        with caplog.at_level(logging.WARNING, logger="amem"):
            assert await propose(continued_the_conversation, "x" * 400) == []
        assert any("nothing usable" in r.getMessage() for r in caplog.records)

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="amem"):
            assert await propose(declined, "x" * 400) == []
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


class TestTheCallItself:
    """`propose` swallows every exception by design, so a broken call is silent.

    A failed extraction must not break whatever asked for it — a session
    ending, a compaction — which means a wrong signature, a dead provider and
    "nothing worth keeping" all arrive as an empty list. Each is asserted
    separately for that reason.
    """

    async def test_it_returns_what_the_model_proposed(self) -> None:
        async def complete(system: str, user: str) -> str:
            return '[{"kind": "project", "content": "the repo is at /x", "key": "svc/repo"}]'

        got = await propose(complete, "x" * 400, session_id="s1")

        assert [(c.content, c.session_id) for c in got] == [("the repo is at /x", "s1")]

    async def test_a_short_conversation_is_not_worth_a_call(self) -> None:
        called = False

        async def complete(system: str, user: str) -> str:
            nonlocal called
            called = True
            return "[]"

        assert await propose(complete, "hi") == []
        assert called is False, "no request for a conversation with nothing in it"

    async def test_the_threshold_is_the_one_that_is_documented(self) -> None:
        async def complete(system: str, user: str) -> str:
            return "[]"

        assert await propose(complete, "x" * (MIN_CONVERSATION_CHARS - 1)) == []

    async def test_a_provider_that_is_down_does_not_raise(self) -> None:
        async def broken(system: str, user: str) -> str:
            raise RuntimeError("provider is down")

        assert await propose(broken, "x" * 400) == []


class TestTheHostCanSupplyItsOwnPrompt:
    """What is worth remembering is not the same everywhere.

    An application with its own domain, its own languages, or its own rules
    about what may be recorded has to be able to say so — and copying this
    function to change one paragraph is how a fork starts.
    """

    async def test_a_supplied_prompt_is_the_one_sent(self) -> None:
        seen: list[str] = []

        async def complete(system: str, user: str) -> str:
            seen.append(user)
            return "[]"

        await propose(
            complete,
            "x" * 400,
            prompt="Only record facts about cats. {conversation} (today: {today})",
        )

        assert seen and seen[0].startswith("Only record facts about cats.")

    async def test_the_system_prompt_is_overridable_too(self) -> None:
        seen: list[str] = []

        async def complete(system: str, user: str) -> str:
            seen.append(system)
            return "[]"

        await propose(complete, "x" * 400, system="You are a cataloguer.")

        assert seen == ["You are a cataloguer."]

    async def test_the_default_is_still_the_measured_one(self) -> None:
        """Overridable, not unset: the published numbers came from this text."""
        seen: list[str] = []

        async def complete(system: str, user: str) -> str:
            seen.append(user)
            return "[]"

        await propose(complete, "hello world " * 40)

        assert "<transcript>" in seen[0]
        assert seen[0].index("</transcript>") < seen[0].index("JSON array")
