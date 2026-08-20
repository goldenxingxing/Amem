**English** | [中文](README.zh-CN.md)

# Amem

Cross-session memory for coding agents. Two text files and the standard
library.

Amem keeps what an agent learns about a user and their projects, carries the
standing parts into every later conversation without being asked, and lets the
rest be searched. It is a library, not a service: no daemon, no vector
database, no embedding model, nothing to install beyond Python.

---

## Why it exists

Most memory libraries are a vector store behind a retrieval call: you ask, it
finds. That answers one shape of question well and leaves two problems
unsolved.

**Some memories are never asked for.** "Never put function names in the
external docs" is followed by *not* doing something. Nobody types a query that
retrieves it, and a system that only answers queries never surfaces it — so
the rule sits in the database, correct and inert, while the agent breaks it.

Measured on 243 real turns from one user's working history: **89% were
instructions** ("fix this", "run the tests", "ship it"), where nothing is
queried at all and the only memory that can help is memory that arrived
uninvited. 8% asked for a single stored fact. 2.5% needed several combined.

**Somebody has to decide what is remembered.** Extraction can notice a fact;
it should not be able to write one. Every other library in this space writes
silently — you find out what it recorded about you afterwards, if you look.

Amem is built around those two answers: memory is split by whether it must be
present or can be looked up, and nothing reaches the store without a person
saying yes.

---

## How it compares

Ten open-source memory systems were surveyed, five measured. Same corpus, same
judge, same content into every one. Configurations and reproduction steps are
in [`benchmarks/README.md`](benchmarks/README.md).

Blank cells are marked with why they are blank:
**✗** the system's design prevents the measurement · **—** not run.

### Where Amem wins outright

| Dimension | **Amem** | Best of the rest | The gap |
|---|---|---|---|
| Install footprint | **nothing beyond the stdlib** | 360 MB dependency tree (mem0) | the others are 0.97–1.4 GB environments |
| Build over 788 turns | **0.0 s** | 0.1 s (BM25, entirely in memory) | Cognee ~20 min, SimpleMem ~2 hours |
| **Write a memory, then search** | **1.7 ms** | the two fastest retrievers **cannot do it** | their index is in memory and must be rebuilt whole |
| Billed tokens over 20 turns | **1,262** | 2,480 (retrieve every turn) | half the cost, widening as the conversation runs |
| Current value after a fact changes | **6/6** | 4/6 (mem0) | mem0 also gave 1 superseded answer and 1 unmarked pair |
| Never-revised rules still present | **3/3** | 1/3 (mem0) | the two it lost went **with no indication** |
| Chinese recall@8 (non-dense) | **58.9%** | 49.3% (mem0 hybrid) | LlamaIndex BM25 scores 2.3% |
| Writes need a person's approval | **yes** | **none of them** | every other system writes silently |
| Store is plain text you can edit | **yes** | **none of them** | the others are vector stores or opaque formats |
| Memory arrives without being asked | **yes** | **none of them** | every other system is query-driven |

The last three rows are design choices rather than scores, but they decide
whether you can **trust it, correct it, and rely on it to govern behaviour**.
No competitor offers any of the three.

### What the alternatives charge you

Every line here was measured, not read off a page of documentation.

| System | What it costs you |
|---|---|
| **mem0** | A 360 MB dependency tree plus an embedding model. 300× slower to build (30.5 s against 0.0 s) and 79× slower to query. **In 2026-04 it dropped UPDATE/DELETE consolidation for single-pass accumulation**, and on six revised facts it answered 1 with the superseded value and put old and new side by side on another without saying which holds; of three never-revised rules it kept 1. |
| **Cognee** | Every query is an LLM call — there is no local index, so no offline use, no predictable latency, no free lookups. ~**20 minutes** to build 788 turns. Its recall looks high (75.4%) because one "result" is a **twenty-turn document**: eight results are 160 turns against everyone else's eight. |
| **SimpleMem** | The best end-to-end quality here (76.3%), paid for with a ~**2-hour** build, an LLM call per query, and the fact that **it returns answers and never the source turns** — you cannot check what it based an answer on, or find the source when it is wrong. |
| **MemOS** | A ~1.2 GB environment and an LLM call per query, for **47.0% end-to-end — below a purely local lexical baseline**. Its recall advantage (69.5%) does not convert into answers. |
| **txtai · LlamaIndex BM25** | These are **retrievers, not memory**: no notion of a fact being superseded, no kinds, no approval, and an in-memory index that must be rebuilt whole on every write. BM25 scores **2.3% on Chinese**. |
| **Graphiti · Zep · Letta · Memori · TencentDB** | Could not be run at all — see "Five that could not be measured" below. |

### Quality

End-to-end accuracy is LLM-judged over 120 questions, reported as a mean with
the spread across identical runs, because **the same system varies by up to ten
points between them**. Recall@8 is deterministic — it asks whether the turn
holding the answer came back — over 302 questions.

| System | End-to-end | runs | spread | Recall@8 EN | Recall@8 ZH |
|---|---|---|---|---|---|
| SimpleMem | **76.3%** | 5 | 73.3–77.5 | ✗ answers, never returns turns | ✗ same |
| Cognee — graph path | **64.3%** | 8 | 63.3–65.8 | ✗ answers, never returns turns | ✗ same |
| *Amem, answered by a stronger model (control)* | *54.5%* | 7 | 52.5–55.8 | — same retrieval as below | — same |
| mem0 — qdrant hybrid | 52.7% | 8 | 49.2–55.8 | **68.5%** | 49.3% |
| **Amem** | 49.4% | 8 | 46.7–53.3 | 64.6% | **58.9%** |
| LlamaIndex BM25 | 48.0% | 8 | 43.3–52.5 | 60.6% | 2.3% |
| MemOS | 47.0% | 2 | 43.3–50.8 | 69.5% ✻ | — English-only run |
| txtai — dense + BM25 | 46.6% | 3 | 43.3–48.3 | 57.6% | 61.9% |
| Cognee — chunk path | 43.0% | 8 | 35.8–45.8 | 75.4% ✻† | — English-only run |
| mem0 — dense, multilingual | — end-to-end not run | — | — | 58.3% | 54.6% |
| BM25 + 5-line CJK tokenizer | — not a system, a baseline | — | — | 60.6% | 51.3% |

**✻** 118-question subset, not comparable with the 302-question rows. On that
same subset Amem scores 61.9% against MemOS's 69.5%.
**†** Not the same budget: one Cognee "result" is a twenty-turn document, so
eight results are 160 turns against everyone else's eight.

On retrieval quality **Amem is mid-field** — the two systems ahead of it both
run an LLM at query time, which is a network round trip per question. **If that
is what you are optimising it is not the library to pick.** The number is here
because a comparison written by an entrant that hides the column it loses is a
comparison whose other columns need not be read.

### Cost

788 turns ingested, 40 queries, one machine.

| System | Build | Query, median | Index on disk | Add one memory, search again | Install |
|---|---|---|---|---|---|
| **Amem** | **0.0 s** | 0.5 ms | 1.0 MB | **1.7 ms** | **0 beyond stdlib** |
| LlamaIndex BM25 | 0.1 s | **0.1 ms** | 0.7 MB | ✗ full rebuild — index is in memory | ~970 MB env |
| txtai | 1.5 s | 8.5 ms | 2.0 MB | ✗ full rebuild — index is in memory | ~970 MB env |
| mem0 (extraction off) | 30.5 s | 39.5 ms | 3.7 MB | — not run; qdrant writes incrementally, so no rebuild is expected | 360 MB tree |
| MemOS | minutes | ✗ every query is an LLM call | ✗ no local index | ✗ no local index | ~1.2 GB env |
| Cognee | ~20 min | ✗ every query is an LLM call | ✗ no local index | ✗ no local index | ~1.0 GB env |
| SimpleMem | ~2 h | ✗ every query is an LLM call | ✗ no local index | ✗ no local index | ~1.4 GB env |

The bottom three build inside an LLM, so their wall-clock is a bill rather than
a benchmark and is not comparable with the top four. Their query latency and
index size are marked ✗ for the same reason: there is no local index to time or
measure, and a millisecond figure for a network round trip would be a figure
about the network.

**Adding one memory and searching again costs 1.7 ms here and a full rebuild in
the two fastest retrievers**, because they hold their index in memory. Memory
is accumulated one entry at a time, so that path runs far more often than any
retrieval. Recorded in the other direction too: BM25 answers a query five times
faster than Amem, and both are far below anything perceptible.

### Token cost per conversation

The metric this field advertises on. Twenty turns, counted from the `usage` the
provider returns, against a floor of the same conversation with no memory.

| Strategy | Prompt tokens | Of which cached | **Paid** | Over floor |
|---|---|---|---|---|
| No memory (floor) | 5,566 | 5,426 | 140 | n/a — this is the floor |
| **Amem — preamble written once** | 45,726 | 44,464 | **1,262** | +1,122 |
| Retrieve and inject per turn | 21,191 | 18,711 | **2,480** | +2,340 |

By nominal tokens the preamble costs 2.2× more. By what is charged it costs
half as much, and the gap widens with the conversation — a preamble is a stable
prefix every later turn reuses, while a retrieval written ahead of each turn
rewrites the prefix and invalidates the cache behind it.

This one is worth every memory author's attention: **a comparison that reports
cost in nominal tokens is reporting the wrong number.**

### Does memory survive its facts changing

Twelve sessions in order, six of nine facts revised partway through, then asked
for the current value. **No other benchmark in this space tests this**, and it
is where mem0 bet the other way in 2026-04, replacing UPDATE/DELETE
consolidation with single-pass accumulation.

| System | Returns current value | Returns superseded | Both, unmarked | Unchanged rules kept |
|---|---|---|---|---|
| **Amem** | **6/6** | 0 | 0 | **3/3** |
| mem0 (`infer=True`) | 4/6 | 1 | 1 | 1/3 |
| txtai · LlamaIndex BM25 | ✗ retrievers, not memory — no notion of a fact being replaced | | | |
| Cognee · MemOS · SimpleMem | — not run | | | |

The last column matters more than the first: **of three never-revised rules,
mem0 kept one**. A standing instruction that stops arriving is a standing
instruction that stops being followed, and **nothing indicates that it went**.

**And Amem does not win this with the mechanism built for it**: deduplication fired
zero times and by design cannot, since differing numbers are a veto and 5494
against 8721 is exactly that shape. What carries it is that every entry states
its date, so both versions sit in the store and a reader can order them.

### Properties no benchmark scores

| | Amem | mem0 | Cognee | MemOS | SimpleMem | txtai · BM25 |
|---|---|---|---|---|---|---|
| Writes need a person's approval | **yes** | no | no | no | no | n/a |
| Store is plain text you can edit | **yes** | no — vector db | no | no | no — lancedb | no |
| Runs with no service or model | **yes** | needs an embedder | needs an LLM | needs an embedder | needs an LLM | needs an embedder |
| Memory arrives without being asked | **yes** | no | no | no | no | no |

**One column is yes on all four rows.** The last one especially is why Amem
exists: every other system here is query-driven — ask and it finds. "Never put function names in the external docs" is not something
anyone asks for, and on 243 real turns **89% were instructions** where nothing
is queried at all. A memory that only works when asked is not working for 89%
of your time.

### Three findings worth more than the ranking

- **What predicts accuracy is whether an LLM runs at query time** — not what is
  stored, not how it is retrieved. The two systems that run one score 64.3% and
  76.3%; the seven that do not score 43.0% to 54.5% and cannot be separated
  inside a ten-point spread, and that group contains pure lexical, pure dense,
  hybrid and LLM-extraction alike. **None of the marketing built around
  storage form shows up in the scores.**
- **Recall does not convert into answers.** Three separate times a system with
  7–11 more points of recall answered no better — Amem over BM25, MemOS over
  Amem, and Amem's own Chinese recall rising 11 points for no change at all. **The
  metric this field reports most does not predict what a user gets.**
- **BM25 scores 2.3% on Chinese** against 60.6% on English, and that gap is why
  the CJK handling here exists — but most of it is a tokenizer, not this code.
  A five-line bigram split ahead of a stock BM25 reaches 51.3%. Amem's
  remaining 7.6 points are real and change no answers.

### Five that could not be measured

Not "worse at memory" — measured against nothing, because something about each
stopped a comparison from running. Each is a cost to whoever adopts it, so they
are listed rather than omitted.

| System | What blocked it |
|---|---|
| **Graphiti** | Its embedded backend does not work. Ten turns through the Kuzu driver produced **2 entities and 0 edges**, and its full-text search errors out because the driver never creates the index it queries. Working as advertised needs Neo4j and a JVM alongside your application. |
| **Zep** | Ships a client, not a library. There is no local mode: `zep-python` and `zep-cloud` are thin wrappers needing a server or a cloud key, so nothing can be evaluated offline. |
| **Letta** | No path to load memory you already have. Memory forms only through live agent turns, so an existing history cannot be imported — no migration onto it, and no cold start from what you already know. |
| **Memori** | Same shape: it captures by intercepting LLM calls, so memory exists only for traffic that flowed through its wrapper. A transcript cannot be handed to it. |
| **TencentDB Agent Memory** | Three Node services and a proxy layer in front of your model's base URL. That is infrastructure, not a dependency, and it was not stood up. |

For Letta and Memori the limitation is about *ingestion*, not answer quality:
bulk-loading a transcript cannot exercise a mechanism that runs during a
conversation, and scoring them that way would repeat — in reverse — the mistake
of scoring a knowledge graph on turn recall. What it does show is a real
constraint on adoption: a memory you cannot load is one you cannot migrate to,
evaluate, or seed.

---

## The split

Every entry has a `kind`, and the kind decides how it reaches a conversation.

| kind | What it holds | How it arrives |
|---|---|---|
| `user` | Who they are, how they work | **Stated in full**, every conversation |
| `feedback` | A correction or standing instruction | **Stated in full**, every conversation |
| `project` | A durable fact about a repo, system or decision | One line in an index; full text on request |
| `reference` | Where something lives that you had to find | One line in an index; full text on request |

The first two are *behavioural*. They change how the agent works and are never
the subject of a question, so they are injected unconditionally and cost
context on every turn whether or not they matter.

The last two are *lookup*. Most are irrelevant to any given conversation, so
carrying all of them everywhere costs more than fetching the occasional right
answer. They appear as a one-line index — enough to know something was
recorded — and the full text is retrieved on demand.

This is the whole architecture. Everything below is what it takes to make each
half work.

---

## How a memory gets made

```
  conversation ──▶ extraction ──▶ candidate queue ──▶ (a person says yes) ──▶ store
                       │                                       │
                   your model                             the only path in
```

**Extraction** runs once per session, where a summary is already being
produced, so it costs one call rather than anything per-turn. It is given the
tail of the conversation and asked for facts that outlive it.

Three things about the prompt matter enough to state:

- **The transcript is embedded, not appended.** With the conversation last, a
  model reads its own final turn as the live one and continues it — answering
  the transcript, or emitting the tool call the transcript was about to make.
  Measured across six real sessions, that produced *zero* usable proposals
  every time. Closing the transcript in tags and stating the task after it
  takes the same sessions to four or five each.
- **Facts carry their date.** "On 2026-05-06 the user moved rate estimation estimation to
  an EWMA" rather than "rate estimation uses an EWMA". Entries have a `created_at`, but
  that answers a different question — when it was *written down*, not when it
  was *true*. Without the date in the sentence, a store cannot answer "when did
  we decide this", and cannot tell a reader which of two versions is current.
- **The common answer is nothing.** The prompt says so, and the model obeys:
  a transcript of pure debugging yields almost nothing, small talk yields
  nothing at all, and raising the cap from five to twelve barely moves the
  count. It is not padding to fill a quota.

**Candidates** are not memories. They sit in a queue, are shown to the agent as
explicitly unapproved, and expire if nobody decides. `suggest()` queues;
`keep()` commits. They are separate calls so the distinction cannot be
collapsed into a flag.

**Direct writes** exist too — `store.add()` — for a fact the user stated
outright. There is nothing to approve when the user just said it. What a model
*inferred* goes through the queue.

---

## What the store looks like

```jsonl
{"id":"4f2a…","kind":"feedback","scope":"persistent","content":"Never force-push to main.","created_at":1767225600.0,"key":"git/force-push"}
{"id":"91c7…","kind":"project","scope":"persistent","content":"On 2026-06-03 the Windows port moved from 5494 to 8721.","created_at":1780531200.0,"key":"win/port"}
```

One JSON object per line, append-mostly. You can `grep` it, `git diff` it, open
it in an editor and fix a typo, and understand what your agent knows about you
by reading it. That is a design commitment, not a storage detail: a memory you
cannot inspect is a memory you cannot correct.

`key` is a short semantic handle — `namespace/slug` — that a model can read,
group by prefix, and mistype visibly. The `id` stays the primary key because it
is written into every stored record; the key is what a model uses to refer to
one. Anything that accepts a handle takes a key, a full id, or an unambiguous
id prefix.

The search index is a **cache**: a SQLite database beside the store, rebuilt
whenever the file changes. Deleting it costs a rebuild and nothing else, which
is exactly what allows the store to stay a file people edit by hand.

---

## How retrieval works

Two mechanisms, and which one leads depends on the script of the query.

**The index** is SQLite FTS5 with a `trigram` tokenizer. The default
`unicode61` splits on non-alphanumerics, and Chinese is written without spaces
— a whole sentence becomes one token and every query for a phrase inside it
misses.

**The scan** is a weighted substring pass over the entries, and it exists
because the most meaningful unit in Chinese is two characters — 邮箱, 配置, 路径
— which is *below* what a trigram index can hold.

Both are needed and neither is enough:

```
query contains CJK  →  weighted scan leads, index fills remaining slots
query is Latin only →  index leads, unchanged
```

Measured on a translated LoCoMo: for Chinese, the index alone reaches 40.1% at
depth 8 and the weighted scan alone 58.9%. For Latin the index is the better
ranker. Choosing per query is what lets the Chinese path improve without
costing the English one anything.

### Why the scan is weighted

Ranking by *how many* needles an entry contains makes a question's grammar
worth as much as its subject. Every two-character window of 邮箱是怎么配置的
is a needle, so 是什 and 什么 count for exactly as much as 邮箱 and 配置, and an
entry containing "什么" outranks the one containing the answer.

English is protected from this by a stopword list. Chinese has none, and
maintaining one per language is a losing game. Instead each needle is weighted
by **inverse document frequency** — how much it narrows things down *in this
store*. Grammar is common here and stops counting; subject matter is rare and
decides the order. No word list, and it adapts to whatever the store is about.

Chinese recall@8 went from 47.7% to 58.9% on that change alone.

### Why it stays fast

A substring pass is linear, which is fine at the tens of entries memory was
designed for and is most of a second at twenty thousand. Two things fix that
without changing what matches:

- **A posting list over entry bigrams.** Document frequency becomes a row
  count and candidates come out of the same lookup, so a query never touches
  entries that cannot match.
- **Incremental indexing.** The index used to be dropped and rebuilt whenever
  the store changed — and the store changes on every write, so adding one
  memory made the next search reindex everything.

At twenty thousand entries: a Chinese query went from 66 ms to 9.8 ms, and a
write followed by a search from about 756 ms to 50 ms.

Both paths share one ranking function. When they had separate scoring code they
disagreed on 96 of 197 real questions — the same weights summed in a different
order reorder ties, and one of those ties was the correct answer leaving the
top eight. A test asserts per query that they agree.

---

## How duplicates are handled on write

Adding a fact that restates a stored one does not create a second entry; it
merges into the existing one and reports what wording it replaced, so a wrong
merge can be undone in the same turn.

Similarity alone is not enough to decide that, so three guards run *in addition
to* the score. Each covers a class where near-identical characters mean a
different fact:

| Guard | What it stops |
|---|---|
| **Length ratio** | A long, detailed entry being replaced by a terse restatement. A merge only ever discards the older text, so losing detail is the harm. |
| **Numeric multiset** | Dates, versions, ports, quotas, ticket ids — the highest-precision facts there are, and the ones where a silent overwrite is hardest to notice. |
| **Negation parity** | Polarity inversion. Parity rather than absence, so two variants of "with no trailing summary" are not blocked by their own "no". |

The case that motivates the second guard: `"Merge freeze begins 2026-03-05"`
against `"…begins on 2026-03-05"` (should merge) and against
`"…begins 2026-04-05"` (must never). **Both score 0.967.** A threshold cannot
tell them apart; comparing the numbers as a multiset can, and comparing them as
a *multiset* rather than positionally means inserting a preposition still
merges.

---

## How the store stays affordable

Behavioural memory is injected whether or not it is relevant, and about eight
thousand characters exist for all of it. That is roughly fifty short rules — or
fourteen paragraph-length ones. Past the limit the oldest simply stop arriving,
and **a standing instruction that stops arriving stops being followed**, with
nothing to show it went missing.

Three mechanisms keep that from happening quietly. All three propose; none
acts.

**Supersession** — a newer entry that replaced an older one. Two signals,
because entries come in two shapes:

- A one-line rule restated more precisely is caught by sequence similarity.
- A multi-step procedure rewritten is not: it keeps its subject and changes its
  wording. That is caught by how much distinctive vocabulary the two share.
- And a revision usually *says so* — "改用 EWMA，不再维护 48 小时窗口", "no
  longer uses a fixed interval". That announcement is stronger evidence than either score,
  and it needs far less shared subject to count.

A wrinkle worth knowing about: announcing a replacement is normally done by
negating what it replaces, which is exactly what the negation guard refuses.
Negation is therefore checked with the announcement wording removed — so "改用
… 不再维护 …" pairs, while "always run the migration" against "never run the
migration", which announces nothing, still does not.

**Dormancy** — entries whose subject has not come up in months. Note what this
does *not* measure: whether the rule was used. A rule is obeyed by *not* doing
something, so a prohibition honoured for a year leaves exactly the trace of one
nobody remembers. Scoring on use would retire prohibitions first — the entries
least safe to lose and the least likely to be missed. Topicality is observable
where compliance is not, and dormant is not wrong: it is the difference between
a rule with work to do and one without.

**Pressure** — how much of the budget is spoken for, raised at 75% rather than
at the limit. A signal that fires when the store overflows fires after entries
have already stopped arriving.

Past 80% the advisory stops being something to mention when convenient. The
softer version was measured doing nothing at all: a real store sat at 83% for
weeks with a concrete list of pairs in every session's opening context — the
handles and the command spelled out — and the subject was never once raised.
"When it fits" never fits, which is this project's own thesis turning up inside
the mechanism meant to act on it.

Raising it more insistently only works if the answer can be recorded, or the
same pair returns next session and the one after, and a prompt that ignores an
answer teaches people to stop giving one. So there are two answers, not one:
retire the older entry, or **affirm** it — meaning both still hold. Affirming
settles the question as it stood rather than granting a permanent exemption: an
entry written later reopens it, because that is a question nobody has asked.

And the answer is often affirm. A later instruction usually *adds* to an
earlier one rather than replacing it, and what it leaves out is still required.
On a real store the newest of three generations of one rule had dropped three
requirements the older two carried — read the README first, take the date from
`date` rather than from context, verify after writing. Retiring on the
advisory's word would have removed all three silently, which is what the entry
being retired was written to prevent. Where that holds, the fix is one merged
entry that keeps every requirement:

```python
store.consolidate(merged_text, replacing=["reports/v1", "reports/v2"])
```

which writes the merged entry before retiring the others — interrupted after
the write leaves a visible duplicate, interrupted the other way round leaves
the requirements gone.

### Staleness is handled by dating, not by merging

Worth stating plainly, because it is the opposite of what the design expected.

Measured on twelve sessions where six facts were revised: dedup fired **zero**
times, and by design cannot fire — differing numbers are a veto, and `5494`
against `8721` is exactly that shape. What made every answer current was that
both versions sit in the store and **each carries its date**, so a reader can
order them.

Which reclassifies consolidation. It is not there to keep the store *correct* —
dating does that. It is there to keep the store *affordable*, because every
revision leaves two entries behind and the ceiling arrives faster the more
often things change.

---

## What it deliberately does not do

Each of these was built or measured and then rejected. The benchmarks are in
`benchmarks/`, including the numbers where Amem loses.

**No embedding model.** A dense retriever was run against this one on the same
store, the same turns and the same judge: it scored 18.1% then 13.7% where the
lexical path scored 14.0% then 15.3%. The ranges overlap completely and the
ordering flipped between runs — the difference is smaller than the judge's own
variance, for 183 MB, a 150× slower build and a 25× slower query.

**No knowledge graph.** The one system that clearly leads on end-to-end
accuracy earns it by synthesising across several facts, and that advantage is
real. But counting the questions actually asked in one user's history, the
share needing two or more stored facts combined is around 1%. A graph is a
large piece of engineering for a question shape that barely occurs.

**No per-turn automatic injection.** Retrieving on every turn and injecting the
top three was measured: roughly **85% of what would be injected does not help**,
and it is paid on every turn. Something relevant exists for 64% of turns, but
retrieval finds it in only a third of those, and no lexical threshold separates
the two — the misses are semantic, and semantics is what the previous paragraph
rules out.

It also costs more than the design it would replace, for a reason that only
shows up on the bill. Writing something new ahead of each turn rewrites the
prompt prefix and invalidates the cache behind it, while a preamble written
once is reused by every later turn. Over twenty turns, retrieving per turn used
half the nominal tokens and paid twice as much — 2,480 against 1,262 — and the
gap widens as a conversation runs on.

**No automatic retirement.** The machinery to detect supersession is here and
deliberately unused for anything but proposals. Retiring a rule that still holds
changes how an agent behaves with nothing to show it happened; leaving a stale
one costs a line of context. The costs are not symmetric, so the decision is
not automatic.

---

## Using it

Python 3.11 or newer. One dependency, which pip will fetch:

```bash
pip install git+https://github.com/goldenxingxing/Amem
```

Not on PyPI yet — the name is reserved but nothing is published while the API
can still move. Pin a commit if you depend on it.

```python
from amem import Store, propose, render

store = Store("~/.myagent/memory")
```

**Opening a conversation** — what the agent is told before anyone speaks. No
query, because the things it most needs to know are the things nobody would
think to ask for:

```python
preamble = render(store.entries(), store.recent(), store.pending())
```

**During** — what it can look up when it half-remembers something:

```python
for hit in store.search("where do daily reports go"):
    print(hit.handle, hit.snippet)

entry = store.get("reports/daily")      # by key, id, or id prefix
```

**Closing** — what it noticed, for a person to decide on. `complete` is your
model; anything matching `async (system, user) -> str` works:

```python
for candidate in await propose(complete, transcript, session_id=session.id):
    store.suggest([candidate])          # queued, not stored

store.keep(candidate_id)                # only after someone said yes
store.dismiss(candidate_id)

store.note_topics(transcript)           # feeds the dormancy ranking
```

**Over time** — the store fills, and entries stop being true:

```python
from amem import find_dormant, find_superseded, pressure

fit, held = pressure(store.entries(), BEHAVIOURAL_BUDGET_CHARS)
find_superseded(store.entries())        # a newer entry that replaced an older
find_dormant(store.entries(), now=...)  # subjects that stopped coming up

store.retire("api/version")             # out of the preamble, still in the file
store.restore("api/version")
```

---

### Which alphabet you write in

Retrieval treats a script by whether it marks word boundaries, not by which
language it is. Scripts that separate words — Latin, Cyrillic, Greek, Arabic,
Hebrew, Hangul, Devanagari — are matched on whole terms; scripts written
without spaces — Han, kana, Thai, Lao, Khmer, Myanmar — are matched on
character windows, because there is nothing else to cut on.

This used to be Han and ASCII, and everything else produced no searchable terms
at all: a query in Korean or Russian returned nothing, silently, with the entry
sitting in the store. Japanese written in kana did the same — the Japanese that
appeared to work was passing on its Han characters.

## What if there is nobody to approve

The approval gate is the one thing here no alternative offers, so it is worth
being exact about what it needs — and it is not a user interface. It needs a
decision by a person, and in an agent the conversation is where that happens:
`render` puts pending proposals in the opening context and the agent raises one
when it is relevant. No UI is involved in that, and none is provided here.

There is deliberately no setting that approves for you. Not because it cannot
be done — it is three lines, and they belong in your code:

```python
for candidate in await propose(complete, transcript):
    store.suggest([candidate])
    store.keep(candidate.id)          # unattended: no one is going to be asked
```

The difference is not capability, it is where the decision is recorded. Written
out like that it is a line a reviewer can see, argue with, and delete. As a
default it would be the behaviour of everyone who never looked, and the one
column this project can claim over every alternative would quietly read the
same as theirs.

Nothing accumulates if nobody decides: proposals cap at twelve and expire after
a fortnight. A queue nobody clears is noise in every future session, and a
proposal nobody acted on for two weeks was not worth acting on.

### Naming what the agent can call

The preamble tells an agent how to act on what it describes, so the wording has
to name something that exists in your host:

```python
render(entries, recent, pending, actions=Actions(
    search='`Memory({"op": "search", "query": "<query>"})`',
    promote='`Memory({"op": "promote", "id": "<id>"})`',
    ...
))
```

The defaults name this library's own methods, which is right when you drive the
store directly and visibly approximate when you have a tool layer. That is the
better of the two failures: this used to name one particular application's
tool, which read as authoritative and was wrong everywhere else.

## Design commitments

Constraints, not preferences. Each is something Amem will give up performance
for.

| | |
|---|---|
| **No dependency beyond the standard library** | `sqlite3` ships with Python. Retrieval adds nothing else; pydantic is the one import, for validation at the file boundary. |
| **The store is a text file** | Greppable, diffable, editable, versionable. The index is a cache that rebuilds. |
| **Nothing is written without approval** | Extraction produces candidates. Candidates are proposals. |
| **Nothing is destroyed** | Superseded entries are retired: out of the injected set, still in the file, still searchable, restorable. |
| **The model is yours** | Amem never imports an LLM client. A test asserts it. |

## Status

Early. The core runs in production inside one application and is being
extracted into this package. The benchmarks it is measured by live in
`benchmarks/` — including the comparisons where it comes mid-field, and the
conclusions that were published here and later retracted.
