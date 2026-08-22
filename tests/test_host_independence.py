"""Nothing here may assume which application is using it.

The package was extracted from one, and the pull of that application kept
showing up: a preamble naming its tool, a data model documented in terms of its
classes, a required field only it varied, constants a foreign host needed and
could not import. Each was found by hand, one at a time, after someone tried to
use the thing.

So the property is asserted instead. These are the checks that would have caught
every one of them.
"""

from __future__ import annotations

import ast
import inspect
import pkgutil
import sys
import tempfile
from pathlib import Path

import pytest

import amem

SOURCE = Path(amem.__file__).parent
#: `__main__` is excluded on purpose: it exists to be a command, so printing
#: and exiting are its whole job. Everything else in the package is something a
#: host imports, and none of it may do either.
MODULES = [m.name for m in pkgutil.iter_modules([str(SOURCE)]) if m.name != "__main__"]

#: Names belonging to the application this was extracted from, or to any other
#: particular host. A word here in a docstring means the package is explaining
#: itself in terms of something its reader does not have.
FOREIGN = (
    "KimiSoul",
    "SessionState",
    "kimi_cli",
    "OpenKimo",
    "archivist",
    "CrossSessionMemoryInjectionProvider",
    "kosong",
)


@pytest.mark.parametrize("module", MODULES)
def test_no_module_explains_itself_by_a_host_type(module: str) -> None:
    text = (SOURCE / f"{module}.py").read_text(encoding="utf-8")

    found = [name for name in FOREIGN if name in text]

    assert not found, (
        f"amem.{module} mentions {found} — a reader of this package does not have those"
    )


#: Everything published, not only the package. The tests ship too, and the ones
#: carried over from the application this was extracted from arrived with its
#: fixtures intact — a repository name in a key, a path under someone's home.
PUBLISHED = sorted(
    p
    for p in Path(__file__).resolve().parents[1].rglob("*")
    if p.is_file()
    and ".git" not in p.parts
    and ".venv" not in p.parts
    and "__pycache__" not in p.parts
    and p.suffix in {".py", ".md", ".toml", ".yml", ".json", ".cfg", ".txt"}
)

#: Words that would only appear here by having been carried in.
#: Written plainly. This file is skipped below, because a list of words to
#: forbid must be allowed to contain them.
CARRIED_IN = ("qunwei", "china.eli", "/Users/q", "acls")


@pytest.mark.parametrize("path", PUBLISHED, ids=lambda p: p.name)
def test_nothing_published_carries_someone_s_own_details(path: Path) -> None:
    """Checked over the whole repository, not just the package.

    The first version of this scanned src/ only, and a test file ported from
    the application it came from sat in the repository for a day naming that
    application's repository and a path under its author's home directory.
    """
    if path.name == Path(__file__).name:
        return  # this file names what it forbids

    text = path.read_text(encoding="utf-8", errors="replace")
    found = [w for w in CARRIED_IN if w in text]

    assert not found, f"{path.name} carries {found}"


def test_no_build_artefact_is_committed() -> None:
    """`.coverage` is a SQLite file of absolute paths, and `git add -A` takes it."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    forbidden = [f for f in tracked if f == ".coverage" or f.startswith(".coverage.")]
    assert not forbidden, f"{forbidden} is a build artefact and holds absolute paths"


@pytest.mark.parametrize("module", MODULES)
def test_no_module_imports_anything_undeclared(module: str) -> None:
    """The promise that makes it installable anywhere, checked per module."""
    allowed = set(sys.stdlib_module_names) | {"amem", "pydantic"}

    for node in ast.walk(ast.parse((SOURCE / f"{module}.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""] if node.level == 0 else []
        else:
            continue
        for name in names:
            assert name.split(".")[0] in allowed, f"amem.{module} imports {name}"


class TestAHostSuppliesOnlyItsOwnThings:
    def test_a_store_needs_a_directory_and_nothing_else(self) -> None:
        assert list(inspect.signature(amem.Store.__init__).parameters) == ["self", "directory"]

    def test_a_tilde_path_is_expanded_rather_than_taken_literally(self) -> None:
        assert "~" not in str(amem.Store("~/anywhere").directory)

    def test_an_entry_can_be_built_without_knowing_this_package_s_conventions(self) -> None:
        """Every field a caller must supply is one they can answer from their own domain."""
        entry = amem.MemoryEntry(kind="project", content="a fact")

        assert entry.scope == "persistent", "scope had to be supplied and never varied"
        assert entry.id and entry.created_at

    def test_nothing_reads_the_environment(self) -> None:
        """A library that reads an env var is configured somewhere its caller cannot see."""
        for module in MODULES:
            text = (SOURCE / f"{module}.py").read_text(encoding="utf-8")
            assert "os.environ" not in text, f"amem.{module} reads the environment"
            assert "getenv" not in text, f"amem.{module} reads the environment"


class TestEverythingAHostNeedsIsExported:
    """Reaching into a submodule for a type or a constant is a host doing the
    package's job. Each of these was needed by the first foreign host written."""

    @pytest.mark.parametrize(
        "name",
        [
            "Store",
            "MemoryEntry",
            "MemoryKind",
            "MemoryScope",
            "MemoryCandidate",
            "SearchHit",
            "SessionSummary",
            "UpsertResult",
            "BEHAVIOURAL_BUDGET_CHARS",
            "PRESSURE_WARN_AT",
            "PRESSURE_ACT_AT",
            "render",
            "Actions",
            "propose",
            "Completer",
            "execute",
            "parse_operation",
            "Operation",
            "OperationResult",
            "UnknownOperation",
            "find_superseded",
            "find_dormant",
            "pressure",
            "fold_text",
        ],
    )
    def test_it_is_reachable_from_the_package_root(self, name: str) -> None:
        assert hasattr(amem, name)
        assert name in amem.__all__

    def test_nothing_is_advertised_that_is_not_there(self) -> None:
        assert [n for n in amem.__all__ if not hasattr(amem, n)] == []


class TestItWorksWithoutAnAgentAtAll:
    """A host with a form, a CLI or a cron job is as much a caller as one with
    an LLM. Nothing in the read/write path may require a model or a prompt."""

    def test_a_store_can_be_used_without_touching_render_or_propose(self) -> None:
        store = amem.Store(Path(tempfile.mkdtemp()))

        store.add("project", "报告写在 output/reports/ 下。", key="r/d")

        assert [h.handle for h in store.search("报告写在哪")] == ["r/d"]
        assert store.get("r/d") is not None
        assert amem.pressure(store.entries(), amem.BEHAVIOURAL_BUDGET_CHARS) == (0, 0)

    def test_consolidation_advice_is_data_before_it_is_prose(self) -> None:
        """A host with its own interface wants the pairs, not a paragraph."""
        store = amem.Store(Path(tempfile.mkdtemp()))
        older = store.add("feedback", "截至 2026-03-04，上报失败采用固定间隔重试。").entry
        newer = amem.MemoryEntry(
            kind="feedback",
            content="截至 2026-04-02，上报失败已改为指数退避，不再使用固定间隔重试。",
        )
        newer.created_at = older.created_at + 1

        found = amem.find_superseded([older, newer])

        assert found and found[0].older.id == older.id
        assert isinstance(found[0].score, float)

    def test_the_model_is_the_caller_s_and_never_constructed_here(self) -> None:
        params = inspect.signature(amem.propose).parameters

        assert "complete" in params, "the completer is passed in"
        assert not {"api_key", "model", "base_url", "client"} & set(params)


class TestTheAlphabetIsNotThisPackageSToChoose:
    """Retrieval used to work in two writing systems and silently fail in the rest.

    The tokeniser matched a Han run or an ASCII word, so Cyrillic, Arabic,
    Hangul, Greek, Hebrew, Devanagari and Thai produced no searchable terms at
    all — every query in them returned nothing, with no error. Japanese written
    in kana did the same; the Japanese that appeared to work was passing on its
    Han characters.

    What decides the treatment is not the language but whether the script marks
    word boundaries: one that does gets whole terms, one that does not gets
    character windows, because there is nothing else to cut on.
    """

    @pytest.mark.parametrize(
        ("script", "stored", "asked"),
        [
            (
                "Latin",
                "The daily report lives in output/reports/daily/.",
                "where do daily reports live",
            ),
            ("Han", "日报写在 output/reports/daily/ 下。", "日报写在哪"),
            ("Kana", "にっぽうは output/reports/daily/ にかきます。", "にっぽうはどこ"),
            ("Hangul", "일일 보고서는 output/reports/daily/ 에 있습니다.", "일일 보고서 어디"),
            ("Cyrillic", "Ежедневный отчёт лежит в output/reports/daily/.", "Где ежедневный отчёт"),
            ("Arabic", "التقرير اليومي في output/reports/daily/.", "أين التقرير اليومي"),
            ("Thai", "รายงานประจำวันอยู่ใน output/reports/daily/", "รายงานประจำวันอยู่ที่ไหน"),
            (
                "Greek",
                "Η ημερήσια αναφορά βρίσκεται στο output/reports/daily/.",
                "πού είναι η ημερήσια αναφορά",
            ),
        ],
    )
    def test_a_query_finds_what_was_stored_in_the_same_script(
        self, script: str, stored: str, asked: str
    ) -> None:
        store = amem.Store(Path(tempfile.mkdtemp()))
        store.add("project", stored, key="r/d")
        store.add("project", "unrelated 无关记录", key="x/1")

        hits = store.search(asked)

        assert hits, f"{script} returned nothing at all"
        assert hits[0].handle == "r/d"

    def test_a_word_does_not_swallow_the_script_beside_it(self) -> None:
        """The first attempt at this tokenised "CodeGraph有什么限制" as one term,
        which cost two points of Chinese recall on the same corpus."""
        from amem.search import _PIECE

        assert _PIECE.findall("CodeGraph有什么限制") == ["CodeGraph", "有什么限制"]

    def test_an_identifier_still_survives_intact(self) -> None:
        """Splitting harder must not break the terms models actually write."""
        from amem.search import _PIECE

        assert "core.py" in _PIECE.findall("core.py 在哪")


class TestNothingHappensThatTheCallerDidNotAskFor:
    def test_no_module_prints(self) -> None:
        for module in MODULES:
            text = (SOURCE / f"{module}.py").read_text(encoding="utf-8")
            assert "\nprint(" not in text and " print(" not in text, f"amem.{module} prints"

    def test_no_module_configures_logging_for_the_process(self) -> None:
        """A library that calls basicConfig decides how its host logs."""
        for module in MODULES:
            text = (SOURCE / f"{module}.py").read_text(encoding="utf-8")
            assert "basicConfig" not in text
            assert "getLogger()" not in text, f"amem.{module} takes the root logger"

    def test_no_module_ends_the_process(self) -> None:
        for module in MODULES:
            text = (SOURCE / f"{module}.py").read_text(encoding="utf-8")
            assert "sys.exit" not in text and "SystemExit" not in text

    def test_reading_does_not_change_what_was_passed_in(self) -> None:
        """A caller's list is the caller's."""
        entries = [
            amem.MemoryEntry(kind="feedback", content="a"),
            amem.MemoryEntry(kind="feedback", content="b"),
        ]
        before = [e.model_dump_json() for e in entries]

        amem.find_superseded(entries)
        amem.pressure(entries, amem.BEHAVIOURAL_BUDGET_CHARS)
        amem.find_dormant(entries, now=1.0)

        assert [e.model_dump_json() for e in entries] == before


class TestTheStoreSurvivesTheWorldItIsGiven:
    def test_a_directory_that_does_not_exist_yet_is_made(self) -> None:
        root = Path(tempfile.mkdtemp())

        store = amem.Store(root / "not" / "there" / "yet")
        store.add("project", "a fact")

        assert len(store.entries()) == 1

    def test_two_stores_on_one_directory_see_each_other(self) -> None:
        """One process, two callers — a web worker and a background job."""
        root = Path(tempfile.mkdtemp())
        first, second = amem.Store(root), amem.Store(root)

        first.add("project", "from the first", key="k/a")
        second.add("project", "from the second", key="k/b")

        assert len(second.entries()) == 2
        assert len(first.entries()) == 2

    def test_a_field_from_a_later_version_does_not_lose_the_entry(self) -> None:
        """Forward compatibility: a newer writer must not empty an older reader's store."""
        import json

        root = Path(tempfile.mkdtemp())
        store = amem.Store(root)
        store.add("project", "an entry", key="k/1")
        row = json.loads(store.path.read_text(encoding="utf-8").splitlines()[0])
        row["a_field_from_the_future"] = 1
        store.path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

        assert len(amem.Store(root).entries()) == 1


class TestTheKeyRuleIsNotEnglishOnly:
    """An agent working in Chinese has no reason to name its memories in English.

    The rule was `[a-z0-9][a-z0-9._-]*`, so 会议/纪要 was rejected outright — the
    same ASCII assumption that made whole scripts retrieve nothing, in the field
    a model chooses itself.
    """

    @pytest.mark.parametrize(
        "key", ["ns/slug", "会议/纪要", "報告/日次", "보고서/일일", "отчёт/ежедневный", "数字/123"]
    )
    def test_a_key_may_be_written_in_any_script(self, key: str) -> None:
        assert amem.MemoryEntry(kind="project", content="x", key=key).key == key

    @pytest.mark.parametrize("key", ["a b/c", "a//b", "/leading", "trailing/", "a/b/c"])
    def test_the_shape_is_still_namespace_slash_slug(self, key: str) -> None:
        """Widening the alphabet must not widen the structure."""
        with pytest.raises(ValueError):
            amem.MemoryEntry(kind="project", content="x", key=key)

    def test_case_is_still_folded(self) -> None:
        assert amem.MemoryEntry(kind="project", content="x", key="UPPER/Case").key == "upper/case"


class TestWhichDayItIs:
    """The date a model resolves "last Tuesday" against is written into a fact.

    It defaults to this process's local one, which is right on a desktop and
    arbitrary on a server: a host in UTC and a user in Shanghai disagree about
    the date for several hours out of every twenty-four, and the prompt itself
    says a wrong date is worse than none.
    """

    async def test_a_host_can_state_the_date(self) -> None:
        sent: list[str] = []

        async def complete(system: str, user: str) -> str:
            sent.append(user)
            return "[]"

        await amem.propose(complete, "x" * 400, today="2026-03-05")

        assert "2026-03-05" in sent[0]

    async def test_the_default_is_still_this_machine_s_today(self) -> None:
        import time

        sent: list[str] = []

        async def complete(system: str, user: str) -> str:
            sent.append(user)
            return "[]"

        await amem.propose(complete, "x" * 400)

        assert time.strftime("%Y-%m-%d") in sent[0]


class TestTheStoreSurvivesWhatIsPutInIt:
    """A JSONL file whose records contain newlines is one bad escape from
    unreadable, and the content comes from conversations nobody controls."""

    @pytest.mark.parametrize(
        ("label", "content"),
        [
            ("newlines", "first\nsecond\nthird"),
            ("crlf", "a\r\nb"),
            ("tabs", "a\tb"),
            ("quotes and backslashes", 'he said "this" and \\that'),
            ("control characters", "a\x00b\x01c"),
            ("line separator", "a b"),
            ("emoji", "记住 🎉 这个"),
            ("very long", "x" * 100_000),
        ],
    )
    def test_it_comes_back_exactly(self, tmp_path: Path, label: str, content: str) -> None:
        store = amem.Store(tmp_path)

        store.add("project", content, key="t/1")

        assert [e.content for e in amem.Store(tmp_path).entries()] == [content]

    def test_one_entry_is_one_line(self, tmp_path: Path) -> None:
        """Otherwise a reader splitting on newlines gets fragments."""
        store = amem.Store(tmp_path)

        store.add("project", "first\nsecond\nthird", key="t/1")

        assert store.path.read_text(encoding="utf-8").rstrip("\n").count("\n") == 0

    @pytest.mark.parametrize("name", ["my store", "我的记忆库", "store (v2) #1"])
    def test_the_directory_may_be_named_anything(self, tmp_path: Path, name: str) -> None:
        store = amem.Store(tmp_path / name)

        store.add("project", "一条事实", key="k/1")

        assert store.search("事实")


class TestMoreThanOneWriter:
    """A web worker, a background job, and the request that started them."""

    def test_threads_do_not_lose_writes(self, tmp_path: Path) -> None:
        import threading

        store = amem.Store(tmp_path)
        errors: list[BaseException] = []

        def write(i: int) -> None:
            try:
                store.add("project", f"from thread {i}", key=f"t/{i}")
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=write, args=(i,)) for i in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        assert len(amem.Store(tmp_path).entries()) == 20

    def test_the_file_is_never_left_torn(self, tmp_path: Path) -> None:
        """Every line has to parse, whoever was writing when."""
        import json
        import threading

        store = amem.Store(tmp_path)
        threads = [
            threading.Thread(
                target=store.add,
                args=(
                    "project",
                    f"entry {i}",
                ),
            )
            for i in range(20)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        for line in store.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                json.loads(line)


class TestTheFramingIsNotNarrowerThanTheThing:
    """It was described as memory "for coding agents" for its whole first week.

    Nothing in it is specific to that: no module mentions code, repositories or
    commits, the kinds are user/feedback/project/reference, and the comparison
    everything rests on was measured on LoCoMo — two people talking about their
    families. The framing came from the application it was extracted from, the
    same way the tool names and the data model did, and it was the last piece
    of that to go.
    """

    def test_no_module_assumes_a_domain(self) -> None:
        domain = ("coding agent", "repository", "pull request", "codebase", "programmer")

        for module in MODULES:
            text = (SOURCE / f"{module}.py").read_text(encoding="utf-8").lower()
            found = [w for w in domain if w.lower() in text]
            assert not found, f"amem.{module} assumes {found}"

    def test_the_package_description_is_not_narrowed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        published = (root / "pyproject.toml").read_text(encoding="utf-8")

        assert "coding agents" not in published

    def test_the_page_says_the_examples_are_only_examples(self) -> None:
        """The examples are from one domain, and a reader should not have to
        infer that the library is too."""
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")

        assert "Nothing in it is specific to a domain" in readme
