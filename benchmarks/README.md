# Benchmarks

What Carryover costs and how well it works, measured rather than claimed — including
where it loses.

Every figure here is from a run whose script is in this directory. Where a
number was published and later found wrong, the correction is kept alongside
it: the mistakes are the most transferable part.

---

## Against other open-source memory systems

Ten projects were surveyed; five were run. The rest could not be measured
honestly, and why is at the bottom.

Same corpus, same judge, same content into every system. Two metrics, because
they disagree: **recall** asks whether the retriever returned the turn holding
the answer, and **end-to-end accuracy** asks whether the question got answered.

### Quality

| System | End-to-end | n | Recall@8 EN | Recall@8 ZH |
|---|---|---|---|---|
| SimpleMem (planning + reflection at query time) | **76.3%** | 5 | N/A | N/A |
| Cognee (graph, answers from extracted structure) | **64.3%** | 8 | N/A | N/A |
| *Carryover, answered by the stronger model (control)* | *54.5%* | 7 | — | — |
| mem0 (qdrant hybrid) | 52.7% | 8 | **68.5%** | 49.3% |
| **Carryover** | 49.4% | 8 | 64.6% | **58.9%** |
| LlamaIndex BM25 | 48.0% | 8 | 60.6% | 2.3% |
| MemOS | 47.0% | 2 | 69.5% ✻ | — |
| txtai (dense + BM25) | 46.6% | 3 | 57.6% | 61.9% |
| Cognee (returning raw chunks) | 43.0% | 8 | 75.4% ✻† | — |

**✻** From a 118-question subset, not comparable with the 302-question rows.
On the same subset Carryover scores 61.9% against MemOS's 69.5%.
**†** Not the same budget: one Cognee "result" is a twenty-turn document, so
eight results are 160 turns against everyone else's eight.

The README carries a shorter version of this table, for choosing. This is the
full one: nothing that was measured is left out of it, including the rows Carryover
loses.

**Carryover comes mid-field, and the honest summary is that it is not the retriever
to pick if retrieval quality is what you are optimising.** Three things are
worth taking from the table beyond the ranking.

**The axis that predicts accuracy is not what is stored or how it is
retrieved.** It is whether an LLM runs at query time. The two systems that do
score 64.3% and 76.3%; the seven that do not score 43.0% to 54.5% and cannot be
told apart inside a ten-point spread — and that group contains pure lexical,
pure dense, hybrid, and LLM-extraction alike.

**Recall does not convert.** Three independent observations: raising Carryover's
Chinese recall by 11 points moved end-to-end accuracy not at all; Carryover beats
the best BM25 by 7.6 points of recall and ties it on answers; MemOS beats Carryover
by 7.6 points of recall and answers no better.

**BM25 collapses on Chinese** — 60.6% English, 2.3% Chinese — and that gap is
the entire reason the CJK handling here exists. But most of it is a tokenizer,
not this code: a five-line bigram split ahead of a stock BM25 reaches 51.3%.
Carryover's remaining 7.6 points over that are real and do not change any answers.

### Cost

788 turns, 40 queries, one machine.

| System | Build | Query (median) | Index on disk | Write then search | Install |
|---|---|---|---|---|---|
| **Carryover** | **0.0 s** | 0.5 ms | 1.0 MB | **1.7 ms** | **0** |
| LlamaIndex BM25 | 0.1 s | **0.1 ms** | 0.7 MB | full rebuild | ~970 MB env |
| txtai | 1.5 s | 8.5 ms | 2.0 MB | full rebuild | ~970 MB env |
| mem0 (extraction off) | 30.5 s | 39.5 ms | 3.7 MB | — | 360 MB tree |
| Cognee | ~20 min | — | — | — | ~1.0 GB env |
| MemOS | minutes | — | — | — | ~1.2 GB env |
| SimpleMem | ~2 h | — | — | — | ~1.4 GB env |

The last three build inside an LLM, so their wall-clock is a bill rather than a
benchmark and is not comparable with the first four.

**Adding one memory and searching again costs 1.7 ms here and a full rebuild
elsewhere**, because BM25 and txtai hold their index in memory. Memory is
accumulated one entry at a time, so that path runs far more often than any
retrieval.

Recorded in the other direction too: BM25 answers a query five times faster
than Carryover does, and both are far below anything perceptible.

### Staleness (`incremental.py`)

Nothing else here tests maintenance. Every other benchmark loads a fixed corpus
and asks about it, which cannot see whether memory survives its facts changing
— and that is where mem0 bet the other way in 2026-04, replacing UPDATE/DELETE
consolidation with single-pass accumulation.

Twelve sessions in order, six of nine facts revised partway through, then asked
for the current value:

| System | Current | Stale | Both, unmarked | Unchanged facts kept |
|---|---|---|---|---|
| **Carryover** | **6/6** | 0 | 0 | **3/3** |
| mem0 (`infer=True`) | 4/6 | 1 | 1 | 1/3 |

mem0 returned the superseded solver for one, handed back both values without
saying which was current for another, and lost two of the three standing
instructions that never changed.

**Carryover does not win this with the mechanism built for it.** Deduplication fired
zero times and by design cannot fire here — differing numbers are a veto, and
5494 against 8721 is exactly that shape. What carries it is that every entry
states its date, so both versions sit in the store and a reader can order them.
Which reclassifies consolidation: staleness is handled by dating, and
consolidation is there for capacity, because every revision leaves two entries
behind.

### Not measured, and why

| | |
|---|---|
| Graphiti | Its embedded Kuzu backend built 2 nodes from 10 turns. Needs Neo4j and a JVM. |
| Zep | A client with no server; needs one running or a cloud key. |
| Letta | Maintains memory by editing it during a conversation. Bulk-loading a transcript cannot exercise that. |
| Memori | Captures by intercepting LLM calls. Same mismatch. |
| TencentDB Agent Memory | Three Node services. Not attempted. |

The middle two are not capability judgements. Scoring a system whose mechanism
is *maintenance during conversation* on a bulk-load protocol would repeat, in
the opposite direction, the mistake of scoring a knowledge graph on turn
recall.

### What flipped, and what it cost to notice

Configuration choices reversed conclusions twice, by more than the gap between
systems.

mem0 with the chroma store its docs recommend **silently disables its own
hybrid retrieval** — English fell from 68.5% to 58.3%. And the first Chinese
run used an English-only embedding model plus mem0's default 0.1 relevance
threshold, which scored it 11.6% and produced a published claim that Carryover led
Chinese by 37 points. Corrected, it trails.

A third nearly went the other way: LlamaIndex's `BM25Retriever` accepts a
`tokenizer`, warns that it is deprecated, and ignores it. Passing a CJK
tokenizer returned results identical to the default, digit for digit — which
reads as "a Chinese tokenizer does not help BM25", a conclusion that happened
to flatter Carryover. It was caught only because the numbers matched too exactly.

**Every one of these errors pointed the same way.** That is not chance: a
number stops being checked when it is pleasant. The reproduction instructions
below exist so someone can check them without trusting this page.

---

## Token cost (`token_cost.py`)

The number this field advertises on. mem0 claims 90% savings; Memori claims
2.8% context overhead. A library that does not know its own is arguing from
silence.

Two designs spend tokens in opposite places, so the comparison has to be fair
to both:

- **Carryover** pays once, at the start. Behavioural memory arrives in full whether
  or not it is relevant. Nothing is spent per turn.
- **Query-driven memory** pays per turn. Nothing arrives uninvited; each turn
  injects whatever a retrieval returned.

Measured against a floor of the same conversation with no memory at all. 20
turns, a store of 29 entries, counted from the `usage` the provider returns —
not estimated with a tokenizer that is not the one being billed.

| Strategy | Prompt tokens | Of which cached | **Paid** | Over floor | Per turn |
|---|---|---|---|---|---|
| No memory (floor) | 5,566 | 5,426 | 140 | — | — |
| **Carryover** (preamble once) | 45,726 | 44,464 | **1,262** | +1,122 | 56 |
| Query-driven (retrieve per turn) | 21,191 | 18,711 | **2,480** | +2,340 | 117 |

**By nominal tokens Carryover costs 2.2× more. By what is actually charged it costs
half as much.**

The difference is prompt prefix caching, and the two designs differ in exactly
the property that decides whether they get it. A preamble written once is a
stable prefix that every later turn reuses — 44,464 of 45,726 tokens came back
cached. A retrieval injected ahead of each turn rewrites the prefix and
invalidates everything behind it, so the strategy with half the nominal tokens
pays twice as much.

And the gap widens with the conversation:

| Turn | Carryover (paid) | Query-driven (paid) |
|---|---|---|
| 5 | 389 | 492 |
| 10 | 652 | 1,010 |
| 20 | **1,262** | **2,480** |

### Two wrong versions of this table

Both were produced, believed briefly, and are recorded because the shape
repeats.

**Counting only `prompt_tokens`** gave "Carryover costs 2.3× more" — charging both
strategies full price for tokens one of them gets at a discount, on the axis
where they differ most.

**A convenient fixture.** The first store held five short rules: 389
characters, 5% of the behavioural budget. The live store it was modelled on
held eleven entries at 79%, because real entries average 576 characters rather
than 80. Sizing the fixture for convenience shrank the single largest cost in
the measurement by a factor of fifteen. The table above uses 21% and is still
conservative.

Both are the same mistake: setting a property of the measurement by what was
easy instead of by what is true, and it is the mistake this whole directory
keeps finding.

---

## Reproducing this

Nothing here is trustworthy on the strength of the page. The scripts are in
this directory and the configuration that produced each number is stated,
because two of the conclusions above were wrong until someone looked.

### Corpus

LoCoMo is not redistributed here. Fetch `locomo10.json` from the dataset's own
repository and put it in this directory. `locomo10_zh.json` is generated:

```bash
python translate_zh.py          # needs BENCH_* below; writes locomo10_zh.json
```

Translation is safe for this metric — the gold labels are turn ids, so the
ground truth survives it, and everything but the language is held fixed.

## Two findings worth more than the ranking

- **What predicts accuracy is whether an LLM runs at query time.** Not what is
  stored, not how it is retrieved. The systems that run one lead; the seven that
  do not sit between 43.0% and 54.5%, close enough that a ten-point spread
  covers all of them, and that group contains pure lexical, pure dense, hybrid
  and LLM-extraction alike. None of the marketing built around storage form
  shows up in the scores.
- **BM25 scores 2.3% on Chinese** against 60.6% on English. That gap is why the
  CJK handling exists, and most of it is a tokenizer rather than any one
  implementation: a five-line bigram split ahead of a stock BM25 already reaches
  51.3%, with Carryover 7.6 points above that.

### Environment

```bash
export BENCH_BASE_URL=...     # any OpenAI-compatible endpoint
export BENCH_API_KEY=...
export BENCH_MODEL=...        # answering and judging
```

Other systems are not dependencies of this package. Install them where you
like and point at them:

```bash
export BENCH_SYS_PATH=/path/to/mem0-install:/path/to/embeddings-install
```

Versions the numbers above were produced with: mem0 2.0.18, cognee 1.5.0,
MemOS (MemoryOS) 2.0.30, SimpleMem 0.1.0, txtai 9.12.0,
llama-index-retrievers-bm25 0.7.1.

### Runs

Every script here, and what each one answers. The first group needs no model:

```bash
python cost.py                 # build, query, disk, write-then-search
python vs_mem0_retrieval.py    # our lexical search against a dense vector store
python oss_compare.py          # several open-source retrievers, one metric
python memory_recall.py        # our recall against LoCoMo's gold evidence
python bm25_with_cjk.py        # is the CJK code worth its size
python recall_from_saved_runs.py   # recall for systems that were scored end-to-end only
```

The rest call a model, and need `BENCH_BASE_URL` / `BENCH_API_KEY` /
`BENCH_MODEL`:

```bash
python final_qa.py             # end-to-end across every system, LLM-judged
python qa_compare.py           # the same systems scored the way a user would
python incremental.py          # does memory go stale when the facts change
python token_cost.py           # what memory costs per conversation, after caching
python extraction_layer.py     # our extraction, measured the way a graph was
python dense_vs_lexical.py     # what semantic retrieval would actually buy
python rejudge.py A=a.json …   # how much of the spread is the judge
python translate_zh.py         # build the Chinese corpus; writes locomo10_zh.json
```

Two read transcripts of your own rather than a fixed corpus, so they need a
directory to read and produce numbers about whoever wrote it:

```bash
TRANSCRIPTS_DIR=… python question_shapes.py   # how many questions need >1 fact
TRANSCRIPTS_DIR=… SESSIONS_DIR=… python turn_retrieval.py   # would per-turn injection help
```

#### Every variable these read

| | |
|---|---|
| `BENCH_BASE_URL` `BENCH_API_KEY` `BENCH_MODEL` | required by anything that calls a model |
| `BENCH_ALT_BASE_URL` `BENCH_ALT_API_KEY` `BENCH_ALT_MODEL` | a second endpoint, for judging with a different model than the one that answered — the control run that separates model from memory |
| `BENCH_PROVIDER` | mem0's LLM provider key, default `openai`; set it if your endpoint needs a different one |
| `BENCH_SYS_PATH` | `:`-separated paths to other systems' installs, prepended to `sys.path` |
| `BENCH_DATA` | corpus filename, default `locomo10.json`; set to `locomo10_zh.json` for the CJK run |
| `BENCH_SAMPLES` `BENCH_QUESTIONS` `BENCH_TURNS` `BENCH_PER_SAMPLE` | how much of the corpus to use |
| `BENCH_EMBED` `BENCH_EMBED_DIMS` `BENCH_TXTAI_MODEL` `DENSE_MODEL` | embedding models, where a system takes one |
| `BENCH_COGNEE` `COGNEE_NOTES` `MEMOS_NOTES` | paths to runs already done, for the systems that cannot be re-run cheaply |
| `REJUDGE_ROUNDS` | repeats when separating judge noise from system noise |
| `TRANSCRIPTS_DIR` `SESSIONS_DIR` | your own transcripts; no default, and the two scripts that need them stop rather than measure nothing |
| `HOP_SAMPLE` `HOP_DUMP` | sample size and dump path for the question-shape count |

Recall and cost are deterministic and should reproduce exactly. End-to-end is
not: **the same system varies by up to ten points across identical runs**, so
it is reported as a mean over repeats with the range beside it, and differences
smaller than that spread are not differences. Re-judging fixed answers puts the
judge's own share of that at 0.8 to 4.2 points — the rest is the systems
themselves answering differently from the same retrieved text.

### Endpoint quirks that cost more time than any parameter

Each surfaced as a run that completed and produced nothing:

- Some endpoints reject `temperature: 0` outright. One control group read 0.0%
  for three runs before that was noticed.
- One endpoint rejects `response_format: json_schema`, which the graph builders
  require; they were pointed at a different model.
- LiteLLM refuses a model name without a provider prefix — `openai/<model>`, not
  `<model>` — and says so as a provider error rather than a naming one.
- Prepending a `pip install --target` tree to `sys.path` lets it decide
  versions for everything else. A tokenizers conflict silently dropped txtai
  from three consecutive comparisons.
