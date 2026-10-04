#!/usr/bin/env python3
"""
Workflow Paths Reference Script

Displays all input data sources, output destinations, and configuration constants
used throughout the Kanji Dojo deck analysis and removal workflow.

Run this to understand the file layout and verify that required data is in place.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from constants import JPDB_CUTOFF_FREQ_RANK

# Import constants and defaults from the workflow modules
try:
    from quality_scorer import DEFAULT_FREQUENCY_THRESHOLD
except ImportError:
    DEFAULT_FREQUENCY_THRESHOLD = JPDB_CUTOFF_FREQ_RANK


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 80}")
    print(f"{title}")
    print(f"{'=' * 80}\n")


def print_path(label: str, path: str | Path, status: str = "") -> None:
    """Print a path with existence check."""
    path = Path(path)
    exists = "✓" if path.exists() else "✗"
    status_str = f" ({status})" if status else ""
    print(f"{exists} {label:40} {str(path)}{status_str}")


def check_directory(label: str, directory: str | Path, pattern: str = "*") -> None:
    """Check a directory and list matching files."""
    directory = Path(directory)
    if not directory.exists():
        print(f"✗ {label:40} {str(directory)} [NOT FOUND]")
        return

    matches = list(directory.glob(pattern))
    if matches:
        print(f"✓ {label:40} {str(directory)} [{len(matches)} file(s)]")
        for match in sorted(matches)[:5]:  # Show first 5
            print(f"    - {match.name}")
        if len(matches) > 5:
            print(f"    ... and {len(matches) - 5} more")
    else:
        print(f"✗ {label:40} {str(directory)} [NO MATCHING FILES]")


def main() -> None:
    """Display workflow paths and verify data availability."""
    print("\n" + "=" * 80)
    print("KANJI DOJO DECK ANALYSIS WORKFLOW - PATHS REFERENCE")
    print("=" * 80)

    # =========================================================================
    print_section("STEP 1: ANALYSIS (analyze_deck.py)")
    # =========================================================================

    print("INPUT DATA SOURCES:\n")

    print_path(
        "Kanji Dojo Database",
        "user_data.sqlite",
        "default location (your current directory)",
    )
    print("   └─ Alternative: --database /path/to/user_data.sqlite\n")

    print_path(
        "JMdict Directory",
        "data/JMDict",
        "relative to this repo",
    )
    print("   └─ Alternative: --jmdict-directory /path/to/JMDict\n")
    check_directory("   JMDict Term Banks", "data/JMDict", "term_bank_*.json")

    print_path(
        "JPDBv2 Frequency Data",
        "../frequency_data/term_meta_bank_1.json",
        "relative to this repo",
    )
    print("   └─ Alternative: --frequency-data /path/to/term_meta_bank_1.json\n")

    print("OUTPUT DESTINATIONS:\n")
    print_path("Analysis Report", "analysis_report.txt", "optional (--output flag)")
    print("   └─ Format: TEXT, JSON, or CSV (--format flag)")
    print("   └─ Verbosity: --verbose for detailed component scores\n")

    print("CONFIGURATION:\n")
    print(f"   Frequency Threshold:    {DEFAULT_FREQUENCY_THRESHOLD}")
    print("      └─ Adjust with: --threshold <N>")
    print("      └─ Entries at/above rank N get zero frequency penalty\n")
    print("   Source Table:           vocab_deck_entry")
    print("      └─ Adjust with: --source-table <TABLE_NAME>\n")

    # =========================================================================
    print_section("STEP 2: INTERACTIVE REVIEW (interactive_reviewer.py)")
    # =========================================================================

    print("INPUT DATA SOURCES:\n")

    print_path(
        "Kanji Dojo Database",
        "user_data.sqlite",
        "read-only, for loading entries",
    )
    print("   └─ Same as Step 1\n")

    print_path(
        "JMdict Directory",
        "data/JMDict",
        "same as Step 1",
    )
    print()

    print_path(
        "JPDBv2 Frequency Data",
        "../frequency_data/term_meta_bank_1.json",
        "same as Step 1",
    )
    print()

    print_path(
        "Decision Log (previous sessions)",
        "decisions.json",
        "loaded if exists; created if first run",
    )
    print("   └─ Alternative: --decision-log /path/to/decisions.json\n")

    print("OUTPUT DESTINATIONS:\n")

    print_path("Decision Log (this session)", "decisions.json", "serialized, resumable")
    print("   └─ Plain JSON format")
    print("   └─ Contains:")
    print("      • Per-entry decisions (keep/remove/undecided)")
    print("      • User notes and timestamps")
    print("      • Completed deck list")
    print("      • Frequency threshold and data paths")
    print("   └─ Safe to hand-edit before Step 4\n")

    print("CONFIGURATION:\n")
    print(f"   Frequency Threshold:    {DEFAULT_FREQUENCY_THRESHOLD}")
    print("   Source Table:           vocab_deck_entry\n")

    # =========================================================================
    print_section("STEP 3: EXPORT DECISIONS (decision_persistence.py)")
    # =========================================================================

    print("INPUT DATA SOURCES:\n")

    print_path("Decision Log", "decisions.json", "from Step 2")
    print()

    print_path(
        "Kanji Dojo Database",
        "user_data.sqlite",
        "read-only, for deck names only",
    )
    print()

    print("OUTPUT DESTINATIONS:\n")

    print_path(
        "Human-Readable Removal List",
        "removal_list.txt",
        "optional export",
    )
    print("   └─ Grouped by decision status:")
    print("      • MARKED FOR REMOVAL")
    print("      • UNDECIDED")
    print("      • MARKED TO KEEP")
    print("   └─ Each entry includes:")
    print("      • Expression, reading, deck ID, deck name")
    print("      • Score and reasons")
    print("      • User notes")
    print("   └─ Safe to hand-edit before Step 4\n")

    print("FORMAT:\n")
    print("   export_removal_list() → Text (default)")
    print("   export_removal_list_csv() → CSV\n")

    # =========================================================================
    print_section("STEP 4: APPLY REMOVALS (apply_removals_main.py)")
    # =========================================================================

    print("INPUT DATA SOURCES:\n")

    print_path("Decision Log", "decisions.json", "from Step 2")
    print("   └─ Alternative: <positional argument>\n")

    print_path(
        "Kanji Dojo Database",
        "user_data.sqlite",
        "read-only during this step",
    )
    print("   └─ Alternative: --database /path/to/user_data.sqlite\n")

    print("OUTPUT DESTINATIONS:\n")

    print_path(
        "Timestamped Backup",
        "user_data_backup_YYYYMMDD_HHMMSS.sqlite",
        "automatic (same dir as input)",
    )
    print("   └─ Created before any deletions")
    print("   └─ Keep for recovery if needed\n")

    print_path(
        "Modified Database (New Copy)",
        "user_data_approved_removals.sqlite",
        "default output",
    )
    print("   └─ Alternative: --output /path/to/custom_name.sqlite")
    print("   └─ IMPORTANT: Removals applied to COPY, not original")
    print("   └─ Original user_data.sqlite unchanged\n")

    print("CONFIGURATION:\n")
    print("   Source Table:           vocab_deck_entry")
    print("      └─ Adjust with: --source-table <TABLE_NAME>\n")

    # =========================================================================
    print_section("STEP 5: VERIFICATION & DEPLOYMENT")
    # =========================================================================

    print("VERIFY REMOVALS:\n")
    print("   sqlite3 user_data_approved_removals.sqlite \\")
    print("     'SELECT COUNT(*) FROM vocab_deck_entry WHERE kanji_reading = ?'")
    print("   → Should return 0 for removed entries\n")

    print("DEPLOY:\n")
    print("   mv user_data.sqlite user_data_original.sqlite")
    print("   mv user_data_approved_removals.sqlite user_data.sqlite\n")

    print("RECOVERY:\n")
    print("   mv user_data.sqlite user_data_removed.sqlite")
    print("   mv user_data_backup_YYYYMMDD_HHMMSS.sqlite user_data.sqlite\n")

    # =========================================================================
    print_section("DIRECTORY STRUCTURE REFERENCE")
    # =========================================================================

    print("Expected layout for this repository:\n")
    print("kanji_dojo_filter/")
    print("├── analyze_deck.py                    (Step 1)")
    print("├── interactive_reviewer.py            (Step 2)")
    print("├── decision_persistence.py            (Step 3)")
    print("├── apply_removals_main.py             (Step 4)")
    print("├── quality_scorer.py")
    print("├── batch_evaluator.py")
    print("├── database_loader.py")
    print("├── removal_decision.py")
    print("├── report_generator.py")
    print("├── filter_lib.py")
    print("├── deck_reader.py")
    print("├── WORKFLOW.md                        (This guide)")
    print("├── workflow_paths.py                  (This script)")
    print("│")
    print("├── data/")
    print("│   └── JMDict/")
    print("│       ├── term_bank_1.json")
    print("│       ├── term_bank_2.json")
    print("│       └── ... (more term_bank_*.json)")
    print("│")
    print("└── (user's working directory)")
    print("    ├── user_data.sqlite               (input)")
    print("    ├── analysis_report.txt            (output, Step 1, optional)")
    print("    ├── decisions.json                 (Step 2, resumable)")
    print("    ├── removal_list.txt               (output, Step 3, optional)")
    print("    ├── user_data_backup_*.sqlite      (output, Step 4, automatic)")
    print("    └── user_data_approved_removals.sqlite (output, Step 4)\n")

    print("../")
    print("└── frequency_data/")
    print("    └── term_meta_bank_1.json          (JPDBv2 frequency rankings)\n")

    # =========================================================================
    print_section("QUICK VERIFICATION CHECKLIST")
    # =========================================================================

    print("Before starting, verify:\n")

    checks = [
        (
            "user_data.sqlite exists",
            lambda: Path("user_data.sqlite").exists(),
        ),
        (
            "data/JMDict/ contains term_bank_*.json",
            lambda: len(list(Path("data/JMDict").glob("term_bank_*.json"))) > 0
            if Path("data/JMDict").exists()
            else False,
        ),
        (
            "../frequency_data/term_meta_bank_1.json exists",
            lambda: Path("../frequency_data/term_meta_bank_1.json").exists(),
        ),
    ]

    for label, check_func in checks:
        try:
            result = check_func()
            status = "✓" if result else "✗"
            print(f"{status} {label}")
        except Exception as exc:
            print(f"✗ {label} (error: {exc})")

    print()

    # =========================================================================
    print_section("COMMAND REFERENCE")
    # =========================================================================

    print("Step 1 - Analyze:\n")
    print("python3 analyze_deck.py \\")
    print("  --database user_data.sqlite \\")
    print("  --jmdict-directory data/JMDict \\")
    print("  --frequency-data ../frequency_data/term_meta_bank_1.json \\")
    print(f"  --threshold {JPDB_CUTOFF_FREQ_RANK} \\")
    print("  --output analysis_report.txt \\")
    print("  --verbose\n")

    print("Step 2 - Review:\n")
    print("python3 interactive_reviewer.py \\")
    print("  --database user_data.sqlite \\")
    print("  --decision-log decisions.json \\")
    print("  --jmdict-directory data/JMDict \\")
    print("  --frequency-data ../frequency_data/term_meta_bank_1.json\n")

    print("Step 3 - Export (optional):\n")
    print("python3 -c \"")
    print(
        "from decision_persistence import load_decision_log, export_removal_list; "
    )
    print(
        "from database_loader import load_deck_mapping; "
    )
    print("log = load_decision_log('decisions.json'); ")
    print("deck_map = load_deck_mapping('user_data.sqlite'); ")
    print("export_removal_list(log, 'removal_list.txt', deck_map)")
    print("\"\n")

    print("Step 4 - Apply:\n")
    print("python3 apply_removals_main.py decisions.json \\")
    print("  --database user_data.sqlite\n")

    print("Step 5 - Deploy:\n")
    print("mv user_data.sqlite user_data_original.sqlite")
    print("mv user_data_approved_removals.sqlite user_data.sqlite\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(2)
