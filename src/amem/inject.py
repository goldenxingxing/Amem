"""Rendering what a new conversation is told before it starts.

The half of memory that is not retrieved. Behavioural entries arrive in full,
because nobody queries for a prohibition; recorded facts arrive as an index to
search from; recent sessions arrive condensed; and anything awaiting approval
arrives marked as not yet true. Each section has its own budget, so one growing
cannot evict another.

Returns a string. How it reaches a model — a system message, a preamble, a
tool result — belongs to whatever is running the agent.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from amem.candidates import MemoryCandidate
from amem.consolidate import (
    BEHAVIOURAL_BUDGET_CHARS,
    PRESSURE_ACT_AT,
    PRESSURE_WARN_AT,
    find_dormant,
    find_superseded,
    pressure,
)
from amem.entry import MemoryEntry
from amem.recent import SessionSummary

INJECTION_TYPE = "cross_session_memory"

# How many recent summaries to surface to the LLM at startup.
_RECENT_INJECTION_LIMIT = 5

# Per-section ceilings, not one shared pool.
#
# A single budget consumed in render order means whichever section grows keeps
# what it takes: two hundred project facts would push out the recaps entirely
# while nothing about them said they should. Sizing each section separately
# makes the trade explicit and keeps it stable as the store grows.
# Behavioural memory gets the most room: it is small, it is instructions, and
# dropping one changes how the agent works without saying so. If this ever
# truncates, that is worth seeing rather than absorbing silently.
_BEHAVIOURAL_BUDGET_CHARS = BEHAVIOURAL_BUDGET_CHARS
_INDEX_BUDGET_CHARS = 4_000
_RECENT_BUDGET_CHARS = 5_000


def _select_newest(
    entries: Sequence[MemoryEntry], budget: int, render: Callable[[MemoryEntry], str]
) -> list[MemoryEntry]:
    """The newest entries whose rendered form fits in *budget*, oldest-first.

    Selection and rendering are separate so the caller can say how many were
    left out — a number the reader needs and the rendered text cannot carry.
    """
    kept: list[MemoryEntry] = []
    used = 0
    for entry in reversed(entries):
        size = len(render(entry)) + 1
        if used + size > budget:
            break
        kept.append(entry)
        used += size
    kept.reverse()
    return kept


def _fit_entries(
    entries: Sequence[MemoryEntry], budget: int, render: Callable[[MemoryEntry], str]
) -> str:
    """Render what fits, preferring the newest, and say how many were left out.

    `persistent.jsonl` is append-only, so entries arrive oldest-first and a
    plain head-truncation keeps the oldest and discards the newest. For
    behavioural memory that is precisely backwards: the newest entry is the
    correction the user gave most recently, and it was the first to be dropped
    once the store outgrew the budget — silently, because a standing
    instruction that is never injected simply stops being followed.

    Selection is by recency; display stays oldest-first, which is how the
    entries read. The count is included because "some were omitted" and "1,879
    were omitted" call for different behaviour from the reader.
    """
    rendered = [(e, render(e)) for e in entries]
    total = sum(len(text) + 1 for _, text in rendered)
    if total <= budget:
        return "\n".join(text for _, text in rendered)

    kept: list[tuple[int, str]] = []
    used = 0
    note_room = 80
    for i in range(len(rendered) - 1, -1, -1):
        text = rendered[i][1]
        if used + len(text) + 1 > budget - note_room:
            break
        kept.append((i, text))
        used += len(text) + 1
    kept.reverse()

    dropped = len(rendered) - len(kept)
    note = f"… ({dropped} older entries not shown — use `search` to reach them)"
    return "\n".join([note, *(text for _, text in kept)])


def _render_dormant(entry: MemoryEntry) -> str:
    since = entry.last_relevant_at or entry.updated_at or entry.created_at
    stamp = time.strftime("%Y-%m", time.localtime(since))
    return f"- {entry.handle} (quiet since {stamp}): {entry.content[:80]}"


@dataclass(frozen=True)
class Actions:
    """How this host lets an agent act on what the preamble describes.

    Every one of these ends up inside a prompt, so it has to name something the
    reader can actually call. The wording used to name one particular
    application's tool — `Memory(operation={"op": ...})` — which was correct in
    that application and silently wrong in every other host, telling an agent to
    call something that does not exist.

    The defaults are the operations in :mod:`amem.operations`, which this
    package can perform: a host that passes them through :func:`amem.execute`
    needs no override at all. Overriding is for a host whose agent reaches them
    through a tool of its own — the wording changes, the operations do not.
    """

    search: str = '`{"op": "search", "query": "<query>"}`'
    get: str = '`{"op": "get", "handle": "<handle>"}`'
    promote: str = '`{"op": "promote", "id": "<id>"}`'
    dismiss: str = '`{"op": "dismiss", "id": "<id>"}`'
    retire: str = '`{"op": "retire", "handle": "<handle>"}`'
    affirm: str = '`{"op": "affirm", "handle": "<handle>"}`'


#: Used when a host does not describe its own. A module-level value rather than
#: a default argument so the frozen instance is shared and not rebuilt per call.
DEFAULT_ACTIONS = Actions()


def render(
    persistent: Sequence[MemoryEntry],
    recent: Sequence[SessionSummary],
    pending: Sequence[MemoryCandidate] = (),
    *,
    actions: Actions | None = None,
) -> str:
    actions = actions or DEFAULT_ACTIONS
    sections: list[str] = []

    # Retired entries stay in the file and stay searchable; what they stop
    # doing is arriving unasked in every conversation. That is the whole point
    # of retiring one, and it is also the only thing retiring does.
    live = [e for e in persistent if e.retired_at is None]
    behavioural = [e for e in live if e.is_behavioural]
    lookup = [e for e in live if not e.is_behavioural]
    retired = len(persistent) - len(live)

    fit, held = pressure(persistent, _BEHAVIOURAL_BUDGET_CHARS)

    if behavioural:
        lines = [
            "## Persistent memory",
            "Stable facts/preferences you've recorded across sessions:",
            "",
        ]
        body = _fit_entries(behavioural, _BEHAVIOURAL_BUDGET_CHARS, lambda e: e.render())
        if fit < held:
            # The ceiling is invisible from inside a session: what did not fit
            # is simply absent, and absent instructions read as instructions
            # that were never given. Saying so is not a fix — consolidation is
            # — but it turns a silent loss into a visible one.
            body += (
                f"\n({held - fit} more not shown here; the store is past what "
                f"this section holds — reachable via {actions.search})"
            )
        if retired:
            # Said once, beside the instructions it affects: an agent told a
            # rule in an earlier session and not told it here should be able to
            # see that the change was deliberate rather than a lapse.
            body += (
                f"\n({retired} retired and no longer in force; still readable via {actions.search})"
            )
        sections.append("\n".join([*lines, body]))

    if lookup:
        # Listed, not quoted. These are facts about particular projects; most
        # are irrelevant to any given conversation, and carrying all of them
        # into every one costs more than fetching the occasional right answer.
        #
        # The budget holds about fifty lines, so past a few hundred entries this
        # stopped being an index of the store and became an index of an
        # arbitrary slice of it — 0.5% of a ten-thousand-entry store — while
        # still being introduced as though it listed everything. A reader who
        # believes the list is complete concludes that what is not in it was
        # never recorded, which is worse than being told to search.
        shown = _select_newest(lookup, _INDEX_BUDGET_CHARS, lambda e: e.render_index())
        omitted = len(lookup) - len(shown)
        heading = (
            f"## Recorded facts (index: {len(shown)} of {len(lookup)})"
            if omitted
            else "## Recorded facts (index)"
        )
        blurb = (
            "Summaries only. Read one in full with "
            f"{actions.get} "
            "when it looks relevant to the task at hand"
        )
        if omitted:
            # Terse on purpose: this is prompt overhead paid on every session
            # whose store has outgrown the list.
            blurb += (
                f". The {omitted} older ones not listed are reachable only via "
                f"{actions.search} — the store knows more than this shows"
            )
        lines = [heading, blurb + ":", ""]
        body = "\n".join(e.render_index() for e in shown)
        sections.append("\n".join([*lines, body]))

    if recent:
        lines = [
            "## Recent session summaries",
            "Condensed records of recent past conversations (oldest first):",
            "",
        ]
        # Recaps arrive oldest-first, so this is the one section where cutting
        # from the end would throw away the newest — the opposite of intent.
        body = _fit("\n\n".join(s.render() for s in recent), _RECENT_BUDGET_CHARS, keep="tail")
        sections.append("\n".join([*lines, body]))

    if pending:
        # Noticed automatically, and deliberately not stored. Listing them here
        # is the whole mechanism: the agent proposes, the user decides, and
        # nothing enters memory on the strength of an extraction alone.
        lines = [
            "## Suggested memories (not saved)",
            (
                "Noticed in earlier conversations and awaiting your decision. Raise one "
                "with the user when it is relevant, then "
                f"{actions.promote} to keep it or "
                f"{actions.dismiss} to drop it. Do not treat these as "
                "established fact — they have not been approved:"
            ),
            "",
        ]
        lines.extend(c.render_index() for c in pending)
        sections.append("\n".join(lines))

    # Only raised once the store is actually past what fits. Below that the
    # ceiling costs nothing and asking the user to prune is busywork; above it,
    # entries are being dropped from every session with no other sign.
    # Raised while there is still room to act. Waiting for the store to
    # overflow means the first signal arrives after entries have already
    # stopped being injected — measured on a real store at 83% of budget, where
    # a quarter of the space was duplicates and nothing had been said.
    used = sum(len(e.render()) + 1 for e in behavioural)
    crowded = used >= _BEHAVIOURAL_BUDGET_CHARS * PRESSURE_WARN_AT
    pressing = used >= _BEHAVIOURAL_BUDGET_CHARS * PRESSURE_ACT_AT
    superseded = find_superseded(persistent) if crowded else []
    dormant = find_dormant(persistent, now=time.time()) if crowded else []
    if superseded or dormant:
        sections.append(
            "\n".join(
                [
                    "## Possibly superseded (not acted on)",
                    (
                        "Older instructions a later one appears to have replaced. "
                        "Nothing has changed. "
                        + (
                            # "When it fits" never fits. Observed on a real store
                            # that sat at 83% of budget for weeks with this list
                            # in every single session and the subject never once
                            # raised — which is the failure this whole design is
                            # about, arriving in the mechanism meant to prevent
                            # it: anything the agent has to remember to bring up
                            # is a thing that does not get brought up.
                            "The store is close enough to full that this is worth "
                            "a minute of the user's time: raise it before this "
                            "conversation ends, once, and take their answer either "
                            "way. "
                            if pressing
                            else "Raise these with the user when it fits. "
                        )
                        + "Take their answer either way and record it: "
                        f"{actions.retire} if the older "
                        "one is genuinely finished, "
                        f"{actions.affirm} if it still "
                        "holds. Affirming is what stops the pair being raised "
                        "again — an unrecorded no comes back next session and "
                        "the one after, and a prompt that ignores the answer "
                        "teaches the user to stop giving one. Retiring keeps "
                        "the entry and its history; it only stops being carried "
                        "into new conversations.\n\n"
                        "Read both entries before proposing anything. A later "
                        "instruction that restates an earlier one usually adds to "
                        "it rather than replacing it, and the requirements it "
                        "leaves out are still requirements — retiring the older "
                        "one then drops them with nothing to show it happened. "
                        "Where that is the case, the fix is one merged entry that "
                        "keeps every requirement, not a retirement. Never retire "
                        "in bulk:"
                    ),
                    "",
                    *(s.render() for s in superseded),
                    *(
                        [
                            "",
                            "Not superseded, only quiet — their subject has not come "
                            "up in months. That is not evidence they are wrong; a "
                            "rule is obeyed by *not* doing something and leaves no "
                            "trace either way, so this ranks what to ask about and "
                            "nothing else:",
                            "",
                        ]
                        if dormant
                        else []
                    ),
                    *(_render_dormant(e) for e in dormant),
                ]
            )
        )

    if not sections:
        return ""

    # The old header only said what to do when the snapshot and the
    # conversation disagree. That left the ordinary case unstated, and an
    # agent that is not told the snapshot is authoritative will go and
    # rediscover what is already in front of it — paying twice and sometimes
    # arriving somewhere else.
    header = (
        "Cross-session memory — what you already know at the start of this "
        "conversation. Treat it as established fact: do not re-derive, re-read "
        "or re-confirm something recorded here unless the live conversation "
        "contradicts it, in which case the conversation wins. If an index entry "
        "below looks relevant to the task, read it rather than guessing at it "
        "from the summary line."
    )
    return header + "\n\n" + "\n\n".join(sections)


def _fit(text: str, budget: int, *, keep: str = "head") -> str:
    """Hold one section to ``budget``, dropping whole lines.

    ``keep="tail"`` drops from the front instead — for content ordered
    oldest-first, where the end is the part worth keeping.

    Either way it says that it cut. The failure that matters here is not the
    missing entry but the confident assumption that nothing is missing.
    """
    if len(text) <= budget:
        return text
    # Not `list`: that returns every entry in full, which is the cost this
    # whole section exists to avoid. Someone reaching a truncated list is
    # looking for one thing, and `search` is how you find one thing.
    note = "… (truncated — use `search` to reach what is not shown)"
    lines = text.splitlines()
    room = budget - len(note) - 1
    if keep == "tail":
        kept: list[str] = []
        used = 0
        for line in reversed(lines):
            if used + len(line) + 1 > room:
                break
            kept.append(line)
            used += len(line) + 1
        return "\n".join([note, *reversed(kept)])
    kept = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > room:
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join([*kept, note])
