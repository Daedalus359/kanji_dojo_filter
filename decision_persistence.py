#!/usr/bin/env python3

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from removal_decision import RemovalDecision, RemovalDecisionLog


def save_decision_log(log: RemovalDecisionLog, file_path: str | Path) -> None:
    """Serialize a decision log to a JSON file."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(log.to_dict(), f, ensure_ascii=False, indent=2)


def load_decision_log(file_path: str | Path) -> RemovalDecisionLog:
    """Load a previously saved decision log."""
    file_path = Path(file_path)
    if not file_path.exists():
        return RemovalDecisionLog()

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return RemovalDecisionLog.from_dict(data)


def export_removal_list(
    log: RemovalDecisionLog, file_path: str | Path, deck_name_map: dict[int, str] | None = None
) -> None:
    """Export a human-readable removal list suitable for hand-editing and downstream processing."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if deck_name_map is None:
        deck_name_map = {}

    removal_decisions = [d for d in log.decisions if d.decision == "remove"]
    keep_decisions = [d for d in log.decisions if d.decision == "keep"]
    undecided = [d for d in log.decisions if d.decision == "undecided"]

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# Kanji Dojo Removal List\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write(f"# Frequency Threshold: {log.frequency_threshold}\n")
        f.write("\n")
        f.write("# This file is suitable for hand-editing and can be used as input to apply_removals.py\n")
        f.write("# Format: expression | reading | deck_id | decision | score | reasons | notes\n")
        f.write("\n")

        if removal_decisions:
            f.write("## MARKED FOR REMOVAL\n")
            f.write("\n")
            for decision in sorted(
                removal_decisions,
                key=lambda d: (
                    -d.score,
                    d.deck_id is not None,
                    d.deck_id or "",
                    d.expression,
                    d.reading,
                ),
            ):
                deck_name = (
                    f"({deck_name_map.get(decision.deck_id, '')})"
                    if decision.deck_id and decision.deck_id in deck_name_map
                    else ""
                )
                f.write(
                    f"{decision.expression:15} | {decision.reading:15} | "
                    f"deck_id={decision.deck_id} {deck_name} | score={decision.score:.3f}\n"
                )
                if decision.reasons:
                    f.write(f"  Reasons: {'; '.join(decision.reasons)}\n")
                if decision.user_notes:
                    f.write(f"  Notes: {decision.user_notes}\n")
                f.write("\n")

        if undecided:
            f.write("## UNDECIDED\n")
            f.write("\n")
            for decision in sorted(
                undecided,
                key=lambda d: (
                    -d.score,
                    d.deck_id is not None,
                    d.deck_id or "",
                    d.expression,
                    d.reading,
                ),
            ):
                deck_name = (
                    f"({deck_name_map.get(decision.deck_id, '')})"
                    if decision.deck_id and decision.deck_id in deck_name_map
                    else ""
                )
                f.write(
                    f"{decision.expression:15} | {decision.reading:15} | "
                    f"deck_id={decision.deck_id} {deck_name} | score={decision.score:.3f}\n"
                )
                if decision.reasons:
                    f.write(f"  Reasons: {'; '.join(decision.reasons)}\n")
                f.write("\n")

        if keep_decisions:
            f.write("## MARKED TO KEEP\n")
            f.write("\n")
            for decision in sorted(
                keep_decisions,
                key=lambda d: (
                    -d.score,
                    d.deck_id is not None,
                    d.deck_id or "",
                    d.expression,
                    d.reading,
                ),
            ):
                deck_name = (
                    f"({deck_name_map.get(decision.deck_id, '')})"
                    if decision.deck_id and decision.deck_id in deck_name_map
                    else ""
                )
                f.write(
                    f"{decision.expression:15} | {decision.reading:15} | "
                    f"deck_id={decision.deck_id} {deck_name} | score={decision.score:.3f}\n"
                )
                if decision.reasons:
                    f.write(f"  Reasons: {'; '.join(decision.reasons)}\n")
                f.write("\n")


def export_removal_list_csv(
    log: RemovalDecisionLog, file_path: str | Path, deck_name_map: dict[int, str] | None = None
) -> None:
    """Export removal decisions as a CSV file suitable for programmatic processing."""
    import csv

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if deck_name_map is None:
        deck_name_map = {}

    with open(file_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "expression",
            "reading",
            "deck_id",
            "deck_name",
            "decision",
            "score",
            "reasons",
            "user_notes",
            "timestamp",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for decision in sorted(
            log.decisions,
            key=lambda d: (-d.score, d.decision, d.deck_id or "", d.expression, d.reading),
        ):
            writer.writerow(
                {
                    "expression": decision.expression,
                    "reading": decision.reading,
                    "deck_id": decision.deck_id or "",
                    "deck_name": deck_name_map.get(decision.deck_id, ""),
                    "decision": decision.decision,
                    "score": round(decision.score, 4),
                    "reasons": "; ".join(decision.reasons),
                    "user_notes": decision.user_notes,
                    "timestamp": decision.timestamp,
                }
            )
