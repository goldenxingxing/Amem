"""``python -m carryover check <store-dir>``.

A module entry point rather than a console script: this package installs one
importable name and nothing on a PATH, and a host that vendored it should be
able to reach the check without anything having been installed at all.

Printing and the exit code live here rather than in :mod:`carryover.check`, which
returns findings and says nothing. A library that writes to stdout has decided
how its caller reports, and one that can raise SystemExit can end a request it
was only asked a question by.
"""

from __future__ import annotations

import sys
from pathlib import Path

from carryover.check import FAIL, report


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "check":
        args = args[1:]
    directory = args[0] if args else None

    capability, evidence = report(directory)

    print("Can this machine run it")
    for finding in capability:
        print(finding.render())

    if evidence:
        print(f"\nWhat has used the store at {Path(str(directory)).expanduser()}")
        for finding in evidence:
            print(finding.render())
    else:
        print("\nPass a store directory to also check what has been using it:")
        print("    python -m carryover check ~/.myagent/memory")

    return 1 if any(f.status == FAIL for f in capability + evidence) else 0


if __name__ == "__main__":
    sys.exit(main())
