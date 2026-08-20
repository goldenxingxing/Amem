"""Say what is missing, rather than raising where it is noticed.

Every script here needs some combination of a corpus that is not redistributed,
an endpoint that is nobody else's to hand out, and transcripts that belong to
whoever is running it. Missing any of them used to surface as a bare traceback
— ``KeyError: 'BENCH_BASE_URL'``, or a FileNotFoundError naming a temp path —
which tells someone that something is wrong and not what to do about it.

Errors are ``SystemExit`` so the message is the whole output: a traceback for a
prerequisite is noise, and a stack pointing into a benchmark suggests a bug in
it rather than a step not yet taken.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

README = "see benchmarks/README.md"


def require_data(path: Path) -> Path:
    """The corpus file, or a message saying where to get it.

    LoCoMo is not redistributed here — it has its own licence and its own home
    — so its absence is the normal state of a fresh clone, not a fault.
    """
    if not path.is_file():
        raise SystemExit(
            f"{path.name} not found in {path.parent}.\n"
            f"Fetch it from the dataset's own repository, or set BENCH_DATA to a copy — {README}"
        )
    return path


def require_env(*names: str) -> list[str]:
    """The values of *names*, or one message listing every one that is unset.

    All of them at once: finding out about the second variable only after
    exporting the first is three round trips for what is one piece of
    information.
    """
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(
            "set " + ", ".join(missing) + f" before running this — {README}\n"
            "Any OpenAI-compatible endpoint will do; nothing here is tied to a vendor."
        )
    return [os.environ[n] for n in names]


def require_args(count: int, usage: str) -> list[str]:
    """Positional arguments, or the usage line.

    A few scripts read files produced by earlier runs rather than a corpus.
    Without this they fail with an IndexError inside main, which reads as a bug
    in the benchmark rather than a missing argument.
    """
    args = sys.argv[1:]
    if len(args) < count:
        raise SystemExit(f"usage: python {Path(sys.argv[0]).name} {usage}")
    return args
