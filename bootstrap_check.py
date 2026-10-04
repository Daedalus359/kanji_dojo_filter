#!/usr/bin/env python3
"""
Bootstrap Verification Script

Checks that all required input files exist and reports when they were last updated.
Run this before starting the workflow to confirm your environment is set up correctly.

Usage:
    python3 bootstrap_check.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from constants import JPDB_CUTOFF_FREQ_RANK

try:
    from quality_scorer import DEFAULT_FREQUENCY_THRESHOLD
except ImportError:
    DEFAULT_FREQUENCY_THRESHOLD = JPDB_CUTOFF_FREQ_RANK


def format_timestamp(mtime: float) -> str:
    """Convert mtime to human-readable timestamp with age."""
    dt = datetime.fromtimestamp(mtime)
    now = datetime.now()
    age = now - dt

    # Format as "YYYY-MM-DD HH:MM:SS (N days ago)"
    date_str = dt.strftime("%Y-%m-%d %H:%M:%S")

    if age.days == 0:
        age_str = "today"
    elif age.days == 1:
        age_str = "yesterday"
    else:
        age_str = f"{age.days} days ago"

    return f"{date_str} ({age_str})"


def check_file(label: str, path: str | Path, required: bool = True) -> bool:
    """Check if a file exists and report its status."""
    path = Path(path)
    exists = path.exists()
    status = "✓" if exists else "✗"

    if exists:
        size_mb = path.stat().st_size / (1024 * 1024)
        mtime = path.stat().st_mtime
        timestamp = format_timestamp(mtime)
        print(f"{status} {label:45} {str(path)}")
        print(f"   Last updated: {timestamp}")
        print(f"   Size: {size_mb:.2f} MB")
        return True
    else:
        requirement = "[REQUIRED]" if required else "[OPTIONAL]"
        print(f"{status} {label:45} {str(path)} {requirement}")
        return False


def check_directory(
    label: str, path: str | Path, pattern: str = "*", min_files: int = 1
) -> bool:
    """Check if a directory exists and contains expected files."""
    path = Path(path)
    exists = path.exists()
    status = "✓" if exists else "✗"

    if exists:
        matches = sorted(path.glob(pattern))
        count = len(matches)
        ok = count >= min_files
        status = "✓" if ok else "✗"

        print(f"{status} {label:45} {str(path)}")
        print(f"   Files found: {count} (expected at least {min_files})")

        if matches:
            # Show total size and most recent update
            total_size = sum(m.stat().st_size for m in matches)
            most_recent = max(m.stat().st_mtime for m in matches)
            timestamp = format_timestamp(most_recent)

            print(f"   Total size: {total_size / (1024 * 1024):.2f} MB")
            print(f"   Most recently updated: {timestamp}")

        return ok
    else:
        print(f"{status} {label:45} {str(path)} [REQUIRED]")
        return False


def main() -> None:
    """Check all required files for the workflow."""
    print("\n" + "=" * 90)
    print("KANJI DOJO DECK ANALYSIS WORKFLOW - BOOTSTRAP CHECK")
    print("=" * 90 + "\n")

    all_ok = True

    # =========================================================================
    print("REQUIRED INPUT FILES:\n")
    # =========================================================================

    print("Kanji Dojo Database:")
    all_ok &= check_file("   user_data.sqlite", "user_data.sqlite", required=True)
    print()

    print("JMdict Vocabulary Data:")
    all_ok &= check_directory(
        "   data/JMDict/", "data/JMDict", pattern="term_bank_*.json", min_files=1
    )
    print()

    print("JPDBv2 Frequency Rankings:")
    all_ok &= check_file(
        "   ../frequency_data/term_meta_bank_1.json",
        "../frequency_data/term_meta_bank_1.json",
        required=True,
    )
    print()

    # =========================================================================
    print("OPTIONAL INPUT FILES:\n")
    # =========================================================================

    print("Resumable Decision Log (only needed if resuming review):")
    check_file("   decisions.json", "decisions.json", required=False)
    print()

    # =========================================================================
    print("EXPECTED OUTPUT LOCATIONS:\n")
    # =========================================================================

    print("These directories will receive generated files:\n")
    print("   Step 1 (Analysis):")
    print("      → analysis_report.txt (optional)")
    print()
    print("   Step 2 (Review):")
    print("      → decisions.json (required, resumable)")
    print()
    print("   Step 3 (Export):")
    print("      → removal_list.txt (optional)")
    print()
    print("   Step 4 (Apply):")
    print("      → user_data_backup_YYYYMMDD_HHMMSS.sqlite (automatic)")
    print("      → user_data_approved_removals.sqlite (new copy)")
    print()

    # =========================================================================
    print("CONFIGURATION SETTINGS:\n")
    # =========================================================================

    print(f"Frequency Threshold:  {DEFAULT_FREQUENCY_THRESHOLD}")
    print("   (words at/above this rank get zero frequency penalty)")
    print()
    print("Source Table:         vocab_deck_entry")
    print("   (adjust with --source-table if your database uses a different name)")
    print()

    # =========================================================================
    if not all_ok:
        print("=" * 90)
        print("STATUS: ✗ BOOTSTRAP CHECK FAILED")
        print("=" * 90)
        print("\nMissing required files. Please check the paths above and ensure:")
        print("  1. user_data.sqlite exists in your current directory")
        print("  2. data/JMDict/ contains term_bank_*.json files")
        print("  3. ../frequency_data/term_meta_bank_1.json exists")
        print("\nFor more details, run:")
        print("  python3 workflow_paths.py")
        print()
        sys.exit(1)
    else:
        print("=" * 90)
        print("STATUS: ✓ ALL REQUIRED FILES FOUND")
        print("=" * 90)
        print("\nYou are ready to start the workflow. Run:\n")
        print("  Step 1 (Analyze):")
        print("    python3 analyze_deck.py --verbose --output analysis_report.txt\n")
        print("  Step 2 (Review):")
        print("    python3 interactive_reviewer.py --decision-log decisions.json\n")
        print("  Step 3 (Export - optional):")
        print("    python3 workflow_paths.py  # Shows export commands\n")
        print("  Step 4 (Apply):")
        print("    python3 apply_removals_main.py decisions.json\n")
        print("For full details, see WORKFLOW.md")
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(2)
