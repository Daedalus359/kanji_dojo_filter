#!/usr/bin/env python3

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator, Tuple

import filter_lib


def iterate_deck_rows(
    connection: sqlite3.Connection, table_name: str
) -> Generator[Tuple[str, str, tuple, list[str]], None, None]:
    """Iterate over all (expression, reading) pairs in a deck table.

    Yields:
        (expression, reading, raw_row, column_names)
    """
    table_info = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    if not table_info:
        raise RuntimeError(f"Could not find table {table_name!r}")

    column_names = [column[1] for column in table_info]
    print(f"Column names in table {table_name}:")
    print(column_names)
    try:
        kanji_index = column_names.index("kanji_reading")
        kana_index = column_names.index("kana_reading")
    except ValueError as exc:
        raise RuntimeError(
            "The source table must contain columns named 'kanji_reading' and 'kana_reading'.\n"
            f"Found columns: {column_names}"
        ) from exc

    rows = connection.execute(f"SELECT * FROM {table_name}").fetchall()
    for row in rows:
        expression = filter_lib.normalize(row[kanji_index])
        reading = filter_lib.normalize(row[kana_index])
        if reading and not expression:
            pass
            # print("Expecting kana-only word:")
            # print(row)
        elif expression and not reading:
            print(f"Expression ({expression}) but no reading ({reading})")
            breakpoint()
            continue
        elif not expression and not reading:
            print(f"No expression ({expression}) and no reading ({reading})")
            breakpoint()
            continue
        yield expression, reading, row, column_names


def load_deck_pairs(
    database_path: str | Path, source_table: str
) -> set[tuple[str, str]]:
    """Load all unique (expression, reading) pairs from a deck table.

    Returns:
        Set of (expression, reading) tuples.
    """
    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {database_path}")

    pair_set = set()
    with sqlite3.connect(database_path) as connection:
        for expression, reading, row, columns in iterate_deck_rows(
            connection, source_table
        ):
            # if expression == "明日":
            #     print(expression, reading, row, columns)
            pair_set.add((expression, reading, row))

    # ashita_ct = 0
    # for err in pair_set:
    #     if err[0] == "明日":
    #         ashita_ct += 1
    #         if ashita_ct > 1:
    #             print("too many ashitas in pair_set!")
    #             #breakpoint()

    return pair_set
