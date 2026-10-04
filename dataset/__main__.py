"""Karmi dataset CLI — one entry point for the tooling.

::

    python -m dataset deidentify fixtures/photos/front_walls_stage.jpg
    python -m dataset export --example
    python -m dataset consent --withdraw karmi-example-0003
    python -m dataset build-examples

Each command also works as its own module (``python -m dataset.deidentify``,
``python -m dataset.export``, ``python -m dataset.consent``).
"""

from __future__ import annotations

import sys
from importlib import import_module
from typing import Sequence

SUBCOMMANDS: dict[str, tuple[str, str]] = {
    "deidentify": ("dataset.deidentify", "de-identify a drawing/photo, or scan a record"),
    "export": ("dataset.export", "export records: JSONL + a Hugging Face folder"),
    "consent": ("dataset.consent", "consent state; withdraw a record"),
    "build-examples": ("dataset.example.build_examples", "rebuild the synthetic example records"),
}

USAGE = """Karmi dataset tooling — commands:

  python -m dataset deidentify <path>            de-identify a drawing or photo
      options: --out PATH, --kind photo|drawing, --json,
               --scan-record RECORD.json [--strict], --include-matches
  python -m dataset export --example             JSONL + HF folder from dataset/example/
  python -m dataset export --records PATH        ... from a record file or directory
  python -m dataset consent --withdraw RECORD_ID withdraw consent; writes a redaction instruction
      options: --records-dir DIR, --reason TEXT, --requested-by ROLE, --list, --json
  python -m dataset build-examples               rebuild dataset/example/ from the repo fixtures

The dataset currently contains no real records — only synthetic examples built
from the repository's own fixtures (see dataset/example/README.md).
"""


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0 if args else 2

    cmd = args[0]
    if cmd not in SUBCOMMANDS:
        print(f"error: unknown command {cmd!r}\n", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    module_name, _desc = SUBCOMMANDS[cmd]
    module = import_module(module_name)

    if cmd == "build-examples":
        module.build_examples()
        return 0
    return module.main(args[1:])


if __name__ == "__main__":
    raise SystemExit(main())