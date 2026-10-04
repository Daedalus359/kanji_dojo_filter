#!/usr/bin/env python3

import argparse
import sys
from collections import defaultdict
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from pprint import pprint
import pandas as pd
import re
from typing import Iterable

import filter_lib
from constants import SAMPLE_WORDS, NORMAL_TAGS, VERB_TYPES, USUALLY_ENTRIES, LOW_PRIORITY_SENSE_INDICATOR_TAGS

import unicodedata

PROJECT_DIRECTORY = Path(__file__).resolve().parent
JMDICT_DIRECTORY = PROJECT_DIRECTORY / "data" / "JMDict"
FREQ_DICT_DIRECTORY = PROJECT_DIRECTORY.parent / "frequency_data" / "term_meta_bank_1.json"

@dataclass(frozen=True)
class InspectionResult:
    has_usually_kana_only_match: bool
    found_matches: bool
    match_count: int

def find_ambiguous_pairs(
    pairs: Iterable[tuple[str, str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """
    Return mappings that have more than one distinct counterpart.

    Returns:
        expression_to_readings:
            Expressions associated with multiple readings.

        reading_to_expressions:
            Readings associated with multiple expressions.
    """
    expression_to_readings = defaultdict(set)
    reading_to_expressions = defaultdict(set)

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

    return (
        expressions_with_multiple_readings,
        readings_with_multiple_expressions,
    )

MARKED_ITEM_RE = re.compile(
    r"^(.*?)\s*[（(]([^（）()]*)[）)]\s*$"
)

def remove_outer_brackets(s):
    if isinstance(s, bytes):
        s = s.decode("utf-8")

    s = str(s)

    if len(s) >= 2:
        first = s[0]
        last = s[-1]

        if (
            len(first) == 1
            and len(last) == 1
            and unicodedata.category(first) == "Ps"
            and unicodedata.category(last) == "Pe"
        ):
            return s[1:-1]

    return s


def marked_list_to_wide_dataframe(items, reading):
    row = {"reading": reading}

    for raw_item in items:
        item = str(raw_item).strip()

        if not item:
            continue

        match = MARKED_ITEM_RE.fullmatch(item)

        if match:
            spelling = match.group(1).strip()
            symbol = match.group(2).strip()
        else:
            spelling = item
            symbol = pd.NA

        if not spelling:
            continue

        if spelling in row:
            raise ValueError(f"Duplicate spelling in forms table: {spelling!r}")

        row[spelling] = symbol

    return pd.DataFrame([row])

def remove_low_priority_matches(matches):
    if len(matches) > 1:
        keep_matches = matches
        for unwanted_tag in LOW_PRIORITY_SENSE_INDICATOR_TAGS:
            #print("Unwanted tag:", unwanted_tag)
            candidate_keep_matches = []
            for m in keep_matches:
                #print(m)
                record = m["record"]
                tags_string = record[2] if len(record) > 2 else ""
                tags = tags_string.split()
                if unwanted_tag not in tags:
                    candidate_keep_matches.append(m)
            if candidate_keep_matches: #if at least one match did not have the unwanted tag
                keep_matches = candidate_keep_matches
                #if prints: print(f"{len(keep_matches)} JMDict match candidates after removing candidates with tag", unwanted_tag)
            if len(candidate_keep_matches) == 1: #no more reduction possible
                break
        matches = keep_matches
    return matches

def parse_structured_forms_table(value):
    """
    Convert a JMdict structured-content table into a DataFrame.

    Returns None when the value does not have the expected shape.
    """
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

    table_rows = outer_content.get("content")

    if not isinstance(table_rows, list) or not table_rows:
        return None

    rows = []

    for table_row in table_rows:
        if not isinstance(table_row, dict):
            return None

        cells = table_row.get("content")

        if not isinstance(cells, list):
            return None

        parsed_cells = []

        for cell in cells:
            if not isinstance(cell, dict):
                return None

            parsed_cells.append(cell.get("content", ""))

        rows.append(parsed_cells)

    if len(rows) < 2:
        return None

    column_names = rows[0]

    column_names = [
        "reading" if name == "" else name
        for name in column_names
    ]

    if not all(isinstance(name, str) for name in column_names):
        return None

    if any(len(row) != len(column_names) for row in rows[1:]):
        return None

    dataframe = pd.DataFrame(rows[1:], columns=column_names)

    return dataframe


def _is_sense_or_tag_string(value, normal_tags):
    """Validate the usual item-2 format: sense number/type followed by tags."""
    if not isinstance(value, str):
        return False

    parts = value.split()
    if not parts:
        return False

    first = parts[0]
    return (
        first.isdigit() or first in normal_tags
    ) and all(tag in normal_tags for tag in parts[1:])


def _is_definitions_record(value):
    """
    Preserve the current definition-record expectation:
    a non-empty list of dictionaries whose first dictionary has `content`.
    """
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, dict) for item in value)
        and "content" in value[0]
    )


def _validate_record_structure(record, expression, reading):
    """
    Validate the positional structure of a record.

    Returns:
        list[tuple[int, str, object]]: (index, message, offending_value)
    """
    errors = []

    for index, value in enumerate(record):
        if index == 0:
            if value != expression:
                errors.append((
                    index,
                    f"Expected expression {expression!r} at index {index}",
                    value,
                ))

        elif index == 1:
            if value != reading:
                errors.append((
                    index,
                    f"Expected reading {reading!r} at index {index}",
                    value,
                ))

        elif index == 2:
            if not (
                value == "forms"
                or _is_sense_or_tag_string(value, NORMAL_TAGS)
            ):
                errors.append((
                    index,
                    "Record item 2 (usu. a sense number and tags)",
                    value,
                ))

        elif index == 3:
            if value and value not in VERB_TYPES:
                errors.append((
                    index,
                    "Record item 3 "
                    "(usually high-level conj. type for verbs or else blank)",
                    value,
                ))

        elif index == 4:
            if not isinstance(value, int):
                errors.append((
                    index,
                    "Record item 4 (usually an integer)",
                    value,
                ))

        elif index == 5:
            # Item 5 has two valid shapes, depending on item 2.
            is_forms_record = len(record) > 2 and record[2] == "forms"

            if not is_forms_record and not _is_definitions_record(value):
                errors.append((
                    index,
                    "Expected definitions "
                    "(a list of dicts with key 'content')",
                    value,
                ))

        elif index == 6:
            if not isinstance(value, int):
                errors.append((
                    index,
                    "Record item 6 (usually an integer)",
                    value,
                ))

        elif index == 7:
            parts = value.split() if isinstance(value, str) else []
            if not (
                len(parts) >= 2
                and parts[0] == "⭐"
                and parts[1] == "ichi"
                and all(item in USUALLY_ENTRIES for item in parts[2:])
            ):
                errors.append((
                    index,
                    f"Record item 7 "
                    f"(Usu. ⭐, ichi, then any of {USUALLY_ENTRIES})",
                    value,
                ))

        else:
            errors.append((
                index,
                "Not used to seeing more than 8 entries in record",
                value,
            ))

    return errors


def _print_structure_errors(errors):
    """Keep validation reporting separate from validation itself."""
    for index, message, value in errors:
        if index == 0:
            print(message)
            print(f"Record item {index} :")
            print(value)

        elif index == 1:
            print(message)
            print(f"Record item {index} :")
            print(value)

        elif index == 2:
            print(f"{message}:")
            print(value)

            # These details are useful when diagnosing malformed tag strings.
            if isinstance(value, str):
                parts = value.split()
                print(isinstance(value, str))
                print(bool(parts) and parts[0].isdigit())
                print(
                    bool(parts)
                    and all(tag in NORMAL_TAGS for tag in parts[1:])
                )

                for tag in parts[1:]:
                    if tag not in NORMAL_TAGS:
                        print(tag, tag in NORMAL_TAGS)
            else:
                print(False)
                print(False)
                print(False)

        else:
            print(f"{message}:")
            print(value)


def _inspect_record_contents(record, expression, reading):
    """
    Inspect content-specific data after positional validation.

    This function intentionally does not validate the general record layout.
    """
    if len(record) <= 5:
        return

    if len(record) > 2 and record[2] == "forms":
        forms_table = parse_structured_forms_table(record[5])

        # Preserve the current behavior: an unparseable table produces
        # no additional diagnostic here.
        if forms_table is None:
            return

        normalized_readings = forms_table["reading"].map(remove_outer_brackets)

        is_star = (
            reading in normalized_readings.to_numpy()
            and expression in forms_table.columns
            and forms_table.loc[
                normalized_readings.eq(reading),
                expression,
            ].eq("★").any()
        )

        if not is_star:
            print("🔴", expression, "[", reading, "] is not high priority.")
            print("Parsed table of reading / writing combos:")
            print(forms_table)

    # Definitions currently have no content-specific inspection beyond
    # structural validation, so there is nothing else to do here.


def inspect_query(
    expression,
    reading,
    term_records,
    tag_descriptions,
    partial=False,
    prints=False,
):
    matches = filter_lib.find_term_records(
        term_records,
        expression,
        reading,
        partial=partial,
    )

    found_matches = bool(matches)

    if prints:
        print(f"JMDict Matches: {len(matches)}")

    if not found_matches:
        if prints:
            print("No matching JMdict term records found.")

    matches = remove_low_priority_matches(matches)

    for match in matches:
        record = match["record"]

        # Phase 1: validate the expected record structure.
        errors = _validate_record_structure(
            record,
            expression,
            reading,
        )
        _print_structure_errors(errors)

        # Phase 2: inspect forms/definitions content.
        _inspect_record_contents(
            record,
            expression,
            reading,
        )

    uk_count = 0

    for item in matches:
        tags = (
            item["record"][2]
            if len(item["record"]) > 2
            else ""
        ).split()

        if "uk" in tags:
            uk_count += 1

    if prints:
        print(
            "uk listed for",
            uk_count,
            "of",
            len(matches),
            "matching senses",
        )

    return InspectionResult(
        has_usually_kana_only_match=uk_count > 0,
        found_matches=found_matches,
        match_count=len(matches),
    )


def evaluate_entry_quality(term_records, tag_descriptions, partial, freq_data, expression, reading, prints=True):
    
    found_matches_JMDict = False
    found_matches_JPDB = False

    inspectionresult = None

    # print("Move main code to evaluate_entry_quality!")
    if prints: print()
    if prints: print()
    if prints: print("=" * 80)
    if prints: print("Expression", expression, "with reading: ", reading)
    if prints: print("=" * 80)
    if prints:
        #has_uk_tags, found_matches_JMDict
        inspectionresult = inspect_query(
            expression,
            reading,
            term_records,
            tag_descriptions,
            partial=partial,
            prints=True,
        )
        
    else:
        # inspect_query() currently contains some unconditional print()
        # and pprint() calls. Capture them so batch mode remains silent.
        with redirect_stdout(StringIO()):
            #has_uk_tags, found_matches_JMDict 
            inspectionresult = inspect_query(
                expression,
                reading,
                term_records,
                tag_descriptions,
                partial=partial,
                prints=False,
            )
    found_matches_JMDict = inspectionresult.found_matches
    has_uk_tags = inspectionresult.has_usually_kana_only_match
    if prints: print("--------------")
    #print("frequency entries:")
    standard_frequency = None
    as_kana_frequency = None
    as_kana_more_common = False
    
    freq_entries = filter_lib.get_frequency_data_for(freq_data, expression, reading)
    if freq_entries:
        found_matches_JPDB = True
    for entry in freq_entries:
        if (entry[0] != expression) or (entry[2]["reading"] != reading):
            if prints:
                print("BAD ENTRY!")
                print(entry)
                print(entry[0], expression, (entry[0] != expression))
                print(entry[2]["reading"], reading, (entry[2]["reading"] != reading))
            continue
        vdv = entry[2]['frequency']
        if str(vdv["value"]) != vdv["displayValue"]:
            # print("The following ppears to be an as-kana frequency:")
            # print(vdv)
            as_kana_frequency = int(vdv["value"])
            # print(as_kana_frequency)
        else:
            # print("The following appears to be the expression's standard frequency:")
            # print(vdv)
            standard_frequency = int(vdv["value"])
        # print(type(entry[2]))
        # print(entry)
        # print()
    if standard_frequency and not as_kana_frequency:
        if prints: print("Only a standard frequency found:", standard_frequency)
    if not standard_frequency:
        if prints: print("ERROR: no standard frequency found")
        if prints: print(freq_entries)
    if standard_frequency and as_kana_frequency:
        if standard_frequency < as_kana_frequency:#lower is more frequent, as these numbers are rankings
            if prints: print("Expression", expression, "'s standard form more common.")
        if as_kana_frequency < standard_frequency:
            if prints: print("Expression", expression, "'s as-kana form more common.")
            as_kana_more_common = True
        if as_kana_frequency == standard_frequency:
            if prints: print("Expression", expression, "'s standard and as-kana frequencies equally common.")
        

        if prints: print("--------------")
        if (has_uk_tags and as_kana_more_common):
            if prints: print("Both JMDict data and JPDBv2 frequency data support", expression, "being mainly written with kana.")


    return (has_uk_tags, as_kana_more_common, found_matches_JMDict, found_matches_JPDB)
    #input("press enter to continue")



def main():
    parser = argparse.ArgumentParser(
        description=(
            "Inspect JMdict records using expression/reading pairs."
        )
    )

    parser.add_argument(
        "-q",
        "--query",
        nargs=2,
        action="append",
        metavar=("EXPRESSION", "READING"),
        help=(
            "Expression and reading pair to inspect. "
            "Can be supplied more than once."
        ),
    )

    parser.add_argument(
        "-p",
        "--partial",
        action="store_true",
        help=(
            "Use partial matching, while still requiring both "
            "expression and reading to match."
        ),
    )

    parser.add_argument(
        "--jmdict-directory",
        type=Path,
        default=JMDICT_DIRECTORY,
        help=(
            "Directory containing term_bank_*.json and "
            "tag_bank_1.json."
        ),
    )

    args = parser.parse_args()

    print(sys.version)

    jmdict_directory = args.jmdict_directory

    if not jmdict_directory.exists():
        raise FileNotFoundError(
            f"JMdict directory not found: {jmdict_directory}"
        )

    # argparse produces a list of two-item lists when --query is used.
    # Convert that into the same expression -> reading dictionary format
    # used by SAMPLE_WORDS.
    if args.query:
        words_to_inspect = {
            expression: reading
            for expression, reading in args.query
        }
    else:
        words_to_inspect = SAMPLE_WORDS

    print("Loading JMdict term records...", file=sys.stderr)

    term_records = filter_lib.load_term_records(
        jmdict_directory
    )

    print("Loading tag descriptions...", file=sys.stderr)

    tag_descriptions = filter_lib.load_tag_descriptions(
        jmdict_directory
    )

    print(
        f"Loaded {len(term_records):,} term records.",
        file=sys.stderr,
    )

    print("Loading frequency data")

    freq_data = filter_lib.load_frequency_data(FREQ_DICT_DIRECTORY)

    for expression, reading in words_to_inspect:
        print("----------------------------------------------------")
        print(expression, "[", reading, "]:")
        (has_uk_tags, as_kana_more_common, found_matches_JMDict, found_matches_JPDB) = evaluate_entry_quality(term_records, tag_descriptions, args.partial, freq_data, expression, reading, prints=False)
        
        if (has_uk_tags and as_kana_more_common):
            print("\t At least one sense from JMDict and also JPDB indicate that", expression, "usually written as kana.")
        if not found_matches_JMDict:
            print("\t No match for", expression, "found in JMDict")
        if not found_matches_JPDB:
            print("\t No match for", expression, "found in JPDB")


    expressions_with_multiple_readings, readings_with_multiple_expressions = find_ambiguous_pairs(SAMPLE_WORDS)

    if expressions_with_multiple_readings:
        print("Expressions with multiple readings:")
        pprint(expressions_with_multiple_readings)
    if readings_with_multiple_expressions:
        print("Readings shared by multiple expressions:")
        pprint(readings_with_multiple_expressions)


if __name__ == "__main__":
    main()