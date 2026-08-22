"""The README states numbers. This checks the code still agrees with them.

Documentation drift is the quietest failure there is: nothing breaks, nobody
is told, and a reader makes decisions from a page that stopped being true. The
figures below are the ones a reader would act on — budgets, thresholds, the
shape of the split — so they are pinned rather than trusted.

Measurements from the benchmarks (recall percentages, timings) are not pinned
here: they describe results on a corpus, not the behaviour of this code, and
belong to `benchmarks/README.md` where the run that produced them is recorded.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import pytest

from amem.consolidate import (
    BEHAVIOURAL_BUDGET_CHARS,
    PRESSURE_ACT_AT,
    PRESSURE_WARN_AT,
)
from amem.entry import BEHAVIOURAL_KINDS, LOOKUP_KINDS
from amem.inject import _INDEX_BUDGET_CHARS

_RAW = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")

#: Prose wraps, so a sentence a reader sees as one line is several in the file.
#: Matching against the wrapped text fails on where the line broke rather than
#: on what it says — which is how this file's first assertion failed.
README = re.sub(r"(?<!\n)\n(?![\n|#\-*])", " ", _RAW)
LINES = _RAW.splitlines()


def test_the_budget_it_quotes_is_the_budget_in_force() -> None:
    """ "about eight thousand characters exist for all of it"."""
    assert BEHAVIOURAL_BUDGET_CHARS == 8_000
    assert "eight thousand characters" in README


def test_the_pressure_threshold_it_quotes_is_the_one_used() -> None:
    assert PRESSURE_WARN_AT == 0.75
    assert "raised at 75%" in README


def test_the_escalation_threshold_it_quotes_is_the_one_used() -> None:
    """Both pages quote it, and a page quoting a threshold nobody uses is worse
    than a page that stays quiet about one."""
    assert PRESSURE_ACT_AT == 0.80
    assert "Past 80% the advisory" in README
    assert "超过 80% 之后" in ZH


def test_both_pages_document_the_answer_that_is_not_retirement() -> None:
    """Affirming is what makes escalating safe; a page describing only one
    answer describes a mechanism that nags."""
    assert "affirm" in README
    assert "store.consolidate(" in README
    assert "确认" in ZH
    assert "store.consolidate(" in ZH


@pytest.mark.parametrize("kind", sorted(BEHAVIOURAL_KINDS))
def test_every_behavioural_kind_is_in_the_table_as_stated_in_full(kind: str) -> None:
    """The split is the architecture; a reader has to be able to see which is which."""
    row = next(line for line in LINES if line.startswith(f"| `{kind}`"))

    assert "Stated in full" in row, f"{kind} is behavioural but the table does not say so"


@pytest.mark.parametrize("kind", sorted(LOOKUP_KINDS))
def test_every_lookup_kind_is_in_the_table_as_indexed(kind: str) -> None:
    row = next(line for line in LINES if line.startswith(f"| `{kind}`"))

    assert "index" in row, f"{kind} is a lookup kind but the table does not say so"


def test_no_kind_is_missing_from_the_table() -> None:
    documented = set(re.findall(r"^\| `(\w+)` \|", _RAW, re.M))

    assert documented == BEHAVIOURAL_KINDS | LOOKUP_KINDS


def test_the_index_budget_it_quotes_is_the_one_used() -> None:
    assert _INDEX_BUDGET_CHARS == 4_000


def test_the_promises_it_makes_are_the_ones_the_tests_enforce() -> None:
    """Each design commitment has a test behind it; this ties the list to them."""
    for promise in (
        "No dependency beyond the standard library",
        "The store is a text file",
        "Nothing is written without approval",
        "Nothing is destroyed",
        "The model is yours",
    ):
        assert promise in README


class TestTheComparisonIsWhereSomeoneWillSeeIt:
    """A comparison a reader has to scroll for is a comparison they will not read.

    It also has to keep saying the uncomfortable half. It is easy for the
    sentence admitting that Amem is mid-field on retrieval to go missing in a
    later edit, and what is left then reads like a page that only reports its
    wins.
    """

    def test_it_comes_before_the_implementation(self) -> None:
        headings = [line for line in _RAW.splitlines() if line.startswith("## ")]

        assert headings.index("## How it compares") < headings.index("## How retrieval works")

    def test_it_says_where_amem_loses(self) -> None:
        assert "it is not the library to pick" in README

    def test_every_unmeasured_system_gives_a_reason(self) -> None:
        """Listing a competitor with a blank cell says nothing; the blank needs a cause."""
        section = README.split("### Five that could not be measured")[1].split("## The split")[0]

        for system in ("Graphiti", "Zep", "Letta", "Memori", "TencentDB"):
            row = next(line for line in section.splitlines() if f"**{system}" in line)
            assert len(row.split("|")[2].strip()) > 60, f"{system} has no stated cause"

    def test_it_does_not_claim_the_unmeasured_ones_are_worse(self) -> None:
        """Two of them were not measured because of our protocol, not their quality."""
        section = README.split("### Five that could not be measured")[1]

        assert "not answer quality" in section
        assert 'Not "worse at memory"' in section

    def test_it_links_to_the_full_tables(self) -> None:
        assert "benchmarks/README.md" in README

    def test_every_blank_cell_says_why_it_is_blank(self) -> None:
        """A dash in a competitor's column is an insinuation unless it is explained.

        The two markers mean different things and both have to be used: ✗ where
        the system's design prevents the measurement, — where it simply was not
        run. Collapsing them would let "we did not try" read as "it cannot".
        """
        section = README.split("## How it compares")[1].split("## The split")[0]

        assert "**✗** the system's design prevents the measurement" in section
        assert "**—** not run" in section

        # Checked per row, not per cell: a row whose first blank explains
        # itself does not need the same sentence repeated in the two beside
        # it, and demanding that would trade clarity for a passing assertion.
        for row in section.splitlines():
            if not row.startswith("|") or "---" in row:
                continue
            cells = [c.strip() for c in row.split("|")[1:-1]]
            if not any(c.startswith(("✗", "—")) for c in cells):
                continue
            explained = any(len(c) > 3 and c.startswith(("✗", "—")) for c in cells)
            assert explained, f"row of bare markers with no reason: {row.strip()[:80]}"

    def test_it_reports_the_spread_next_to_the_end_to_end_numbers(self) -> None:
        """A single number implies a precision this metric does not have."""
        section = README.split("## How it compares")[1]

        assert "varies by up to ten points" in section
        assert "spread" in section


ZH = (Path(__file__).resolve().parents[1] / "README.zh-CN.md").read_text(encoding="utf-8")


class TestTheTranslationStaysInStep:
    """A translated README is the classic thing that quietly goes stale.

    Nobody notices: the English page gets a new finding, the Chinese one keeps
    the old number, and a reader who picked the wrong language reads something
    that stopped being true. Structure and figures are checked rather than
    prose — the wording is a translator's business, the numbers are not.
    """

    def test_both_pages_offer_the_other(self) -> None:
        assert "[中文](README.zh-CN.md)" in _RAW
        assert "[English](README.md)" in ZH

    def test_they_have_the_same_sections(self) -> None:
        def headings(text: str) -> int:
            return len([line for line in text.splitlines() if line.startswith("## ")])

        assert headings(ZH) == headings(_RAW), "a section was added or dropped in one language"

    def test_the_comparison_numbers_are_identical(self) -> None:
        """Percentages are language-independent; a mismatch is a stale translation."""

        def figures(text: str) -> list[str]:
            section = text.split("How it compares")[-1] if "How it compares" in text else text
            section = section.split("和开源方案的对比")[-1]
            return re.findall(r"\b\d+\.\d%", section)

        english = figures(_RAW.split("## The split")[0])
        chinese = figures(ZH.split("## 两类记忆")[0])

        assert chinese == english, "the two comparison tables disagree"

    def test_the_admission_survives_translation(self) -> None:
        """The sentence conceding mid-field retrieval is the one worth losing in a translation."""
        assert "它不是该选的库" in ZH

    def test_the_blank_cell_legend_is_translated_not_dropped(self) -> None:
        assert "该系统的设计使这项测量无法进行" in ZH
        assert "没有跑" in ZH


def _zh_prose() -> list[str]:
    """Chinese README lines, with code fences and code spans blanked.

    Blanked rather than dropped: removing them would join two paragraphs that
    a code block separates, and the wrap check below reads adjacent lines.
    """
    lines, fence = [], False
    for line in ZH.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            lines.append("")
            continue
        lines.append("" if fence or "`" in line else line)
    return lines


class TestTheChineseTypesetsCorrectly:
    """Chinese punctuation and spacing rules a Latin-trained eye does not see.

    Every one of these was a real defect in the first draft. They matter more
    here than they would in a document nobody reads closely: the page argues
    that a store you cannot inspect is a store you cannot correct, and a page
    that is visibly careless about its own text argues the opposite.
    """

    def test_no_hard_wrapped_chinese_paragraphs(self) -> None:
        """Markdown renders a newline as a space — invisible in English, wrong in Chinese."""
        lines = _zh_prose()
        wrapped = [
            (a, b)
            for a, b in itertools.pairwise(lines)
            if re.search(r"[一-鿿，。、；：？！]$", a) and re.match(r"[一-鿿]", b)
        ]
        assert not wrapped, f"{len(wrapped)} line breaks would render as spaces mid-sentence"

    def test_chinese_clauses_use_full_width_commas(self) -> None:
        """A half-width comma beside a full-width period is the mismatch that reads as sloppy."""
        for line in _zh_prose():
            assert not re.search(r"[一-鿿],|,[一-鿿]", line), line

    def test_latin_and_chinese_are_separated_by_a_space(self) -> None:
        for line in _zh_prose():
            assert not re.search(r"[一-鿿][A-Za-z0-9]|[A-Za-z0-9][一-鿿]", line), line

    def test_paired_punctuation_is_balanced(self) -> None:
        """Half-converting one side of a pair leaves （like this) — the classic sed casualty."""
        assert ZH.count("（") == ZH.count("）")
        assert ZH.count("“") == ZH.count("”")
        assert ZH.count("「") == ZH.count("」")


class TestTheUsageBlockRuns:
    """The integration in the README is executed, not proofread.

    A usage example is the first thing a reader copies and the last thing
    anyone re-runs. This one names every call a host makes, so it goes stale
    the moment a signature moves — and a stale one costs more than none: it
    reads as tested.
    """

    def _integration_block(self, text: str, heading: str) -> str:
        section = text[text.index(heading) :]
        return re.search(r"```python\n(.*?)```", section, re.S).group(1)

    def test_every_call_it_names_exists(self, tmp_path: Path) -> None:
        import amem

        block = self._integration_block(_RAW, "### The whole integration")
        # Against an instance, not the class: `directory` is set in __init__,
        # and a check that misses it would also miss a renamed attribute.
        store = amem.Store(tmp_path)

        for name in set(re.findall(r"amem\.(\w+)", block)):
            assert hasattr(amem, name), f"README names amem.{name}"
        for name in set(re.findall(r"store\.(\w+)", block)):
            assert hasattr(store, name), f"README names store.{name}"

    def test_it_compiles(self) -> None:
        """Catches the half-edited paste — the failure a reader hits first."""
        block = self._integration_block(_RAW, "### The whole integration")

        compile(block, "README.md", "exec")

    def test_it_actually_stores_and_retrieves(self, tmp_path: Path) -> None:
        """Run as written, with only the two things it says are the host's.

        The four calls in it are the whole contract this package offers a host,
        so this is the closest thing here to an integration test for somebody
        else's application.
        """
        import asyncio

        block = self._integration_block(_RAW, "### The whole integration")
        source = block.replace(
            'store = amem.Store("~/.myagent/memory")',
            f"store = amem.Store({str(tmp_path)!r})",
        ).replace(
            "async def ask_the_user(what: str) -> bool: ...",
            "async def ask_the_user(what: str) -> bool:\n    return True",
        )
        namespace: dict[str, object] = {
            "append_summary": lambda *a, **k: None,
            "summary_of": lambda text: text,
        }
        exec(compile(source, "README.md", "exec"), namespace)

        async def model(system: str, user: str) -> str:
            return (
                '[{"kind": "project", "content": "报告写在 output/reports/ 下。",'
                ' "key": "报告/日次"}]'
            )

        asyncio.run(namespace["on_session_end"]("用户：报告写在 output/reports/ 下。" * 20, model))
        store = namespace["store"]
        assert len(store.pending()) == 1, "extraction queued nothing"

        promoted = asyncio.run(
            namespace["memory_tool"]({"op": "promote", "id": store.pending()[0].id})
        )
        assert "报告/日次" in promoted

        found = asyncio.run(namespace["memory_tool"]({"op": "search", "query": "报告写在哪"}))
        assert "报告/日次" in found
        assert "报告/日次" in namespace["opening_context"]()

    def test_an_unknown_operation_is_answered_usefully(self, tmp_path: Path) -> None:
        """The README shows the error path; it has to be worth showing."""
        import asyncio

        block = self._integration_block(_RAW, "### The whole integration")
        source = block.replace(
            'store = amem.Store("~/.myagent/memory")',
            f"store = amem.Store({str(tmp_path)!r})",
        ).replace("async def ask_the_user(what: str) -> bool: ...", "")
        namespace: dict[str, object] = {}
        exec(compile(source, "README.md", "exec"), namespace)

        answer = asyncio.run(namespace["memory_tool"]({"op": "teleport"}))

        assert "teleport" in answer
        assert "search" in answer, "it should name the operations that do exist"


def test_both_pages_show_the_same_integration() -> None:
    """A translated example is where a reader in that language starts.

    It drifts the same way the prose does, and worse: prose that lags is
    confusing, code that lags does not run. Compared on the calls rather than
    the comments, which are the translator's.
    """

    def calls(text: str, heading: str) -> set[str]:
        section = text[text.index(heading) :]
        block = re.search(r"```python\n(.*?)```", section, re.S).group(1)
        return set(re.findall(r"(?:amem|store)\.\w+", block))

    assert calls(ZH, "### 完整接入") == calls(_RAW, "### The whole integration")
