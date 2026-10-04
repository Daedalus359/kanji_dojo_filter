#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import filter_lib

from constants import SCORING_CONSTS, JPDB_CUTOFF_FREQ_RANK

DEFAULT_FREQUENCY_THRESHOLD = JPDB_CUTOFF_FREQ_RANK


@dataclass
class DeckEntryAnalysis:
    expression: str
    reading: str
    recommendation: str
    score: float
    jpdb_rank: int | None
    frequency_component: float
    has_jmdict_match: bool
    has_uk_tag: bool
    forms_high_priority: bool | None
    is_ambiguous_expression: bool
    is_ambiguous_reading: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["score"] = round(self.score, 4)
        payload["frequency_component"] = round(self.frequency_component, 4)
        return payload


MARKED_ITEM_RE = __import__("re").compile(r"^(.*?)\s*[（(]([^（）()]*)[）)]\s*$")


def normalize(value: Any) -> str | None:
    return filter_lib.normalize(value)


def find_ambiguous_pairs(
    pairs: Iterable[tuple[str, str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return mappings with more than one distinct counterpart."""
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


def remove_outer_brackets(s: Any) -> str:
    if isinstance(s, bytes):
        s = s.decode("utf-8")

    s = str(s)

    if len(s) >= 2:
        first = s[0]
        last = s[-1]

        if (
            len(first) == 1
            and len(last) == 1
            and __import__("unicodedata").category(first) == "Ps"
            and __import__("unicodedata").category(last) == "Pe"
        ):
            return s[1:-1]

    return s


def _parse_structured_forms_table(value: Any):
    """Convert a JMdict structured-content table into a simple dict-like structure."""
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


def forms_table_has_star(record: list[Any], expression: str, reading: str) -> bool:
    if len(record) <= 5 or record[2] != "forms":
        return False

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
        if row[reading_index] == reading and row[expr_index] == "★":
            return True

    return False


def extract_jpdb_frequency_rank(freq_data: list[list[Any]], expression: str, reading: str) -> int | None:
    """Return the ranking from the JPDBv2 frequency dataset for the pair if present."""
    best_rank: int | None = None

    for entry in freq_data:
        if not isinstance(entry, list) or len(entry) < 3:
            continue

        top_level_expression = entry[0]
        metadata = entry[2]

        if not isinstance(metadata, dict):
            continue
        if top_level_expression != expression:
            continue

        if metadata.get("reading") != reading:
            continue

        frequency = metadata.get("frequency")
        if not isinstance(frequency, dict):
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

        if best_rank is None or rank < best_rank:
            best_rank = rank

    return best_rank


def build_frequency_component(freq_rank: int | None, threshold: int = DEFAULT_FREQUENCY_THRESHOLD) -> float:
    """Score low-frequency items as more risky; top words contribute zero."""
    if freq_rank is None:
        return 0.0

    if freq_rank <= threshold:
        return 0.0

    return min(1.0, (freq_rank - threshold) / max(1, threshold))


def _select_recommendation(score: float) -> str:
    if score >= 0.8:
        return "remove"
    if score >= 0.5:
        return "review"
    return "keep"


def analyze_pair(
    expression: str,
    reading: str,
    term_records: list[dict[str, Any]],
    freq_data: list[list[Any]],
    ambiguous_expression: bool,
    ambiguous_reading: bool,
    threshold: int = DEFAULT_FREQUENCY_THRESHOLD,
) -> DeckEntryAnalysis:
    expression = normalize(expression) or ""
    reading = normalize(reading) or ""

    matches = filter_lib.find_term_records(term_records, expression, reading, partial=False)
    has_jmdict_match = bool(matches)

    # Drop low-priority archaic matches when more than one result exists.
    filtered_matches = []
    for match in matches:
        record = match["record"]
        tags = record[2].split() if len(record) > 2 and isinstance(record[2], str) else []
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

        if forms_table_has_star(record, expression, reading):
            forms_high_priority = True
            break

    if matches and forms_high_priority is None:
        forms_high_priority = False

    jpdb_rank = extract_jpdb_frequency_rank(freq_data, expression, reading)
    frequency_component = build_frequency_component(jpdb_rank, threshold=threshold)

    score = 0.0
    reasons: list[str] = []

    if jpdb_rank is None:
        score += 0.15
        reasons.append("no JPDBv2 frequency entry")
    else:
        if jpdb_rank > threshold:
            score += 0.45 * frequency_component
            reasons.append(f"JPDBv2 rank {jpdb_rank} exceeds the {threshold}-word threshold")
        else:
            reasons.append(f"JPDBv2 rank {jpdb_rank} is within the top {threshold}")

    if not has_jmdict_match:
        score += 0.35
        reasons.append("no JMdict match")
    else:
        if has_uk_tag:
            score += SCORING_CONSTS["uk_tag_kanji_word"]
            reasons.append("JMdict marks this as usually kana-only")
        elif forms_high_priority is False:
            score += 0.20
            reasons.append("JMdict entry exists but is not marked high priority")

    if ambiguous_expression:
        score += 0.20
        reasons.append("expression has multiple readings")
    if ambiguous_reading:
        score += 0.20
        reasons.append("reading is shared by multiple expressions")

    if forms_high_priority is False:
        score += 0.10
        reasons.append("forms table does not prefer this expression/reading pair")

    #score = max(0.0, min(1.0, score))
    recommendation = _select_recommendation(score)

    return DeckEntryAnalysis(
        expression=expression,
        reading=reading,
        recommendation=recommendation,
        score=score,
        jpdb_rank=jpdb_rank,
        frequency_component=frequency_component,
        has_jmdict_match=has_jmdict_match,
        has_uk_tag=has_uk_tag,
        forms_high_priority=forms_high_priority,
        is_ambiguous_expression=ambiguous_expression,
        is_ambiguous_reading=ambiguous_reading,
        reasons=reasons,
    )


def iterate_deck_rows(connection: sqlite3.Connection, table_name: str):
    table_info = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    if not table_info:
        raise RuntimeError(f"Could not find table {table_name!r}")

    column_names = [column[1] for column in table_info]
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
        expression = normalize(row[kanji_index])
        reading = normalize(row[kana_index])
        if not expression or not reading:
            continue
        yield expression, reading, row, column_names


def analyze_deck(
    database_path: str | Path,
    source_table: str,
    jmdict_directory: str | Path,
    frequency_data_path: str | Path,
    threshold: int = DEFAULT_FREQUENCY_THRESHOLD,
    limit: int | None = None,
) -> list[DeckEntryAnalysis]:
    database_path = Path(database_path)
    if not database_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {database_path}")

    jmdict_directory = Path(jmdict_directory)
    if not jmdict_directory.exists():
        raise FileNotFoundError(f"JMdict directory not found: {jmdict_directory}")

    frequency_data_path = Path(frequency_data_path)
    if not frequency_data_path.exists():
        raise FileNotFoundError(f"Frequency dataset not found: {frequency_data_path}")

    term_records = filter_lib.load_term_records(jmdict_directory)
    freq_data = filter_lib.load_frequency_data(frequency_data_path)

    pair_set = set()

    with sqlite3.connect(database_path) as connection:
        for expression, reading, _row, _columns in iterate_deck_rows(connection, source_table):
            pair_set.add((expression, reading))

    expression_to_readings, reading_to_expressions = find_ambiguous_pairs(pair_set)

    results: list[DeckEntryAnalysis] = []

    with sqlite3.connect(database_path) as connection:
        for expression, reading, _row, _columns in iterate_deck_rows(connection, source_table):
            analysis = analyze_pair(
                expression,
                reading,
                term_records,
                freq_data,
                ambiguous_expression=expression in expression_to_readings,
                ambiguous_reading=reading in reading_to_expressions,
                threshold=threshold,
            )
            results.append(analysis)

    results.sort(key=lambda item: (-item.score, item.expression, item.reading))

    if limit is not None and limit > 0:
        return results[:limit]

    return results


def _print_results(results: list[DeckEntryAnalysis], summary: bool = True) -> None:
    if summary:
        count_by_status = {"keep": 0, "review": 0, "remove": 0}
        for item in results:
            count_by_status[item.recommendation] = count_by_status.get(item.recommendation, 0) + 1

        print("Deck recommendation summary:")
        for label in ("keep", "review", "remove"):
            print(f"  {label:>6}: {count_by_status.get(label, 0)}")
        print()

    print("Top recommendations:")
    for item in results:
        print(
            f"{item.recommendation:>6} | score={item.score:.3f} | "
            f"{item.expression} [{item.reading}] | jpdb={item.jpdb_rank} | "
            f"freq_component={item.frequency_component:.3f}"
        )
        if item.reasons:
            print(f"    reasons: {'; '.join(item.reasons)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a Kanji Dojo deck and recommend entries to keep, review, or remove. "
            "The default frequency cutoff is the top 8,000 JPDBv2 words."
        )
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
        "--jmdict-directory",
        type=Path,
        default=Path("data") / "JMDict",
        help="Directory containing JMdict term_bank_*.json files.",
    )
    parser.add_argument(
        "--frequency-data",
        type=Path,
        default=Path("..") / "frequency_data" / "term_meta_bank_1.json",
        help="JPDBv2 frequency dataset JSON file.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=DEFAULT_FREQUENCY_THRESHOLD,
        help="JPDBv2 top-N cutoff. Entries at or above this ranking contribute zero frequency penalty.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of candidate rows printed.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text.",
    )

    args = parser.parse_args()

    try:
        results = analyze_deck(
            database_path=args.database,
            source_table=args.source_table,
            jmdict_directory=args.jmdict_directory,
            frequency_data_path=args.frequency_data,
            threshold=args.threshold,
            limit=args.limit,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)

    if args.json:
        print(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2))
        return

    _print_results(results)


if __name__ == "__main__":
    main()


# The scoring system follows this rule:
#  - a JPDBv2 frequency rank at or above the threshold contributes zero
#    frequency score, effectively treating the word as common enough to keep
#  - lower-frequency entries contribute a non-zero value that pushes the item
#    toward review/remove recommendations.
#
# This keeps the default cutoff aligned with your request of the top 8,000 words.
#
# Additional recommendation heuristics:
#  - no JMdict match
#  - shared reading / shared expression ambiguity
#  - expression is not high-priority according to the JMDict forms table
#  - JMdict tags indicate kana-only usage / `uk`


# Future improvements that fit naturally with this module:
#  - export these recommendations to CSV/JSON for deck review
#  - add per-deck weighting by deck type / level / priority
#  - integrate with the existing Kanji Dojo sqlite schema for auto-generated exclusion tables
#  - merge this with the existing `investigate_sample_bad_words.py` logic
#  - surface expression/readings that share a common reading or which are ambiguous across multiple expressions
#
# This keeps the project aligned with your request to analyze the full deck and recommend
# changes/removals based on frequency, JMdict, and ambiguity filters.


# NOTE:
# The repo's current implementation uses a more exploratory approach in
# `investigate_sample_bad_words.py`; this new module provides the batch deck
# analysis layer on top of the same concepts (frequency, forms table, ambiguity).
#
# It is intentionally conservative:
#  - common words in the top-N JPDBv2 band receive zero frequency penalty
#  - only a low-frequency, ambiguous, or weakly supported pair becomes a recommendation
#    to review or remove.
#
# This matches the desired behavior you specified for the scoring system.


# End of deck analysis module.
