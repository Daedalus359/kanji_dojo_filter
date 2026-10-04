#!/usr/bin/env python3

import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

#clipboard stuff
import base64
import os
import subprocess

import filter_lib

from .. import kd_config as cfg
from .. import kd_lib

PROJECT_DIRECTORY = Path(__file__).resolve().parent

#location of kanji dojo user database shared by multiple scripts
DATA_DIRECTORY = cfg.DATA_DIRECTORY

DATABASE = "user_data.sqlite"
JMDICT_DIRECTORY = PROJECT_DIRECTORY / "data" / "JMDict"

SOURCE_TABLE = "vocab_deck_entry"
OUTPUT_TABLE = "vocab_deck_entries_to_exclude"

def main():
    if not DATABASE.exists():
        raise FileNotFoundError(
            f"SQLite database not found: {DATABASE}"
        )

    if not JMDICT_DIRECTORY.exists():
        raise FileNotFoundError(
            f"JMdict directory not found: {JMDICT_DIRECTORY}"
        )

    uk_terms = load_uk_terms()

    print(
        f"\nFound {len(uk_terms):,} unique "
        f"expression/reading pairs tagged uk."
    )

    # i = 0
    # for (expression, reading) in uk_terms:
    #     print(expression, ":", reading, "is a uk JMDict entry")
    #     i += 1
    #     if i > 20:
    #         break

    #input("press enter to continue.")

    connection = sqlite3.connect(DATABASE)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        # Find the source table's column names.
        table_info = connection.execute(
            f"PRAGMA table_info({SOURCE_TABLE})"
        ).fetchall()

        if not table_info:
            raise RuntimeError(
                f"Could not find table {SOURCE_TABLE!r}"
            )

        column_names = [column[1] for column in table_info]

        try:
            kanji_index = column_names.index("kanji_reading")
            kana_index = column_names.index("kana_reading")
        except ValueError as error:
            raise RuntimeError(
                "The source table must contain columns named "
                "'kanji_reading' and 'kana_reading'.\n"
                f"Found columns: {column_names}"
            ) from error

        # Read all vocab_deck_entry rows.
        rows = connection.execute(
            f"SELECT * FROM {SOURCE_TABLE}"
        ).fetchall()

        matching_rows = []

        for row in rows:
            kanji_reading = normalize(row[kanji_index])
            kana_reading = normalize(row[kana_index])

            # Match both the written expression and its reading.
            if (kanji_reading, kana_reading) in uk_terms:
                matching_rows.append(row)

        # Interactively review every matching row before creating the output
        # table.
        print()
        print(
            f"Reviewing {len(matching_rows):,} candidate "
            f"matching row(s)."
        )
        print("Commands: [y] keep, [n] exclude, [a] keep all remaining, [q] quit")
        print()

        reviewed_rows = []

        for position, row in enumerate(matching_rows, start=1):
            row_data = dict(zip(column_names, row))

            print("=" * 70)
            print(f"Candidate {position} of {len(matching_rows)}")
            print(f"id:             {row_data.get('id')}")
            print(f"deck_id:        {row_data.get('deck_id')}")
            print(f"kanji_reading:  {row_data.get('kanji_reading')}")
            print(f"kana_reading:   {row_data.get('kana_reading')}")
            print(f"meaning:        {row_data.get('meaning')}")
            print(f"word_id:        {row_data.get('word_id')}")
            print("=" * 70)

            copy_to_clipboard(row_data.get('kanji_reading'))

            while True:
                try:
                    answer = input(
                        "Keep this entry? [y/n/a/q]: "
                    ).strip().lower()
                except (KeyboardInterrupt, EOFError):
                    print("\nReview cancelled.")
                    connection.close()
                    return

                if answer in {"y", "yes"}:
                    reviewed_rows.append(row)
                    break

                if answer in {"n", "no", ""}:
                    print("Excluded.")
                    break

                if answer in {"a", "all"}:
                    reviewed_rows.extend(matching_rows[position - 1:])
                    print(
                        f"Kept the remaining "
                        f"{len(matching_rows) - position + 1:,} row(s)."
                    )
                    break

                if answer in {"q", "quit"}:
                    print("Review cancelled. No output table was changed.")
                    connection.close()
                    return

                print("Please enter y, n, a, or q.")

            # If the user selected "all", all remaining rows have already
            # been added, so stop asking questions.
            if answer in {"a", "all"}:
                break

        # Use only the rows approved during the interactive review from this
        # point onward.
        matching_rows = reviewed_rows

        print()
        print(
            f"Keeping {len(matching_rows):,} row(s) "
            f"after interactive review."
        )

        #copy_to_clipboard("かなあ")#test
        #input()

        # for row in matching_rows:
        #     print(row)

        # Recreate the output table if the script has been run before.
        connection.execute(
            f"DROP TABLE IF EXISTS {OUTPUT_TABLE}"
        )

        # Create an empty table with the same columns as the source table.
        connection.execute(
            f"""
            CREATE TABLE {OUTPUT_TABLE} AS
            SELECT *
            FROM {SOURCE_TABLE}
            WHERE 0
            """
        )

        quoted_columns = ", ".join(
            f'"{column_name}"'
            for column_name in column_names
        )

        placeholders = ", ".join(
            "?"
            for _ in column_names
        )

        connection.executemany(
            f"""
            INSERT INTO {OUTPUT_TABLE} ({quoted_columns})
            VALUES ({placeholders})
            """,
            matching_rows,
        )

        connection.commit()

        print(
            f"Found {len(matching_rows):,} matching rows in "
            f"{SOURCE_TABLE}."
        )
        print(f"Created table: {OUTPUT_TABLE}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()