#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from quality_scorer import ScoringResult


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"
    CSV = "csv"


def _print_text_result(result: ScoringResult, verbose: bool = False) -> None:
    """Print a single ScoringResult in human-readable text format."""
    print(
        f"{result.expression:20} [{result.reading:15}] | "
        f"score={result.total_score:.3f} | jpdb={result.jpdb_rank}"
    )
    if verbose and result.reasons:
        print(f"    reasons: {'; '.join(result.reasons)}")
    if verbose and result.component_scores:
        print(f"    components: {result.component_scores}")


def print_report(
    results: Iterable[ScoringResult],
    output_format: OutputFormat = OutputFormat.TEXT,
    output_file: Path | None = None,
    verbose: bool = False,
    summary: bool = True,
) -> None:
    """Generate and print a report of scoring results.

    Args:
        results: Iterable of ScoringResult objects (typically sorted by score).
        output_format: Format for the report (text, json, csv).
        output_file: If provided, write to this file instead of stdout.
        verbose: If True, include component breakdowns and reasons.
        summary: If True, include a summary section at the top.
    """
    results_list = list(results)

    if output_format == OutputFormat.JSON:
        _write_json_report(results_list, output_file)
    elif output_format == OutputFormat.CSV:
        _write_csv_report(results_list, output_file)
    else:  # TEXT
        _write_text_report(
            results_list, output_file, verbose=verbose, summary=summary
        )


def _write_text_report(
    results: list[ScoringResult],
    output_file: Path | None = None,
    verbose: bool = False,
    summary: bool = True,
) -> None:
    """Write a human-readable text report."""
    output = open(output_file, "w", encoding="utf-8") if output_file else None

    def print_line(*args: Any, **kwargs: Any) -> None:
        print(*args, **kwargs, file=output)

    try:
        if summary:
            nonzero_count = sum(1 for r in results if r.total_score > 0)
            print_line(f"Analysis Summary:")
            print_line(f"  Total entries: {len(results)}")
            print_line(f"  Entries with nonzero score: {nonzero_count}")
            print_line()

        if verbose:
            print_line(f"Detailed Analysis:")
        else:
            print_line(f"Entries with nonzero score (for manual review):")

        print_line()
        for result in results:
            if result.total_score > 0:
                _print_text_result(result, verbose=verbose)

    finally:
        if output:
            output.close()


def _write_json_report(
    results: list[ScoringResult], output_file: Path | None = None
) -> None:
    """Write results as JSON."""
    data = [r.to_dict() for r in results]
    output = open(output_file, "w", encoding="utf-8") if output_file else None

    try:
        json.dump(
            data,
            output or __import__("sys").stdout,
            ensure_ascii=False,
            indent=2,
        )
    finally:
        if output:
            output.close()


def _write_csv_report(
    results: list[ScoringResult], output_file: Path | None = None
) -> None:
    """Write results as CSV."""
    output = open(output_file, "w", encoding="utf-8", newline="") if output_file else None

    try:
        fieldnames = [
            "expression",
            "reading",
            "total_score",
            "jpdb_rank",
            "has_jmdict_match",
            "has_uk_tag",
            "forms_high_priority",
            "is_ambiguous_expression",
            "is_ambiguous_reading",
            "reasons",
        ]
        writer = csv.DictWriter(output or __import__("sys").stdout, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = {
                "expression": result.expression,
                "reading": result.reading,
                "total_score": round(result.total_score, 4),
                "jpdb_rank": result.jpdb_rank or "",
                "has_jmdict_match": result.has_jmdict_match,
                "has_uk_tag": result.has_uk_tag,
                "forms_high_priority": result.forms_high_priority or "",
                "is_ambiguous_expression": result.is_ambiguous_expression,
                "is_ambiguous_reading": result.is_ambiguous_reading,
                "reasons": "; ".join(result.reasons),
            }
            writer.writerow(row)
    finally:
        if output:
            output.close()
