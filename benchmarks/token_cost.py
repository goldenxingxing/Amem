"""What memory costs, in the only unit anyone is billed in.

Retrieval quality has been measured to death here. Cost in tokens has not been
measured at all, and it is the number this field advertises on — mem0 claims
90% savings, Memori claims 2.8% context overhead — so a library that does not
know its own is arguing from silence.

The measurement has to be an honest one for two designs that spend tokens in
opposite places:

- **Carryover** pays once, at the start. Behavioural memory arrives in full whether
  or not it is relevant, and the index arrives with it. Nothing is spent per
  turn, and the prefix is stable, so a provider that caches prompt prefixes
  charges for it once.
- **Query-driven memory** pays per turn. Nothing arrives uninvited; each turn
  embeds a query and injects what came back. Cheap on turn one, and paid again
  on turn fifty.

Which is cheaper is therefore a function of conversation length, and quoting
either number without the other is marketing. This reports the crossover.

Counted, not estimated: the endpoint returns `usage`, so every figure here is
what the provider billed. The tokenizer is whatever the model uses, which is
the point — an estimate with tiktoken would be a different number from the one
on the invoice.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from _prereq import require_env

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from carryover import Store, render
from carryover.consolidate import BEHAVIOURAL_BUDGET_CHARS

TURNS = int(os.environ.get("BENCH_TURNS", "40"))
TOP_K = 3

#: A fixed stand-in for the assistant's turn.
#:
#: Letting each run keep the model's actual reply made the three histories
#: diverge for reasons that have nothing to do with memory — one run's longer
#: answers cost more on every later turn, and the query-driven strategy landed
#: *below* the no-memory floor, which is not a thing that can happen. Holding
#: the reply constant leaves the injected memory as the only difference.
FIXED_REPLY = "好的，我按你说的做，稍后汇报结果。"


def _tick(index: int, total: int) -> None:
    """Say where it is. Every call is a network round trip against a growing
    context, so a run of any size takes long enough that silence is
    indistinguishable from a hang — as it was, for nineteen minutes."""
    if (index + 1) % 5 == 0 or index + 1 == total:
        print(f"    {index + 1}/{total}", flush=True)


@dataclass
class Usage:
    """What a provider billed, accumulated over a conversation.

    `cached` is not a detail. Providers charge a fraction for prompt tokens
    that hit a prefix cache, and the two designs here differ in exactly the
    property that decides whether they hit one: a preamble written once is a
    stable prefix every later turn reuses, while a retrieval injected ahead of
    each turn rewrites the prefix and invalidates the cache behind it.

    Counting only `prompt_tokens` charges both at full price and hides the
    difference that matters — it made the preamble look 2.3x more expensive
    than it is.
    """

    prompt: int = 0
    cached: int = 0
    completion: int = 0
    calls: int = 0
    per_turn: list[int] = field(default_factory=list)
    per_turn_fresh: list[int] = field(default_factory=list)

    def add(self, payload: dict) -> None:
        usage = payload.get("usage") or {}
        prompt = usage.get("prompt_tokens", 0)
        details = usage.get("prompt_tokens_details") or {}
        cached = usage.get("cached_tokens") or details.get("cached_tokens") or 0
        self.prompt += prompt
        self.cached += cached
        self.completion += usage.get("completion_tokens", 0)
        self.calls += 1
        self.per_turn.append(prompt)
        self.per_turn_fresh.append(prompt - cached)

    @property
    def fresh(self) -> int:
        """Prompt tokens that were not served from cache — what is charged in full."""
        return self.prompt - self.cached

    @property
    def total(self) -> int:
        return self.prompt + self.completion


class Model:
    def __init__(self, concurrency: int = 4) -> None:
        self._sem = asyncio.Semaphore(concurrency)
        self._url = os.environ["BENCH_BASE_URL"].rstrip("/") + "/chat/completions"
        self._key = os.environ["BENCH_API_KEY"]
        self._model = os.environ["BENCH_MODEL"]

    async def ask(self, client: httpx.AsyncClient, messages: list[dict]) -> dict:
        async with self._sem:
            for attempt in range(3):
                try:
                    r = await client.post(
                        self._url,
                        headers={"Authorization": f"Bearer {self._key}"},
                        json={"model": self._model, "messages": messages},
                    )
                    r.raise_for_status()
                    return r.json()
                except Exception:
                    if attempt == 2:
                        return {}
                    await asyncio.sleep(1.5 * (attempt + 1))
        return {}


def seeded_store(directory: Path) -> Store:
    """A store in the shape real entries take, at the size this table was measured on.

    Entry length decides everything here, so it is stated rather than left to
    be inferred: eleven behavioural entries of roughly 130 characters each, plus
    eighteen lookup entries, rendering to a preamble of about 4,000 characters.
    That preamble is what produced the token figures in benchmarks/README.md —
    quote them against a store of that size, and scale them for a larger one,
    since the preamble is the entire cost being measured.

    It is deliberately not the smallest thing that would run. The first version
    used five short rules totalling 389 characters, and understated the cost by
    an order of magnitude against any store anyone actually accumulates.
    """
    store = Store(directory)
    detail = (
        "背景：该约定在一次评审后确立，此前曾因未遵守导致一次返工；适用范围覆盖所有"
        "对外交付物，内部草稿不受限制；例外情况需在提交说明里写明理由。"
    )
    behavioural = [
        "对外文档不得出现代码函数名与文件名（如 _retry_policy、pipeline_config_v2），"
        "只保留功能化描述；第三方库的公开类名除外。",
        "验证结论必须由我自己重跑确认后才能汇报，不能只转述子代理给出的结果；交付前逐项核实。",
        "日报按 output/reports/daily/SOP.md 写，写前必须执行三个扫描（会话、代码、"
        "交付物），缺一不可；内容聚焦产出而非过程。",
        "后台任务启动后留在对话里轮询，不要直接结束会话；除非用户明确要求。",
        "子代理超时不要设得太紧：过紧的超时会杀掉运行中的子代理并浪费其部分进度。",
    ]
    # Five distinct rules, cycled to eleven entries: repetition is fine because
    # what is being measured is how many characters the preamble costs, not what
    # they say.
    for i in range(11):
        store.add("feedback", f"{behavioural[i % len(behavioural)]}（第 {i + 1} 条）{detail}")
    for i in range(18):
        store.add(
            "project",
            f"采集管线项目事实 {i}：模块与路径约定、参数取值与其来源，"
            f"以及该决定在 2026 年做出时的背景说明。",
            key=f"pipeline/fact-{i}",
        )
    return store


async def run_preloaded(model: Model, client: httpx.AsyncClient, store: Store, turns: list[str]):
    """Carryover: one preamble at the start, nothing per turn."""
    preamble = render(store.entries(), store.recent(), store.pending())
    usage = Usage()
    history = [{"role": "system", "content": preamble}]
    for i, turn in enumerate(turns):
        history.append({"role": "user", "content": turn})
        usage.add(await model.ask(client, history))
        history.append({"role": "assistant", "content": FIXED_REPLY})
        _tick(i, len(turns))
    return usage, len(preamble)


async def run_per_turn(model: Model, client: httpx.AsyncClient, store: Store, turns: list[str]):
    """Query-driven: nothing at the start, a retrieval injected on every turn."""
    entries = {e.id: e.content for e in store.entries()}
    usage = Usage()
    history: list[dict] = []
    for i, turn in enumerate(turns):
        hits = store.search(turn, limit=TOP_K)
        if hits:
            recalled = "\n".join(entries[h.entry_id] for h in hits)
            history.append({"role": "system", "content": f"Relevant memory:\n{recalled}"})
        history.append({"role": "user", "content": turn})
        usage.add(await model.ask(client, history))
        history.append({"role": "assistant", "content": FIXED_REPLY})
        _tick(i, len(turns))
    return usage, 0


async def run_no_memory(model: Model, client: httpx.AsyncClient, store: Store, turns: list[str]):
    """The floor: what the same conversation costs with no memory at all."""
    usage = Usage()
    history: list[dict] = []
    for i, turn in enumerate(turns):
        history.append({"role": "user", "content": turn})
        usage.add(await model.ask(client, history))
        history.append({"role": "assistant", "content": FIXED_REPLY})
        _tick(i, len(turns))
    return usage, 0


def conversation(n: int) -> list[str]:
    """Turns in the shape the question-shape measurement found: mostly instructions."""
    asks = [
        "把 predict_N 的调用顺序理一下，先 reset 再 predict 对吗",
        "跑一下测试",
        "这个分支和 perf_backport 有什么区别",
        "改完提交",
        "日报写一下",
        "本地打包",
        "文档里这段描述改一下",
        "端口冲突了，看看怎么回事",
    ]
    return [asks[i % len(asks)] for i in range(n)]


async def main() -> None:
    require_env("BENCH_BASE_URL", "BENCH_API_KEY", "BENCH_MODEL")
    import tempfile

    store = seeded_store(Path(tempfile.mkdtemp()))
    entries = store.entries()
    behavioural = sum(len(e.render()) + 1 for e in entries if e.is_behavioural)
    print(
        f"记忆库：{len(entries)} 条（行为类 {behavioural} 字符 = 预算的 "
        f"{behavioural / BEHAVIOURAL_BUDGET_CHARS * 100:.0f}%）"
    )
    turns = conversation(TURNS)
    print(f"会话：{len(turns)} 轮\n")

    model = Model()
    strategies = {
        "无记忆（地板）": run_no_memory,
        "Carryover（开场一次性注入）": run_preloaded,
        "查询驱动（每轮检索注入）": run_per_turn,
    }
    results = {}
    async with httpx.AsyncClient(timeout=180) as client:
        for label, runner in strategies.items():
            usage, preamble_chars = await runner(model, client, store, turns)
            results[label] = usage
            extra = f"  开场 {preamble_chars} 字符" if preamble_chars else ""
            print(
                f"  {label}: {usage.calls} 次调用，输入 {usage.prompt:,} tokens{extra}", flush=True
            )

    floor = results["无记忆（地板）"]
    print(f"\n{'策略':<26}{'输入':>11}{'其中缓存':>10}{'实付':>10}{'比地板多':>11}{'每轮均摊':>11}")
    print("-" * 76)
    for label, usage in results.items():
        overhead = usage.fresh - floor.fresh
        print(
            f"{label:<24}{usage.prompt:>11,}{usage.cached:>10,}{usage.fresh:>10,}"
            f"{overhead:>11,}{overhead / max(1, len(turns)):>11.0f}"
        )

    print("\n累计实付（未命中缓存的输入 tokens），按轮次：")
    print(f"{'轮':>4}" + "".join(f"{label.split('（')[0]:>16}" for label in results))
    for i in sorted({0, 4, 9, min(19, len(turns) - 1), len(turns) - 1}):
        if i >= len(turns):
            continue
        row = "".join(f"{sum(u.per_turn_fresh[: i + 1]):>16,}" for u in results.values())
        print(f"{i + 1:>4}{row}")


if __name__ == "__main__":
    asyncio.run(main())
