#!/usr/bin/env python3

from __future__ import annotations

import shutil
import sqlite3
import sys
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
    backup_path = database_path.parent / f"{database_path.stem}_backup_{timestamp}{database_path.suffix}"

    shutil.copy2(database_path, backup_path)
    print(f"Backup created: {backup_path}")

    return backup_path


def apply_removals_to_database(
    database_path: str | Path,
    decision_log: RemovalDecisionLog,
    source_table: str = "vocab_deck_entry",
    dry_run: bool = False,
) -> dict[str, int]:
    """Apply removal decisions to the database.

    Args:
        database_path: Path to the SQLite database.
        decision_log: Loaded RemovalDecisionLog with user decisions.
        source_table: Name of the table containing vocab entries.
        dry_run: If True, don't actually modify the database.

    Returns:
        dict with statistics about removals (removed_count, kept_count, etc.)
    """
    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    # Collect removal decisions by deck
    removals_by_deck: dict[int | None, list[dict[str, Any]]] = {}
    for decision in decision_log.decisions:
        if decision.decision == "remove":
            if decision.deck_id not in removals_by_deck:
                removals_by_deck[decision.deck_id] = []
            removals_by_deck[decision.deck_id].append(
                {
                    "expression": decision.expression,
                    "reading": decision.reading,
                    "deck_id": decision.deck_id,
                }
            )

    stats = {"removed_count": 0, "kept_count": 0, "errors": 0}

    if not removals_by_deck:
        print("No removal decisions found in the log.")
        return stats

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")

        # Get table schema
        table_info = connection.execute(f"PRAGMA table_info({source_table})").fetchall()
        if not table_info:
            raise RuntimeError(f"Could not find table {source_table!r}")

        column_names = [column[1] for column in table_info]
        if "kanji_reading" not in column_names or "kana_reading" not in column_names:
            raise RuntimeError(
                f"Table {source_table} must contain 'kanji_reading' and 'kana_reading' columns"
            )

        for deck_id, removals in removals_by_deck.items():
            print(f"\nProcessing removals for deck_id={deck_id}...")
            print(f"  {len(removals)} entries to remove")

            for removal in removals:
                expression = removal["expression"]
                reading = removal["reading"]

                if dry_run:
                    print(f"  [DRY RUN] Would remove: {expression} [{reading}]")
                    stats["removed_count"] += 1
                else:
                    try:
                        cursor = connection.execute(
                            f"SELECT COUNT(*) FROM {source_table} WHERE kanji_reading = ? AND kana_reading = ?",
                            (expression, reading),
                        )
                        count = cursor.fetchone()[0]

                        if count > 0:
                            connection.execute(
                                f"DELETE FROM {source_table} WHERE kanji_reading = ? AND kana_reading = ?",
                                (expression, reading),
                            )
                            print(f"  Removed: {expression} [{reading}]")
                            stats["removed_count"] += 1
                        else:
                            print(f"  Not found: {expression} [{reading}]")
                            stats["errors"] += 1
                    except sqlite3.Error as e:
                        print(f"  ERROR removing {expression} [{reading}]: {e}")
                        stats["errors"] += 1

        if not dry_run:
            connection.commit()
            print("\nChanges committed to database.")

    return stats


def get_removal_stats_by_deck(
    database_path: str | Path,
    decision_log: RemovalDecisionLog,
    deck_name_map: dict[int, str] | None = None,
) -> dict[int | None, dict[str, Any]]:
    """Get statistics about planned removals grouped by deck.

    Returns:
        dict mapping deck_id -> {"count": int, "entries": list[dict]}
    """
    if deck_name_map is None:
        deck_name_map = {}

    stats_by_deck: dict[int | None, dict[str, Any]] = {}

    for decision in decision_log.decisions:
        if decision.decision == "remove":
            deck_id = decision.deck_id
            if deck_id not in stats_by_deck:
                stats_by_deck[deck_id] = {
                    "count": 0,
                    "deck_name": deck_name_map.get(deck_id, f"Deck {deck_id}" if deck_id is not None else "unassigned"),
                    "entries": [],
                }

            stats_by_deck[deck_id]["count"] += 1
            stats_by_deck[deck_id]["entries"].append(
                {
                    "expression": decision.expression,
                    "reading": decision.reading,
                    "score": decision.score,
                }
            )

    return stats_by_deck


def prompt_approval_for_deck(
    deck_id: int | None,
    deck_name: str,
    entries: list[dict[str, Any]],
) -> bool:
    """Prompt the user to approve removals for a single deck.

    Returns:
        True if the user approves, False otherwise.
    """
    print(f"\n{'='*80}")
    print(f"Deck: {deck_name} (id={deck_id})")
    print(f"{'='*80}")
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

    Args:
        database_path: Path to the original SQLite database.
        decision_log: Loaded RemovalDecisionLog.
        deck_name_map: Optional mapping of deck_id -> deck_name.
        source_table: Name of the table containing vocab entries.
        output_path: If provided, save the modified database here instead of overwriting.
    """
    if deck_name_map is None:
        deck_name_map = {}

    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    # Get statistics
    removal_stats = get_removal_stats_by_deck(database_path, decision_log, deck_name_map)

    if not removal_stats:
        print("No removal decisions found.")
        return

    total_removals = sum(s["count"] for s in removal_stats.values())
    print(f"\nReview Summary: {total_removals} total removals across {len(removal_stats)} deck(s)")
    print()

    # Sort decks for consistent ordering
    sorted_deck_ids = sorted(
        removal_stats.keys(), key=lambda d: (d is None, d or -1)
    )

    approved_count = 0
    rejected_count = 0

    for deck_id in sorted_deck_ids:
        stats = removal_stats[deck_id]
        try:
            approved = prompt_approval_for_deck(
                deck_id, stats["deck_name"], stats["entries"]
            )
            if approved:
                approved_count += 1
            else:
                rejected_count += 1
                print(f"Skipped removals for {stats['deck_name']}")
        except KeyboardInterrupt:
            print("\n\nApproval process cancelled by user.")
            return

    if approved_count == 0:
        print("\nNo decks approved for removal. Exiting.")
        return

    print(f"\n{approved_count} deck(s) approved, {rejected_count} skipped.")

    # Create backup
    print("\nCreating backup...")
    backup_path = backup_database(database_path)

    # Determine output path
    if output_path is None:
        output_path = database_path
    else:
        output_path = Path(output_path)
        # Copy the original to the output location first
        shutil.copy2(database_path, output_path)

    print(f"\nApplying removals to: {output_path}")

    # Apply removals
    stats = apply_removals_to_database(
        output_path, decision_log, source_table=source_table, dry_run=False
    )

    print(f"\nRemoval Statistics:")
    print(f"  Removed: {stats['removed_count']}")
    print(f"  Errors: {stats['errors']}")
    print(f"\nOriginal database: {database_path}")
    print(f"Backup created at: {backup_path}")
    print(f"Modified database: {output_path}")
