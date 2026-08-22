"""Whether this is working, and whether anything is using it.

Every way this package fails is quiet. Extraction that returns nothing looks
like a conversation with nothing worth keeping, which is the common and correct
answer. A search that returns nothing looks like a store with no match. A
preamble that was never rendered looks like an agent that simply did not need
to know. None of them raise, on purpose — a memory system must not break the
thing it is attached to — and the cost of that is you cannot tell working from
absent by watching.

So it is asked directly, in two halves.

**Capability** is about this machine: can the index be built, does retrieval
come back, is the store readable. It runs against a scratch directory and
touches nothing of yours.

**Evidence** is about your store: which integration points have left a mark. A
session summary means something calls the session-end hook. A candidate means
extraction ran. A topical stamp means the conversation was passed back. An
entry means somebody approved one. Nothing here can prove a call happens — only
that it has happened at least once, which is the question worth asking after
wiring it up.

    python -m carryover check ~/.myagent/memory

Returns findings and prints nothing. The command lives in :mod:`carryover.__main__`,
because a host embedding this in its own interface wants the answers, not this
package's opinion about stdout — and a library that can end its caller's
process is not one you can call from inside a request.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from carryover.candidates import CANDIDATES_FILENAME, CandidateFile
from carryover.consolidate import (
    BEHAVIOURAL_BUDGET_CHARS,
    PRESSURE_ACT_AT,
    PRESSURE_WARN_AT,
    find_superseded,
    pressure,
)
from carryover.entry import MemoryEntry
from carryover.recent import RECENT_FILENAME, read_recent_summaries
from carryover.store import Store

OK = "ok"
WARN = "warn"
FAIL = "fail"
UNUSED = "unused"


@dataclass(frozen=True)
class Finding:
    """One answer, and what to do about it if it is not the good one."""

    name: str
    status: str
    detail: str
    remedy: str = ""

    def render(self) -> str:
        mark = {OK: "ok  ", WARN: "warn", FAIL: "FAIL", UNUSED: "--  "}[self.status]
        line = f"  [{mark}] {self.name}: {self.detail}"
        if self.remedy and self.status != OK:
            line += f"\n         → {self.remedy}"
        return line


def check_capability() -> list[Finding]:
    """Whether the machine can run this at all. Touches nothing of yours."""
    out: list[Finding] = []

    import carryover

    python = sys.version.split()[0]
    out.append(Finding("installed", OK, f"carryover {carryover.__version__} on Python {python}"))

    # The index needs FTS5 with a trigram tokeniser, which arrived in SQLite
    # 3.34. Without it retrieval still works — it falls back to the scan — but
    # ranking is the scan's and large stores are slower, and that is worth
    # knowing rather than discovering as "results feel worse here".
    version = sqlite3.sqlite_version
    try:
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='trigram')")
        out.append(Finding("sqlite index", OK, f"FTS5 with trigram, sqlite {version}"))
    except sqlite3.Error as exc:
        out.append(
            Finding(
                "sqlite index",
                WARN,
                f"unavailable on sqlite {version} ({exc})",
                "Retrieval falls back to the scan and stays correct. For ranking and "
                "speed on a large store, use a Python built against sqlite 3.34+.",
            )
        )

    scratch = Store(Path(tempfile.mkdtemp(prefix="carryover-check-")))
    scratch.add("project", "日报写在 output/reports/daily/ 下。", key="probe/zh")
    scratch.add("project", "The daily report lives in output/reports/daily.", key="probe/en")
    found = {
        "Chinese": [h.handle for h in scratch.search("日报写在哪个目录")],
        "Latin": [h.handle for h in scratch.search("where do daily reports live")],
    }
    missing = [script for script, hits in found.items() if not hits]
    if missing:
        out.append(
            Finding(
                "retrieval",
                FAIL,
                f"a probe stored and then not found ({', '.join(missing)})",
                "This is a defect in this package, not in your wiring. Please report it "
                "with the output of this command.",
            )
        )
    else:
        out.append(Finding("retrieval", OK, "a probe stored and found again, both scripts"))

    preamble = carryover.render(scratch.entries(), [])
    if "probe/zh" in preamble:
        out.append(Finding("preamble", OK, f"renders, {len(preamble)} characters for 2 entries"))
    else:
        out.append(Finding("preamble", FAIL, "rendered without the entries it was given"))

    return out


def check_evidence(directory: Path) -> list[Finding]:
    """Which integration points have left a mark on *this* store.

    Absence is reported as `--`, not as a failure: a store nobody has written
    to yet looks exactly like one whose host forgot to call anything, and only
    you know which it is. What each line gives you is the call that would have
    left the mark.
    """
    out: list[Finding] = []
    store = Store(directory)

    if not store.path.exists():
        # Reported and then carried on past, not returned from. A host that has
        # just been wired up is often exactly here: extraction running, nothing
        # approved yet — and stopping would hide the one line that says so.
        out.append(
            Finding(
                "store",
                UNUSED,
                f"nothing approved yet ({store.path} does not exist)",
                "If that path is not where your host points Store(), the rest of this "
                "is about the wrong directory.",
            )
        )
        out.append(_summaries(directory))
        out.append(_candidates(directory, []))
        return out

    entries = store.entries()
    live = [e for e in entries if e.retired_at is None]
    kinds: dict[str, int] = {}
    for entry in live:
        kinds[entry.kind] = kinds.get(entry.kind, 0) + 1
    out.append(
        Finding(
            "store",
            OK if entries else UNUSED,
            f"{len(entries)} entries at {store.path}"
            + (f" ({', '.join(f'{k} {n}' for k, n in sorted(kinds.items()))})" if kinds else ""),
            "" if entries else "Nothing approved yet. `store.add()` or `store.keep()` writes here.",
        )
    )

    out.append(_summaries(directory))
    out.append(_candidates(directory, entries))
    out.append(_topics(live))
    out.append(_consolidation(entries))
    out.append(_budget(entries))
    return out


def _summaries(directory: Path) -> Finding:
    summaries = read_recent_summaries(directory / RECENT_FILENAME, limit=50)
    if not summaries:
        return Finding(
            "session summaries",
            UNUSED,
            "none recorded",
            "Nothing calls the end-of-session hook. Write one with "
            "`append_summary(dir / 'recent.jsonl', summary)` when a conversation ends.",
        )
    newest = max(s.created_at for s in summaries)
    return Finding(
        "session summaries",
        OK,
        f"{len(summaries)} recorded, newest {_ago(newest)}",
    )


def _candidates(directory: Path, entries: list[MemoryEntry]) -> Finding:
    queued = CandidateFile(directory / CANDIDATES_FILENAME).read()
    file_exists = (directory / CANDIDATES_FILENAME).exists()
    if queued:
        return Finding(
            "extraction",
            OK,
            f"{len(queued)} proposal(s) waiting for a decision",
            "Show these to the user — a queue nobody clears expires in a fortnight.",
        )
    if file_exists:
        # The file having existed is the evidence. An empty queue is the normal
        # resting state: proposals are approved, dismissed, or expire.
        return Finding("extraction", OK, "has run; the queue is currently empty")
    # No file has ever been written, which is where the honest answer runs out.
    # Extraction that ran and found nothing writes nothing, and finding nothing
    # is the common and correct answer — so this cannot tell "never called" from
    # "called and quiet". Saying which would be a guess, and the point of this
    # package is that a quiet failure and a quiet success are not the same thing
    # and must not be reported as one.
    hint = (
        "Either nothing calls `propose(complete, transcript)` + `store.suggest()`, or it "
        "runs and finds nothing — which is the common answer and not a fault. To tell "
        "them apart, turn on DEBUG for the `carryover` logger for one session: a refusal logs "
        "at DEBUG, a reply that could not be read logs at WARNING, and a call that never "
        "happened logs neither."
    )
    if entries:
        hint += " The entries here were written directly rather than proposed."
    return Finding("extraction", UNUSED, "no proposal has ever been queued", hint)


def _topics(live: list[MemoryEntry]) -> Finding:
    stamped = [e for e in live if e.last_relevant_at is not None]
    if not live:
        return Finding("topical stamps", UNUSED, "no entries to stamp")
    if not stamped:
        return Finding(
            "topical stamps",
            UNUSED,
            f"none of {len(live)} entries has been stamped",
            "Either nothing calls `store.note_topics(transcript)`, or it is called and "
            "no entry's subject has come up — both leave no mark. Dormancy ranking has "
            "nothing to go on either way. It costs a pass over text you already have.",
        )
    newest = max(e.last_relevant_at or 0 for e in stamped)
    return Finding(
        "topical stamps",
        OK,
        f"{len(stamped)} of {len(live)} stamped, newest {_ago(newest)}",
    )


def _consolidation(entries: list[MemoryEntry]) -> Finding:
    retired = sum(1 for e in entries if e.retired_at is not None)
    affirmed = sum(1 for e in entries if e.affirmed_at is not None)
    pairs = find_superseded(entries)
    if retired or affirmed:
        return Finding(
            "consolidation",
            OK,
            f"{retired} retired, {affirmed} affirmed, {len(pairs)} pair(s) open",
        )
    if pairs:
        return Finding(
            "consolidation",
            WARN,
            f"{len(pairs)} pair(s) look superseded and none has been answered",
            "Read both entries before acting: a later instruction usually adds to an "
            "earlier one rather than replacing it. `store.consolidate()` to merge, "
            "`store.affirm()` if both still hold.",
        )
    return Finding("consolidation", OK, "nothing looks superseded")


def _budget(entries: list[MemoryEntry]) -> Finding:
    fit, held = pressure(entries, BEHAVIOURAL_BUDGET_CHARS)
    used = sum(len(e.render()) + 1 for e in entries if e.is_behavioural and e.retired_at is None)
    share = used / BEHAVIOURAL_BUDGET_CHARS
    detail = f"{used}/{BEHAVIOURAL_BUDGET_CHARS} characters ({share:.0%}), {fit} of {held} fit"
    if fit < held:
        return Finding(
            "budget",
            FAIL,
            detail,
            f"{held - fit} behavioural entries are not reaching conversations, and nothing "
            "in a session would say so. Consolidate or retire.",
        )
    if share >= PRESSURE_ACT_AT:
        return Finding("budget", WARN, detail, "Past the point where this is worth acting on now.")
    if share >= PRESSURE_WARN_AT:
        return Finding("budget", WARN, detail, "Worth consolidating while it is still cheap.")
    return Finding("budget", OK, detail)


def _ago(when: float) -> str:
    seconds = max(0.0, time.time() - when)
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86_400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86_400)}d ago"


def report(directory: Path | str | None = None) -> tuple[list[Finding], list[Finding]]:
    """Both halves. Returns (capability, evidence); evidence is empty without a directory."""
    capability = check_capability()
    evidence = check_evidence(Path(directory).expanduser()) if directory else []
    return capability, evidence
