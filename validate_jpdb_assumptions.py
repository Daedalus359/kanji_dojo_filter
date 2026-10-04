#!/usr/bin/env python3
"""
Validate assumptions about JPDBv2 frequency data structure.

This script inspects the term_meta_bank_1.json file to understand:
1. The structure of frequency entries
2. How "as-kana" variants are represented
3. How to reliably match entries by (expression, reading) pairs
4. Edge cases for kana-only words like する、いる、ある
"""

import json
from pathlib import Path
from pprint import pprint
from typing import Any


def load_freq_data(file_path: str | Path) -> list[list[Any]]:
    """Load JPDBv2 frequency data."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def inspect_entry(entry: list[Any], index: int = None) -> None:
    """Pretty-print one frequency entry with annotations."""
    if index is not None:
        print(f"\n{'=' * 80}")
        print(f"Entry #{index}")
        print(f"{'=' * 80}")

    if not isinstance(entry, list) or len(entry) < 3:
        print("ERROR: Invalid entry structure")
        pprint(entry)
        return

    expression = entry[0]
    sequence_or_variant = entry[1]
    metadata = entry[2]

    print(f"[0] Expression: {expression!r}")
    print(f"[1] Sequence/Variant: {sequence_or_variant!r} (type: {type(sequence_or_variant).__name__})")
    print(f"[2] Metadata:")

    if isinstance(metadata, dict):
        for key, value in metadata.items():
            if key == "frequency":
                print(f"    {key}:")
                if isinstance(value, dict):
                    for k, v in value.items():
                        print(f"        {k}: {v!r}")
                else:
                    print(f"        {value!r}")
            else:
                print(f"    {key}: {value!r}")
    else:
        pprint(metadata)


def find_entries_matching(
    freq_data: list[list[Any]],
    expression: str,
    reading: str = None,
) -> list[tuple[int, list[Any]]]:
    """
    Find all entries where:
    - entry[0] (expression) == expression
    - (optionally) entry[2]["reading"] == reading

    Returns list of (index, entry) tuples.
    """
    matches = []
    for idx, entry in enumerate(freq_data):
        if not isinstance(entry, list) or len(entry) < 3:
            continue

        if entry[0] == expression:
            if reading is None:
                matches.append((idx, entry))
            elif isinstance(entry[2], dict) and entry[2].get("reading") == reading:
                matches.append((idx, entry))

    return matches


def analyze_as_kana_variants(freq_data: list[list[Any]]) -> None:
    """
    Analyze how as-kana variants are stored.

    Hypothesis: When an expression has both a standard form and a kana-only form,
    they appear as separate entries with:
    - Same expression
    - Different readings
    - Different frequency values
    """
    print("\n" + "=" * 80)
    print("ANALYZING AS-KANA VARIANTS")
    print("=" * 80)

    expression_counts = {}
    for entry in freq_data:
        if isinstance(entry, list) and len(entry) >= 3:
            expr = entry[0]
            expression_counts[expr] = expression_counts.get(expr, 0) + 1

    multi_entries = {expr: count for expr, count in expression_counts.items() if count > 1}
    print(f"\nFound {len(multi_entries)} expressions with multiple entries.")
    print("\nShowing first 10 examples:")

    for expr, count in list(multi_entries.items())[:10]:
        print(f"\n  Expression {expr!r} has {count} entries:")
        matches = find_entries_matching(freq_data, expr)
        for idx, entry in matches:
            reading = entry[2].get("reading") if isinstance(entry[2], dict) else "?"
            freq_val = entry[2].get("frequency", {}) if isinstance(entry[2], dict) else {}
            if isinstance(freq_val, dict):
                freq_rank = freq_val.get("value", "?")
            else:
                freq_rank = "?"
            print(f"    [{idx}] reading={reading!r}, frequency={freq_rank}")

def validate_kana_only_words(freq_data: list[list[Any]]) -> None:
    """
    Test lookup of pure kana words: する、いる、ある、etc.

    These should be in the frequency data as expression=reading=kana string.
    """
    print("\n" + "=" * 80)
    print("VALIDATING KANA-ONLY WORDS")
    print("=" * 80)

    test_words = [
        ("する", "する"),
        ("いる", "いる"),
        ("ある", "ある"),
        ("言う", "いう"),
        ("明日", "あす"),
        ("明日", "あした"),
    ]

    for expression, reading in test_words:
        print(f"\nLooking for: expression={expression!r}, reading={reading!r}")
        matches = find_entries_matching(freq_data, expression, reading)

        if matches:
            print(f"  ✓ Found {len(matches)} match(es)")
            for idx, entry in matches[:5]:
                inspect_entry(entry, index=idx)
        else:
            print(f"  ✗ No match found")
            all_expr_matches = find_entries_matching(freq_data, expression)
            if all_expr_matches:
                print(f"    But found {len(all_expr_matches)} entry(ies) with expression={expression!r}:")
                for idx, entry in all_expr_matches[:5]:
                    if isinstance(entry[2], dict):
                        r = entry[2].get("reading", "?")
                    else:
                        r = "?"
                    print(f"      [{idx}] reading={r!r}")

def check_frequency_value_structure(freq_data: list[list[Any]]) -> None:
    """
    Analyze the frequency value structure to understand displayValue vs value.

    Hypothesis: displayValue is formatted string, value is the numeric rank.
    """
    print("\n" + "=" * 80)
    print("ANALYZING FREQUENCY VALUE STRUCTURE")
    print("=" * 80)

    entries_with_freq = []
    for idx, entry in enumerate(freq_data):
        if (
            isinstance(entry, list)
            and len(entry) >= 3
            and isinstance(entry[2], dict)
            and "frequency" in entry[2]
        ):
            entries_with_freq.append((idx, entry))

    print(f"\nFound {len(entries_with_freq)} entries with frequency data.")
    print("\nAnalyzing first 10 examples:")

    for idx, entry in entries_with_freq[:10]:
        freq_obj = entry[2]["frequency"]
        print(f"\n  Entry {idx}: {entry[0]!r} [{entry[2].get('reading', '?')!r}]")

        if isinstance(freq_obj, dict):
            print(f"    Type: dict")
            for key, val in freq_obj.items():
                print(f"      {key}: {val!r} ({type(val).__name__})")
        else:
            print(f"    Type: {type(freq_obj).__name__}")
            print(f"    Value: {freq_obj!r}")


def suggest_lookup_improvements(freq_data: list[list[Any]]) -> None:
    """
    Based on observations, suggest improvements to filter_lib.get_frequency_data_for().
    """
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS FOR LOOKUP LOGIC")
    print("=" * 80)

    print("""
1. EXACT MATCH (current implementation):
   - Match on entry[0] == expression AND metadata["reading"] == reading
   - This should work for most cases

2. FALLBACK FOR MISSING READING:
   - Some entries might not have a "reading" field in metadata
   - Should match on entry[0] == expression only as fallback

3. HANDLING AS-KANA VARIANTS:
   - When looking up an expression, consider returning ALL matching entries
   - This allows identifying which reading is "standard" vs "as-kana"
   - Compare frequencies to determine which form is more common

4. NORMALIZATION:
   - Ensure expression/reading are normalized (NFC) before comparison
   - Handle half-width vs full-width kana if needed

5. KANA-ONLY WORDS:
   - Special handling for words where expression == reading
   - These should be indexed under their kana spelling in frequency data
   - Test: する、いる、ある should be findable directly
   """)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate JPDBv2 frequency data assumptions."
    )
    parser.add_argument(
        "--freq-data",
        type=Path,
        default=Path("..") / "frequency_data" / "term_meta_bank_1.json",
        help="Path to JPDBv2 term_meta_bank_1.json",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full inspection of sample entries",
    )

    args = parser.parse_args()

    if not args.freq_data.exists():
        print(f"Error: Frequency data file not found: {args.freq_data}")
        raise SystemExit(1)

    print(f"Loading frequency data from {args.freq_data}...")
    freq_data = load_freq_data(args.freq_data)
    print(f"Loaded {len(freq_data):,} entries\n")

    check_frequency_value_structure(freq_data)
    analyze_as_kana_variants(freq_data)
    validate_kana_only_words(freq_data)
    suggest_lookup_improvements(freq_data)

    if args.verbose:
        print("\n" + "=" * 80)
        print("SAMPLE ENTRIES (first 5)")
        print("=" * 80)
        for i, entry in enumerate(freq_data[:5]):
            inspect_entry(entry, index=i)


if __name__ == "__main__":
    main()