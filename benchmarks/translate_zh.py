"""Translate LoCoMo into Chinese without disturbing what is being measured.

The CJK numbers in the README come from this file's output. Translation is a
fair transformation here for one reason: the gold labels are turn ids, not
text. Translating every turn and every question leaves the mapping from a
question to its evidence turn exactly where it was, so the ground truth
survives intact and the only variable that moved is the writing system.

Two rules the prompt enforces, because breaking either would quietly invalidate
the run rather than fail it:

- Speaker names stay in Latin script. They are how a retriever ties a question
  to its turn, and transliterating them would hand a lexical system a harder
  problem than the English run had.
- Numbers, dates and proper nouns are carried across unchanged. A translated
  date is a changed fact, and several LoCoMo questions turn on exactly those.

Turns are translated in batches and written back into a copy of the original
structure, so the output is a drop-in for BENCH_DATA:

    BENCH_BASE_URL=... BENCH_API_KEY=... BENCH_MODEL=... python translate_zh.py
    BENCH_DATA=locomo10_zh.json python vs_mem0_retrieval.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from _prereq import require_data, require_env

HERE = Path(__file__).parent
SOURCE = HERE / os.environ.get("BENCH_DATA", "locomo10.json")
TARGET = HERE / os.environ.get("BENCH_ZH_OUT", "locomo10_zh.json")
SAMPLES = int(os.environ.get("BENCH_SAMPLES", "2"))
BATCH = int(os.environ.get("BENCH_BATCH", "20"))
CONCURRENCY = int(os.environ.get("BENCH_CONCURRENCY", "6"))

PROMPT = """\
把下面每一行英文翻译成自然的简体中文。

规则：
- 逐行对应，输入几行就输出几行，不要合并、不要拆分、不要加编号。
- 说话人姓名保持拉丁字母原样，不要音译。
- 数字、日期、专有名词原样保留。
- 只输出译文，不要任何解释。

"""


async def _translate(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, lines: list[str]
) -> list[str]:
    """Translate one batch, falling back to the original text on failure.

    Falling back rather than raising: a batch that will not translate should
    cost its own turns' Chinese, not the whole run.
    """
    async with sem:
        for _ in range(3):
            try:
                r = await client.post(
                    os.environ["BENCH_BASE_URL"].rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {os.environ['BENCH_API_KEY']}"},
                    json={
                        "model": os.environ["BENCH_MODEL"],
                        "messages": [{"role": "user", "content": PROMPT + "\n".join(lines)}],
                    },
                )
                out = r.json()["choices"][0]["message"]["content"].strip().splitlines()
                out = [line.strip() for line in out if line.strip()]
                if len(out) == len(lines):
                    return out
            except Exception:
                await asyncio.sleep(1.0)
        return lines


async def main() -> None:
    require_env("BENCH_BASE_URL", "BENCH_API_KEY", "BENCH_MODEL")
    require_data(SOURCE)
    if not SOURCE.is_file():
        raise SystemExit(f"{SOURCE.name} not found — see benchmarks/README.md")

    data = json.loads(SOURCE.read_text(encoding="utf-8"))[:SAMPLES]

    # Collect every translatable string with where it came from, so the
    # structure is rebuilt by assignment rather than reconstructed.
    slots: list[tuple[dict, str]] = []
    for sample in data:
        convo = sample["conversation"]
        for name in [k for k in convo if k.startswith("session_") and "date" not in k]:
            for turn in convo[name]:
                if turn.get("text"):
                    slots.append((turn, "text"))
        for qa in sample.get("qa", []):
            if (qa.get("question") or "").strip():
                slots.append((qa, "question"))
            if isinstance(qa.get("answer"), str) and qa["answer"].strip():
                slots.append((qa, "answer"))

    print(f"{len(slots)} 条待翻译，每批 {BATCH} 条")

    sem = asyncio.Semaphore(CONCURRENCY)
    batches = [slots[i : i + BATCH] for i in range(0, len(slots), BATCH)]
    async with httpx.AsyncClient(timeout=180) as client:
        results = await asyncio.gather(
            *(_translate(client, sem, [obj[key] for obj, key in b]) for b in batches)
        )

    for batch, translated in zip(batches, results, strict=True):
        for (obj, key), text in zip(batch, translated, strict=True):
            obj[key] = text

    TARGET.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"写出 {TARGET.name}")


if __name__ == "__main__":
    asyncio.run(main())
