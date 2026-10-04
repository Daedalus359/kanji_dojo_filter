#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from pprint import pprint

from batch_evaluator import evaluate_deck
from quality_scorer import DEFAULT_FREQUENCY_THRESHOLD, ScoringWeights
from report_generator import OutputFormat, print_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze a Kanji Dojo deck and recommend entries for manual review. "
            "Entries with a nonzero score are candidates for removal or adjustment. "
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
        "--output",
        type=Path,
        default=None,
        help="Write report to this file instead of stdout.",
    )
    parser.add_argument(
        "--format",
        type=OutputFormat,
        choices=[OutputFormat.TEXT, OutputFormat.JSON, OutputFormat.CSV],
        default=OutputFormat.TEXT,
        help="Output format for the report.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include component breakdowns and detailed reasoning.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        default=True,
        help="Include a summary section at the top (default: true).",
    )

    args = parser.parse_args()

    try:
        results = evaluate_deck(
            database_path=args.database,
            source_table=args.source_table,
            jmdict_directory=args.jmdict_directory,
            frequency_data_path=args.frequency_data,
            weights=None,  # Use default weights
            threshold=args.threshold,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)

    print_report(
        results,
        output_format=args.format,
        output_file=args.output,
        verbose=args.verbose,
        summary=args.summary,
    )

    # for result in results:
    #     pprint(result)




if __name__ == "__main__":
    main()
