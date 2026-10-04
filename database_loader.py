#!/usr/bin/env python3

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import filter_lib


def load_deck_mapping(
    database_path: str | Path, source_table: str = "vocab_deck_entry"
) -> dict[int, str]:
    """Load a mapping of deck_id -> deck_name from the database.

    Returns an empty dict if no deck information is available.
    """
    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {database_path}")

    deck_mapping = {}

    try:
        with sqlite3.connect(database_path) as connection:
            # Try to find the deck table
            cursor = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%deck%'"
            )
            tables = cursor.fetchall()
            # Look for a table that has deck_id and name/title columns
            for (table_name,) in tables:
                cursor = connection.execute(f"PRAGMA table_info({table_name})")
                columns = {col[1] for col in cursor.fetchall()}
                if "deck_id" in columns or "id" in columns:
                    if any(name_col in columns for name_col in ["name", "title"]):
                        name_col = (
                            "name"
                            if "name" in columns
                            else "title"
                            if "title" in columns
                            else None
                        )
                        if name_col:
                            try:
                                cursor = connection.execute(
                                    f"SELECT id, {name_col} FROM {table_name}"
                                )
                                for deck_id, deck_name in cursor.fetchall():
                                    deck_mapping[deck_id] = deck_name
                            except sqlite3.OperationalError:
                                pass
    except Exception:
        pass

    return deck_mapping


def load_entries_by_deck(
    database_path: str | Path, source_table: str = "vocab_deck_entry"
) -> dict[int | None, list[dict[str, Any]]]:
    """Load all deck entries grouped by deck_id.

    Returns:
        dict mapping deck_id (or None for unassigned) -> list of entry dicts.
    """
    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {database_path}")

    entries_by_deck: dict[int | None, list[dict[str, Any]]] = {}

    with sqlite3.connect(database_path) as connection:
        table_info = connection.execute(
            f"PRAGMA table_info({source_table})"
        ).fetchall()
        if not table_info:
            raise RuntimeError(f"Could not find table {source_table!r}")

        column_names = [column[1] for column in table_info]

        # Check for required columns
        if "kanji_reading" not in column_names or "kana_reading" not in column_names:
            raise RuntimeError(
                f"Table {source_table} must contain 'kanji_reading' and 'kana_reading' columns"
            )

        # Check for deck_id column
        has_deck_id = "deck_id" in column_names

        rows = connection.execute(f"SELECT * FROM {source_table}").fetchall()

        for row in rows:
            row_dict = dict(zip(column_names, row))

            expression = filter_lib.normalize(row_dict.get("kanji_reading"))
            reading = filter_lib.normalize(row_dict.get("kana_reading"))

            if not expression or not reading:
                continue

            deck_id = row_dict.get("deck_id") if has_deck_id else None

            if deck_id not in entries_by_deck:
                entries_by_deck[deck_id] = []

            entries_by_deck[deck_id].append(
                {
                    "expression": expression,
                    "reading": reading,
                    "deck_id": deck_id,
                    "row": row_dict,
                }
            )

    return entries_by_deck
