#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from apply_removals import apply_removals_interactive
from database_loader import load_deck_mapping
from decision_persistence import load_decision_log


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Apply removal decisions from a decision log to the Kanji Dojo database. "
            "Reviews removals one deck at a time and prompts for approval before modifying the database."
        )
    )
    parser.add_argument(
        "decision_log",
        type=Path,
        help="Path to the saved decision log (JSON file from interactive_reviewer.py).",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default="user_data.sqlite",
        help="Path to the Kanji Dojo SQLite database.",
    )
    parser.add_argument(
        "--source-table",
        default="vocab_deck_entry",
        help="Table containing the deck entries.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Save the modified database to this path instead of overwriting the original.",
    )

    args = parser.parse_args()

    if not args.decision_log.exists():
        print(f"Error: Decision log not found: {args.decision_log}", file=sys.stderr)
        raise SystemExit(1)

    if not args.database.exists():
        print(f"Error: Database not found: {args.database}", file=sys.stderr)
        raise SystemExit(1)

    try:
        # Load the decision log
        print(f"Loading decision log from {args.decision_log}...", file=sys.stderr)
        decision_log = load_decision_log(args.decision_log)

        # Load deck name mapping
        print(f"Loading deck information from {args.database}...", file=sys.stderr)
        deck_name_map = load_deck_mapping(args.database, args.source_table)

        # Apply removals interactively
        apply_removals_interactive(
            database_path=args.database,
            decision_log=decision_log,
            deck_name_map=deck_name_map,
            source_table=args.source_table,
            output_path=args.output,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
