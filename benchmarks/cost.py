"""What each system costs to run, in the four units a user actually pays.

Retrieval quality is where every comparison in this field competes, and it is
the axis on which this project is mid-field. These four are the axis on which
it is not, so they are measured with the same corpus and the same machine.

Build, query and disk are the conventional three. The fourth — write one
memory, then search — is here because it is the path a memory system is
actually on. Memories arrive one at a time, and a system that rebuilds its
index on every write pays that cost far more often than it pays for any single
lookup. Two of the fastest retrievers here cannot do it at all: their index
lives in memory and has to be rebuilt whole, which is reported rather than
timed, because a number would imply the operation exists.

Systems whose build and query happen inside an LLM are not comparable on any of
this — their build time is a bill, not a benchmark, and timing a network round
trip measures the network. They are listed with the reason instead of a number.

    BENCH_SYS_PATH=/path/to/mem0-install python cost.py
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _prereq import require_data

HERE = Path(__file__).parent
DATA = HERE / os.environ.get("BENCH_DATA", "locomo10.json")
SAMPLES = int(os.environ.get("BENCH_SAMPLES", "2"))
QUERIES = int(os.environ.get("BENCH_TURNS", "40"))

for extra in os.environ.get("BENCH_SYS_PATH", "").split(":"):
    if extra:
        sys.path.insert(0, extra)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def corpus() -> tuple[list[str], list[str]]:
    """Every turn as plain text, plus the questions to time queries with."""
    turns: list[str] = []
    questions: list[str] = []
    for sample in json.loads(DATA.read_text(encoding="utf-8"))[:SAMPLES]:
        convo = sample["conversation"]
        names = sorted(
            (k for k in convo if k.startswith("session_") and "date" not in k),
            key=lambda n: int(n.split("_")[1]),
        )
        turns += [
            f"{t['speaker']}: {t['text']}"
            for n in names
            for t in convo[n]
            if t.get("text") and t.get("dia_id")
        ]
        questions += [
            qa["question"].strip()
            for qa in sample.get("qa", [])
            if (qa.get("question") or "").strip()
        ]
    return turns, questions[:QUERIES]


def _dir_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


# ------------------------------------------------------------------ systems
#
# Each returns (build_seconds, [query_seconds…], index_bytes, write_then_search)
# with write_then_search None when the system cannot do it incrementally.


def ours(turns: list[str], questions: list[str]):
    from carryover.entry import MemoryEntry
    from carryover.search import MemorySearchIndex

    tmp = Path(tempfile.mkdtemp())
    source = tmp / "persistent.jsonl"
    source.write_text("", encoding="utf-8")
    entries = [MemoryEntry(kind="project", scope="persistent", content=t) for t in turns]
    index = MemorySearchIndex(tmp / "search.db", source)

    t0 = time.perf_counter()
    index.search(questions[0], entries, limit=8)  # first search is what builds it
    build = time.perf_counter() - t0

    timings = []
    for q in questions:
        t0 = time.perf_counter()
        index.search(q, entries, limit=8)
        timings.append(time.perf_counter() - t0)

    # One more memory, then search — the path this is really on.
    entries.append(MemoryEntry(kind="project", scope="persistent", content="一条新记下的事实。"))
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    t0 = time.perf_counter()
    index.search(questions[0], entries, limit=8)
    incremental = time.perf_counter() - t0

    size = _dir_bytes(tmp) - source.stat().st_size
    shutil.rmtree(tmp, ignore_errors=True)
    return build, timings, size, incremental


def llamaindex_bm25(turns: list[str], questions: list[str]):
    from llama_index.core.schema import TextNode
    from llama_index.retrievers.bm25 import BM25Retriever

    nodes = [TextNode(text=t, id_=str(i)) for i, t in enumerate(turns)]
    t0 = time.perf_counter()
    retriever = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=8)
    build = time.perf_counter() - t0

    timings = []
    for q in questions:
        t0 = time.perf_counter()
        retriever.retrieve(q)
        timings.append(time.perf_counter() - t0)

    tmp = Path(tempfile.mkdtemp())
    retriever.persist(str(tmp))
    size = _dir_bytes(tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    # No incremental write: the index is in memory and adding a node means
    # constructing the retriever again over everything.
    return build, timings, size, None


def txtai_hybrid(turns: list[str], questions: list[str]):
    from txtai import Embeddings

    emb = Embeddings(
        path=os.environ.get("BENCH_TXTAI_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        content=True,
        hybrid=True,
    )
    t0 = time.perf_counter()
    emb.index([(i, t, None) for i, t in enumerate(turns)])
    build = time.perf_counter() - t0

    timings = []
    for q in questions:
        t0 = time.perf_counter()
        emb.search(q, 8)
        timings.append(time.perf_counter() - t0)

    tmp = Path(tempfile.mkdtemp())
    emb.save(str(tmp))
    size = _dir_bytes(tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    return build, timings, size, None


SYSTEMS = {
    "Carryover": ours,
    "LlamaIndex BM25": llamaindex_bm25,
    "txtai": txtai_hybrid,
}

#: Reported rather than timed. Building happens inside an LLM, so the duration
#: is a bill; there is no local index to size or to query.
NOT_COMPARABLE = {
    "mem0": "install it to time it; 30.5s build, 39.5ms query, 3.7MB — see vs_mem0_retrieval.py",
    "MemOS": "an LLM call per query; no local index",
    "Cognee": "an LLM call per query; no local index",
    "SimpleMem": "an LLM call per query; no local index",
}


def main() -> None:
    require_data(DATA)
    if not DATA.is_file():
        raise SystemExit(f"{DATA.name} not found — see benchmarks/README.md")

    turns, questions = corpus()
    print(f"{len(turns)} turns of corpus, {len(questions)} queries\n")
    print(f"{'system':<20}{'build':>10}{'query p50':>12}{'index':>12}{'write+search':>16}")
    print("-" * 70)

    for name, run in SYSTEMS.items():
        try:
            build, timings, size, incremental = run(turns, questions)
        except ImportError as exc:
            print(f"{name:<20}{'not installed — ' + str(exc.name):>50}")
            continue
        inc = f"{incremental * 1000:.1f} ms" if incremental is not None else "full rebuild"
        print(
            f"{name:<20}{build:>9.1f}s"
            f"{statistics.median(timings) * 1000:>10.1f} ms"
            f"{size / 1e6:>10.1f} MB"
            f"{inc:>16}"
        )

    for name, why in NOT_COMPARABLE.items():
        print(f"{name:<20}{why}")


if __name__ == "__main__":
    main()
