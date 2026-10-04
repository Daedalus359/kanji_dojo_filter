#!/usr/bin/env python3

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

from removal_decision import RemovalDecisionLog


def backup_database(database_path: str | Path) -> Path:
    """Create a timestamped backup of the original database.

    Returns:
        Path to the backup file.
    """
    from datetime import datetime

    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = database_path.parent / (
        f"{database_path.stem}_backup_{timestamp}{database_path.suffix}"
    )

    shutil.copy2(database_path, backup_path)
    print(f"Backup created: {backup_path}")

    return backup_path


def filter_removal_decisions_by_decks(
    decision_log: RemovalDecisionLog,
    approved_deck_ids: set[int | None],
) -> RemovalDecisionLog:
    """Return a filtered decision log containing only remove decisions for approved decks."""
    filtered = RemovalDecisionLog(
        frequency_threshold=decision_log.frequency_threshold,
        jmdict_directory=decision_log.jmdict_directory,
        frequency_data_path=decision_log.frequency_data_path,
    )
    filtered.decisions = [
        decision
        for decision in decision_log.decisions
        if decision.decision == "remove" and decision.deck_id in approved_deck_ids
    ]
    filtered.completed_decks = set(approved_deck_ids)
    return filtered


def apply_removals_to_database(
    database_path: str | Path,
    decision_log: RemovalDecisionLog,
    source_table: str = "vocab_deck_entry",
    dry_run: bool = False,
    approved_deck_ids: set[int | None] | None = None,
) -> dict[str, int]:
    """Apply removal decisions to the database.

    Safe behavior:
    - deletion is always scoped by deck_id when the table has a deck_id column
    - original data is not overwritten unless the caller explicitly writes to the original file
    - the caller may pass approved_deck_ids to restrict application to approved decks only
    """
    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    decisions = list(decision_log.decisions)
    if approved_deck_ids is not None:
        decisions = [
            decision
            for decision in decisions
            if decision.decision == "remove" and decision.deck_id in approved_deck_ids
        ]
    else:
        decisions = [
            decision for decision in decisions if decision.decision == "remove"
        ]

    if not decisions:
        print("No approved removal decisions found in the log.")
        return {"removed_count": 0, "kept_count": 0, "errors": 0}

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")

        table_info = connection.execute(f"PRAGMA table_info({source_table})").fetchall()
        if not table_info:
            raise RuntimeError(f"Could not find table {source_table!r}")

        column_names = [column[1] for column in table_info]
        has_deck_id = "deck_id" in column_names

        if "kanji_reading" not in column_names or "kana_reading" not in column_names:
            raise RuntimeError(
                f"Table {source_table} must contain 'kanji_reading' and 'kana_reading' columns"
            )

        stats = {"removed_count": 0, "kept_count": 0, "errors": 0}

        for decision in decisions:
            expression = decision.expression
            reading = decision.reading
            deck_id = decision.deck_id

            if dry_run:
                print(f"  [DRY RUN] Would remove: {expression} [{reading}] from deck={deck_id}")
                stats["removed_count"] += 1
                continue

            try:
                if has_deck_id:
                    if deck_id is None:
                        cursor = connection.execute(
                            f"DELETE FROM {source_table} WHERE deck_id IS NULL AND kanji_reading = ? AND kana_reading = ?",
                            (expression, reading),
                        )
                    else:
                        cursor = connection.execute(
                            f"DELETE FROM {source_table} WHERE deck_id = ? AND kanji_reading = ? AND kana_reading = ?",
                            (deck_id, expression, reading),
                        )
                else:
                    cursor = connection.execute(
                        f"DELETE FROM {source_table} WHERE kanji_reading = ? AND kana_reading = ?",
                        (expression, reading),
                    )

                deleted_rows = cursor.rowcount
                if deleted_rows > 0:
                    print(f"  Removed: {expression} [{reading}] from deck={deck_id}")
                    stats["removed_count"] += deleted_rows
                else:
                    print(f"  Not found: {expression} [{reading}] in deck={deck_id}")
                    stats["errors"] += 1
            except sqlite3.Error as exc:
                print(f"  ERROR removing {expression} [{reading}] from deck={deck_id}: {exc}")
                stats["errors"] += 1

        if not dry_run:
            connection.commit()
            print("\nChanges committed to database.")

    return stats


def get_removal_stats_by_deck(
    decision_log: RemovalDecisionLog,
    deck_name_map: dict[int, str] | None = None,
) -> dict[int | None, dict[str, Any]]:
    """Get statistics about planned removals grouped by deck."""
    if deck_name_map is None:
        deck_name_map = {}

    stats_by_deck: dict[int | None, dict[str, Any]] = {}

    for decision in decision_log.decisions:
        if decision.decision != "remove":
            continue

        deck_id = decision.deck_id
        if deck_id not in stats_by_deck:
            stats_by_deck[deck_id] = {
                "count": 0,
                "deck_name": (
                    deck_name_map.get(deck_id, f"Deck {deck_id}" if deck_id is not None else "unassigned")
                ),
                "entries": [],
            }

        stats_by_deck[deck_id]["count"] += 1
        stats_by_deck[deck_id]["entries"].append(
            {"expression": decision.expression, "reading": decision.reading, "score": decision.score}
        )

    return stats_by_deck


def prompt_approval_for_deck(
    deck_id: int | None,
    deck_name: str,
    entries: list[dict[str, Any]],
) -> bool:
    """Prompt the user to approve removals for a single deck."""
    print(f"\n{'=' * 80}")
    print(f"Deck: {deck_name} (id={deck_id})")
    print(f"{'=' * 80}")
    print(f"Will remove {len(entries)} entries:\n")

    for entry in sorted(entries, key=lambda e: (-e["score"], e["expression"], e["reading"])):
        print(f"  - {entry['expression']:15} [{entry['reading']:15}] score={entry['score']:.3f}")

    print()
    while True:
        try:
            answer = input("Approve these removals? [y]es, [n]o, [q]uit: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return False

        if answer in {"y", "yes"}:
            return True
        elif answer in {"n", "no"}:
            return False
        elif answer in {"q", "quit"}:
            raise KeyboardInterrupt("User quit during approval")
        else:
            print("Please enter y, n, or q.")


def apply_removals_interactive(
    database_path: str | Path,
    decision_log: RemovalDecisionLog,
    deck_name_map: dict[int, str] | None = None,
    source_table: str = "vocab_deck_entry",
    output_path: str | Path | None = None,
) -> None:
    """Interactively review and apply removals deck by deck.

    Safety: if output_path is omitted, a new file will be created instead of modifying the original database.
    """
    if deck_name_map is None:
        deck_name_map = {}

    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    removal_stats = get_removal_stats_by_deck(decision_log, deck_name_map)
    if not removal_stats:
        print("No removal decisions found.")
        return

    total_removals = sum(stats["count"] for stats in removal_stats.values())
    print(f"\nReview Summary: {total_removals} total removals across {len(removal_stats)} deck(s)")
    print()

    sorted_deck_ids = sorted(removal_stats.keys(), key=lambda d: (d is None, d or -1))

    approved_deck_ids: set[int | None] = set()

    for deck_id in sorted_deck_ids:
        stats = removal_stats[deck_id]
        try:
            approved = prompt_approval_for_deck(deck_id, stats["deck_name"], stats["entries"])
            if approved:
                approved_deck_ids.add(deck_id)
                print(f"Approved removals for {stats['deck_name']}")
            else:
                print(f"Skipped removals for {stats['deck_name']}")
        except KeyboardInterrupt:
            print("\nApproval process cancelled by user.")
            return

    if not approved_deck_ids:
        print("\nNo decks approved for removal. No database changes will be applied.")
        return

    if output_path is None:
        output_path = database_path.with_name(
            f"{database_path.stem}_approved_removals{database_path.suffix}"
        )
    else:
        output_path = Path(output_path)

    if output_path.resolve() == database_path.resolve():
        raise ValueError(
            "Refusing to overwrite the original database. Use a different --output path or omit --output to write to a new file."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(database_path, output_path)

    backup_path = backup_database(database_path)
    print(f"\nApplying approved removals to: {output_path}")

    filtered_log = filter_removal_decisions_by_decks(decision_log, approved_deck_ids)
    stats = apply_removals_to_database(
        output_path,
        filtered_log,
        source_table=source_table,
        dry_run=False,
    )

    print(f"\nRemoval Statistics:")
    print(f"  Removed: {stats['removed_count']}")
    print(f"  Errors: {stats['errors']}")
    print(f"\nOriginal database: {database_path}")
    print(f"Backup created at: {backup_path}")
    print(f"Modified database: {output_path}")
    print("The original database was not modified.")


__all__ = [
    "backup_database",
    "filter_removal_decisions_by_decks",
    "apply_removals_to_database",
    "get_removal_stats_by_deck",
    "prompt_approval_for_deck",
    "apply_removals_interactive",
]
