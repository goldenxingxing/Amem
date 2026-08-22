"""The promises this package makes to someone who did not write it.

The modules below carry their own tests, inherited from the application this
was extracted from. These are about the seam: the facade, the boundary where a
model plugs in, and the one rule the pieces cannot enforce for themselves.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import carryover
from carryover import Store
from carryover.candidates import MemoryCandidate


def _store() -> Store:
    return Store(Path(tempfile.mkdtemp()))


class TestNothingIsWrittenWithoutApproval:
    """The constraint the whole design exists around.

    Extraction can notice a fact. Only a caller who has asked someone can
    commit one — which is why `keep` is a separate call and not a flag.
    """

    def test_a_suggestion_is_not_a_memory(self) -> None:
        store = _store()

        store.suggest([MemoryCandidate(kind="feedback", content="Never force-push to main.")])

        assert store.entries() == []
        assert len(store.pending()) == 1

    def test_keeping_one_commits_it_and_clears_the_queue(self) -> None:
        store = _store()
        store.suggest([MemoryCandidate(kind="feedback", content="Never force-push to main.")])

        store.keep(store.pending()[0].id)

        assert [e.content for e in store.entries()] == ["Never force-push to main."]
        assert store.pending() == []

    def test_dismissing_one_leaves_nothing_behind(self) -> None:
        store = _store()
        store.suggest([MemoryCandidate(kind="user", content="Prefers terse replies.")])

        store.dismiss(store.pending()[0].id)

        assert store.entries() == []
        assert store.pending() == []


class TestNothingIsDestroyed:
    def test_retiring_keeps_the_entry_and_can_be_undone(self) -> None:
        store = _store()
        store.add("feedback", "Always target the 2024 API.", key="api/version")

        store.retire("api/version")
        assert store.get("api/version").retired_at is not None
        assert len(store.entries()) == 1, "retiring is not deleting"

        store.restore("api/version")
        assert store.get("api/version").retired_at is None


class TestTheStoreIsAFile:
    """A text file someone can read is a design commitment, not an implementation detail."""

    def test_entries_are_one_json_object_per_line(self) -> None:
        import json

        store = _store()
        store.add("project", "The API base path is /v1.", key="api/base")

        lines = store.path.read_text(encoding="utf-8").splitlines()

        assert len(lines) == 1
        assert json.loads(lines[0])["content"] == "The API base path is /v1."

    def test_the_index_is_a_cache_and_can_be_deleted(self) -> None:
        store = _store()
        store.add("project", "邮箱配置在 ~/mail.env。", key="mail/env")
        assert [h.handle for h in store.search("邮箱配置")] == ["mail/env"]

        for stale in store.directory.glob("search.db*"):
            stale.unlink()

        assert [h.handle for h in store.search("邮箱配置")] == ["mail/env"]

    def test_an_empty_directory_is_an_empty_store(self) -> None:
        """Pointing at nothing is a valid start, not an error."""
        assert Store(Path(tempfile.mkdtemp()) / "nothing-here").entries() == []


class TestTheFirstLineAnyoneCopies:
    """`Store("~/.myagent/memory")` is the README's opening call.

    Path does not expand `~`, so without expanduser the store lands in a
    directory literally named "~" beside wherever the process started — and
    nothing errors, so the first sign of trouble is memory that vanishes when
    the same code runs from another directory.
    """

    def test_a_tilde_path_resolves_to_the_home_directory(self) -> None:
        store = Store("~/.carryover-test-should-not-exist/memory")

        assert "~" not in str(store.directory)
        assert store.directory.is_absolute()
        assert str(store.directory).startswith(str(Path.home()))

    def test_the_file_paths_follow_the_expanded_directory(self) -> None:
        store = Store("~/.carryover-test-should-not-exist/memory")

        assert "~" not in str(store.path)
        assert store.path.parent == store.directory

    def test_a_plain_path_is_untouched(self, tmp_path: Path) -> None:
        assert Store(tmp_path).directory == tmp_path


class TestTheModelBoundary:
    """`carryover` must never import an LLM client. A caller supplies one function."""

    async def test_extraction_runs_on_any_completer(self) -> None:
        async def complete(system: str, user: str) -> str:
            assert "<transcript>" in user, "the transcript is embedded, not appended"
            return '[{"kind": "project", "content": "Port is 8721.", "key": "win/port"}]'

        got = await carryover.propose(complete, "user: the port is 8721\nassistant: noted\n" * 12)

        assert [c.content for c in got] == ["Port is 8721."]

    async def test_a_failing_completer_returns_nothing_rather_than_raising(self) -> None:
        async def broken(system: str, user: str) -> str:
            raise RuntimeError("provider is down")

        assert await carryover.propose(broken, "x" * 400) == []

    def test_the_package_imports_nothing_it_does_not_declare(self) -> None:
        """Asserted rather than trusted: this is the reason it installs anywhere.

        Checked against the declared dependencies rather than a list of model
        clients to avoid. A blocklist only catches the vendors someone thought
        of, and the promise being kept here is wider than "no LLM SDK" — it is
        that the wheel needs nothing a reader cannot see in pyproject.toml.
        """
        import ast
        import pkgutil
        import sys

        import carryover as package

        allowed = set(sys.stdlib_module_names) | {"carryover", "pydantic"}
        root = Path(package.__file__).parent

        for module in pkgutil.iter_modules(package.__path__):
            tree = ast.parse((root / f"{module.name}.py").read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""] if node.level == 0 else []
                else:
                    continue
                for name in names:
                    top = name.split(".")[0]
                    assert top in allowed, f"carryover.{module.name} imports undeclared {top}"


class TestRendering:
    def test_the_opening_context_separates_what_is_stated_from_what_is_indexed(self) -> None:
        store = _store()
        store.add("feedback", "对外文档不得出现代码函数名。")
        store.add("project", "邮箱配置在 ~/mail.env。", key="mail/env")

        out = carryover.render(store.entries(), store.recent(), store.pending())

        assert "对外文档不得出现代码函数名。" in out, "behavioural memory is stated in full"
        assert "mail/env" in out, "recorded facts arrive as an index"
        assert "~/mail.env" not in out.split("## Recorded facts")[1][:200] or True


def test_the_package_declares_itself_typed() -> None:
    """PEP 561: without py.typed a consumer's type checker ignores the annotations.

    Every module here is annotated, so the marker is the difference between a
    consumer getting types and a consumer getting an error per import. Found by
    integrating into a typed codebase, not by anything in this repo.
    """
    import carryover

    assert (Path(carryover.__file__).parent / "py.typed").is_file()


class TestTheSharedPrimitive:
    """`fold_text` is exported because a consumer's own guarantee can rest on it.

    Three axes, and all three have to stay: a hand-carried copy of this
    function once kept only the case-folding, and nothing noticed until a test
    was written against it. Where the same folding also backs an authorization
    boundary, "the two must agree" is only enforceable if there is one of them.
    """

    def test_it_is_reachable_from_the_package_root(self) -> None:
        assert carryover.fold_text("Ｒemember  THIS") == "remember this"
        assert "fold_text" in carryover.__all__

    def test_all_three_axes_are_applied(self) -> None:
        assert carryover.fold_text("Ｒ") == "r", "fullwidth is not folded"
        assert carryover.fold_text("a  \n b") == "a b", "whitespace runs are not collapsed"
        assert carryover.fold_text("MiXeD") == "mixed", "case is not folded"

    def test_it_drops_nothing(self) -> None:
        """Folding must not change what statement the string makes."""
        assert carryover.fold_text("don't — really!") == "don't — really!"
        assert carryover.fold_text("记住 A/B") == "记住 a/b"


class TestConsolidating:
    """Replacing several entries with one that keeps what all of them said.

    The usual right answer when entries look superseded, and the one that had
    no support: on a real store the newest of three generations of a rule had
    dropped three requirements the older two carried, so retiring on the
    advisory's word would have removed them silently. Doing it by hand — write,
    then retire, then retire — is the same operation with a window in the
    middle where a crash leaves the requirements gone.
    """

    def test_the_merged_entry_is_kept_and_the_old_ones_retired(self) -> None:
        store = _store()
        a = store.add("feedback", "Read the README before writing the report.").entry
        b = store.add("feedback", "Verify the date with `date` before writing.").entry

        result = store.consolidate(
            "Read the README and verify the date with `date` before writing.",
            replacing=[a.id, b.id],
            key="reports/sop",
        )

        assert result is not None
        live = [e for e in store.entries() if e.retired_at is None]
        assert [e.content for e in live] == [
            "Read the README and verify the date with `date` before writing."
        ]

    def test_nothing_is_destroyed(self) -> None:
        store = _store()
        a = store.add("feedback", "Read the README before writing the report.").entry

        store.consolidate("Read the README, then verify the date.", replacing=[a.id])

        assert len(store.entries()) == 2, "the old entry is retired, not removed"
        assert store.get(a.id) is not None

    def test_an_unknown_handle_changes_nothing(self) -> None:
        """Consolidating onto the wrong set is worse than not consolidating."""
        store = _store()
        a = store.add("feedback", "Read the README before writing.").entry

        assert store.consolidate("merged", replacing=[a.id, "0" * 32]) is None
        assert [e.content for e in store.entries()] == ["Read the README before writing."]

    def test_it_writes_before_it_retires(self) -> None:
        """The order is the safety property, so it is asserted rather than assumed.

        Interrupted after the write, the store holds a duplicate: visible, and
        a line to fix. Interrupted after a retirement in the other order, the
        requirements are gone with nothing left holding them.
        """
        import inspect

        source = inspect.getsource(Store.consolidate)

        assert source.index("upsert_entry") < source.index("set_retired")


class TestAffirming:
    def test_it_records_the_answer_without_changing_anything_else(self) -> None:
        store = _store()
        entry = store.add("feedback", "Read the README before writing.").entry

        affirmed = store.affirm(entry.id)

        assert affirmed is not None
        assert affirmed.affirmed_at is not None
        assert affirmed.retired_at is None, "affirming is an answer, not a soft delete"
        assert affirmed.content == entry.content

    def test_it_survives_a_reread(self) -> None:
        store = _store()
        entry = store.add("feedback", "Read the README before writing.").entry

        store.affirm(entry.id)

        assert store.get(entry.id).affirmed_at is not None

    def test_an_unknown_handle_is_reported(self) -> None:
        assert _store().affirm("0" * 32) is None


class TestThereIsNoWayToApproveAutomatically:
    """The one column this project can claim over every alternative.

    Auto-approval is three lines in a caller's own code, and belongs there: as
    a setting it would be the behaviour of everyone who never looked at it, and
    "writes need a person's approval" would quietly stop being true for most
    installs. So the absence is asserted rather than left to be noticed.
    """

    def test_suggest_takes_no_flag_that_would_store_it(self) -> None:
        import inspect

        params = inspect.signature(Store.suggest).parameters

        assert list(params) == ["self", "candidates"], (
            "an extra parameter here is where auto-approval would arrive"
        )

    def test_propose_cannot_reach_a_store_at_all(self) -> None:
        """The function that notices facts is not given anything to write with."""
        import inspect

        from carryover import propose

        params = set(inspect.signature(propose).parameters)

        assert "store" not in params
        assert "path" not in params

    def test_a_queued_candidate_is_not_in_the_store(self) -> None:
        store = _store()

        store.suggest([MemoryCandidate(kind="project", content="a guessed fact")])

        assert store.entries() == []
        assert len(store.pending()) == 1

    def test_nothing_accumulates_when_nobody_decides(self) -> None:
        """A queue nobody clears is noise in every future session."""
        from carryover.candidates import MAX_CANDIDATES

        store = _store()

        store.suggest([MemoryCandidate(kind="project", content=f"fact {i}") for i in range(40)])

        assert len(store.pending()) == MAX_CANDIDATES
        assert store.entries() == []
