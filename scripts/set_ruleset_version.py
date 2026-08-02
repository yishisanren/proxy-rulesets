#!/usr/bin/env python3
"""Copy a sing-box source rule-set while changing only its schema version."""

import json
from pathlib import Path
import sys


def set_ruleset_version(input_path: Path, output_path: Path, version: int) -> None:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise ValueError("input must be a sing-box source rule-set with a rules list")

    data["version"] = version
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(f"Usage: {argv[0]} INPUT OUTPUT VERSION", file=sys.stderr)
        return 2

    set_ruleset_version(Path(argv[1]), Path(argv[2]), int(argv[3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
