#!/usr/bin/env python3

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from pprint import pprint
import hashlib
import pickle

import time



import filter_lib

from jitendex_yomitan_tools import load_j_y_term_bank, search_j_y_entries, is_j_y_redirect, get_j_y_redirect_target
# Example:
# bank = load_j_y_term_bank("./data/Jitendex_Yomitan/")
# matches = search_j_y_entries(bank, "さ来年")

# for entry in matches:
#     if is_j_y_redirect(entry):
#         print(get_j_y_redirect_target(entry))  # 再来年

from deck_reader import load_deck_pairs
from quality_scorer import (
    DEFAULT_FREQUENCY_THRESHOLD,
    ScoringResult,
    ScoringWeights,
    #compute_score,
)

CACHE_MAX_AGE_SECONDS = 12 * 60 * 60 #max cache age is 12h

@dataclass(frozen=True, slots=True)
class ExpressionInfo:
    expression: str
    reading: str
    expression_maybe_kana: str
    jpdb_rank: Optional[int]
    has_jmdict_match: bool
    j_y_redirect_tgt: Optional[tuple(str, str)]
    j_y_irregular: bool
    has_uk_tag: bool
    forms_high_priority: bool
    is_ambiguous_expression: bool
    is_ambiguous_reading: bool
    matching_row: tuple


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
        if len(readings) > 1 and expression
    }

    readings_with_multiple_expressions = {
        reading: sorted(expressions, key=lambda expression: (expression is None, expression))
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
    prompt_for_cached_output: bool = False,
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

    cache_key = "|".join((
        str(database_path.resolve()),
        source_table,
        str(jmdict_directory.resolve()),
        str(frequency_data_path.resolve()),
    ))
    cache_id = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
    cache_path = database_path.with_name(
        f"{database_path.stem}.evaluate_deck.{cache_id}.pkl"
    )

    if prompt_for_cached_output and cache_path.exists():
        cache_mtime = cache_path.stat().st_mtime
        cache_age = time.time() - cache_mtime
        source_mtime = Path(__file__).resolve().stat().st_mtime

        kd_data_mtime = database_path.stat().st_mtime
        kd_data_age = time.time() - kd_data_mtime
        print(database_path)

        print(f"Cache age (hrs): {(cache_age/3600):.1f}")
        print(f"KD user data age (hrs): {(kd_data_age/3600):.1f}")
        #print(kd_data_mtime)

        cache_is_recent = (0 <= cache_age <= CACHE_MAX_AGE_SECONDS) and (0 <= kd_data_age <= CACHE_MAX_AGE_SECONDS)
        #breakpoint()
        code_has_not_changed_since_cache = cache_mtime >= source_mtime
        data_has_not_changed_since_cache = cache_mtime >= kd_data_mtime

        if cache_is_recent and code_has_not_changed_since_cache and data_has_not_changed_since_cache:
            answer = input(
                f"Load saved output from {cache_path}? [y/n] "
            ).strip().lower()

            if answer in {"y", "yes"}:
                with cache_path.open("rb") as f:
                    cached = pickle.load(f)
                if cached.get("version") == 1:
                    return cached["output"]
                print("Cached output has an unsupported format; recomputing.")
        else:
            print("Cache is expired or the code / KD user data changed since it was saved; recomputing.")

    print("Loading JMdict term records...", file=sys.stderr)
    term_records = filter_lib.load_term_records(jmdict_directory)

    print("Loading JPDBv2 frequency data...", file=sys.stderr)
    freq_data = filter_lib.load_frequency_data(frequency_data_path)

    print("Loading Jitendex_Yomitan data...")
    j_y_bank = load_j_y_term_bank("./data/Jitendex_Yomitan/")

    print("Loading deck pairs...", file=sys.stderr)
    pair_set_with_rows = load_deck_pairs(database_path, source_table)
    pair_set = [(expression, reading) for (expression, reading, row) in pair_set_with_rows]

    print(f"Found {len(pair_set)} unique (expression, reading) pairs.", file=sys.stderr)

    # Build ambiguity maps
    expr_to_readings, reading_to_expressions = find_ambiguous_pairs(pair_set)

    results = []

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

    #sorted_pairs = sorted(pair_set)
    sorted_pairs_w_rows = sorted(
        pair_set_with_rows, 
        key=lambda item: (item[0] is None, item[0], item[1], item[2])
    )


    print("Evaluating entries...", file=sys.stderr)
    loop_len = len(sorted_pairs_w_rows)
    for (i, (expression, reading, row)) in enumerate(sorted_pairs_w_rows):
        if expression is None and reading:
            expression = reading
            # print("Setting expression to reading for:")
            # print(row)
        if i % 250 == 0:
            print(i, "of", loop_len)
        jpdb_rank = extract_jpdb_frequency_rank(
            jpdb_index, 
            expression, 
            reading,
            )


        key = (
            filter_lib.normalize(expression),
            filter_lib.normalize(reading),
        )
        matches = jmdict_exact_index.get(key, ())
        if not matches and expression == reading:#case where Kanji Dojo DB may correctly have a usu-kana entry set up
            #print(expression, reading)
            match_keys = [(jm_e, jm_r) for (jm_e, jm_r) in jmdict_exact_index if jm_r == reading]
            # for match_key in match_keys:
            #     print(match_key)
            if len(match_keys) == 1:
                matches = jmdict_exact_index.get(match_keys[0], ())
            else:
                matches = []
                for match_key in match_keys:
                    matches += jmdict_exact_index[match_key]
                #breakpoint()
            #breakpoint()
        has_jmdict_match = bool(matches)

        

        # Remove low-priority (archaic) matches
        filtered_matches = []
        for match in matches:
            #print("------------------------------------------------------------match:")
            #print("\t", match)
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

        expression_maybe_kana=expression if expression is not None else reading

        j_y_redirect_tgt = None
        j_y_matches = search_j_y_entries(j_y_bank, expression_maybe_kana)
        j_y_matches_w_reading = [m for m in j_y_matches if m[1] == reading]
        j_y_irregular = False
        if j_y_matches_w_reading:
            j_y_matches = j_y_matches_w_reading


        # if key == ('下る', 'さがる'):
        #     breakpoint()
        for match in j_y_matches:
            
            if is_j_y_redirect(match):
                (j_y_redirect_exp, j_y_redirect_rdg) = get_j_y_redirect_target(match)
                
                if j_y_redirect_rdg is None and j_y_redirect_exp:
                    j_y_redirect_rdg = j_y_redirect_exp#hopefully this only happens if the expression is all kana
                    #pprint(match)
                if (reading == j_y_redirect_rdg) or (j_y_redirect_rdg is None and reading == j_y_redirect_exp):
                    
                    j_y_redirect_tgt = (j_y_redirect_exp, j_y_redirect_rdg)
                    print(f"Jitendex data suggests a possible redirect of {expression_maybe_kana}[{reading}] -> {j_y_redirect_exp}[{j_y_redirect_rdg}].")
                    #breakpoint()
                # else:
                #     print(f"Not assigning this redirect to result based on reading mismatch: {reading} vs {j_y_redirect_rdg}")
                
                #pprint(match)
            else:
                #print(match[2])
                if "irregular" in match[2]:
                    print(expression, reading, match[2])
                    j_y_irregular = True
                


        info = ExpressionInfo(
            expression=expression,
            reading=reading,
            expression_maybe_kana=expression_maybe_kana,
            jpdb_rank=jpdb_rank,
            has_jmdict_match=has_jmdict_match,
            j_y_redirect_tgt=j_y_redirect_tgt,#None or (j_y_redirect_exp, j_y_redirect_rdg)
            j_y_irregular=j_y_irregular,
            has_uk_tag=has_uk_tag,
            forms_high_priority=forms_high_priority,
            is_ambiguous_expression=expression in expr_to_readings,
            is_ambiguous_reading=reading in reading_to_expressions,
            matching_row=row
        )

        if not has_jmdict_match and not j_y_redirect_tgt:
            print(f"No JMDict Match for {expression}, {reading}")
            breakpoint()


        results.append(info)

    output = (results, pair_set_with_rows)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("wb") as f:
        pickle.dump({"version": 1, "output": output}, f)

    return output


    #return (results, pair_set_with_rows)

