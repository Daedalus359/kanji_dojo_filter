#!/usr/bin/env python3

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import filter_lib
from deck_reader import load_deck_pairs
from quality_scorer import (
    DEFAULT_FREQUENCY_THRESHOLD,
    ScoringResult,
    ScoringWeights,
    #compute_score,
)

@dataclass(frozen=True, slots=True)
class ExpressionInfo:
    expression: str
    reading: str
    jpdb_rank: Optional[int]
    has_jmdict_match: bool
    has_uk_tag: bool
    forms_high_priority: bool
    is_ambiguous_expression: bool
    is_ambiguous_reading: bool


JPDBIndex = dict[tuple[str, str], int]


def build_jpdb_frequency_index(
    freq_data: list[list[Any]],
) -> JPDBIndex:
    """Map (expression, reading) to its lowest JPDBv2 rank."""
    index: JPDBIndex = {}

    for entry in freq_data:
        if not isinstance(entry, list) or len(entry) < 3:
            continue

        expression = entry[0]
        metadata = entry[2]

        if not isinstance(expression, str) or not isinstance(metadata, dict):
            continue

        reading = metadata.get("reading")
        frequency = metadata.get("frequency")

        if not isinstance(reading, str) or not isinstance(frequency, dict):
            continue

        value = frequency.get("value")

        if isinstance(value, int):
            rank = value
        elif isinstance(value, str):
            try:
                rank = int(value)
            except ValueError:
                continue
        else:
            continue

        key = (expression, reading)
        previous = index.get(key)

        if previous is None or rank < previous:
            index[key] = rank

    return index


def extract_jpdb_frequency_rank(
    index: JPDBIndex,
    expression: str,
    reading: str,
) -> int | None:
    return index.get((expression, reading))


def find_ambiguous_pairs(
    pairs: set[tuple[str, str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return mappings where one element maps to multiple of the other."""
    expression_to_readings: defaultdict[str, set[str]] = defaultdict(set)
    reading_to_expressions: defaultdict[str, set[str]] = defaultdict(set)

    for expression, reading in pairs:
        expression_to_readings[expression].add(reading)
        reading_to_expressions[reading].add(expression)

    expressions_with_multiple_readings = {
        expression: sorted(readings)
        for expression, readings in expression_to_readings.items()
        if len(readings) > 1
    }

    readings_with_multiple_expressions = {
        reading: sorted(expressions)
        for reading, expressions in reading_to_expressions.items()
        if len(expressions) > 1
    }

    return expressions_with_multiple_readings, readings_with_multiple_expressions


def _not_beaten_in_forms_table(
    record: list[Any], expression: str, reading: str
) -> bool:
    """Check if the forms table marks the (expression, reading) pair with a star."""
    if len(record) <= 5 or record[2] != "forms":
        #in this case, there is no forms table
        return True

    forms_table = _parse_structured_forms_table(record[5])
    if forms_table is None:
        return False

    columns = forms_table["columns"]
    rows = forms_table["rows"]

    if expression not in columns:
        return False

    expr_index = columns.index(expression)
    reading_index = columns.index("reading") if "reading" in columns else None

    if reading_index is None:
        return False

    for row in rows:
        if len(row) <= max(reading_index, expr_index):
            continue
        if row[reading_index] == reading and row[expr_index] == "\u2605":
            return True

    return False


def _parse_structured_forms_table(value: Any):
    """Parse a JMdict structured-content table into a simple dict-like structure."""
    if not (
        isinstance(value, list)
        and len(value) == 1
        and isinstance(value[0], dict)
        and value[0].get("type") == "structured-content"
    ):
        return None

    outer_content = value[0].get("content")
    if not isinstance(outer_content, dict):
        return None

    rows = outer_content.get("content")
    if not isinstance(rows, list) or not rows:
        return None

    parsed_rows = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        cells = row.get("content")
        if not isinstance(cells, list):
            return None
        parsed_rows.append([cell.get("content", "") for cell in cells])

    if len(parsed_rows) < 2:
        return None

    column_names = parsed_rows[0]
    column_names = ["reading" if name == "" else name for name in column_names]

    if not all(isinstance(name, str) for name in column_names):
        return None

    if any(len(row) != len(column_names) for row in parsed_rows[1:]):
        return None

    frame = {"columns": column_names, "rows": parsed_rows[1:]}
    return frame


def evaluate_deck(
    database_path: str | Path,
    source_table: str,
    jmdict_directory: str | Path,
    frequency_data_path: str | Path,
    weights: ScoringWeights | None = None,
    threshold: int = DEFAULT_FREQUENCY_THRESHOLD,
) -> list[ScoringResult]:
    """Analyze all entries in a Kanji Dojo deck.

    Returns:
        List of ScoringResult objects, sorted by total_score (descending).
    """
    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {database_path}")

    jmdict_directory = Path(jmdict_directory)
    if not jmdict_directory.exists():
        raise FileNotFoundError(f"JMdict directory not found: {jmdict_directory}")

    frequency_data_path = Path(frequency_data_path)
    if not frequency_data_path.exists():
        raise FileNotFoundError(f"Frequency dataset not found: {frequency_data_path}")

    print("Loading JMdict term records...", file=sys.stderr)
    term_records = filter_lib.load_term_records(jmdict_directory)

    print("Loading JPDBv2 frequency data...", file=sys.stderr)
    freq_data = filter_lib.load_frequency_data(frequency_data_path)

    print("Loading deck pairs...", file=sys.stderr)
    pair_set = load_deck_pairs(database_path, source_table)

    print(f"Found {len(pair_set)} unique (expression, reading) pairs.", file=sys.stderr)

    # Build ambiguity maps
    expr_to_readings, reading_to_expressions = find_ambiguous_pairs(pair_set)

    results: list[ScoringResult] = []

    normalized_term_records = [
        {
            **item,
            "record": [
                filter_lib.normalize(item["record"][0]),
                filter_lib.normalize(item["record"][1]),
                *item["record"][2:],
            ],
        }
        for item in term_records
    ]

    # Build this once instead of scanning 500k records for every pair.
    jmdict_exact_index = defaultdict(list)


    for item in normalized_term_records:
        record = item["record"]

        if len(record) < 2:
            continue

        key = (record[0], record[1])
        jmdict_exact_index[key].append(item)

    jpdb_index = build_jpdb_frequency_index(freq_data)

    sorted_pairs = sorted(pair_set)

    print("Evaluating entries...", file=sys.stderr)
    loop_len = len(sorted_pairs)
    for (i, (expression, reading)) in enumerate(sorted_pairs):
        if i % 250 == 0:
            print(i, "of", loop_len)
        jpdb_rank = extract_jpdb_frequency_rank(
            jpdb_index, 
            expression, 
            reading,
            )
        #jpdb_rank = extract_jpdb_frequency_rank(freq_data, expression, reading)

        # # Check JMdict match
        # matches = filter_lib.find_term_records(
        #     term_records, expression, reading, partial=False
        # )
        # has_jmdict_match = bool(matches)

        key = (
            filter_lib.normalize(expression),
            filter_lib.normalize(reading),
        )

        matches = jmdict_exact_index.get(key, ())
        has_jmdict_match = bool(matches)

        # Remove low-priority (archaic) matches
        filtered_matches = []
        for match in matches:
            record = match["record"]
            tags = (
                record[2].split()
                if len(record) > 2 and isinstance(record[2], str)
                else []
            )
            if "arch" not in tags:
                filtered_matches.append(match)

        if filtered_matches:
            matches = filtered_matches

        has_uk_tag = False
        forms_high_priority = None

        for match in matches:
            record = match["record"]
            if len(record) > 2 and isinstance(record[2], str):
                tags = record[2].split()
                has_uk_tag = has_uk_tag or "uk" in tags

            if _not_beaten_in_forms_table(record, expression, reading):
                forms_high_priority = True
                break

        if matches and forms_high_priority is None:
            forms_high_priority = False

        # Compute score
        # score_result = compute_score(
        #     jpdb_rank=jpdb_rank,
        #     has_jmdict_match=has_jmdict_match,
        #     has_uk_tag=has_uk_tag,
        #     forms_high_priority=forms_high_priority,
        #     is_ambiguous_expression=expression in expr_to_readings,
        #     is_ambiguous_reading=reading in reading_to_expressions,
        #     weights=weights,
        #     threshold=threshold,
        # )

        info = ExpressionInfo(
            expression=expression,
            reading=reading,
            jpdb_rank=jpdb_rank,
            has_jmdict_match=has_jmdict_match,
            has_uk_tag=has_uk_tag,
            forms_high_priority=forms_high_priority,
            is_ambiguous_expression=expression in expr_to_readings,
            is_ambiguous_reading=reading in reading_to_expressions,
        )



        # score_result.expression = expression
        # score_result.reading = reading

        # results.append(score_result)
        results.append(info)

    # Sort by score descending, then expression, then reading
    # results.sort(key=lambda r: (-r.total_score, r.expression, r.reading))

    return results

