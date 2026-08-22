[English](DESIGN.md) | [中文](DESIGN.zh-CN.md) · [README](README.md)

# How it works

The mechanisms behind the four claims on the [README](README.md): that memory
arrives without being asked, that Chinese retrieval works, that a duplicate
write does not silently overwrite a different fact, and that a full store says
so before entries stop arriving.

Each section is here rather than on the front page because a reader deciding
whether to use this needs the result, not the derivation. The derivations are
worth keeping — most of them are wrong turns that cost something to find — but
they are reference, not a pitch.

---

## How a memory gets made

```
  conversation ──▶ extraction ──▶ candidate queue ──▶ (someone says yes) ──▶ store
                        │                    │
                    your model         the only way in
```

**Extraction** runs once per session, where a summary is already being made, so
it costs one call rather than per-turn overhead. Three things about the prompt
are worth writing down:

- **The transcript is embedded in it, not appended to it.** With the
  conversation last, the model reads its own final turn as the live one and
  continues it: answering the transcript, or emitting the tool call it was about
  to make. Measured over six real sessions, that produced zero usable proposals.
  Closing the transcript and stating the task after it gives four to five each.
- **Facts carry their date.** "On 2026-05-06 the user moved rate estimation to
  an EWMA", not "rate estimation uses an EWMA". Entries have a `created_at`, but
  that answers a different question: when it was *recorded*, not when it was
  *true*.
- **The common answer is "nothing".** The prompt says so and the model obeys: a
  debugging session produces almost nothing, small talk none, and raising the
  cap from five to twelve barely changes the count.

**A candidate is not a memory.** It sits in a queue, shown as undecided, and
expires if nobody acts. `suggest()` queues; `keep()` commits. Two separate calls,
so the distinction cannot be erased by a flag.

**Direct writes** exist too — `store.add()` — for a fact the user stated
outright. What a model *inferred* goes through the queue.

## How retrieval works

Two mechanisms, and which leads depends on the writing system of the query —
not on which language it is, but on whether that script marks word boundaries.
Scripts that separate words (Latin, Cyrillic, Greek, Arabic, Hebrew, Hangul,
Devanagari) are matched on whole terms; scripts written without spaces (Han,
kana, Thai, Lao, Khmer, Myanmar) are matched on character windows, because
there is nothing else to cut on.

**The index** is SQLite FTS5 with the `trigram` tokenizer. The default
`unicode61` splits on non-alphanumerics, and Chinese has no spaces — a whole
sentence becomes one token and any query for a phrase inside it misses.

**The scan** is a weighted substring match, and it exists because the most
meaningful unit in Chinese is two characters — 邮箱, 配置, 路径 — which is
*below* what a trigram index can hold.

Both are needed and neither is enough:

```
query contains an unspaced script  →  weighted scan leads, index fills the rest
query is spaced                    →  index leads, unchanged
```

Measured on translated LoCoMo: for Chinese the index alone reaches 40.1% at
depth 8 and the weighted scan alone 58.9%; for Latin the index is the better
ranker. **Choosing per query** is what makes the Chinese gain cost the English
path nothing.

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

A substring pass is linear — fine at the tens of entries memory was designed
for, most of a second at twenty thousand. Two things fix that without changing
what matches: **a posting list over entry bigrams**, so document frequency is a
row count and a query never touches entries that cannot match, and
**incremental indexing**, because the index used to be rebuilt on every write.
At twenty thousand entries a Chinese query went from 66 ms to 9.8 ms, and a
write followed by a search from about 756 ms to 50 ms.

Both paths share one ranking function. When they had separate scoring code they
disagreed on 96 of 197 real questions — the same weights summed in a different
order reorder ties, and one of those ties was the correct answer leaving the
top eight.

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
thousand characters exist for all of it — roughly fifty short rules, or fourteen
paragraph-length ones. Past the limit the oldest simply stop arriving, and **a
standing instruction that stops arriving stops being followed**, with nothing to
show it went missing.

Three mechanisms watch for that. All three propose; none acts.

**Supersession** — a newer entry that replaced an older one. Caught three ways,
because entries come in two shapes and revisions usually announce themselves: a
one-line rule restated more precisely shows up in sequence similarity, a
rewritten procedure in shared vocabulary, and "改用 EWMA，不再维护 48 小时窗口"
or "no longer uses a fixed interval" states the relationship outright. The
announcement is the strongest of the three and needs the least shared subject.

Announcing a replacement means negating what it replaces, which is what the
negation guard refuses — so negation is checked with the announcement wording
removed. "改用 … 不再维护 …" pairs; "always run the migration" against "never
run the migration", which announces nothing, still does not.

**Dormancy** — entries whose subject has not come up in months. Note what it
does *not* measure: whether the rule was used. A rule is obeyed by *not* doing
something, so a prohibition honoured for a year leaves the trace of one nobody
remembers, and scoring on use would retire prohibitions first — the entries
least safe to lose and least likely to be missed.

**Pressure** — how much of the budget is spoken for, raised at 75% rather than
at the limit, because a signal that fires on overflow fires after entries have
stopped arriving. Past 80% the advisory stops being something to mention when
convenient: the softer wording was measured doing nothing at all on a real store
that sat at 83% for weeks with the list in every session and the subject never
once raised.

That only works if the answer can be recorded, or the same pair returns forever
and a prompt that ignores an answer teaches people to stop giving one. So there
are two: retire the older entry, or **affirm** it — both still hold. Affirming
settles the question as it stood; an entry written later reopens it.

And affirm is often the right one. A later instruction usually *adds* to an
earlier one, and what it leaves out is still required — on a real store the
third generation of a rule had dropped three requirements the first two carried,
and retiring on the advisory's word would have removed them silently. Where that
holds, merge instead:

```python
store.consolidate(merged_text, replacing=["reports/v1", "reports/v2"])
```

It writes before it retires: interrupted after the write leaves a visible
duplicate, interrupted the other way leaves the requirements gone.

### Staleness is handled by dating, not by merging

The opposite of what the design expected. Measured on twelve sessions where six
facts were revised: dedup fired **zero** times and by design cannot — differing
numbers are a veto, and `5494` against `8721` is exactly that shape. What made
every answer current was that both versions sit in the store and **each carries
its date**.

Which reclassifies consolidation: it is not there to keep the store *correct*,
dating does that. It is there to keep it *affordable*, because every revision
leaves two entries behind.

---
